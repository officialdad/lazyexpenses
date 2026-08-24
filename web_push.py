"""Web Push (RFC 8291) — the zero-configuration bill-reminder transport.

Everything a user would otherwise have to paste is generated here and kept on the
volume next to paid.json/waivers.json:

  <DATA_DIR>/vapid.json      the VAPID keypair, made on first use and then kept
  <DATA_DIR>/push_subs.json  {endpoint: {"p256dh": …, "auth": …}}, written by the PWA

`cryptography` is the one thing the stdlib cannot replace: VAPID is ES256 over P-256
and the payload is ECDH + HKDF + AES-GCM, and hashlib/hmac do not do elliptic curves.
pywebpush would pull four packages to save these ~80 lines. It is imported INSIDE the
functions that need it, so remind_bills.py stays runnable on Telegram alone from a
machine that only installed pdfplumber.

Everything degrades quietly: no keys, no subscriptions, an unreachable push service or
a browser that revoked its subscription are all logged and return, never raise.
"""
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Push services want a way to contact whoever is sending; nothing here is emailed.
# Apple validates the domain and rejects an unresolvable one with 403 BadJwtToken, which
# is why the default is a real https:// URL and not a mailto: on a .invalid domain (#76).
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "https://github.com/officialdad/lazyexpenses")
TTL = "86400"          # let the push service hold a reminder for a day if the phone is off
RECORD_SIZE = 4096     # RFC 8188 rs; one record is plenty for a two-line notification


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)   # atomic on POSIX, same as /api/paid


# ---------------------------------------------------------------- subscriptions
def subs_path() -> Path:
    return _dir() / "push_subs.json"


def load_subs() -> dict:
    try:
        d = json.loads(subs_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}       # missing or corrupt only costs the user re-enabling reminders


def save_subs(subs: dict) -> None:
    _write_json(subs_path(), subs)


# ---------------------------------------------------------------- VAPID
def _pub_bytes(priv) -> bytes:
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    return priv.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)


def vapid_keys():
    """(private key object, public key as base64url). Generated on first call.

    NEVER rotate this on its own: the public key is baked into every subscription the
    browsers already handed us, so a new pair silently orphans all of them. A corrupt
    file is the one case where that is unavoidable, and it says so in the log.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    p = _dir() / "vapid.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            priv = ec.derive_private_key(int.from_bytes(_unb64(d["private"]), "big"),
                                         ec.SECP256R1())
            return priv, d["public"]
        except Exception as e:
            print(f"push: {p} unreadable ({e}); generating a new VAPID key — "
                  "existing subscriptions will have to be re-enabled", flush=True)
    priv = ec.generate_private_key(ec.SECP256R1())
    pub = _b64(_pub_bytes(priv))
    _write_json(p, {"private": _b64(priv.private_numbers().private_value.to_bytes(32, "big")),
                    "public": pub})
    return priv, pub


def vapid_jwt(priv, audience: str, subject: str = VAPID_SUBJECT) -> str:
    """RFC 8292 signed token. ES256 wants the raw r||s pair, not the DER `sign()` gives."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils
    head = _b64(b'{"typ":"JWT","alg":"ES256"}')
    claims = _b64(json.dumps({"aud": audience, "exp": int(time.time()) + 12 * 3600,
                              "sub": subject}, separators=(",", ":")).encode())
    signed = f"{head}.{claims}".encode()
    r, s = utils.decode_dss_signature(priv.sign(signed, ec.ECDSA(hashes.SHA256())))
    return f"{head}.{claims}." + _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


# ---------------------------------------------------------------- payload encryption
def encrypt(payload: bytes, p256dh: bytes, auth: bytes, *, salt=None, as_priv=None) -> bytes:
    """RFC 8291 `aes128gcm`, single record — the body a push service forwards verbatim.

    `salt` and `as_priv` are random per message; they are injectable only so the RFC's
    own test vector can be reproduced byte for byte (test_web_push.py).
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt = salt or os.urandom(16)
    as_priv = as_priv or ec.generate_private_key(ec.SECP256R1())
    as_pub = _pub_bytes(as_priv)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), p256dh)
    shared = as_priv.exchange(ec.ECDH(), ua_pub)

    # HKDF, spelled out: one HMAC per step is smaller than importing a KDF for it.
    prk_key = hmac.new(auth, shared, hashlib.sha256).digest()
    ikm = hmac.new(prk_key, b"WebPush: info\x00" + p256dh + as_pub + b"\x01",
                   hashlib.sha256).digest()
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = hmac.new(prk, b"Content-Encoding: aes128gcm\x00\x01", hashlib.sha256).digest()[:16]
    nonce = hmac.new(prk, b"Content-Encoding: nonce\x00\x01", hashlib.sha256).digest()[:12]

    # 0x02 is the last-record padding delimiter (RFC 8188 §2).
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub
    return header + body


# ---------------------------------------------------------------- sending
def _origin(endpoint: str) -> str:
    u = urllib.parse.urlsplit(endpoint)
    return f"{u.scheme}://{u.netloc}"


def send(title: str, body: str, url: str = "/") -> int:
    """Notify every stored subscription. Returns how many the push service accepted.

    0 is not a failure — it is what "nobody has turned reminders on" looks like, and
    remind_bills.send() decides what to do about it.
    """
    subs = load_subs()
    if not subs:
        return 0
    try:
        priv, pub = vapid_keys()
    except Exception as e:   # cryptography missing, volume read-only, ...
        print(f"push unavailable: {e}", flush=True)
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url}).encode()
    ok, gone = 0, []
    for endpoint, k in subs.items():
        try:
            req = urllib.request.Request(
                endpoint, data=encrypt(payload, _unb64(k["p256dh"]), _unb64(k["auth"])),
                method="POST", headers={
                    "Content-Encoding": "aes128gcm",
                    "Content-Type": "application/octet-stream",
                    "TTL": TTL,
                    "Authorization": f"vapid t={vapid_jwt(priv, _origin(endpoint))},k={pub}",
                })
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            ok += 1
        except urllib.error.HTTPError as e:
            # 404/410 = the browser dropped this subscription. Keeping it means failing
            # forever on a client that no longer exists, so forget it.
            if e.code in (404, 410):
                gone.append(endpoint)
            print(f"push {e.code} from {_origin(endpoint)}: "
                  f"{e.read().decode(errors='replace')[:200]}", flush=True)
        except Exception as e:
            print(f"push failed for {_origin(endpoint)}: {e}", flush=True)
    if gone:
        save_subs({k: v for k, v in load_subs().items() if k not in gone})
        print(f"push: dropped {len(gone)} expired subscription(s)", flush=True)
    return ok
