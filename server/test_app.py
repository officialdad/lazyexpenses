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
        # #62: `version` is additive; APP_VERSION is unset here, i.e. exactly a bare
        # `docker build` / checkout run, which must say "dev" and never a stale semver.
        assert c.get("/healthz").json() == {"ok": True, "version": "dev"}


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


def test_release_critical_static_files_revalidate_and_hashed_assets_do_not():
    """#75: starlette's StaticFiles sets an ETag but no Cache-Control, so the correctness
    of the update path rested on a browser default we never set — in sw.js, the file by
    which every client learns a release happened.

    `no-cache` is revalidate-every-time, NOT `no-store`: the ETag still turns an unchanged
    file into a 304. Mutation check: swap it for max-age, or drop the immutable branch,
    and this goes red."""
    with tempfile.TemporaryDirectory() as d:
        web = os.path.join(d, "web_build")
        c, _ = _client(d, web=web)
        os.makedirs(os.path.join(web, "_app", "immutable", "chunks"), exist_ok=True)
        files = {"sw.js": "self.addEventListener('push',()=>{})",
                 "manifest.webmanifest": "{}",
                 "_app/immutable/chunks/abc123.js": "export const x=1"}
        for name, body in files.items():
            with open(os.path.join(web, *name.split("/")), "w", encoding="utf-8") as fh:
                fh.write(body)

        for name in ("sw.js", "manifest.webmanifest"):
            r = c.get("/" + name)
            assert r.status_code == 200, name
            assert r.headers["cache-control"] == "no-cache", name
        # the SPA shell is a stable url whose bytes change every release, same rule
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert c.get("/nope").headers["cache-control"] == "no-cache"   # fallback path too

        # content-addressed: the filename changes when the bytes do, so cache it forever
        r = c.get("/_app/immutable/chunks/abc123.js")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "public, max-age=31536000, immutable"

        # no-cache, not no-store — an unchanged sw.js must still 304 rather than re-send
        etag = c.get("/sw.js").headers["etag"]
        assert c.get("/sw.js", headers={"if-none-match": etag}).status_code == 304


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
        assert c.get("/healthz").json()["ok"] is True


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


def test_cats_post_persists_to_the_pvc_and_reruns_the_pipeline(monkeypatch):
    """#82: a confirmation is written next to waivers.json and applied straight away —
    parse.py reads it AFTER the per-PDF cache, so the re-run is a warm one."""
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        ran = []
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: ran.append(dd) or {})
        assert c.get("/data/cats.json").json() == {}
        r = c.post("/api/cats", json={"merchant": "BINGXUE", "category": "F&B"})
        assert r.status_code == 200, r.text
        assert r.json() == {"BINGXUE": "F&B"}
        assert len(ran) == 1
        assert c.get("/data/cats.json").json() == {"BINGXUE": "F&B"}
        # clearing is the only undo — an override beats CATS, so CATS cannot correct it
        c.post("/api/cats", json={"merchant": "BINGXUE", "category": None})
        assert c.get("/data/cats.json").json() == {}
        assert len(ran) == 2


def test_cats_post_rejects_a_category_outside_the_taxonomy(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: 1 / 0)  # must not run
        assert c.post("/api/cats", json={"merchant": "X", "category": "Snacks"}).status_code == 400
        assert c.post("/api/cats", json={"category": "F&B"}).status_code == 400
        assert not os.path.exists(os.path.join(d, "cats.json"))


def test_ingest_announces_only_a_bill_that_was_not_there_before(monkeypatch):
    """#83: the trigger is a new bills[] entry, not an upload. Re-posting a statement is
    idempotent by design (content-hash filename), so it must stay silent."""
    import remind_bills
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        sent = []
        monkeypatch.setattr(remind_bills, "send", sent.append)
        month = remind_bills.today_myt().strftime("%Y-%m")

        def fake_run(dd):
            with open(os.path.join(dd, "app.json"), "w", encoding="utf-8") as fh:
                json.dump({"bills": [{"bank": "cimb", "statement_month": month,
                                      "current_balance": 812.5,
                                      "payment_due_date": "2026-09-05"}]}, fh)
            return {"VERIFIED": 1}

        monkeypatch.setattr(appmod.pipeline, "run_pipeline", fake_run)
        c.post("/ingest", files={"file": ("s.pdf", b"%PDF-1.4", "application/pdf")},
               data={"bank": "cimb"})
        assert len(sent) == 1 and "CIMB" in sent[0] and "812.50" in sent[0]
        # the same statement again: same bills[], nothing new to say
        c.post("/ingest", files={"file": ("s.pdf", b"%PDF-1.4", "application/pdf")},
               data={"bank": "cimb"})
        assert len(sent) == 1, sent
        state = json.load(open(os.path.join(d, "reminded.json"), encoding="utf-8"))
        assert state == [f"arrived|cimb|{month}"], state


def test_a_backfill_records_arrivals_without_sending_any_of_them(monkeypatch):
    """#91: announce()'s own floor drops anything older than last month, but bills[] is
    the NEWEST statement per bank — so walking a year of mail ends on a current-month
    bill per bank, above that floor, and six banks would be a burst of push. During a
    backfill every arrival is seeded instead: recorded, never sent."""
    import remind_bills
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        sent = []
        monkeypatch.setattr(remind_bills, "send", sent.append)
        month = remind_bills.today_myt().strftime("%Y-%m")

        def fake_run(dd):
            with open(os.path.join(dd, "app.json"), "w", encoding="utf-8") as fh:
                json.dump({"bills": [{"bank": "cimb", "statement_month": month,
                                      "current_balance": 812.5,
                                      "payment_due_date": "2026-09-05"}]}, fh)
            return {"VERIFIED": 1}

        monkeypatch.setattr(appmod.pipeline, "run_pipeline", fake_run)
        c.app.state.backfill["running"] = True
        c.post("/ingest", files={"file": ("s.pdf", b"%PDF-1.4", "application/pdf")},
               data={"bank": "cimb"})
        assert sent == [], sent
        # recorded, so the statement is not announced later either — it is not news then
        state = json.load(open(os.path.join(d, "reminded.json"), encoding="utf-8"))
        assert state == [f"arrived|cimb|{month}"], state


def test_the_backfill_route_starts_a_run_and_reports_progress(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        # no credentials: a 400 before anything is scheduled
        assert c.post("/api/settings/backfill").status_code == 400
        monkeypatch.setattr(appmod.settings, "get",
                            lambda name, default=None: "set" if name.startswith("GMAIL") else default)

        called = {}

        def fake_main(dry, criteria, stat):
            called.update(dry=dry, criteria=criteria)
            stat.update(total=9, done=9, ingested=7, skipped=2, unknown=["Your statement"])

        monkeypatch.setattr(appmod.fetch_mail, "main", fake_main)
        assert c.post("/api/settings/backfill").json()["running"] is True
        got = c.get("/api/settings/backfill").json()
        for _ in range(50):                      # it runs off the request thread
            if not got["running"]:
                break
            got = c.get("/api/settings/backfill").json()
        # the search is ALL and the run is not a dry run — anything but UNSEEN is readonly
        # in fetch_mail, which is what keeps \Seen off a year of mail
        assert called == {"dry": False, "criteria": "ALL"}
        assert (got["running"], got["ingested"], got["skipped"]) == (False, 7, 2)
        assert got["unknown"] == ["Your statement"]
        # a second press while one is going is a 409, not a second walk of the mailbox
        c.app.state.backfill["running"] = True
        assert c.post("/api/settings/backfill").status_code == 409


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
    """The mail fetch is a timer in this process that does nothing unless both GMAIL_*
    values are set - same contract as the reminders. Since #40 the LOOP always starts and
    the check moved inside the tick (credentials can be typed into the UI while the
    process runs), so what this pins is the observable half: no credentials, no fetch.
    IMAP itself is stubbed; no mailbox is touched."""
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
            assert c.get("/healthz").json()["ok"] is True
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


# ---------------------------------------------------------------- web push (#39)

def test_push_key_is_generated_on_first_call_and_stable_after():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        k = c.get("/api/push/key").json()["key"]
        assert k and c.get("/api/push/key").json()["key"] == k
        assert os.path.exists(os.path.join(d, "vapid.json"))


def test_push_subscribe_stores_and_unsubscribe_forgets():
    """Same volume-write shape as /api/paid: one JSON file next to it, atomic rewrite."""
    import web_push
    ep = "https://push.example.net/abc"
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        r = c.post("/api/push/subscribe",
                   json={"endpoint": ep, "keys": {"p256dh": "BAAA", "auth": "AAAA"}})
        assert r.json() == {"subscribed": True, "count": 1}, r.json()
        assert os.path.exists(os.path.join(d, "push_subs.json"))
        assert list(web_push.load_subs()) == [ep]
        # no keys = the UI's off switch
        assert c.post("/api/push/subscribe", json={"endpoint": ep}).json()["count"] == 0
        assert web_push.load_subs() == {}


def test_push_subscribe_rejects_a_missing_endpoint():
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert c.post("/api/push/subscribe", json={"keys": {}}).status_code == 400
        assert c.post("/api/push/subscribe",
                      json={"endpoint": "javascript:alert(1)"}).status_code == 400


def test_push_routes_are_gated_by_app_password_like_every_other_api_route():
    """The gate derives its set from the router, so a route added later is covered the
    day it is added (#51). A subscription is somewhere to send balances to."""
    with tempfile.TemporaryDirectory() as d:
        c, _ = _gated(d)
        try:
            assert c.get("/api/push/key").status_code == 401
            assert c.post("/api/push/subscribe", json={"endpoint": "https://x/y"}).status_code == 401
        finally:
            _ungate()


def test_reminder_loop_runs_without_any_configuration_but_stays_quiet():
    """#39 flips the lifespan gate: Web Push needs no env var, so the loop always starts
    and decides per tick whether anyone is listening. Nothing configured -> no send."""
    import threading

    import remind_bills
    ticked = threading.Event()
    real_env = {k: os.environ.pop(k, None) for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    real_send = remind_bills.send
    remind_bills.send = lambda t: ticked.set()
    # #40 made the schedule tick-time config, so the test sets it the way a deployment
    # does (the environment) instead of poking a module constant that no longer exists.
    os.environ["REMIND_HOUR"], os.environ["REMIND_POLL"] = "0", "1"
    try:
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "app.json"), "w", encoding="utf-8") as fh:
                json.dump({"bills": [{"bank": "hsbc", "statement_month": "2026-08",
                                      "current_balance": 1.0,
                                      "payment_due_date": "2020-01-01"}]}, fh)
            c, appmod = _client(d)
            with c:                                   # entering runs the lifespan
                assert not ticked.wait(1.0), "sent with no transport configured"
            # a browser subscribes -> the very same loop starts delivering
            import web_push
            web_push.save_subs({"https://push.example.net/x": {"p256dh": "B", "auth": "A"}})
            assert remind_bills.transports_configured()
            c, appmod = _client(d)
            with c:
                assert ticked.wait(5), "subscribed, but never reminded"
    finally:
        remind_bills.send = real_send
        os.environ.pop("REMIND_HOUR", None)
        os.environ.pop("REMIND_POLL", None)
        for k, v in real_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


# ---------------------------------------------------------------- first-run setup (#40)
# settings.json on the volume, environment wins, secrets write-only. The security half of
# this block is the point of the issue: there is no login by default (#65), so a secret
# that can be read back is a secret that has leaked.

SECRET_VALUES = {
    "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
    "TELEGRAM_BOT_TOKEN": "123456:AAtotally-secret-bot-token",
    "CC_PW_CIMB": "cimb-pdf-password",
    "CC_PW_HSBC": "hsbc-pdf-password",
}


def _clean_settings_env():
    for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "GMAIL_LABEL", "IMAP_HOST", "FETCH_POLL",
              "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "REMIND_HOUR", "REMIND_DAYS",
              "REMIND_TEMPLATE", "CC_PW_CIMB", "CC_PW_HSBC"):
        os.environ.pop(k, None)


def test_settings_start_empty_and_report_every_secret_as_unconfigured():
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        s = c.get("/api/settings").json()
        assert s["values"]["GMAIL_USER"] == ""
        assert s["locked"] == []
        assert s["banks"] == list(__import__("parse").BANKS)
        assert set(s["secrets"]) >= {"GMAIL_APP_PASSWORD", "TELEGRAM_BOT_TOKEN", "CC_PW_CIMB"}
        assert not any(s["secrets"].values())


def test_settings_round_trip_through_the_volume():
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        r = c.post("/api/settings", json={"GMAIL_USER": "me@example.com", "GMAIL_LABEL": "CC",
                                          "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop"})
        assert r.status_code == 200
        # written where the other state files live, and readable by the next process
        assert json.loads(open(os.path.join(d, "settings.json"), encoding="utf-8").read()) == {
            "GMAIL_APP_PASSWORD": "abcd efgh ijkl mnop",
            "GMAIL_LABEL": "CC", "GMAIL_USER": "me@example.com"}
        s = c.get("/api/settings").json()
        assert s["values"]["GMAIL_USER"] == "me@example.com"   # not a secret: shown back
        assert s["secrets"]["GMAIL_APP_PASSWORD"] is True      # a secret: a bool, no value
        # "" clears
        c.post("/api/settings", json={"GMAIL_APP_PASSWORD": ""})
        assert c.get("/api/settings").json()["secrets"]["GMAIL_APP_PASSWORD"] is False


def test_settings_reject_a_name_that_is_not_on_the_whitelist():
    """These values are merged into the parse.py subprocess environment, so an arbitrary
    name is arbitrary environment injection. APP_PASSWORD is refused too: the gate must
    not be settable through the thing it gates."""
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        for bad in ("LD_PRELOAD", "PATH", "PYTHONPATH", "APP_PASSWORD", "cc_pw_cimb"):
            r = c.post("/api/settings", json={bad: "x"})
            assert r.status_code == 400, f"{bad} was accepted"
            assert bad in r.json()["detail"]
        assert not os.path.exists(os.path.join(d, "settings.json"))


def test_no_endpoint_ever_returns_a_secret_value():
    """THE security contract of #40 (see #65). Every secret is written through the API,
    then every route the app serves is swept for the value. Not masked, not truncated,
    not last-four — the string must not appear anywhere in any response.

    Mutation check: make settings.public() emit the value (or a mask of it) and this
    goes red on the very first sweep.
    """
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        assert c.post("/api/settings", json=SECRET_VALUES).status_code == 200
        paths = ["/api/settings", "/data/app.json", "/data/paid.json", "/data/waivers.json",
                 "/bills", "/healthz", "/", "/index.html"]
        bodies = [c.post("/api/settings", json={}).text]           # the POST response too
        bodies += [c.get(p).text for p in paths]
        for value in SECRET_VALUES.values():
            for body in bodies:
                assert value not in body
                # and no prefix of it either: a "masked" secret is still a leaked one
                assert value[:6] not in body
        # ...while the pipeline still gets them, which is the whole point of storing them
        assert appmod.settings.env()["CC_PW_CIMB"] == SECRET_VALUES["CC_PW_CIMB"]


def test_environment_wins_over_settings_json_and_says_so():
    """An existing .env / k8s-Secret deployment must behave exactly as it did before this
    file existed — so env is read first, the volume value is never even written over it,
    and the name comes back `locked` for the UI to grey out."""
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        c.post("/api/settings", json={"GMAIL_USER": "volume@example.com",
                                      "REMIND_HOUR": "21", "CC_PW_CIMB": "from-the-volume"})
        assert appmod.settings.get("GMAIL_USER") == "volume@example.com"
        assert appmod.settings.get_int("REMIND_HOUR", 9) == 21

        os.environ["GMAIL_USER"] = "env@example.com"
        os.environ["REMIND_HOUR"] = "6"
        os.environ["CC_PW_CIMB"] = "from-the-env"
        try:
            assert appmod.settings.get("GMAIL_USER") == "env@example.com"
            assert appmod.settings.get_int("REMIND_HOUR", 9) == 6
            assert appmod._remind_hour() == 6
            # the parse.py subprocess must not be handed the shadowed volume copy
            assert "CC_PW_CIMB" not in appmod.settings.env()
            s = c.get("/api/settings").json()
            assert s["values"]["GMAIL_USER"] == "env@example.com"
            assert set(s["locked"]) == {"GMAIL_USER", "REMIND_HOUR", "CC_PW_CIMB"}
            # a POST to a locked name is ignored, not applied and not silently persisted
            c.post("/api/settings", json={"GMAIL_USER": "hijack@example.com"})
            assert appmod.settings.get("GMAIL_USER") == "env@example.com"
            assert appmod.settings.load()["GMAIL_USER"] == "volume@example.com"
        finally:
            _clean_settings_env()
        # env gone -> the volume value is back, untouched
        assert appmod.settings.get("GMAIL_USER") == "volume@example.com"


def test_settings_survive_a_corrupt_file():
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "settings.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        c, appmod = _client(d)
        assert c.get("/api/settings").status_code == 200
        assert appmod.settings.load() == {}


def test_settings_routes_are_gated_by_app_password_like_every_other_api_route():
    _clean_settings_env()
    with tempfile.TemporaryDirectory() as d:
        try:
            c, _ = _gated(d)
            assert c.get("/api/settings").status_code == 401
            assert c.post("/api/settings", json={"GMAIL_USER": "x@y.z"}).status_code == 401
            assert c.post("/api/settings/test-mail").status_code == 401
            assert c.post("/api/settings/test-reminder").status_code == 401
        finally:
            _ungate()


def test_test_mail_reports_what_it_found_and_never_marks_anything_seen():
    """The Test connection button. IMAP is stubbed — the assertion is that it selects
    READ-ONLY, so testing a connection can never consume a statement mail."""
    _clean_settings_env()
    import fetch_mail

    class FakeIMAP:
        selected = None

        def __init__(self, host):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            if p != "right-password":
                raise RuntimeError("AUTHENTICATIONFAILED")

        def select(self, mailbox, readonly=False):
            FakeIMAP.selected = (mailbox, readonly)
            return "OK", [b"3"]        # imaplib returns a status; NO means no such label

        def search(self, charset, *criteria):
            return "OK", [b"1 2 3"]

    real = fetch_mail.imaplib.IMAP4_SSL
    fetch_mail.imaplib.IMAP4_SSL = FakeIMAP
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _client(d)
            # nothing configured -> a sentence, not a stack trace
            r = c.post("/api/settings/test-mail")
            assert r.status_code == 400 and "app password" in r.json()["detail"]
            c.post("/api/settings", json={"GMAIL_USER": "me@example.com",
                                          "GMAIL_APP_PASSWORD": "wrong", "GMAIL_LABEL": "CC"})
            assert c.post("/api/settings/test-mail").status_code == 400
            c.post("/api/settings", json={"GMAIL_APP_PASSWORD": "right-password"})
            body = c.post("/api/settings/test-mail").json()
            assert body == {"ok": True, "user": "me@example.com", "label": "CC", "unread": 3}
            assert FakeIMAP.selected == ('"CC"', True), "a connection test must be read-only"
    finally:
        fetch_mail.imaplib.IMAP4_SSL = real
        _clean_settings_env()


def test_test_reminder_sends_one_message_and_reports_a_failure_as_one():
    _clean_settings_env()
    import remind_bills
    sent, real = [], remind_bills.send
    remind_bills.send = lambda t: sent.append(t)
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _client(d)
            assert c.post("/api/settings/test-reminder").json() == {"ok": True}
            assert sent == [appmod.TEST_REMINDER]
            # send() raises only when NOTHING got through — that is the reportable case
            remind_bills.send = lambda t: (_ for _ in ()).throw(
                RuntimeError("no reminder transport configured"))
            r = c.post("/api/settings/test-reminder")
            assert r.status_code == 400 and "no reminder transport" in r.json()["detail"]
    finally:
        remind_bills.send = real


def test_telegram_and_the_template_come_from_settings_too():
    """The reminder half of tick-time config: a Telegram pair typed into the UI configures
    a transport, and a template typed into the UI renders the next message — no restart."""
    _clean_settings_env()
    import remind_bills
    with tempfile.TemporaryDirectory() as d:
        c, _ = _client(d)
        assert remind_bills.transports_configured() is False
        c.post("/api/settings", json={"TELEGRAM_BOT_TOKEN": "1:aa", "TELEGRAM_CHAT_ID": "42"})
        assert remind_bills.transports_configured() is True
        bill = {"bank": "cimb", "statement_month": "2026-08", "current_balance": 12.5,
                "payment_due_date": "2026-08-20"}
        import datetime as _dt
        assert "cimb" not in remind_bills.message(bill, _dt.date(2026, 8, 18))
        c.post("/api/settings", json={"REMIND_TEMPLATE": "{bank} owes {amount} ({when})"})
        assert remind_bills.message(bill, _dt.date(2026, 8, 18)) == "CIMB owes 12.50 (in 2d)"
        c.post("/api/settings", json={"REMIND_DAYS": "30"})
        assert remind_bills.remind_days() == 30
    _clean_settings_env()


# ---------------------------------------------------- shipped default password (#65)
# .env.example now ships APP_PASSWORD=changeme@123, so the documented `docker compose up`
# path is CLOSED rather than open. A shipped default is a known credential, so the two
# things that make it survivable are a loud boot warning and a banner in the UI — both
# driven by a boolean that never carries the value.

def test_default_password_is_reported_as_a_boolean_and_only_when_it_is_the_default():
    """Mutation check: return the password instead of the bool from _settings_view(), or
    drop the `== DEFAULT_PASSWORD` comparison, and this goes red."""
    _clean_settings_env()
    _ungate()
    with tempfile.TemporaryDirectory() as d:
        # no gate at all -> not the default (there is nothing to change)
        c, appmod = _client(d)
        assert c.get("/api/settings").json()["default_password"] is False
        assert appmod.DEFAULT_PASSWORD == "changeme@123", ".env.example ships this exact value"
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _gated(d, password="changeme@123")
            c.post("/api/login", json={"password": "changeme@123"})
            for r in (c.get("/api/settings"), c.post("/api/settings", json={})):
                assert r.json()["default_password"] is True
        # a real password -> no banner
        with tempfile.TemporaryDirectory() as d:
            c, _ = _gated(d, password="something-only-i-know")
            c.post("/api/login", json={"password": "something-only-i-know"})
            assert c.get("/api/settings").json()["default_password"] is False
    finally:
        _ungate()
        _clean_settings_env()


def test_the_app_password_itself_never_comes_back_over_the_api():
    """The gate's own credential is a secret like any other (#40's contract, #65's default).
    Log in, then sweep every route for the password — including the session cookie, which
    is a MAC over the expiry and must not carry the password itself.

    Mutation check: add the password to _settings_view() (or to /api/login's body) and the
    sweep goes red.
    """
    _clean_settings_env()
    pw = "changeme@123"
    try:
        with tempfile.TemporaryDirectory() as d:
            c, appmod = _gated(d, password=pw)
            login = c.post("/api/login", json={"password": pw})
            assert login.status_code == 200
            paths = ["/api/settings", "/data/app.json", "/data/paid.json", "/data/waivers.json",
                     "/bills", "/healthz", "/", "/index.html"]
            bodies = [login.text, c.post("/api/settings", json={}).text]
            bodies += [c.get(p).text for p in paths]
            bodies.append(c.cookies.get(appmod.COOKIE) or "")
            for body in bodies:
                assert pw not in body
                assert pw[:6] not in body      # a masked credential is still a leaked one
    finally:
        _ungate()
        _clean_settings_env()


def test_the_default_password_is_warned_about_at_startup_and_does_not_block_boot():
    """One unmissable line in `docker logs`, and the app still serves — someone mid-setup
    must not be locked out by the warning about being locked out.

    Mutation check: drop the print (or the _default_password() guard) and this goes red.
    """
    _clean_settings_env()
    import contextlib
    import io

    def boot(password):
        os.environ.pop("APP_PASSWORD", None)
        if password:
            os.environ["APP_PASSWORD"] = password
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                c, _ = _client(d)
                with c:                        # entering the context runs the lifespan
                    assert c.get("/healthz").status_code == 200   # boot was NOT refused
            return buf.getvalue()

    try:
        out = boot("changeme@123")
        assert "APP_PASSWORD" in out and "default" in out
        assert len([ln for ln in out.splitlines() if "APP_PASSWORD" in ln]) == 1
        # #72: no password is its OWN warning, and it used to be the silent case — the
        # one deployment actually exposed produced the quietest log. One or the other,
        # never both: a missing password is not a default password.
        none = boot(None)
        assert "NO login" in none and "default" not in none
        assert len([ln for ln in none.splitlines() if "APP_PASSWORD" in ln]) == 1
        assert "NO login" not in out
        assert boot("something-only-i-know").strip() == ""
    finally:
        _ungate()
        _clean_settings_env()


def test_an_unauthenticated_deployment_says_so_over_the_api():
    """#72: `default_password` answers False with no password set, which reads as "it was
    changed" and is backwards — it is False because there is nothing to change. So the
    open deployment needs its own flag, or the UI cannot tell the good state from the
    worst one.

    Mutation check: drop `unauthenticated` from _settings_view(), or derive it from
    DEFAULT_PASSWORD instead of from "is anything set", and this goes red."""
    _clean_settings_env()
    _ungate()
    try:
        with tempfile.TemporaryDirectory() as d:
            c, _ = _client(d)                 # no gate: the state #72 is about
            body = c.get("/api/settings").json()
            assert body["unauthenticated"] is True
            assert body["default_password"] is False       # and this is why it needs a flag
        for pw in ("changeme@123", "something-only-i-know"):
            with tempfile.TemporaryDirectory() as d:
                c, _ = _gated(d, password=pw)
                c.post("/api/login", json={"password": pw})
                assert c.get("/api/settings").json()["unauthenticated"] is False
    finally:
        _ungate()
        _clean_settings_env()
