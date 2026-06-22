"""Plain-assert tests (run from repo root: python -m pytest server/test_pipeline.py)."""
import csv
import importlib
import json
import os
import sys
import tempfile

# repo root on path (scripts live there)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_build_bills_skips_non_iso_smonth():
    import export_data
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "reconciliation.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["bank", "smonth", "cur", "due", "status"])
            w.writeheader()
            # An UNKNOWN-smonth NO_BALANCE row must NOT win over a real month.
            w.writerow({"bank": "hsbc", "smonth": "UNKNOWN", "cur": "", "due": "", "status": "NO_BALANCE"})
            w.writerow({"bank": "hsbc", "smonth": "2026-05", "cur": "1234.50", "due": "2026-06-05", "status": "VERIFIED"})
        bills = export_data.build_bills(csv_path=p)
        assert len(bills) == 1
        b = bills[0]
        assert b["bank"] == "hsbc"
        assert b["statement_month"] == "2026-05"
        assert b["current_balance"] == 1234.50
        assert b["payment_due_date"] == "2026-06-05"


def test_out_respects_env():
    os.environ["STMT_OUT"] = "/tmp/custom-app.json"
    import export_data
    importlib.reload(export_data)
    assert export_data.OUT == "/tmp/custom-app.json"
    del os.environ["STMT_OUT"]
    importlib.reload(export_data)


def test_src_respects_env():
    os.environ["STMT_SRC"] = "/tmp/pdfs"
    import parse
    importlib.reload(parse)
    assert parse.SRC == "/tmp/pdfs"
    del os.environ["STMT_SRC"]
    importlib.reload(parse)


def test_save_pdf_is_content_hashed_and_idempotent():
    from server import pipeline
    with tempfile.TemporaryDirectory() as d:
        p1 = pipeline.save_pdf(d, "cimb", b"%PDF-FAKE-1")
        p2 = pipeline.save_pdf(d, "cimb", b"%PDF-FAKE-1")  # same bytes -> same path, no dup
        assert p1 == p2
        assert p1.parent.name == "pdfs"
        assert p1.name.startswith("cimb_") and p1.name.endswith(".pdf")
        assert len(list(p1.parent.glob("*.pdf"))) == 1
        p3 = pipeline.save_pdf(d, "cimb", b"%PDF-FAKE-2")  # different bytes -> new file
        assert p3 != p1
        assert len(list(p1.parent.glob("*.pdf"))) == 2


def test_recon_summary_counts_status_column():
    from server import pipeline
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "reconciliation.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=["file", "status"])
            w.writeheader()
            w.writerow({"file": "a.pdf", "status": "VERIFIED"})
            w.writerow({"file": "b.pdf", "status": "VERIFIED"})
            w.writerow({"file": "c.pdf", "status": "REVIEW"})
        assert pipeline.recon_summary(d) == {"VERIFIED": 2, "REVIEW": 1}


def test_recon_summary_missing_file_is_empty():
    from server import pipeline
    with tempfile.TemporaryDirectory() as d:
        assert pipeline.recon_summary(d) == {}
