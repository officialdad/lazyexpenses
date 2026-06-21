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
            {"type": "sub", "merchant": "Claude.ai", "rmMonthly": 180.0, "stale": False},
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


def test_payload_has_required_keys():
    payload = export_data.build_payload(
        rows=[{"c": "maybank·3829", "m": "2026-06", "g": "F&B", "a": 12.0, "t": 0, "d": "x"}],
        insights_out={"installments": [], "recs": []},
    )
    for k in ["rows", "months", "cards", "cats", "colors", "catIcon", "icons", "recs", "installments", "transfers", "range", "nonSpend", "committed"]:
        assert k in payload
    assert payload["months"] == ["2026-06"]
    assert payload["committed"]["monthly"] == 0.0


if __name__ == "__main__":
    test_build_committed_sums_subs_and_installments()
    test_payload_has_required_keys()
    print("OK")
