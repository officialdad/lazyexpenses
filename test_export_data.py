"""Tests for export_data.py.

NOTE: insights.py uses "type" (not "kind") to distinguish rec types,
and "rmMonthly" (not "monthly") for per-sub price.
The fixture below reflects the REAL insights.compute() field names.
"""
import export_data


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
    for k in ["rows", "months", "cards", "cats", "colors", "catIcon", "icons", "recs", "installments", "transfers", "range", "nonSpend", "committed", "cycles"]:
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


if __name__ == "__main__":
    test_build_committed_sums_subs_and_installments()
    test_payload_has_required_keys()
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        test_build_cycles_modes_the_statement_day(pathlib.Path(d))
        test_build_cycles_tie_breaks_to_latest(pathlib.Path(d))
    test_payload_includes_cycles()
    print("OK")
