#!/usr/bin/env python3
"""Emit web/src/lib/data/app.json for the Svelte PWA.

Thin exporter: reuses dashboard.load() + insights.compute() so all extraction,
categorization, and leak logic stays in the frozen parse.py/insights.py. Adds only
a `committed` block (recurring monthly obligations) for the headroom hero.

FIELD NAME NOTE: insights.compute() recs use:
  - r["type"]      (not "kind") to distinguish sub/creep/oneoff
  - r["rmMonthly"] (not "monthly") for per-sub monthly price
  - r["stale"]     (bool) for staleness flag
  installments[] use:
  - p["monthly"]   for monthly charge
  - p["name"]      for display name
"""
import csv
import json
import os
from collections import Counter

import dashboard
import insights

OUT = os.path.join("web", "src", "lib", "data", "app.json")


def build_committed(insights_out):
    """Sum recurring monthly obligations: active subs + installments.

    Uses "type" (not "kind") and "rmMonthly" (not "monthly") to match the
    real insights.compute() output shape. The exported items use "kind" as
    the field name so Svelte consumers get a consistent, clean contract.
    """
    inst = insights_out.get("installments", []) or []
    active_inst = [p for p in inst if not p.get("ended", False)]
    inst_total = round(sum(float(p.get("monthly", 0) or 0) for p in active_inst), 2)
    items = [{"name": p.get("name", "?"), "monthly": round(float(p.get("monthly", 0) or 0), 2),
              "kind": "installment"} for p in active_inst]

    subs_total = 0.0
    sub_cats: list[str] = []
    for r in insights_out.get("recs", []) or []:
        # insights.py uses r["type"] == "sub" (not "kind")
        # and r["rmMonthly"] for the per-sub monthly price (not "monthly")
        if r.get("type") == "sub" and not r.get("stale"):
            m = round(float(r.get("rmMonthly", 0) or 0), 2)
            subs_total += m
            items.append(
                {
                    "name": r.get("merchant", r.get("name", "?")),
                    "monthly": m,
                    "kind": "sub",
                }
            )
            cat = r.get("cat")
            if cat and cat not in sub_cats:
                sub_cats.append(cat)
    subs_total = round(subs_total, 2)
    sub_cats.sort()

    return {
        "monthly": round(inst_total + subs_total, 2),
        "subs": subs_total,
        "installments": inst_total,
        "subCats": sub_cats,
        "items": items,
    }


def build_cycles(csv_path="transactions.csv"):
    """Map each card -> its statement closing day (1-31).

    Day is the mode of statement_date day-of-month per card; ties break to the
    day of the most recent statement_date. Keyed "<bank>·<last4>" to match rows[].c.
    """
    dates: dict[str, list[str]] = {}
    with open(csv_path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            key = f"{r['bank']}·{r['card_last4']}"
            sd = (r.get("statement_date") or "").strip()
            if sd:
                dates.setdefault(key, []).append(sd)
    cycles: dict[str, int] = {}
    for key, ds in dates.items():
        days = [int(d.split("-")[2]) for d in ds]
        cnt = Counter(days)
        top = max(cnt.values())
        tied = {d for d, c in cnt.items() if c == top}
        # tie-break: day of the latest statement_date among tied days
        latest = max(d for d in ds if int(d.split("-")[2]) in tied)
        cycles[key] = int(latest.split("-")[2])
    return cycles


def build_payload(rows, insights_out, cycles=None):
    """Assemble the full app.json payload from transaction rows + insights output."""
    months = sorted({r["m"] for r in rows})
    cards = sorted({r["c"] for r in rows})
    # Only include cats that actually appear in the data, in COLORS order
    cats = [c for c in dashboard.COLORS if any(r["g"] == c for r in rows)]
    # dashboard.NON_SPEND is a list; pass it through as-is
    return {
        "rows": rows,
        "months": months,
        "cards": cards,
        "cats": cats,
        "nonSpend": dashboard.NON_SPEND,  # a list (Svelte: use .includes())
        "colors": dashboard.COLORS,
        "catIcon": dashboard.CAT_ICON,
        "icons": dashboard.MDI,
        "range": f"{months[0]} → {months[-1]}" if months else "",
        "recs": insights_out.get("recs", []),
        "installments": insights_out.get("installments", []),
        "transfers": insights_out.get("transfers", []),
        "committed": build_committed(insights_out),
        "cycles": cycles or {},
    }


def main():
    rows = dashboard.load()
    insights_out = insights.compute(rows)
    cycles = build_cycles()
    payload = build_payload(rows, insights_out, cycles)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))
    print(
        f"wrote {OUT}: {len(rows)} txns, "
        f"committed RM{payload['committed']['monthly']}/mo "
        f"(subs RM{payload['committed']['subs']}, "
        f"installments RM{payload['committed']['installments']})"
    )


if __name__ == "__main__":
    main()
