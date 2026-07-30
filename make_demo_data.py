#!/usr/bin/env python3
"""Generate an obviously-fake demo dataset so the project runs without real statements.

Writes the two CSVs parse.py produces — transactions.csv and reconciliation.csv —
and then gets out of the way: insights.py, dashboard.py and export_data.py all read
those files and run completely unchanged. That is deliberate. The generator feeds the
existing pipeline; it is not a second code path through it.

    python make_demo_data.py
    python insights.py && python export_data.py && python dashboard.py

EVERYTHING HERE IS INVENTED. Merchants, cards, amounts, the cardholder — none of it
is real, lightly-edited or otherwise. Card last-fours are 0001-0007 so a glance tells
you it is synthetic. Banks are the six real filename keys because that is what the
parser dispatches on.

The data is shaped to exercise every insights.py detector, so the Cuts view has
something in it:

  - two live subscriptions and one cancelled (stale) one
  - a tier-stepped subscription (price rises mid-history, reported at its CURRENT
    price — the "recent window" rule)
  - an installment plan carrying a printed ":NN/MM" counter, plus its ":0/MM"
    principal memo, so exact progress and memo-dropping both get hit
  - a balance transfer
  - a category that visibly creeps over the last three months
  - a big one-off in the newest month
  - a refund credit that nets off its category
  - monthly cashback credits

Months are anchored to the current month, so the newest statement is always recent
and the bills panel has something live to show. Amounts are jittered from a seeded
RNG, so a given --seed reproduces byte-for-byte within a day.
"""
import argparse
import csv
import random
from datetime import date, timedelta

TXN_FIELDS = ["bank", "card_last4", "statement_month", "statement_date", "post_date",
              "txn_date", "description", "amount", "type", "category", "source_file"]
RECON_FIELDS = ["file", "bank", "smonth", "sdate", "due", "n", "prev", "debit",
                "credit", "expected", "cur", "diff", "status"]

# bank -> (last4s on the statement, statement closing day, opening balance)
# cimb/rhb/alliance carry several cards per statement, matching the real parser.
BANKS = {
    "maybank":  (["0001"], 18, 1850.00),
    "cimb":     (["0002", "0003"], 5, 3120.00),
    "sc":       (["0004"], 22, 940.00),
    "alliance": (["0005"], 11, 610.00),
    "hsbc":     (["0006"], 27, 2275.00),
    "rhb":      (["0007"], 8, 480.00),
}

# Recurring everyday spend: (bank, last4, description, category, base amount, per-month count)
REGULARS = [
    ("maybank", "0001", "DEMO MART GROCERS",        "Groceries",    142.00, 3),
    ("cimb",    "0002", "PASAR SEGAR DEMO",         "Groceries",     88.50, 2),
    ("hsbc",    "0006", "PETROL STESEN DEMO",       "Vehicle",      120.00, 3),
    ("rhb",     "0007", "TEKSI DEMO RIDE",          "Vehicle",       23.00, 4),
    ("sc",      "0004", "KEDAI KOPI DEMO",          "F&B",           31.00, 4),
    ("alliance","0005", "APOTEK DEMO PHARMACY",     "Health/Insurance", 64.00, 1),
    ("cimb",    "0003", "DEMO DEPT STORE",          "Shopping",     210.00, 1),
]

# Subscriptions. Only Subscriptions / Telco-Utilities are eligible (insights.SUB_CATS).
# (bank, last4, desc, category, price, first month index, last month index or None)
SUBS = [
    ("sc",      "0004", "DEMOFLIX STREAMING", "Subscriptions",    45.90, 0, None),
    ("maybank", "0001", "PIXELTUNES MUSIC",   "Subscriptions",    19.90, 0, -4),
    ("cimb",    "0002", "NOVATEL FIBRE",      "Telco/Utilities",  99.00, 0, None),
]
NOVATEL_NEW_PRICE = 149.00      # tier step for the last 4 months

CREEP_CAT = "F&B"
CREEP_MERCHANTS = [("rhb", "0007", "DEMO BUBBLE TEA"), ("rhb", "0007", "WARUNG DEMO NASI")]


def month_key(anchor, back):
    y, m = anchor.year, anchor.month - back
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def _day(ym, day):
    """ISO date for `day` of month `ym`, clamped to the month's last day."""
    y, m = map(int, ym.split("-"))
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return min(date(y, m, day), nxt - timedelta(days=1)).isoformat()


def build(n_months, seed):
    rng = random.Random(seed)
    anchor = date.today().replace(day=1)
    months = [month_key(anchor, i) for i in range(n_months - 1, -1, -1)]
    last3, newest = set(months[-3:]), months[-1]
    txns = []

    def add(bank, last4, ym, desc, cat, amount, credit=False, excl=False):
        txns.append({
            "bank": bank, "card_last4": last4, "statement_month": ym,
            "statement_date": _day(ym, BANKS[bank][1]),
            "post_date": _day(ym, rng.randint(1, 27)), "txn_date": _day(ym, rng.randint(1, 27)),
            "description": desc, "amount": round(amount, 2),
            "type": "credit" if credit else "debit", "category": cat,
            "source_file": f"{bank}_demo_{ym}.pdf", "_excl": excl,
        })

    def jitter(base, pct=0.18):
        return max(1.0, base * (1 + rng.uniform(-pct, pct)))

    for i, ym in enumerate(months):
        for bank, last4, desc, cat, base, per_month in REGULARS:
            for _ in range(per_month):
                add(bank, last4, ym, desc, cat, jitter(base))

        for bank, last4, desc, cat, price, first, last in SUBS:
            end = len(months) + last if last is not None else len(months)
            if not (first <= i < end):
                continue
            # NOVATEL steps up for the last 4 months: find_subs measures stability on the
            # recent window, so this stays a sub and is reported at the new price.
            p = NOVATEL_NEW_PRICE if (desc == "NOVATEL FIBRE" and i >= len(months) - 4) else price
            add(bank, last4, ym, desc, cat, p)

        # a category that quietly creeps: flat baseline, then a step up over the last 3 months
        for bank, last4, desc in CREEP_MERCHANTS:
            n = 5 if ym in last3 else 3
            for _ in range(n):
                add(bank, last4, ym, desc, CREEP_CAT, jitter(24.0 if ym in last3 else 17.0))

        # 12-month purchase plan on cimb, with the bank's printed counter.
        # Month 0 posts the deferred principal as a ":0/12" memo (billed later) — insights
        # must drop it rather than count it as a monthly charge.
        if i == 0:
            add("cimb", "0002", ym, "INSTL DEMOTECH LAPTOP-12M :0/12", "Installments/BT", 4800.00, excl=True)
        if 1 <= i <= 12:
            add("cimb", "0002", ym, f"INSTL DEMOTECH LAPTOP-12M :{i:02d}/12", "Installments/BT", 400.00)

        # a balance transfer running alongside it
        if 2 <= i <= min(len(months) - 1, 25):
            add("maybank", "0001", ym, f"BALANCE TRANSFER DEMO-24M :{i - 1:02d}/24", "Installments/BT", 312.50)

        # cashback: a credit in Rebate/Cashback, invisible to every spend chart by design
        for bank, (last4s, _, _) in BANKS.items():
            add(bank, last4s[0], ym, "CASHBACK REBATE DEMO", "Rebate/Cashback", jitter(18.0), credit=True)

    # one big one-off in the newest month. Merchant appears in exactly one month, so it
    # survives the recurrence guard that stops recurring insurance/SaaS masquerading as a splurge.
    # Deliberately in Travel, which carries no regular monthly spend: dropped into a category
    # with a small steady baseline it would ALSO trip find_creep, and one purchase showing up
    # as two different recommendations is a false positive, not a richer demo.
    add("hsbc", "0006", newest, "DEMO AIRLINES SKYFARE", "Travel", 4200.00)

    # a refund: a credit under a merchant category, which nets off that category's spend
    if len(months) >= 2:
        add("sc", "0004", months[-2], "SKYVIEW DEMO HOTEL -REV", "Travel", 980.00, credit=True)
        add("sc", "0004", months[-3 if len(months) > 2 else -2], "SKYVIEW DEMO HOTEL", "Travel", 980.00)

    # bill payments, sized to keep the running balance sane rather than to reconcile —
    # the recon rows below are derived from whatever these actually come out as.
    for ym in months:
        for bank, (last4s, _, _) in BANKS.items():
            paid = sum(t["amount"] for t in txns
                       if t["bank"] == bank and t["statement_month"] == ym
                       and t["type"] == "debit" and not t["_excl"])
            add(bank, last4s[0], ym, "PAYMENT - THANK YOU DEMO", "Transfers/Payments",
                paid * rng.uniform(0.80, 0.95), credit=True)

    return months, txns


def reconcile(months, txns):
    """Derive reconciliation rows from the transactions, so the demo genuinely balances.

    prev + debit - credit = expected = cur, diff 0, status VERIFIED — the same check
    parse.py runs against the bank's own printed figures. Excluded contra memos (the
    ":0/MM" deferred principal) are left out of the debit total, exactly as parse.py does.
    """
    recon, prev = [], {b: v[2] for b, v in BANKS.items()}
    for ym in months:
        for bank, (_, close_day, _) in BANKS.items():
            rows = [t for t in txns if t["bank"] == bank and t["statement_month"] == ym]
            if not rows:
                continue
            debit = sum(t["amount"] for t in rows if t["type"] == "debit" and not t["_excl"])
            credit = sum(t["amount"] for t in rows if t["type"] == "credit")
            p = prev[bank]
            cur = round(p + debit - credit, 2)
            sdate = _day(ym, close_day)
            recon.append({
                "file": f"{bank}_demo_{ym}.pdf", "bank": bank, "smonth": ym, "sdate": sdate,
                "due": (date.fromisoformat(sdate) + timedelta(days=20)).isoformat(),
                "n": len(rows), "prev": round(p, 2), "debit": round(debit, 2),
                "credit": round(credit, 2), "expected": cur, "cur": cur,
                "diff": 0.0, "status": "VERIFIED",
            })
            prev[bank] = cur
    return recon


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--months", type=int, default=14,
                    help="how many months to generate (>= 6, or creep detection has nothing to compare)")
    ap.add_argument("--seed", type=int, default=7, help="RNG seed; same seed reproduces the same amounts")
    a = ap.parse_args()
    if a.months < 6:
        ap.error("--months must be at least 6: find_creep compares the last 3 months against the prior 3")

    months, txns = build(a.months, a.seed)
    recon = reconcile(months, txns)

    with open("transactions.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=TXN_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(txns, key=lambda t: (t["statement_month"], t["bank"], t["post_date"])))
    with open("reconciliation.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=RECON_FIELDS)
        w.writeheader()
        w.writerows(recon)

    print(f"wrote transactions.csv ({len(txns)} synthetic txns) and "
          f"reconciliation.csv ({len(recon)} statements, all VERIFIED)")
    print(f"months {months[0]} → {months[-1]}, {len(BANKS)} banks, "
          f"{sum(len(v[0]) for v in BANKS.values())} cards — ALL DATA IS FAKE")
    print("next: python insights.py && python export_data.py && python dashboard.py")


if __name__ == "__main__":
    main()
