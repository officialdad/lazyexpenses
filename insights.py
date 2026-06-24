#!/usr/bin/env python3
"""Deterministic leak detection over transactions.csv -> ranked recommendations.

Pure stdlib, offline, no LLM. Imported by dashboard.py (embeds recs in the page)
and runnable standalone (writes recommendations.csv for build-time tuning).
"""
import re
from collections import Counter
from statistics import mean, median, pstdev

NON_SPEND = {"Installments/BT", "Transfers/Payments", "Rebate/Cashback"}
SUBS_SKIP = NON_SPEND | {"Health/Insurance", "Charity"}

# CHANGE 1: allowlist for subscription detection
SUB_CATS = {"Subscriptions", "Telco/Utilities"}

INSTALLMENT_MERCHANTS = {"SENHENG", "HOME PRODUCT"}

def _is_installment(merchant):
    return any(k in merchant for k in INSTALLMENT_MERCHANTS)

def _ev_cat(evidence):
    gs = [e["g"] for e in evidence if isinstance(e, dict) and "g" in e]
    return Counter(gs).most_common(1)[0][0] if gs else ""

_TRAIL = re.compile(r"^(?:\d+|(?=.*\d)[\dA-Z*#/.:\-]{3,})$")  # pure digits OR token containing a digit + digits/uppercase/punct/colon, 3+ chars (colon strips the monthly ":NN/MM" installment ratio so it doesn't break merchant recurrence grouping)


def norm_merchant(desc):
    s = re.sub(r"\s+", " ", desc.upper()).strip()
    toks = s.split(" ")
    while toks and _TRAIL.fullmatch(toks[-1]):
        toks.pop()
    return " ".join(toks)


def find_subs(rows):
    by = {}
    for r in rows:
        # CHANGE 1: use SUB_CATS allowlist instead of SUBS_SKIP denylist
        if r["t"] != 0 or r["g"] not in SUB_CATS or _is_bnpl(r["d"]):
            continue
        by.setdefault(norm_merchant(r["d"]), []).append(r)
    out = []
    for merchant, rs in by.items():
        months = {r["m"] for r in rs}
        if len(months) < 4:
            continue
        if len(rs) / len(months) > 1.3:        # high-frequency -> not a sub
            continue
        rs_sorted = sorted(rs, key=lambda r: r["m"])
        recent = [r["a"] for r in rs_sorted[-4:]]       # last up-to-4 charges
        m = mean(recent)
        if m <= 0:
            continue
        cv = (pstdev(recent) / m) if len(recent) > 1 else 0.0
        if cv >= 0.15:                          # unstable recent price -> not a sub
            continue
        med = median(recent)                            # current price
        out.append({
            "type": "sub", "merchant": merchant, "rmMonthly": round(med, 2),
            "months": len(months), "last": max(months), "rmAnnual": round(med * 12, 2),
            "evidence": rs_sorted,
        })
    return out


def _net(rows, cat, month):
    return sum((r["a"] if r["t"] == 0 else -r["a"])
               for r in rows if r["g"] == cat and r["m"] == month)


def _cat_merchant_breakdown(rows, g, months):
    prev_m, last_m = set(months[-6:-3]), set(months[-3:])
    by = {}
    for r in rows:
        if r["g"] != g:
            continue
        d = by.setdefault(norm_merchant(r["d"]), {"prev": 0.0, "recent": 0.0})
        v = r["a"] if r["t"] == 0 else -r["a"]
        if r["m"] in last_m:
            d["recent"] += v
        elif r["m"] in prev_m:
            d["prev"] += v
    out = [{"merchant": k, "prev": round(x["prev"], 2), "recent": round(x["recent"], 2),
            "delta": round(x["recent"] - x["prev"], 2)} for k, x in by.items()]
    out.sort(key=lambda d: -d["delta"])
    return out[:6]


def find_creep(rows, months):
    if len(months) < 6:
        return []
    cats = {r["g"] for r in rows if r["g"] not in NON_SPEND}
    out = []
    for g in cats:
        ser = [_net(rows, g, m) for m in months]
        prev3, last3 = ser[-6:-3], ser[-3:]
        pm = mean(prev3)
        if pm <= 50:                       # floor: ignore near-zero baselines
            continue
        lm = mean(last3)
        if lm / pm <= 1.2:                 # not creeping enough
            continue
        out.append({
            "type": "creep", "cat": g, "prevAvg": round(pm, 2), "recentAvg": round(lm, 2),
            "rmMonthly": round(lm - pm, 2), "rmAnnual": round((lm - pm) * 12, 2),
            "evidence": _cat_merchant_breakdown(rows, g, months),
        })
    return out


_OO_EXCLUDE = {"Installments/BT", "Transfers/Payments"}

_BNPL = re.compile(r"SPAYLATER|REPAYMENT")
def _is_bnpl(d):
    return bool(_BNPL.search(d.upper()))


def find_oneoffs(rows, months):
    disc = [r for r in rows if r["t"] == 0 and r["g"] not in NON_SPEND and not _is_bnpl(r["d"])]
    if not disc:
        return []
    amts = sorted(r["a"] for r in disc)
    p95 = amts[min(len(amts) - 1, int(len(amts) * 0.95))]
    cat_amts = {}
    for r in disc:
        cat_amts.setdefault(r["g"], []).append(r["a"])
    cat_med = {g: median(v) for g, v in cat_amts.items()}
    rec_months = {}
    for r in disc:
        rec_months.setdefault(norm_merchant(r["d"]), set()).add(r["m"])
    recent = set(months[-2:])
    out = []
    for r in rows:
        if r["t"] != 0 or r["g"] in _OO_EXCLUDE or r["m"] not in recent or _is_bnpl(r["d"]):
            continue
        if len(rec_months.get(norm_merchant(r["d"]), ())) >= 2:
            continue
        med = cat_med.get(r["g"], r["a"])
        if r["a"] > p95 or r["a"] > 3 * med:
            out.append({
                "type": "oneoff", "merchant": r["d"], "amount": round(r["a"], 2),
                "cat": r["g"], "month": r["m"], "c": r["c"],
                "mult": round(r["a"] / med, 1) if med else 0.0, "rmAnnual": round(r["a"], 2),
            })
    out.sort(key=lambda o: -o["amount"])
    return out


# === CHANGE 2: find_installments ===

_BT_MARKERS = ("BALANCE TRANSFER", "BAL TRANSFER", "BALANCE TFER", "SMART MOVE", "T/F ER IN")

def _is_bt(desc):
    u = desc.upper()
    return any(m in u for m in _BT_MARKERS)

def _is_memo(desc):
    return bool(re.search(r"\b0/\d+\b", desc)) or "T/F ER IN" in desc.upper()

def _plan_key(desc):
    s = re.sub(r"\s+", " ", desc.upper()).strip()
    s = re.sub(r"^INSTL\s+", "", s)
    s = re.sub(r"\s*:.*$", "", s)              # strip trailing colon/ratio segment
    s = re.sub(r"\s+\d+\s+OF\s+\d+$", "", s)   # strip " NN OF MM"
    s = re.sub(r"\s+\d+$", "", s)              # strip trailing counter
    return s.strip()

def _disp(key):
    s = re.sub(r"^[%\s]+", "", key)            # leading %% / spaces
    s = re.sub(r"[\s:\-]+$", "", s)            # trailing - : spaces
    return s.strip() or key

def _term_from(descs):
    # Plan term from the name suffix ('-NNM' / 'E36'); fallback used only when the bank
    # doesn't print a trustworthy per-installment counter (see _counter).
    for d in descs:
        u = d.upper()
        m = re.search(r"-(\d+)\s*M(?:TH)?\b", u) or re.search(r"\bE(\d+)\b", u)
        if m:
            return int(m.group(1))
    return None

def _counter(descs):
    """(term, progress) from the bank's printed installment counter — ':NN/MM'
    (maybank/cimb/rhb) or 'NN OF MM' (alliance) — or None when the counters aren't a
    trustworthy current/total series. Guard: the total (denominator) must be CONSTANT
    across the plan's months and the current (numerator) must not exceed it. This
    rejects reversed 'total/current' layouts, stray colon-dates, and other unseen
    formats — those fall back to the seen-count estimate, never a confident wrong
    number. Progress is the max current seen (memo rows post 0, harmlessly dominated)."""
    pairs = []
    for d in descs:
        u = d.upper()
        pairs += [(int(a), int(b)) for a, b in re.findall(r":\s*(\d{1,3})/(\d{2,3})\b", u)]
        pairs += [(int(a), int(b)) for a, b in re.findall(r"\b(\d+)\s+OF\s+(\d+)\b", u)]
    totals = {b for _, b in pairs}
    if len(totals) != 1:                 # no counter, or term not constant -> distrust
        return None
    term = totals.pop()
    prog = max(a for a, _ in pairs)
    return (term, prog) if prog <= term else None

def _add_months(ym, n):
    y, mo = map(int, ym.split("-"))
    mo += n
    y += (mo - 1) // 12
    mo = (mo - 1) % 12 + 1
    return f"{y:04d}-{mo:02d}"

def find_installments(rows):
    months = sorted({r["m"] for r in rows})
    newest_idx = len(months) - 1
    midx = {m: i for i, m in enumerate(months)}
    # source: Installments/BT category OR override merchants (mis-categorized retail plans)
    src = [r for r in rows if r["t"] == 0 and
           (r["g"] == "Installments/BT" or any(k in norm_merchant(r["d"]) for k in INSTALLMENT_MERCHANTS))]
    plan_grp, xfer_grp = {}, {}
    for r in src:
        (xfer_grp if _is_bt(r["d"]) else plan_grp).setdefault(_plan_key(r["d"]), []).append(r)

    def _summ(grp):
        charge = [r for r in grp if not _is_memo(r["d"])]
        if not charge:
            return None
        last = max(r["m"] for r in charge)
        monthly = round(sum(r["a"] for r in charge if r["m"] == last), 2)
        seen = len({r["m"] for r in charge})
        gap = newest_idx - midx[last]
        return charge, last, monthly, seen, gap

    plans = []
    for key, grp in plan_grp.items():
        s = _summ(grp)
        if not s:
            continue
        charge, last, monthly, seen, gap = s
        cnt = _counter([r["d"] for r in grp])
        if cnt:                                          # exact from the bank's counter
            term, prog = cnt
            remaining, est = max(0, term - prog), False
        else:                                            # estimate from payments seen
            term, prog = _term_from([r["d"] for r in grp]), None
            remaining, est = (max(0, term - seen), True) if term is not None else (None, False)
        end_month = _add_months(last, remaining) if remaining is not None else None
        remain_bal = round(monthly * remaining, 2) if remaining is not None else None
        plans.append({"type": "installment", "name": _disp(key), "cat": "Installments/BT",
                      "monthly": monthly, "term": term, "progressN": prog, "seen": seen,
                      "last": last, "lastGap": gap, "ended": gap >= 2,
                      "remaining": remaining, "endMonth": end_month, "remainBal": remain_bal,
                      "est": est, "evidence": sorted(charge, key=lambda r: r["m"])})
    plans.sort(key=lambda p: -p["monthly"])

    transfers = []
    for key, grp in xfer_grp.items():
        s = _summ(grp)
        if not s:
            continue
        charge, last, monthly, seen, gap = s
        transfers.append({"type": "transfer", "name": _disp(key), "cat": "Installments/BT",
                          "monthly": monthly, "seen": seen, "last": last, "lastGap": gap,
                          "ended": gap >= 2, "paidInWindow": round(sum(r["a"] for r in charge), 2),
                          "evidence": sorted(charge, key=lambda r: r["m"])})
    transfers.sort(key=lambda t: -t["monthly"])
    return {"plans": plans, "transfers": transfers}


def compute(rows):
    months = sorted({r["m"] for r in rows})
    month_idx = {m: i for i, m in enumerate(months)}
    newest_idx = len(months) - 1
    subs = find_subs(rows)
    creep = find_creep(rows, months)
    oo = find_oneoffs(rows, months)
    recs = []
    # CHANGE 3: simplified subs loop — no installment branch, all subs are real subs
    for s in subs:
        last_gap = newest_idx - month_idx.get(s["last"], newest_idx)
        stale = last_gap >= 2
        cat = _ev_cat(s.get("evidence", []))
        hint = "Already cancelled?" if stale else "Cancel?"
        recs.append({**s, "severity": s["rmAnnual"], "cat": cat,
                     "title": f'{s["merchant"]} — RM{s["rmMonthly"]:.0f}/mo',
                     "line": f'{s["months"]} months running · RM{s["rmAnnual"]:.0f}/yr',
                     "hint": hint, "lastGap": last_gap, "stale": stale})
    for c in creep:
        recs.append({**c, "severity": c["rmAnnual"],
                     "rmMonthly": c["rmMonthly"],
                     "cat": c["cat"],
                     "title": f'{c["cat"]} — up RM{c["rmMonthly"]:.0f}/mo',
                     "line": f'RM{c["prevAvg"]:.0f} → RM{c["recentAvg"]:.0f}/mo · +RM{c["rmAnnual"]:.0f}/yr',
                     "hint": "Watch"})
    for o in oo:
        recs.append({**o, "severity": o["amount"], "rmMonthly": 0.0, "rmAnnual": o["amount"],
                     "cat": o["cat"],
                     "evidence": [o],
                     "title": f'{o["merchant"]} — RM{o["amount"]:.0f}',
                     "line": f'{o["cat"]} · {o["month"]} · {o["mult"]}× category norm',
                     "hint": "Planned?"})
    recs.sort(key=lambda r: -r["severity"])
    savings = sum(s["rmAnnual"] for s in subs) + sum(c["rmAnnual"] for c in creep)
    inst = find_installments(rows)
    return {"recs": recs, "savingsAnnual": round(savings, 2),
            "installments": inst["plans"], "transfers": inst["transfers"],
            "counts": {"sub": len([r for r in recs if r["type"] == "sub"]),
                       "installment": len(inst["plans"]), "transfer": len(inst["transfers"]),
                       "creep": len(creep), "oneoff": len(oo)}}


def _load(src="transactions.csv"):
    import csv
    rows = []
    with open(src, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            rows.append({"c": f"{r['bank']}·{r['card_last4']}", "m": r["statement_month"],
                         "g": r["category"], "a": round(float(r["amount"]), 2),
                         "t": 0 if r["type"] == "debit" else 1, "d": r["description"][:46]})
    return rows


if __name__ == "__main__":
    import csv, sys
    rows = _load()
    out = compute(rows)
    print(f"savings RM{out['savingsAnnual']:.0f}/yr  counts={out['counts']}")
    with open("recommendations.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["type", "title", "line", "rmMonthly", "rmAnnual", "hint"])
        for r in out["recs"]:
            w.writerow([r["type"], r["title"], r["line"],
                        r.get("rmMonthly", 0), r["rmAnnual"], r["hint"]])
    for r in out["recs"][:15]:
        print(f'  [{r["type"]:6}] {r["title"]}  ·  {r["line"]}')
