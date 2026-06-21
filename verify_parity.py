"""Guard: export_data payload matches dashboard.py payload on shared keys."""
import dashboard, insights, export_data


def main():
    rows = dashboard.load()
    legacy_keys = {"rows", "months", "cards", "cats", "nonSpend", "colors", "catIcon", "icons", "range"}
    insights_out = insights.compute(rows)
    payload = export_data.build_payload(rows, insights_out)
    months = sorted({r["m"] for r in rows})
    assert payload["months"] == months, "month set drift"
    assert set(payload["cards"]) == {r["c"] for r in rows}, "card set drift"
    assert "committed" in payload and payload["committed"]["monthly"] >= 0
    for k in legacy_keys:
        assert k in payload, f"missing legacy key {k}"

    # Guard: committed.subs and committed.installments must match
    # what we can re-derive directly from insights_out (catches future field-name drift)
    expected_subs = round(
        sum(
            float(r.get("rmMonthly", 0) or 0)
            for r in (insights_out.get("recs") or [])
            if r.get("type") == "sub" and not r.get("stale")
        ),
        2,
    )
    expected_inst = round(
        sum(
            float(p.get("monthly", 0) or 0)
            for p in (insights_out.get("installments") or [])
            if not p.get("ended", False)
        ),
        2,
    )
    committed = payload["committed"]
    assert committed["subs"] == expected_subs, (
        f"committed.subs mismatch: payload={committed['subs']} expected={expected_subs}"
    )
    assert committed["installments"] == expected_inst, (
        f"committed.installments mismatch: payload={committed['installments']} expected={expected_inst}"
    )
    assert "subCats" in committed, "committed.subCats missing from payload"
    assert isinstance(committed["subCats"], list), "committed.subCats must be a list"

    print(
        f"PARITY OK: {len(rows)} rows, {len(months)} months, "
        f"committed RM{committed['monthly']}/mo "
        f"(subs RM{committed['subs']}, installments RM{committed['installments']}, "
        f"subCats={committed['subCats']})"
    )


if __name__ == "__main__":
    main()
