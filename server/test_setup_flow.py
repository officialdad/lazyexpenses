"""End-to-end for the first-run flow (#40): what someone does with no terminal.

Slow — it runs the real pipeline (parse.py -> insights.py -> export_data.py) over a
temporary volume. The statements are the synthetic ones make_demo_data.py generates, so
this needs no real bank data and runs in CI.

Two paths, and the second is the one the issue is actually about:
  1. empty volume -> upload -> VERIFIED -> /data/app.json serves a populated dashboard
  2. a LOCKED statement -> `locked: true` -> the password goes in through /api/settings
     -> the same file is posted again -> VERIFIED

Run from repo root: python -m pytest server/test_setup_flow.py -v
"""
import importlib
import io
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_demo_data  # noqa: E402

SETTINGS_ENV = ("CC_PW_MAYBANK", "CC_PW_CIMB", "GMAIL_USER", "GMAIL_APP_PASSWORD")


def _statement(bank="maybank"):
    """(pdf bytes, bank) for one synthetic statement, rendered exactly as
    `make_demo_data.py --pdfs` renders it."""
    months, txns = make_demo_data.build(3, seed=7)
    recon = make_demo_data.reconcile(months, txns)
    r = next(r for r in recon if r["bank"] == bank)
    rows = sorted([t for t in txns if t["bank"] == bank and t["statement_month"] == r["smonth"]],
                  key=lambda t: (t["post_date"], t["description"]))
    return make_demo_data.RENDERERS[bank](r, rows), bank


def _client(d):
    for k in SETTINGS_ENV:
        os.environ.pop(k, None)
    os.environ["DATA_DIR"] = d
    os.environ["WEB_DIR"] = os.path.join(d, "web_build")
    os.makedirs(os.environ["WEB_DIR"], exist_ok=True)
    with open(os.path.join(os.environ["WEB_DIR"], "index.html"), "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><title>spa</title>")
    from server import app as appmod
    importlib.reload(appmod)
    from fastapi.testclient import TestClient
    return TestClient(appmod.create_app())


def _post(c, content, bank):
    return c.post("/ingest", data={"bank": bank},
                  files={"file": (f"{bank}.pdf", content, "application/pdf")})


def test_an_empty_volume_becomes_a_populated_dashboard_from_one_upload():
    """The acceptance criterion, whole: nothing on the volume, no terminal, one POST."""
    content, bank = _statement()
    with tempfile.TemporaryDirectory() as d:
        c = _client(d)
        # this is the state the setup flow renders for — a 404, not a blank page
        assert c.get("/data/app.json").status_code == 404
        r = _post(c, content, bank)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["recon"].get("VERIFIED", 0) == 1, body
        assert body["locked"] is False and body["warning"] is False
        data = c.get("/data/app.json").json()
        assert data["rows"] and data["bills"]
        assert json.loads(open(os.path.join(d, "app.json"), encoding="utf-8").read())["rows"]


def test_a_locked_statement_asks_for_its_password_and_succeeds_on_retry():
    """Step 2 of the flow. parse.py raises PdfminerException(PDFPasswordIncorrect) whose
    str() is EMPTY, so the reconciliation row says only ERROR — `locked` is what turns
    that into a question the UI can ask. pypdf is test-only, exactly as in
    test_parse_password.py; without it the encryption half is skipped."""
    pypdf = pytest.importorskip("pypdf")
    plain, bank = _statement()
    w = pypdf.PdfWriter(clone_from=io.BytesIO(plain))
    w.encrypt("s3cret", algorithm="AES-128")
    buf = io.BytesIO()
    w.write(buf)
    locked = buf.getvalue()

    with tempfile.TemporaryDirectory() as d:
        c = _client(d)
        body = _post(c, locked, bank).json()
        assert body["recon"].get("ERROR") == 1, body
        assert body["locked"] is True, "a locked PDF must be reported as locked, not just ERROR"
        assert c.get("/data/app.json").json()["rows"] == []

        # ...the answer goes in where the covering email said it, and nowhere else
        key = f"CC_PW_{bank.upper()}"
        assert c.post("/api/settings", json={key: "s3cret"}).status_code == 200
        assert c.get("/api/settings").json()["secrets"][key] is True
        assert "s3cret" not in c.get("/api/settings").text

        # retry: same bytes, same content hash, same file on the volume — save_pdf is
        # idempotent, so this is a reparse and not a second statement.
        body = _post(c, locked, bank).json()
        assert body["recon"].get("VERIFIED") == 1, body
        assert body["locked"] is False
        assert len(os.listdir(os.path.join(d, "pdfs"))) == 1
        assert c.get("/data/app.json").json()["rows"]


def test_a_corrupt_pdf_is_an_error_but_not_a_password_question():
    """`locked` must not become "something went wrong" — the UI would then ask for a
    password that cannot help. /Encrypt is what separates the two."""
    with tempfile.TemporaryDirectory() as d:
        c = _client(d)
        body = _post(c, b"%PDF-1.4\nnot really a pdf\n%%EOF\n", "hsbc").json()
        assert body["recon"].get("ERROR") == 1, body
        assert body["locked"] is False
