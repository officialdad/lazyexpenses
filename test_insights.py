import insights as I

def t_norm_merchant():
    assert I.norm_merchant("SPOTIFY AB 12345678") == "SPOTIFY AB"
    assert I.norm_merchant("spotify  ab") == "SPOTIFY AB"
    assert I.norm_merchant("NETFLIX.COM 4929-XXXX") == "NETFLIX.COM"
    assert I.norm_merchant("GRAB* RIDE 88231/02") == "GRAB* RIDE"
    assert I.norm_merchant("TESCO") == "TESCO"

def _row(c, m, g, a, t, d):
    return {"c": c, "m": m, "g": g, "a": a, "t": t, "d": d}

def t_find_subs():
    rows = []
    # a real subscription: same merchant, stable RM27, 4 distinct months, 1/mo
    for m in ["2026-01", "2026-02", "2026-03", "2026-04"]:
        rows.append(_row("cardA", m, "Subscriptions", 27.0, 0, "SPOTIFY AB 9001"))
    # variable, high-frequency merchant -> NOT a sub (groceries)
    for m in ["2026-01", "2026-02", "2026-03"]:
        for amt in (40.0, 130.0, 12.0):
            rows.append(_row("cardA", m, "Groceries", amt, 0, "TESCO 55"))
    subs = I.find_subs(rows)
    names = [s["merchant"] for s in subs]
    assert "SPOTIFY AB" in names, names
    assert "TESCO" not in names, names
    spo = next(s for s in subs if s["merchant"] == "SPOTIFY AB")
    assert spo["months"] == 4
    assert abs(spo["rmMonthly"] - 27.0) < 1e-6
    assert abs(spo["rmAnnual"] - 324.0) < 1e-6
    assert spo["last"] == "2026-04"

def t_find_creep():
    months = ["2025-10","2025-11","2025-12","2026-01","2026-02","2026-03"]
    rows = []
    # F&B creeping: prev3 ~100/mo, last3 ~200/mo  -> ratio 2.0, prev>50
    for m, amt in zip(months, [100,100,100,200,200,200]):
        rows.append(_row("cardA", m, "F&B", float(amt), 0, "MAMAK"))
    # Telco flat at 60/mo -> no creep
    for m in months:
        rows.append(_row("cardA", m, "Telco/Utilities", 60.0, 0, "MAXIS"))
    # tiny baseline category: prev3 avg < 50 floor -> skipped even if doubled
    for m, amt in zip(months, [10,10,10,30,30,30]):
        rows.append(_row("cardA", m, "Charity", float(amt), 0, "ZAKAT"))
    creep = I.find_creep(rows, months)
    cats = [c["cat"] for c in creep]
    assert "F&B" in cats, cats
    assert "Telco/Utilities" not in cats, cats
    assert "Charity" not in cats, cats          # below RM50 prev-avg floor
    fb = next(c for c in creep if c["cat"] == "F&B")
    assert abs(fb["rmMonthly"] - 100.0) < 1e-6   # 200 - 100
    assert abs(fb["rmAnnual"] - 1200.0) < 1e-6

def t_find_oneoffs():
    months = ["2026-01","2026-02"]
    rows = []
    # baseline small F&B debits to set a low category median / P95
    for i in range(20):
        rows.append(_row("cardA", "2026-01", "F&B", 20.0, 0, f"CAFE {i}"))
    # a big one-off in the latest month -> flagged
    rows.append(_row("cardA", "2026-02", "Shopping", 800.0, 0, "BIG TV STORE"))
    # an installment of similar size -> excluded
    rows.append(_row("cardA", "2026-02", "Installments/BT", 900.0, 0, "PLAN 03/12"))
    oo = I.find_oneoffs(rows, months)
    descs = [o["merchant"] for o in oo]
    assert any("BIG TV STORE" in d for d in descs), descs
    assert not any("PLAN" in d for d in descs), descs
    assert all("c" in o for o in oo), "one-offs must carry card field"

def t_compute():
    months = ["2025-10","2025-11","2025-12","2026-01","2026-02","2026-03"]
    rows = []
    for m in months:                                   # sub: RM50/mo stable
        rows.append(_row("cardA", m, "Subscriptions", 50.0, 0, "NETFLIX 77"))
    for m, amt in zip(months, [100,100,100,300,300,300]):   # creep F&B +200/mo
        rows.append(_row("cardA", m, "F&B", float(amt), 0, "MAMAK"))
    out = I.compute(rows)
    assert out["counts"]["sub"] >= 1
    assert out["counts"]["creep"] >= 1
    # sorted descending by severity
    sev = [r["severity"] for r in out["recs"]]
    assert sev == sorted(sev, reverse=True), sev
    # savings = sub annual (600) + creep annual delta (2400), one-offs excluded
    assert abs(out["savingsAnnual"] - (600.0 + 2400.0)) < 1e-6, out["savingsAnnual"]
    # every rec has the render contract keys
    for r in out["recs"]:
        for k in ("type","severity","title","line","rmMonthly","rmAnnual","hint"):
            assert k in r, (k, r)

def t_subs_cancel_candidates_only():
    months5 = ["2025-12","2026-01","2026-02","2026-03","2026-04"]
    rows = []
    # insurance recurring 5 months stable -> must NOT be a sub
    for m in months5:
        rows.append(_row("cardA", m, "Health/Insurance", 236.0, 0, "PRUBSN-RPS 8949916916"))
    # charity recurring 5 months -> must NOT be a sub
    for m in months5:
        rows.append(_row("cardA", m, "Charity", 79.0, 0, "CANCER SOCIETY"))
    # only-3-month stable Subscriptions merchant -> must NOT be a sub (4-month rule)
    for m in ["2026-02","2026-03","2026-04"]:
        rows.append(_row("cardA", m, "Subscriptions", 50.0, 0, "FUEL COINCIDENCE 99"))
    # genuine 4-month SaaS -> MUST be a sub (control)
    for m in ["2026-01","2026-02","2026-03","2026-04"]:
        rows.append(_row("cardA", m, "Subscriptions", 42.0, 0, "GOOGLE WHATSAPP BIZ 1"))
    names = [s["merchant"] for s in I.find_subs(rows)]
    assert not any("PRUBSN" in n for n in names), names
    assert not any("CANCER" in n for n in names), names
    assert not any("FUEL COINCIDENCE" in n for n in names), names
    assert any("GOOGLE WHATSAPP" in n for n in names), names

def t_oneoffs_exclude_bnpl():
    months = ["2026-01","2026-02"]
    rows = []
    for i in range(20):
        rows.append(_row("cardA", "2026-01", "Shopping", 40.0, 0, f"STORE {i}"))
    rows.append(_row("cardA", "2026-02", "Shopping", 594.0, 0, "SPAYLATER REPAYMENT"))
    rows.append(_row("cardA", "2026-02", "Shopping", 600.0, 0, "BIG REAL SPLURGE"))
    descs = [o["merchant"] for o in I.find_oneoffs(rows, months)]
    assert not any("SPAYLATER" in d for d in descs), descs
    assert any("BIG REAL SPLURGE" in d for d in descs), descs

def t_sub_staleness():
    months = ["2025-12","2026-01","2026-02","2026-03","2026-04","2026-05"]
    rows = []
    for m in months:                                  # active sub through latest month
        rows.append(_row("cardA", m, "Subscriptions", 42.0, 0, "GOOGLE WHATSAPP 1"))
    for m in ["2025-12","2026-01","2026-02","2026-03"]:  # dead sub, last=2026-03, gap=2
        rows.append(_row("cardA", m, "Subscriptions", 50.0, 0, "ERASER IO 7"))
    subs = {r["merchant"]: r for r in I.compute(rows)["recs"] if r["type"] == "sub"}
    assert subs["GOOGLE WHATSAPP"]["stale"] is False
    assert subs["GOOGLE WHATSAPP"]["hint"] == "Cancel?"
    assert subs["ERASER IO"]["stale"] is True
    assert subs["ERASER IO"]["lastGap"] == 2
    assert subs["ERASER IO"]["hint"] == "Already cancelled?"

def t_creep_evidence():
    months = ["2025-10","2025-11","2025-12","2026-01","2026-02","2026-03"]
    rows = []
    for m, amt in zip(months, [50,50,50,110,110,110]):    # MAXIS rising
        rows.append(_row("cardA", m, "Telco/Utilities", float(amt), 0, "MAXIS 1"))
    for m in months:                                      # UNIFI flat
        rows.append(_row("cardA", m, "Telco/Utilities", 60.0, 0, "UNIFI 2"))
    tel = next(c for c in I.find_creep(rows, months) if c["cat"] == "Telco/Utilities")
    assert tel["evidence"], "expected merchant breakdown"
    assert "MAXIS" in tel["evidence"][0]["merchant"]
    assert tel["evidence"][0]["delta"] > 0

def t_oneoffs_exclude_recurring():
    months = ["2026-01","2026-02"]
    rows = []
    for i in range(20):
        rows.append(_row("cardA", "2026-01", "Subscriptions", 30.0, 0, f"SMALL {i}"))
    # recurring big charge across both months -> must NOT be a one-off
    rows.append(_row("cardA", "2026-01", "Subscriptions", 410.0, 0, "CLAUDE AI ANTHROPIC"))
    rows.append(_row("cardA", "2026-02", "Subscriptions", 405.0, 0, "CLAUDE AI ANTHROPIC"))
    # true single splurge -> must remain a one-off
    rows.append(_row("cardA", "2026-02", "Travel", 2000.0, 0, "AIRASIA FLIGHT KUL"))
    descs = [o["merchant"] for o in I.find_oneoffs(rows, months)]
    assert not any("CLAUDE" in d for d in descs), descs
    assert any("AIRASIA" in d for d in descs), descs

def t_sub_price_step():
    months = ["2025-11","2025-12","2026-01","2026-02","2026-03","2026-04","2026-05","2026-06"]
    amts   = [85,84,83,342,404,403,412,405]            # Pro tier -> upgraded to Max tier
    rows = [_row("cardA", m, "Subscriptions", float(a), 0, "CLAUDE AI ANTHROPIC")
            for m, a in zip(months, amts)]
    subs = {s["merchant"]: s for s in I.find_subs(rows)}
    assert "CLAUDE AI ANTHROPIC" in subs, list(subs)
    s = subs["CLAUDE AI ANTHROPIC"]
    assert s["rmMonthly"] > 350, s["rmMonthly"]        # current price, not the old ~85
    assert s["months"] == 8

def t_subs_exclude_bnpl():
    months = ["2026-01","2026-02","2026-03","2026-04"]
    rows = []
    for m in months:                                   # recurring BNPL repayment -> NOT a sub
        rows.append(_row("cardA", m, "Shopping", 600.0, 0, "SPAYLATER REPAYMENT"))
    for m in months:                                   # real sub control
        rows.append(_row("cardA", m, "Subscriptions", 42.0, 0, "GOOGLE WHATSAPP 1"))
    names = [s["merchant"] for s in I.find_subs(rows)]
    assert not any("SPAYLATER" in n for n in names), names
    assert any("GOOGLE WHATSAPP" in n for n in names), names

# === CHANGE 1: Akmal fix — updated test (replaces old t_installment_split) ===
def t_installment_split():
    months = ["2026-01","2026-02","2026-03","2026-04"]
    rows = []
    for m in months:
        rows.append(_row("cardA", m, "Shopping", 149.95, 0, "%%SENHENG (SE001) -"))
    for m in months:
        rows.append(_row("cardA", m, "Subscriptions", 42.0, 0, "GOOGLE WHATSAPP 1"))
    out = I.compute(rows)
    sub_names = [r["merchant"] for r in out["recs"] if r["type"] == "sub"]
    assert any("GOOGLE WHATSAPP" in n for n in sub_names), sub_names
    assert not any("SENHENG" in n for n in sub_names), sub_names           # not a sub anymore
    inst_names = [p["name"] for p in out["installments"]]
    assert any("SENHENG" in n for n in inst_names), inst_names              # surfaced as installment
    assert abs(out["savingsAnnual"] - 504.0) < 1e-6                         # only google counts
    assert out["counts"]["installment"] >= 1

# === CHANGE 2: new find_installments tests ===
def t_installments_classify_and_track():
    months = ["2025-09","2025-10","2025-11","2025-12","2026-01","2026-02","2026-03","2026-04","2026-05","2026-06"]
    rows = []
    for m, n in {"2026-01":"01","2026-02":"02","2026-03":"03","2026-04":"04","2026-05":"05","2026-06":"06"}.items():
        rows.append(_row("alliance·4963", m, "Installments/BT", 266.67, 0, f"INSTL PULLMAN HOME GALLERY {n} OF 12"))
    for m in months:
        rows.append(_row("cimb·4388", m, "Installments/BT", 222.22, 0, "HARVEY NORMAN-IKANO-36M :"))
    rows.append(_row("cimb·4388", "2026-06", "Installments/BT", 296.75, 0, "LOTUS'S IOI CITY-3M : 0/03"))  # memo
    rows.append(_row("cimb·4388", "2026-06", "Installments/BT", 98.92, 0, "LOTUS'S IOI CITY-3M :"))
    for m in months:
        rows.append(_row("rhb·4297", m, "Installments/BT", 500.0, 0, "SMART MOVE BAL TRANSFER :"))
        rows.append(_row("rhb·4297", m, "Installments/BT", 250.0, 0, "SMART MOVE BAL TRANSFER :"))
    rows.append(_row("maybank·5161", "2026-05", "Installments/BT", 3600.0, 0, "BALANCE TFER - PLAN G T/F ER IN"))  # memo
    rows.append(_row("maybank·5161", "2026-05", "Installments/BT", 615.56, 0, "BALANCE TRANSFER PLAN G"))
    for m in months[:6]:
        rows.append(_row("sc·3829", m, "Shopping", 149.95, 0, "%%SENHENG (SE001) -"))
    for m in ["2025-06","2025-07","2025-08"]:
        rows.append(_row("cimb·4388", m, "Installments/BT", 71.75, 0, "GRAND SENHENG-BANGI-12M :"))
    out = I.find_installments(rows)
    plans = {p["name"]: p for p in out["plans"]}
    xfers = {t["name"]: t for t in out["transfers"]}
    pull = next(p for k, p in plans.items() if "PULLMAN" in k)
    assert pull["term"] == 12 and pull["progressN"] == 6 and pull["remaining"] == 6 and pull["est"] is False
    assert pull["endMonth"] == "2026-12"
    assert abs(pull["remainBal"] - 6 * 266.67) < 1e-2
    hv = next(p for k, p in plans.items() if "HARVEY" in k)
    assert hv["term"] == 36 and hv["progressN"] is None and hv["est"] is True
    assert abs(hv["monthly"] - 222.22) < 1e-6
    lot = next(p for k, p in plans.items() if "LOTUS" in k)
    assert abs(lot["monthly"] - 98.92) < 1e-2                  # memo 296.75 excluded
    senh = [k for k in plans if "SENHENG" in k]
    assert len(senh) == 2, senh                                   # SC and CIMB plans stay separate
    assert any(abs(plans[k]["monthly"] - 149.95) < 1e-2 for k in senh)
    assert any(abs(plans[k]["monthly"] - 71.75) < 1e-2 for k in senh)
    sm = next(t for k, t in xfers.items() if "SMART MOVE" in k)
    assert abs(sm["monthly"] - 750.0) < 1e-6                   # 500+250 latest month
    pg = next(t for k, t in xfers.items() if "PLAN G" in k)
    assert abs(pg["monthly"] - 615.56) < 1e-2                  # T/F ER IN memo excluded

def t_akmal_not_sub():
    months = ["2026-01","2026-02","2026-03","2026-04"]
    rows = []
    for m in months:
        rows.append(_row("sc·3829", m, "F&B", 25.0, 0, "AKMAL SQUARED SDN B 43900"))
    for m in months:
        rows.append(_row("sc·3829", m, "Subscriptions", 42.0, 0, "GOOGLE WHATSAPP 1"))
    for m in months:
        rows.append(_row("sc·3829", m, "Telco/Utilities", 209.0, 0, "TIMEDOTCOM 7"))
    names = [s["merchant"] for s in I.find_subs(rows)]
    assert not any("AKMAL" in n for n in names), names
    assert any("GOOGLE WHATSAPP" in n for n in names), names
    assert any("TIMEDOTCOM" in n for n in names), names

if __name__ == "__main__":
    t_norm_merchant()
    t_find_subs()
    t_find_creep()
    t_find_oneoffs()
    t_compute()
    t_subs_cancel_candidates_only()
    t_oneoffs_exclude_bnpl()
    t_sub_staleness()
    t_creep_evidence()
    t_oneoffs_exclude_recurring()
    t_sub_price_step()
    t_subs_exclude_bnpl()
    t_installment_split()
    t_installments_classify_and_track()
    t_akmal_not_sub()
    print("OK")
