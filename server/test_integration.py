"""End-to-end: post a real unlocked PDF -> app.json regenerated, recon VERIFIED.
Slow (runs the real pipeline). Run from repo root: python -m pytest server/test_integration.py -v
Skips automatically if no sample PDF is present."""
import glob
import importlib
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLES = sorted(glob.glob(os.path.join("cc-statements", "*.pdf")))


@pytest.mark.skipif(not SAMPLES, reason="no sample PDF in cc-statements/")
def test_ingest_real_pdf_regenerates_app_json():
    sample = SAMPLES[0]
    bank = os.path.basename(sample).split("_")[0]
    with tempfile.TemporaryDirectory() as d:
        os.environ["DATA_DIR"] = d
        os.environ["WEB_DIR"] = os.path.join(d, "web_build")
        os.makedirs(os.environ["WEB_DIR"], exist_ok=True)
        with open(os.path.join(os.environ["WEB_DIR"], "index.html"), "w") as fh:
            fh.write("<!doctype html>")
        from server import app as appmod
        importlib.reload(appmod)
        from fastapi.testclient import TestClient

        client = TestClient(appmod.create_app())
        with open(sample, "rb") as fh:
            content = fh.read()
        r = client.post("/ingest", data={"bank": bank},
                        files={"file": (os.path.basename(sample), content, "application/pdf")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["recon"].get("VERIFIED", 0) >= 1
        # app.json written to the PVC and readable via the route
        app_json = json.loads((open(os.path.join(d, "app.json"), encoding="utf-8")).read())
        assert "bills" in app_json and len(app_json["bills"]) >= 1
        assert client.get("/bills").json()  # non-empty
