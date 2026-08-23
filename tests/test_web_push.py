"""Tests for web_push.py — the crypto, and the 410 that means "forget this browser".

The encryption is checked against RFC 8291's own published test vector, byte for byte,
rather than a round trip against ourselves: a round trip agrees with whatever we did,
including a misread of the spec. The VAPID token is checked by verifying its signature
with the public key, which is what the push service does with it.

No network: urlopen is stubbed.
"""
import io
import json
import os
import tempfile
import urllib.error
import urllib.request

import web_push
from web_push import _b64, _unb64

# ---- RFC 8291 §5 + Appendix A ------------------------------------------------------
RFC_PLAINTEXT = b"When I grow up, I want to be a watermelon"
RFC_UA_PUBLIC = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
RFC_AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
RFC_SALT = "DGv6ra1nlYgDCS1FRnbzlw"
RFC_AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
RFC_BODY = ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
            "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
            "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_encrypt_matches_the_rfc_8291_test_vector():
    from cryptography.hazmat.primitives.asymmetric import ec
    as_priv = ec.derive_private_key(int.from_bytes(_unb64(RFC_AS_PRIVATE), "big"),
                                    ec.SECP256R1())
    got = web_push.encrypt(RFC_PLAINTEXT, _unb64(RFC_UA_PUBLIC), _unb64(RFC_AUTH),
                           salt=_unb64(RFC_SALT), as_priv=as_priv)
    assert _b64(got) == RFC_BODY, _b64(got)


def test_encrypt_is_actually_decryptable_by_the_subscriber():
    """The vector proves the algorithm; this proves a random salt/ephemeral key still
    lands, by decrypting with the receiver's private key the way a browser would."""
    from cryptography.hazmat.primitives.asymmetric import ec
    ua_priv = ec.derive_private_key(
        int.from_bytes(_unb64("q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"), "big"),
        ec.SECP256R1())
    auth = _unb64(RFC_AUTH)
    body = web_push.encrypt(b"hello", _unb64(RFC_UA_PUBLIC), auth)

    import hashlib
    import hmac
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, as_pub = body[:16], body[21:86]
    shared = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), as_pub))
    prk_key = hmac.new(auth, shared, hashlib.sha256).digest()
    ikm = hmac.new(prk_key, b"WebPush: info\x00" + _unb64(RFC_UA_PUBLIC) + as_pub + b"\x01",
                   hashlib.sha256).digest()
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = hmac.new(prk, b"Content-Encoding: aes128gcm\x00\x01", hashlib.sha256).digest()[:16]
    nonce = hmac.new(prk, b"Content-Encoding: nonce\x00\x01", hashlib.sha256).digest()[:12]
    assert AESGCM(cek).decrypt(nonce, body[86:], None) == b"hello\x02"


def test_vapid_jwt_verifies_with_the_public_key():
    """What the push service does with the token: split it, verify ES256 over the first
    two segments, then read the audience it claims."""
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_DIR"] = d
        priv, pub = web_push.vapid_keys()
        tok = web_push.vapid_jwt(priv, "https://push.example.net")
        head, claims, sig = tok.split(".")
        raw = _unb64(sig)
        assert len(raw) == 64, "ES256 is raw r||s, not DER"
        der = utils.encode_dss_signature(int.from_bytes(raw[:32], "big"),
                                         int.from_bytes(raw[32:], "big"))
        pk = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _unb64(pub))
        pk.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if bad
        body = json.loads(_unb64(claims))
        assert body["aud"] == "https://push.example.net", body
        assert body["sub"].startswith("mailto:") and body["exp"] > 0, body
        assert json.loads(base64.urlsafe_b64decode(head + "=="))["alg"] == "ES256"


def test_vapid_key_is_generated_once_and_then_reused():
    """Rotating it would orphan every subscription the browsers already hold."""
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_DIR"] = d
        _, a = web_push.vapid_keys()
        _, b = web_push.vapid_keys()
        assert a == b and os.path.exists(os.path.join(d, "vapid.json"))


def _sub(d, endpoint="https://push.example.net/x"):
    os.environ["DATA_DIR"] = d
    web_push.save_subs({endpoint: {"p256dh": RFC_UA_PUBLIC, "auth": RFC_AUTH}})
    return endpoint


def test_no_subscriptions_is_zero_not_an_exception():
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_DIR"] = d
        assert web_push.send("t", "b") == 0


def test_send_posts_an_encrypted_body_with_a_vapid_header():
    seen = {}

    def fake(req, timeout=None):
        seen["url"], seen["body"], seen["hdrs"] = req.full_url, req.data, req.headers
        return io.BytesIO(b"")

    real, urllib.request.urlopen = urllib.request.urlopen, fake
    try:
        with tempfile.TemporaryDirectory() as d:
            ep = _sub(d)
            assert web_push.send("Bill due", "Pay CIMB") == 1
    finally:
        urllib.request.urlopen = real
    assert seen["url"] == ep
    assert seen["hdrs"]["Content-encoding"] == "aes128gcm"
    auth = seen["hdrs"]["Authorization"]
    assert auth.startswith("vapid t=") and ",k=" in auth, auth
    # the cleartext must not be on the wire
    assert b"Pay CIMB" not in seen["body"] and len(seen["body"]) > 86


def test_410_drops_the_subscription_instead_of_retrying_forever():
    def gone(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 410, "Gone", {}, io.BytesIO(b"expired"))

    real, urllib.request.urlopen = urllib.request.urlopen, gone
    try:
        with tempfile.TemporaryDirectory() as d:
            _sub(d)
            assert web_push.send("t", "b") == 0
            assert web_push.load_subs() == {}, "410 must delete the stored subscription"
    finally:
        urllib.request.urlopen = real


def test_a_500_keeps_the_subscription():
    """Only 404/410 mean "this browser is gone"; a push service having a bad day does not."""
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, io.BytesIO(b"x"))

    real, urllib.request.urlopen = urllib.request.urlopen, boom
    try:
        with tempfile.TemporaryDirectory() as d:
            ep = _sub(d)
            assert web_push.send("t", "b") == 0
            assert list(web_push.load_subs()) == [ep]
    finally:
        urllib.request.urlopen = real


def test_reminder_send_fans_out_to_both_transports_once():
    """#39's contract: one message per bill, not one per transport, and Telegram still
    behaves exactly as it did when its two variables are set."""
    import remind_bills
    tg, wp = [], []
    real_tg, real_wp = remind_bills.send_telegram, remind_bills.send_webpush
    remind_bills.send_telegram = lambda t: (tg.append(t), 1)[1]
    remind_bills.send_webpush = lambda t: (wp.append(t), 1)[1]
    try:
        remind_bills.send("<b>Head</b>\nBody")
        assert len(tg) == 1 and len(wp) == 1
        # nothing configured at all is an error, so run() does not record the bill
        remind_bills.send_telegram = remind_bills.send_webpush = lambda t: 0
        try:
            remind_bills.send("x")
            raise AssertionError("expected a failure")
        except RuntimeError as e:
            assert "no reminder transport" in str(e), e
        # one transport down, the other up: delivered, and NOT retried
        remind_bills.send_webpush = lambda t: 1

        def dead(t):
            raise RuntimeError("telegram 400: chat not found")
        remind_bills.send_telegram = dead
        remind_bills.send("x")   # must not raise
    finally:
        remind_bills.send_telegram, remind_bills.send_webpush = real_tg, real_wp


def test_webpush_strips_the_telegram_html_and_splits_title_from_body():
    import remind_bills
    seen = {}
    real = web_push.send
    web_push.send = lambda title, body, url="/": seen.update(t=title, b=body) or 1
    try:
        assert remind_bills.send_webpush(
            "<b>Automated Credit Card Payment Reminder</b>\n\nPay CIMB RM <code>10.00</code>") == 1
        assert seen["t"] == "Automated Credit Card Payment Reminder", seen
        assert seen["b"] == "Pay CIMB RM 10.00", seen
    finally:
        web_push.send = real


if __name__ == "__main__":
    test_encrypt_matches_the_rfc_8291_test_vector()
    test_encrypt_is_actually_decryptable_by_the_subscriber()
    test_vapid_jwt_verifies_with_the_public_key()
    test_vapid_key_is_generated_once_and_then_reused()
    test_no_subscriptions_is_zero_not_an_exception()
    test_send_posts_an_encrypted_body_with_a_vapid_header()
    test_410_drops_the_subscription_instead_of_retrying_forever()
    test_a_500_keeps_the_subscription()
    test_reminder_send_fans_out_to_both_transports_once()
    test_webpush_strips_the_telegram_html_and_splits_title_from_body()
    print("OK")
