"""Tests for export_data.py.

NOTE: insights.py uses "type" (not "kind") to distinguish rec types,
and "rmMonthly" (not "monthly") for per-sub price.
The fixture below reflects the REAL insights.compute() field names.
"""
import csv
import os
import tempfile
import export_data
from export_data import build_bills


def _write_recon(path, rows):
    cols = ['file', 'bank', 'smonth', 'sdate', 'due', 'n', 'prev', 'debit',
            'credit', 'expected', 'cur', 'diff', 'status']
    with open(path, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})


def test_build_committed_sums_subs_and_installments():
    # Fixture matches REAL insights.compute() output shape:
    #   recs[].type (not .kind), recs[].rmMonthly (not .monthly), recs[].stale
    #   installments[].monthly, installments[].name, installments[].ended
    insights_out = {
        "installments": [
            {"name": "Senheng -36M", "monthly": 460.0},
            {"name": "OldPlan -12M", "monthly": 200.0, "ended": True},
        ],
        "recs": [
            {"type": "sub", "merchant": "Claude.ai", "rmMonthly": 180.0, "stale": False, "cat": "Subscriptions"},
            {"type": "sub", "merchant": "OldGym", "rmMonthly": 99.0, "stale": True},
            {"type": "creep", "cat": "Telco/Utilities"},
        ],
    }
    c = export_data.build_committed(insights_out)
    assert c["installments"] == 460.0    # ended 200 excluded
    assert c["subs"] == 180.0            # stale sub excluded
    assert c["monthly"] == 640.0
    kinds = sorted(i["kind"] for i in c["items"])
    assert kinds == ["installment", "sub"]
    # ended plan must not appear in items
    assert not any(i["name"] == "OldPlan -12M" for i in c["items"])
    # subCats must include the active sub's category
    assert "subCats" in c, "subCats key missing"
    assert c["subCats"] == ["Subscriptions"], f"unexpected subCats: {c['subCats']}"


def test_payload_has_required_keys():
    payload = export_data.build_payload(
        rows=[{"c": "maybank·3829", "m": "2026-06", "g": "F&B", "a": 12.0, "t": 0, "d": "x"}],
        insights_out={"installments": [], "recs": []},
    )
    for k in ["rows", "months", "cards", "cats", "colors", "catIcon", "icons", "recs", "installments", "transfers", "range", "nonSpend", "committed", "cycles", "bills"]:
        assert k in payload
    assert payload["months"] == ["2026-06"]
    assert payload["committed"]["monthly"] == 0.0


def test_build_cycles_modes_the_statement_day(tmp_path):
    csv_path = tmp_path / "t.csv"
    csv_path.write_text(
        "bank,card_last4,statement_date\n"
        "alliance,4963,2025-06-16\n"
        "alliance,4963,2025-07-16\n"
        "alliance,4963,2025-08-16\n"
        "sc,3829,2025-06-19\n"
        "sc,3829,2025-07-20\n"   # tie-break: 19 appears twice -> 19 wins by count
        "sc,3829,2025-08-19\n",
        encoding="utf-8",
    )
    cy = export_data.build_cycles(str(csv_path))
    assert cy["alliance·4963"] == 16
    assert cy["sc·3829"] == 19


def test_build_cycles_tie_breaks_to_latest(tmp_path):
    csv_path = tmp_path / "t.csv"
    csv_path.write_text(
        "bank,card_last4,statement_date\n"
        "x,1,2025-06-10\n"
        "x,1,2025-07-20\n",   # 1-1 tie on count -> latest date's day (20) wins
        encoding="utf-8",
    )
    cy = export_data.build_cycles(str(csv_path))
    assert cy["x·1"] == 20


def test_payload_includes_cycles():
    payload = export_data.build_payload(
        rows=[{"c": "maybank·3829", "m": "2026-06", "g": "F&B", "a": 12.0, "t": 0, "d": "x"}],
        insights_out={"installments": [], "recs": []},
        cycles={"maybank·3829": 28},
    )
    assert payload["cycles"] == {"maybank·3829": 28}


def test_build_bills_picks_newest_non_duplicate_per_bank():
    rows = [
        {'bank': 'cimb', 'smonth': '2026-04', 'cur': '2092.13', 'due': '2026-05-11', 'status': 'VERIFIED'},
        {'bank': 'cimb', 'smonth': '2026-03', 'cur': '1500.00', 'due': '2026-04-11', 'status': 'VERIFIED'},
        {'bank': 'cimb', 'smonth': '2026-04', 'cur': '2092.13', 'due': '2026-05-11', 'status': 'DUPLICATE'},
        {'bank': 'sc',   'smonth': '2026-06', 'cur': '880.50',  'due': '2026-07-09', 'status': 'VERIFIED'},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'reconciliation.csv')
        _write_recon(p, rows)
        bills = build_bills(p)

    by = {b['bank']: b for b in bills}
    assert set(by) == {'cimb', 'sc'}, by
    assert by['cimb']['statement_month'] == '2026-04'
    assert by['cimb']['current_balance'] == 2092.13
    assert by['cimb']['payment_due_date'] == '2026-05-11'
    assert by['cimb']['minimum_payment'] is None
    assert by['sc']['payment_due_date'] == '2026-07-09'


def test_build_bills_handles_null_due():
    rows = [{'bank': 'hsbc', 'smonth': '2026-04', 'cur': '100.00', 'due': '', 'status': 'VERIFIED'}]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'reconciliation.csv')
        _write_recon(p, rows)
        bills = build_bills(p)
    assert bills[0]['payment_due_date'] is None


if __name__ == "__main__":
    test_build_committed_sums_subs_and_installments()
    test_payload_has_required_keys()
    import pathlib
    with tempfile.TemporaryDirectory() as d:
        test_build_cycles_modes_the_statement_day(pathlib.Path(d))
        test_build_cycles_tie_breaks_to_latest(pathlib.Path(d))
    test_payload_includes_cycles()
    test_build_bills_picks_newest_non_duplicate_per_bank()
    test_build_bills_handles_null_due()
    print("OK")
