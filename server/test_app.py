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
