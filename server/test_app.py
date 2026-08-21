"""FastAPI route tests. Run from repo root: python -m pytest server/test_app.py -v"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client(tmp, web=None):
    """Build a TestClient against a temp DATA_DIR / WEB_DIR."""
    os.environ["DATA_DIR"] = tmp
    os.environ["WEB_DIR"] = web or os.path.join(tmp, "web_build")
    os.makedirs(os.environ["WEB_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["WEB_DIR"], "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><title>spa</title>")
    from server import app as appmod
    import importlib
    importlib.reload(appmod)
    from fastapi.testclient import TestClient
    return TestClient(appmod.create_app()), appmod


def test_healthz():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.get("/healthz").json() == {"ok": True}


def test_bills_empty_when_no_app_json():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.get("/bills").json() == []


def test_data_and_bills_read_from_pvc_not_baked():
    with tempfile.TemporaryDirectory() as d:
        # PVC app.json says "pvc"; baked build/data/app.json (if any) must be shadowed.
        with open(os.path.join(d, "app.json"), "w", encoding="utf-8") as fh:
            json.dump({"bills": [{"bank": "cimb", "payment_due_date": "2026-07-05"}], "src": "pvc"}, fh)
        c, _ = _client(d)
        assert c.get("/data/app.json").json()["src"] == "pvc"
        bills = c.get("/bills").json()
        assert bills[0]["bank"] == "cimb"


def test_spa_served_at_root():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        r = c.get("/")
        assert r.status_code == 200
        assert "spa" in r.text


def test_prerendered_route_and_spa_fallback():
    # Extensionless prerendered routes (/trends) must resolve to <route>.html, and any
    # unknown path must fall back to the SPA shell — without this the Workbox precache
    # install 404s on /trends|/cuts and the PWA never goes offline (and /trends 404s online).
    with tempfile.TemporaryDirectory() as d:
        web = os.path.join(d, "web_build")
        c, _ = _client(d, web=web)
        with open(os.path.join(web, "trends.html"), "w", encoding="utf-8") as fh:
            fh.write("<!doctype html><title>trends</title>")
        # /trends -> trends.html (was 404 in prod)
        r = c.get("/trends")
        assert r.status_code == 200 and "trends" in r.text
        # exact .html still works
        assert c.get("/trends.html").status_code == 200
        # unknown route -> SPA shell index.html, not a 404
        r = c.get("/totally-unknown-route")
        assert r.status_code == 200 and "spa" in r.text
        # API routes are matched before the static mount and are unaffected
        assert c.get("/healthz").json() == {"ok": True}


def test_ingest_saves_pdf_and_runs_pipeline(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        calls = {}

        def fake_run(data_dir):
            calls["ran"] = str(data_dir)
            return {"VERIFIED": 69, "REVIEW": 0}

        monkeypatch.setattr(appmod.pipeline, "run_pipeline", fake_run)
        r = c.post("/ingest", data={"bank": "cimb"}, files={"file": ("s.pdf", b"%PDF-FAKE", "application/pdf")})
        assert r.status_code == 200
        body = r.json()
        assert body["bank"] == "cimb"
        assert body["recon"]["VERIFIED"] == 69
        assert body["warning"] is False
        assert str(calls["ran"]) == str(d)
        # PDF landed in the bucket
        pdfs = os.listdir(os.path.join(d, "pdfs"))
        assert len(pdfs) == 1 and pdfs[0].startswith("cimb_")


def _ingest(monkeypatch, counts):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: counts)
        return c.post("/ingest", data={"bank": "sc"},
                      files={"file": ("s.pdf", b"%PDF-X", "application/pdf")}).json()


def test_ingest_rejects_unknown_bank_without_touching_the_volume(monkeypatch):
    # The file is the point: a typo used to land on the PVC and report NO_BALANCE forever.
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: 1 / 0)  # must not run
        r = c.post("/ingest", data={"bank": "mybank"},
                   files={"file": ("s.pdf", b"%PDF-Z", "application/pdf")})
        assert r.status_code == 400
        assert not os.path.exists(os.path.join(d, "pdfs"))


def test_ingest_error_names_the_valid_banks():
    import parse
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        detail = c.post("/ingest", data={"bank": "mybank"},
                        files={"file": ("s.pdf", b"%PDF-Z", "application/pdf")}).json()["detail"]
        for b in parse.BANKS:
            assert b in detail


def test_ingest_accepts_every_dispatched_bank(monkeypatch):
    import parse
    for bank in parse.BANKS:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _client(d)
            monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: {"VERIFIED": 1})
            r = c.post("/ingest", data={"bank": bank},
                       files={"file": ("s.pdf", b"%PDF-" + bank.encode(), "application/pdf")})
            assert r.status_code == 200 and r.json()["bank"] == bank
            assert os.listdir(os.path.join(d, "pdfs"))[0].startswith(bank + "_")


def test_ingest_case_folds_bank_to_the_lowercase_filename(monkeypatch):
    # The filename carries the bank forever, so it must be the form parse_statement expects.
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: {"VERIFIED": 1})
        r = c.post("/ingest", data={"bank": " Maybank "},
                   files={"file": ("s.pdf", b"%PDF-M", "application/pdf")})
        assert r.status_code == 200 and r.json()["bank"] == "maybank"
        assert os.listdir(os.path.join(d, "pdfs"))[0].startswith("maybank_")


def test_ingest_warns_on_review(monkeypatch):
    assert _ingest(monkeypatch, {"VERIFIED": 68, "REVIEW": 1})["warning"] is True


def test_ingest_warns_on_error(monkeypatch):
    # a locked or corrupt PDF: parse blew up, nothing reconciled. Must not read as clean.
    body = _ingest(monkeypatch, {"ERROR": 1, "NO_BALANCE": 1})
    assert body["warning"] is True
    assert body["problems"] == {"ERROR": 1, "NO_BALANCE": 1}


def test_ingest_warns_on_no_balance(monkeypatch):
    assert _ingest(monkeypatch, {"VERIFIED": 68, "NO_BALANCE": 1})["warning"] is True


def test_ingest_duplicates_alone_do_not_warn(monkeypatch):
    # the mail history re-exports the same statement under several filenames; dedup
    # marking those DUPLICATE is the system working, not a problem to flag.
    body = _ingest(monkeypatch, {"VERIFIED": 69, "DUPLICATE": 4})
    assert body["warning"] is False
    assert body["problems"] == {}


def test_ingest_500_on_pipeline_failure(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)

        def boom(dd):
            raise RuntimeError("parse exploded")

        monkeypatch.setattr(appmod.pipeline, "run_pipeline", boom)
        r = c.post("/ingest", data={"bank": "rhb"}, files={"file": ("s.pdf", b"%PDF-Y", "application/pdf")})
        assert r.status_code == 500


def test_paid_empty_when_no_file():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.get("/data/paid.json").json() == []


def test_paid_post_adds_and_removes_persisting_to_pvc():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        r = c.post("/api/paid", json={"key": "cimb|2026-06", "paid": True})
        assert r.status_code == 200
        assert r.json() == ["cimb|2026-06"]
        # survives independently of app.json (read back from the PVC)
        assert c.get("/data/paid.json").json() == ["cimb|2026-06"]
        # toggling off removes it
        c.post("/api/paid", json={"key": "cimb|2026-06", "paid": False})
        assert c.get("/data/paid.json").json() == []


def test_paid_post_rejects_missing_key():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.post("/api/paid", json={"paid": True}).status_code == 400


def test_reminder_tick_reads_bills_and_paid_from_pvc():
    """The in-process reminder reads the PVC directly (no self-HTTP). Telegram stubbed."""
    import remind_bills
    with tempfile.TemporaryDirectory() as d:
        _, appmod = _client(d)
        bills = [
            {"bank": "hsbc", "statement_month": "2026-08", "current_balance": 10.0,
             "payment_due_date": "2026-08-22"},
            {"bank": "cimb", "statement_month": "2026-08", "current_balance": 20.0,
             "payment_due_date": "2026-08-22"},   # marked paid -> skipped
            {"bank": "rhb", "statement_month": "2026-08", "current_balance": 30.0,
             "payment_due_date": None},           # no due date -> skipped, not guessed
        ]
        with open(os.path.join(d, "app.json"), "w", encoding="utf-8") as fh:
            json.dump({"bills": bills}, fh)
        with open(os.path.join(d, "paid.json"), "w", encoding="utf-8") as fh:
            json.dump(["cimb|2026-08"], fh)

        sent = []
        real_send, real_today = remind_bills.send, remind_bills.today_myt
        remind_bills.send = sent.append
        remind_bills.today_myt = lambda: __import__("datetime").date(2026, 8, 20)
        try:
            got = appmod._reminder_tick()
            assert [b["bank"] for b in got] == ["hsbc"], got
            assert len(sent) == 1 and "HSBC" in sent[0]
            assert appmod._reminder_tick() == []           # state file dedupes
            assert os.path.exists(os.path.join(d, "reminded.json"))
        finally:
            remind_bills.send, remind_bills.today_myt = real_send, real_today


def test_fetch_loop_runs_only_when_gmail_is_configured():
    """The mail fetch is a timer in this process, off unless both GMAIL_* vars are set -
    same contract as the reminders. IMAP itself is stubbed; no mailbox is touched."""
    import threading

    import fetch_mail
    called = threading.Event()
    real, real_env = fetch_mail.main, {k: os.environ.pop(k, None)
                                       for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD")}
    fetch_mail.main = lambda *a, **k: called.set()
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _client(d)
            with c:                                  # entering runs the lifespan
                assert not called.wait(0.5), "fetched without credentials"
            os.environ["GMAIL_USER"] = "someone@example.com"
            os.environ["GMAIL_APP_PASSWORD"] = "app-password"
            c, _ = _client(d)
            with c:
                assert called.wait(5), "configured, but never fetched"
    finally:
        fetch_mail.main = real
        for k, v in real_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_reminder_tick_noop_without_app_json():
    with tempfile.TemporaryDirectory() as d:
        _, appmod = _client(d)
        assert appmod._reminder_tick() == []


# ---------------------------------------------------------------- password gate (#51)
# APP_PASSWORD off = today's behaviour, unchanged. On = every API route needs the cookie
# or the header, except /healthz (the k8s probes) and the login route itself.

def _gated(d, password="hunter2"):
    """A client with the gate ON. Returns (client, appmod)."""
    os.environ["APP_PASSWORD"] = password
    return _client(d)


def _ungate():
    os.environ.pop("APP_PASSWORD", None)


def test_gate_is_off_unless_app_password_is_set():
    # Same off-unless-configured contract as TELEGRAM_* and GMAIL_*: an existing
    # deployment that sets nothing must keep working with no cookie at all.
    _ungate()
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.get("/bills").status_code == 200
        assert c.get("/data/paid.json").status_code == 200
        # and login says so rather than 401-ing a caller who cannot possibly authenticate
        assert c.post("/api/login", json={"password": "anything"}).json() == {"ok": True, "auth": False}


def test_gate_401s_the_data_routes_but_not_the_shell():
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _gated(d)
            for path in ("/bills", "/data/app.json", "/data/paid.json", "/data/waivers.json"):
                assert c.get(path).status_code == 401, path
            assert c.post("/api/paid", json={"key": "cimb|2026-06", "paid": True}).status_code == 401
            # The SPA shell stays public — it is code, not data, and the browser needs a
            # page to render the password prompt in.
            r = c.get("/")
            assert r.status_code == 200 and "spa" in r.text
    finally:
        _ungate()


def test_healthz_is_reachable_unauthenticated_in_both_modes():
    # NOT NEGOTIABLE: the k8s liveness/readiness probes send no cookie and no header.
    _ungate()
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.get("/healthz").status_code == 200
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _gated(d)
            assert c.get("/healthz").status_code == 200
            assert c.get("/healthz").json() == {"ok": True}
    finally:
        _ungate()


def test_correct_password_issues_a_working_cookie():
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _gated(d)
            assert c.get("/bills").status_code == 401
            r = c.post("/api/login", json={"password": "hunter2"})
            assert r.status_code == 200 and r.json()["auth"] is True
            ck = r.cookies.get(appmod.COOKIE)
            assert ck and "." in ck                       # signed, not the password
            assert "hunter2" not in ck
            set_cookie = r.headers["set-cookie"].lower()
            assert "httponly" in set_cookie and "samesite=lax" in set_cookie
            assert "secure" not in set_cookie             # TestClient speaks http
            # the client kept the cookie: the gated routes now answer
            assert c.get("/bills").status_code == 200
            assert c.post("/api/paid", json={"key": "cimb|2026-06", "paid": True}).status_code == 200
    finally:
        _ungate()


def test_wrong_password_is_rejected_and_sets_no_cookie():
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _gated(d)
            r = c.post("/api/login", json={"password": "hunter3"})
            assert r.status_code == 401
            assert appmod.COOKIE not in r.cookies
            assert c.get("/bills").status_code == 401
            # an empty/missing password is not a way in either
            assert c.post("/api/login", json={}).status_code == 401
    finally:
        _ungate()


def test_forged_and_expired_cookies_are_rejected():
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _gated(d)
            for bad in ("", "garbage", "9999999999.deadbeef", appmod._issue_token("hunter3")):
                c.cookies.set(appmod.COOKIE, bad)
                assert c.get("/bills").status_code == 401, bad
            # a correctly signed but expired token is still no
            exp = int(__import__("time").time()) - 1
            c.cookies.set(appmod.COOKIE, f"{exp}.{appmod._sign(exp, 'hunter2')}")
            assert c.get("/bills").status_code == 401
    finally:
        _ungate()


def test_cookie_is_secure_when_the_request_came_over_https():
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _gated(d)
            r = c.post("/api/login", json={"password": "hunter2"},
                       headers={"x-forwarded-proto": "https"})
            assert "secure" in r.headers["set-cookie"].lower()
    finally:
        _ungate()


def test_fetch_loop_can_still_ingest_with_the_gate_on(monkeypatch):
    """The trap #51 names: _fetch_loop goes back out through /ingest over the loopback,
    carrying no cookie. fetch_mail.ingest() sends APP_PASSWORD as X-App-Password instead,
    which is the same value the server holds. This drives the REAL fetch_mail.ingest and
    replays the request it built into the app, so both halves are exercised.
    """
    import contextlib
    import io

    import fetch_mail
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _gated(d)
            monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: {"VERIFIED": 1})

            def urlopen(req, timeout=None):        # loopback stand-in
                r = c.post("/ingest", content=req.data, headers=dict(req.header_items()))
                assert r.status_code == 200, (r.status_code, r.text)
                return contextlib.closing(io.BytesIO(r.content))

            monkeypatch.setattr(fetch_mail.urllib.request, "urlopen", urlopen)
            assert fetch_mail.ingest(b"%PDF-LOOP", "cimb")["recon"] == {"VERIFIED": 1}
            assert os.listdir(os.path.join(d, "pdfs"))[0].startswith("cimb_")

            # the header is not a rubber stamp: a wrong one is still 401, and no header
            # at all (what a naive loopback POST looks like) is too.
            for hdr in ({"x-app-password": "wrong"}, {}):
                r = c.post("/ingest", data={"bank": "cimb"},
                           files={"file": ("s.pdf", b"%PDF-N", "application/pdf")}, headers=hdr)
                assert r.status_code == 401, hdr
    finally:
        _ungate()


# ------------------------------------------------- the static mount is not a way around
# A route-level dependency cannot gate a StaticFiles mount: the mount is not an APIRoute,
# so it never runs one. The build baked web/static/data/*.json into web_build/data/, which
# put app.json INSIDE the public mount - and every path variant that misses the exact
# "/data/app.json" route fell through to it. Both halves are fixed: the gate is now
# middleware over a normalised path, and the Dockerfile stops shipping build/data.

SENTINEL = b"BAKED-INTO-IMAGE-SECRET"

# All five reach the same file. curl --path-as-is sends them verbatim.
BYPASS_PATHS = (
    "/data/app.json",
    "//data/app.json",
    "/data/app.json/",
    "/./data/app.json",
    "/data//app.json",
    "/x/../data/app.json",
    "/DATA/app.json",          # only a bypass on a case-insensitive filesystem
    "/data/paid.json",
    "/data/waivers.json",
    "//bills",
)


def _raw_get(asgi_app, path, headers=()):
    """GET a RAW path straight into the ASGI app.

    NOT TestClient: httpx normalises `//x`, `/./x` and `/a/../x` client-side, so a
    TestClient-based version of this test passes with the hole wide open (verified).
    A real client sends them verbatim; so does this.
    """
    import asyncio
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
        "root_path": "", "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }
    got = {"body": b""}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            got["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            got["body"] += msg.get("body", b"")

    asyncio.run(asgi_app(scope, receive, send))
    return got["status"], got["body"]


def _baked_web(d):
    """A WEB_DIR shaped like the image used to be: shell assets AND a data/ dir."""
    web = os.path.join(d, "web_build")
    os.makedirs(os.path.join(web, "data"), exist_ok=True)
    os.makedirs(os.path.join(web, "_app"), exist_ok=True)
    with open(os.path.join(web, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><title>spa</title>")
    with open(os.path.join(web, "_app", "app.js"), "w", encoding="utf-8") as fh:
        fh.write("console.log(1)")
    with open(os.path.join(web, "manifest.webmanifest"), "w", encoding="utf-8") as fh:
        fh.write('{"name":"m"}')
    for name in ("app.json", "paid.json", "waivers.json"):
        with open(os.path.join(web, "data", name), "wb") as fh:
            fh.write(SENTINEL)
    return web


def test_no_path_variant_reaches_data_through_the_static_mount():
    try:
        with tempfile.TemporaryDirectory() as d:
            web = _baked_web(d)
            os.environ["APP_PASSWORD"] = "hunter2"
            c, appmod = _client(d, web=web)
            for path in BYPASS_PATHS:
                status, body = _raw_get(c.app, path)
                assert status == 401, f"{path} -> {status} {body[:80]!r}"
                assert SENTINEL not in body, f"{path} served the baked file"
            # the header and cookie still work on the canonical path
            status, _ = _raw_get(c.app, "/data/app.json", [("x-app-password", "hunter2")])
            assert status == 404          # gate passed; no app.json on the PVC
            tok = appmod._issue_token("hunter2")
            status, _ = _raw_get(c.app, "/data/app.json", [("cookie", f"{appmod.COOKIE}={tok}")])
            assert status == 404
    finally:
        _ungate()


def test_the_shell_still_loads_while_locked():
    # The login form cannot render if the gate eats the assets that draw it.
    try:
        with tempfile.TemporaryDirectory() as d:
            web = _baked_web(d)
            os.environ["APP_PASSWORD"] = "hunter2"
            c, _ = _client(d, web=web)
            for path in ("/", "/index.html", "/_app/app.js", "/manifest.webmanifest",
                         "/healthz", "//healthz", "/some-spa-route"):
                status, body = _raw_get(c.app, path)
                assert status == 200, f"{path} -> {status}"
                assert SENTINEL not in body
    finally:
        _ungate()


def test_norm_collapses_every_variant_to_one_string():
    from server import app as appmod
    for path in ("//data/app.json", "/data/app.json/", "/./data/app.json",
                 "/data//app.json", "/x/../data/app.json", "/data/./app.json",
                 "///data//.//app.json"):
        assert appmod._norm(path) == "/data/app.json", path
    assert appmod._norm("/") == "/"
    assert appmod._norm("//") == "/"
    assert appmod._norm("/..") == "/"          # cannot climb out


def test_the_image_does_not_ship_the_baked_data_dir():
    """web/static/data/*.json is a local dev fixture; adapter-static copies it into
    build/data/, which lands inside the public static mount. Nothing else can catch this
    without building the image, so check the line that removes it."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "Dockerfile"), encoding="utf-8") as fh:
        dockerfile = fh.read()
    assert "rm -rf build/data" in dockerfile, "the image would bake web/static/data into web_build"
    # and it has to happen in the web stage, before the COPY --from=web
    assert dockerfile.index("rm -rf build/data") < dockerfile.index("COPY --from=web")
