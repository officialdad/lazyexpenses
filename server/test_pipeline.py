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
