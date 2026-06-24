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


def test_ingest_warns_on_review(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        c, appmod = _client(d)
        monkeypatch.setattr(appmod.pipeline, "run_pipeline", lambda dd: {"VERIFIED": 68, "REVIEW": 1})
        r = c.post("/ingest", data={"bank": "sc"}, files={"file": ("s.pdf", b"%PDF-X", "application/pdf")})
        assert r.json()["warning"] is True


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
