"""Guard: export_data payload matches dashboard.py payload on shared keys."""
import dashboard, insights, export_data


def main():
    rows = dashboard.load()
    legacy_keys = {"rows", "months", "cards", "cats", "nonSpend", "colors", "catIcon", "icons", "range"}
    payload = export_data.build_payload(rows, insights.compute(rows))
    months = sorted({r["m"] for r in rows})
    assert payload["months"] == months, "month set drift"
    assert set(payload["cards"]) == {r["c"] for r in rows}, "card set drift"
    assert "committed" in payload and payload["committed"]["monthly"] >= 0
    for k in legacy_keys:
        assert k in payload, f"missing legacy key {k}"
    print(f"PARITY OK: {len(rows)} rows, {len(months)} months, committed RM{payload['committed']['monthly']}/mo")


if __name__ == "__main__":
    main()
