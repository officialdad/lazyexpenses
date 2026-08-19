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

--pdfs writes statement PDFs instead, into cc-statements/, and lets parse.py produce
the CSVs itself:

    python make_demo_data.py --pdfs && python parse.py

Same data, one layer lower. That is the only way parse.py — six banks of layout rules,
where a misread becomes confidently wrong money — gets any automated coverage, because
real statements can never enter this repo or CI. Each bank's renderer reproduces the
quirk that makes its branch exist; test_demo_pdfs.py is the round-trip check.
"""
import argparse
import csv
import os
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
    ("cimb",    "0002", "PASARAYA SEGAR DEMO",         "Groceries",     88.50, 2),
    ("hsbc",    "0006", "PETROL STESEN DEMO",       "Vehicle",      120.00, 3),
    ("rhb",     "0007", "TEKSI DEMO RIDE",          "Vehicle",       23.00, 4),
    ("sc",      "0004", "KEDAI KOPI DEMO",          "F&B",           31.00, 4),
    ("alliance","0005", "APOTEK DEMO PHARMACY",     "Health/Insurance", 64.00, 1),
    ("cimb",    "0003", "DEMO DEPT STORE",          "Shopping",     210.00, 1),
]

# Subscriptions. Only Subscriptions / Telco-Utilities are eligible (insights.SUB_CATS).
# (bank, last4, desc, category, price, first month index, last month index or None)
SUBS = [
    ("sc",      "0004", "DEMOFLIX STREAMING SUBSCRIPTION", "Subscriptions",    45.90, 0, None),
    ("maybank", "0001", "PIXELTUNES MUSIC SUBSCRIPTION",   "Subscriptions",    19.90, 0, -4),
    ("cimb",    "0002", "NOVATEL FIBRE",      "Telco/Utilities",  99.00, 0, None),
]
NOVATEL_NEW_PRICE = 149.00      # tier step for the last 4 months

CREEP_CAT = "F&B"
CREEP_MERCHANTS = [("rhb", "0007", "DEMO BUBBLE TEA CAFE"), ("rhb", "0007", "WARUNG DEMO NASI")]


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

        # A foreign-currency charge. The bank prints the original amount next to the MYR
        # one, so the row carries TWO money tokens — find_amount takes the rightmost, and
        # the description keeps the other. A real recurring USD SaaS bill, so it also
        # shows up in the Cuts view as the subscription it is.
        add("hsbc", "0006", ym, "DEMO CLOUD HOST SUBSCRIPTION 12.99 USD", "Subscriptions", jitter(58.40, 0.05))

        # cashback: a credit in Rebate/Cashback, invisible to every spend chart by design
        for bank, (last4s, _, _) in BANKS.items():
            add(bank, last4s[0], ym, "CASHBACK REBATE DEMO", "Rebate/Cashback", jitter(18.0), credit=True)

    # one big one-off in the newest month. Merchant appears in exactly one month, so it
    # survives the recurrence guard that stops recurring insurance/SaaS masquerading as a splurge.
    # Deliberately in Travel, which carries no regular monthly spend: dropped into a category
    # with a small steady baseline it would ALSO trip find_creep, and one purchase showing up
    # as two different recommendations is a false positive, not a richer demo.
    add("hsbc", "0006", newest, "DEMO SKYFARE RESORTS", "Travel", 4200.00)

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


# ============================ synthetic PDFs (--pdfs) ============================
# The CSV mode above hands parse.py's OUTPUT to everything downstream. This mode
# builds its INPUT instead: real-shaped statement PDFs that parse.py has to read
# back. That is the only way parse.py itself — six banks of layout rules, where a
# misread turns into confidently wrong money — gets any automated coverage at all,
# because real statements can never enter this repo or CI.
#
# The balances printed on each statement come straight from reconcile(), so a
# generated statement reconciles for the same reason a real one does: previous +
# debit - credit lands on the printed current balance. If a layout stops parsing,
# the reconciliation says REVIEW instead of quietly producing a wrong number.
#
# Fidelity bar: not visual, but "does this drive that bank's actual code path".
# Text is placed at real coordinates because row reconstruction groups words by
# their y position (parse.rows_of) — flowing text would leave the core trick
# untested. Each bank's quirks are called out at its renderer.

PAGE_W, PAGE_H = 595.0, 842.0          # A4
TOP_Y, LINE_H, PAGE_BOTTOM = 50.0, 13.0, 800.0
X_L, X_DESC, X_MID, X_AMT = 40.0, 150.0, 300.0, 430.0
CR_CARD = 15.00                        # the card deliberately left in credit; see _cimb/_alliance

MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MON_FULL = ["January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"]


def _money(v):
    return f"{v:,.2f}"


def _amt(t):
    """The money token as a bank prints it — a trailing CR marks a credit."""
    return _money(t["amount"]) + ("CR" if t["type"] == "credit" else "")


def _dm(iso):        # 28/03
    return f"{iso[8:10]}/{iso[5:7]}"


def _dmy2(iso):      # 28/03/26
    return f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}"


def _dmy4(iso):      # 28/03/2026
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _dmon(iso):      # 28 Mar
    return f"{iso[8:10]} {MON[int(iso[5:7]) - 1]}"


def _dmony(iso):     # 28 Mar 2026
    return f"{_dmon(iso)} {iso[:4]}"


def _dmonyf(iso):    # 28 March 2026
    return f"{iso[8:10]} {MON_FULL[int(iso[5:7]) - 1]} {iso[:4]}"


def _esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _pdf(pages, w=PAGE_W, h=PAGE_H, size=9):
    """Smallest valid multi-page PDF placing text at absolute coordinates.

    `pages` is a list of pages, each a list of (x, y_from_top, text). Offsets in
    the xref are computed, not guessed. No reportlab, no new dependency — this is
    test_parse_password.py::_minimal_pdf generalised to many chunks and many pages.
    """
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,                                    # /Pages, needs the kid ids below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for i, chunks in enumerate(pages):
        pid = 4 + 2 * i                          # page object; its content stream is pid + 1
        kids.append(b"%d 0 R" % pid)
        body = [b"BT /F1 %d Tf" % size]
        for x, ytop, text in chunks:
            body.append(b"1 0 0 1 %.2f %.2f Tm (%s) Tj"
                        % (x, h - ytop, _esc(text).encode("latin-1", "replace")))
        stream = b"\n".join(body + [b"ET"])
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 3 0 R >> >> >>" % (int(w), int(h), pid + 1))
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(pages))

    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1) + b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref))
    return bytes(out)


class _Sheet:
    """Lays chunks out a line at a time and paginates.

    Every chunk on a line shares one y, so parse.rows_of rebuilds exactly the row
    that was written. The optional third element of a chunk nudges it off that
    shared baseline: amounts are written 1pt low so the reconstruction has to lean
    on its y-tolerance rather than on an exact coordinate match, which is the
    situation the real SC and CIMB statements create.
    """

    def __init__(self):
        self.pages, self._cur, self._y = [], [], TOP_Y

    def line(self, *chunks):
        if self._y > PAGE_BOTTOM:
            self.newpage()
        for c in chunks:
            self._cur.append((c[0], self._y + (c[2] if len(c) > 2 else 0.0), str(c[1])))
        self._y += LINE_H
        return self

    def gap(self, n=1):
        self._y += LINE_H * n
        return self

    def newpage(self):
        self.pages.append(self._cur)
        self._cur, self._y = [], TOP_Y
        return self

    def pdf(self):
        return _pdf(self.pages + [self._cur])


def _maybank(r, rows):
    """Single card, `dd/mm dd/mm` rows, and an address block sitting between the
    letterhead and the figures — the interleaving that makes recon_balances per-bank."""
    s = _Sheet()
    s.line((X_L, "MAYBANK DEMO BERHAD (000000-X)"))
    s.line((X_L, "AHMAD DEMO BIN DEMO"))
    s.line((X_L, "NO 32 JALAN DEMO 5/6"))
    s.line((X_L, "71450 DEMO TOWN NEGERI DEMO"))
    s.gap()
    s.line((X_L, "Statement Date"), (X_MID - 90, _dmony(r["sdate"])),
           (X_MID + 40, "Payment Due Date"), (X_AMT + 60, _dmony(r["due"])))
    s.line((X_L, "CARD NO 1234-5678-9012-0001"))
    s.gap()
    s.line((X_L, "PREVIOUS STATEMENT BALANCE"), (X_AMT, _money(r["prev"])))
    for t in rows:
        s.line((X_L, f'{_dm(t["post_date"])} {_dm(t["txn_date"])}'),
               (X_DESC, t["description"]), (X_AMT, _amt(t), 1.0))
    s.line((X_L, "SUB TOTAL / JUMLAH"), (X_AMT, _money(r["cur"])))
    return s.pdf()


def _cimb(r, rows):
    """Several cards on one statement: a summary table on page 1, then per-card
    transaction sections on page 2 that the parser attributes by tracking card-number
    headers. Card 0003 is deliberately left in credit so the CR sign-flip in
    recon_balances is exercised — the two printed balances still sum to the total.
    CIMB-i installment rows carry the `:NN/MM` counter, `:0/MM` being the deferred
    principal that must NOT count toward this month's debit."""
    s = _Sheet()
    s.line((X_L, "CIMB ISLAMIC BANK DEMO BERHAD"))
    s.line((X_L, "AHMAD DEMO BIN DEMO"))
    s.gap()
    # No "Statement Date" label anywhere: CIMB prints "Statement / Invoice Date", so
    # stmt_month has to fall through its tight anchor to the loose one.
    s.line((X_L, "Statement / Invoice Date"), (X_MID, "Payment Due Date"))
    s.line((X_L, _dmony(r["sdate"])), (X_MID, _dmony(r["due"])))
    s.gap()
    s.line((X_L, "PREVIOUS BALANCE"), (X_AMT, _money(r["prev"])))
    s.gap()
    s.line((X_L, "CARD"), (X_DESC, "NAME"), (250.0, "PREV BAL"), (320.0, "PURCHASES"),
           (390.0, "PAYMENTS"), (460.0, "STMT BAL"), (525.0, "MIN PAY"))
    s.line((X_L, f'1234-5678-9012-0002 AHMAD DEMO {_money(r["prev"] + CR_CARD)} '
                 f'{_money(r["debit"])} {_money(r["credit"])} '
                 f'{_money(r["cur"] + CR_CARD)} 50.00'))
    s.line((X_L, f'1234-5678-9012-0003 AHMAD DEMO {_money(CR_CARD)}CR 0.00 0.00 '
                 f'{_money(CR_CARD)}CR 0.00'))
    s.newpage()
    s.line((X_L, "TRANSACTION DETAILS"))
    for last4 in sorted({t["card_last4"] for t in rows}):
        s.gap()
        s.line((X_L, f"1234-5678-9012-{last4}"))
        for t in [x for x in rows if x["card_last4"] == last4]:
            s.line((X_L, f'{_dmon(t["post_date"])} {_dmon(t["txn_date"])}'),
                   (X_DESC, t["description"]), (X_AMT, _amt(t), 1.0))
    return s.pdf()


def _sc(r, rows):
    """The Payment Due Date is printed ABOVE the statement date. That layout is why
    stmt_month anchors on the full "Statement Date" label: a loose anchor grabbed the
    due date and silently filed three real statements in the wrong month. The card
    number is masked, so last4 has to come from the masked-number fallback."""
    s = _Sheet()
    s.line((X_L, "STANDARD CHARTERED BANK DEMO MALAYSIA BERHAD"))
    s.line((X_L, "STATEMENT OF ACCOUNT"))
    s.gap()
    # The title line above is load-bearing: it is the first "Statement" in the document,
    # so a loose anchor walks from it straight into the due date below and files the
    # statement a month late. Only the tight "Statement Date" label gets this right.
    s.line((X_L, "Payment Due Date / Tarikh Akhir :"), (X_MID, _dmony(r["due"])))
    s.line((X_L, "Statement Date / Tarikh Penyata :"), (X_MID, _dmony(r["sdate"])))
    s.line((X_L, "Card No 5520-40XX-XXXX-0004"))
    s.gap()
    s.line((X_L, "PREVIOUS STATEMENT"), (X_AMT, _money(r["prev"])))
    for t in rows:
        s.line((X_L, f'{_dmon(t["post_date"])} {_dmon(t["txn_date"])}'),
               (X_DESC, t["description"]), (X_AMT, _amt(t), 1.0))
    s.line((X_L, "New BALANCE / Baki Baru"), (X_AMT, _money(r["cur"])))
    return s.pdf()


def _hsbc(r, rows):
    """HSBC runs its labels together with no spaces at all, and spells the due date's
    month out in full."""
    s = _Sheet()
    s.line((X_L, "HSBC BANK DEMO MALAYSIA BERHAD"))
    s.gap()
    s.line((X_L, "StatementDate"), (X_MID - 90, _dmony(r["sdate"])),
           (X_MID + 40, "PaymentDueDate"), (X_AMT + 60, _dmonyf(r["due"])))
    s.line((X_L, "CardNumber 1234-5678-9012-0006"))
    s.gap()
    s.line((X_L, "YourPreviousStatementBalance"), (X_AMT, _money(r["prev"])))
    for t in rows:
        s.line((X_L, f'{_dmon(t["post_date"])} {_dmon(t["txn_date"])}'),
               (X_DESC, t["description"]), (X_AMT, _amt(t), 1.0))
    s.line((X_L, "Yourstatementbalance"), (X_AMT, _money(r["cur"])))
    return s.pdf()


def _rhb(r, rows):
    """RHB puts the due date on the line BELOW its label and in dd/mm/yyyy, and labels
    both balances bilingually."""
    s = _Sheet()
    s.line((X_L, "RHB BANK DEMO BERHAD"))
    s.gap()
    s.line((X_L, "Statement Date"), (X_MID - 90, _dmony(r["sdate"])))
    s.line((X_L, "Payment Due Date"))
    s.line((X_L, _dmy4(r["due"])))
    s.line((X_L, "CARD NO 1234-5678-9012-0007"))
    s.gap()
    s.line((X_L, "OPENING BALANCE / BAKI MULA"), (X_AMT, _money(r["prev"])))
    for t in rows:
        s.line((X_L, f'{_dmon(t["post_date"])} {_dmon(t["txn_date"])}'),
               (X_DESC, t["description"]), (X_AMT, _amt(t), 1.0))
    s.line((X_L, "Outstanding Balance / Baki Terkini"), (X_AMT, _money(r["cur"])))
    return s.pdf()


def _alliance(r, rows):
    """Structurally unlike the other five: the date sits on the line ABOVE the
    description and amount, and parse_alliance requires that adjacency — one logical
    row per line would leave its whole parser untested. Labels are Malay, and the
    virtual card sits in credit, which is the CR that sum_signed has to negate or the
    reconciliation comes out wrong by exactly twice that balance."""
    s = _Sheet()
    s.line((X_L, "ALLIANCE BANK DEMO MALAYSIA BERHAD"))
    s.gap()
    s.line((X_L, "Tarikh Penyata"), (X_MID - 90, _dmy2(r["sdate"])))
    s.line((X_L, "Tarikh Bayaran Perlu Dibuat"), (X_MID - 90, _dmy2(r["due"])))
    s.gap()
    s.line((X_L, "VISA PLATINUM DEMO 1234 5678 9012 0005"))
    s.line((X_L, "PREVIOUS STATEMENT BALANCE"), (X_AMT, _money(r["prev"] + CR_CARD)))
    for t in rows:
        s.line((X_L, f'{_dmy2(t["txn_date"])} {_dmy2(t["post_date"])}'))
        s.line((X_L, t["description"]), (X_AMT, _amt(t), 1.0))
    # A rewards line that carries a money-shaped number but no date above it. Requiring
    # the date/description adjacency is exactly what stops this being read as a purchase.
    s.line((X_L, "MATA GANJARAN / REWARD POINTS EARNED"), (X_AMT, "1,250.00"))
    s.line((X_L, "CURRENT BALANCE"), (X_AMT, _money(r["cur"] + CR_CARD)))
    s.gap()
    s.line((X_L, "VISA VIRTUAL DEMO 1234 5678 9012 0009"))
    s.line((X_L, "PREVIOUS STATEMENT BALANCE"), (X_AMT, _money(CR_CARD)), (X_AMT + 60, "CR"))
    s.line((X_L, "CURRENT BALANCE"), (X_AMT, _money(CR_CARD)), (X_AMT + 60, "CR"))
    return s.pdf()


RENDERERS = {"maybank": _maybank, "cimb": _cimb, "sc": _sc,
             "hsbc": _hsbc, "rhb": _rhb, "alliance": _alliance}


def write_pdfs(months, txns, recon, outdir="cc-statements"):
    """Render every reconciliation row as the statement it was derived from."""
    os.makedirs(outdir, exist_ok=True)
    written = []
    for r in recon:
        rows = sorted([t for t in txns if t["bank"] == r["bank"]
                       and t["statement_month"] == r["smonth"]],
                      key=lambda t: (t["post_date"], t["description"]))
        path = os.path.join(outdir, r["file"])
        with open(path, "wb") as fh:
            fh.write(RENDERERS[r["bank"]](r, rows))
        written.append(path)

    # One deliberate duplicate. The mail history really does re-export the same
    # statement under several filenames, which is why parse.py fingerprint-dedups —
    # and that dedup is only tested if it happens at least once.
    src = os.path.join(outdir, f"maybank_demo_{months[-1]}.pdf")
    if os.path.exists(src):
        dup = os.path.join(outdir, f"maybank_demo_{months[-1]}_copy.pdf")
        with open(dup, "wb") as fh:
            fh.write(open(src, "rb").read())
        written.append(dup)
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--months", type=int, default=14,
                    help="how many months to generate (>= 6, or creep detection has nothing to compare)")
    ap.add_argument("--seed", type=int, default=7, help="RNG seed; same seed reproduces the same amounts")
    ap.add_argument("--pdfs", action="store_true",
                    help="write synthetic statement PDFs for parse.py to read back, instead of "
                         "writing the CSVs directly (run parse.py afterwards to produce them)")
    ap.add_argument("--outdir", default="cc-statements", help="where --pdfs writes (default cc-statements/)")
    a = ap.parse_args()
    if a.months < 6:
        ap.error("--months must be at least 6: find_creep compares the last 3 months against the prior 3")

    months, txns = build(a.months, a.seed)
    recon = reconcile(months, txns)

    if a.pdfs:
        written = write_pdfs(months, txns, recon, a.outdir)
        print(f"wrote {len(written)} synthetic statement PDFs to {a.outdir}/ "
              f"({len(recon)} statements + 1 deliberate duplicate)")
        print(f"months {months[0]} -> {months[-1]}, {len(BANKS)} banks, "
              f"{sum(len(v[0]) for v in BANKS.values())} cards - ALL DATA IS FAKE")
        print("next: python parse.py   (every statement should reconcile VERIFIED)")
        return

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
