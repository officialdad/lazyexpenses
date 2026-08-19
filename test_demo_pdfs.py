"""Plain-assert tests for the synthetic statements (make_demo_data.py --pdfs).

This is the only automated coverage parse.py has. Real statements cannot enter the
repo or CI, so the generator writes PDFs shaped like each bank's real layout and the
parser has to read them back to the cent.

The strong assertion is the round trip: reconcile() decides what each statement says,
the renderer prints it, and parse.py re-derives previous/debit/credit/current from the
words on the page. They have to agree, which they only can if every transaction row
parsed, every balance label was found, and every bank-specific quirk was handled.

Run from the repo root: python test_demo_pdfs.py   ->  OK
"""
import csv
import os
import subprocess
import sys
import tempfile

import make_demo_data as demo
import parse

MONTHS = 8


def _generate(outdir):
    months, txns = demo.build(MONTHS, seed=7)
    recon = demo.reconcile(months, txns)
    demo.write_pdfs(months, txns, recon, outdir)
    return months, txns, recon


def _close(a, b, tol=0.011):
    return a is not None and b is not None and abs(a - b) <= tol


def main():
    with tempfile.TemporaryDirectory() as d:
        months, txns, recon = _generate(d)
        parsed = {}

        # ---- every statement reconciles, and to the figures it was built from ----
        for r in recon:
            path = os.path.join(d, r["file"])
            meta, got = parse.parse_statement(path)
            parsed[r["file"]] = (meta, got)
            tag = f'{r["bank"]} {r["smonth"]}'
            assert meta["status"] == "VERIFIED", f"{tag}: status {meta['status']}, diff={meta['diff']}"
            assert meta["smonth"] == r["smonth"], f"{tag}: smonth {meta['smonth']}"
            assert meta["sdate"] == r["sdate"], f"{tag}: sdate {meta['sdate']}"
            assert meta["due"] == r["due"], f"{tag}: due {meta['due']} expected {r['due']}"
            assert meta["n"] == r["n"], f"{tag}: {meta['n']} rows parsed, {r['n']} written"
            for k in ("prev", "cur", "debit", "credit"):
                assert _close(meta[k], r[k]), f"{tag}: {k} {meta[k]} != {r[k]}"

        # ---- transactions round-trip, not just their totals ----
        for r in recon:
            meta, got = parsed[r["file"]]
            src = [t for t in txns if t["bank"] == r["bank"] and t["statement_month"] == r["smonth"]]
            assert (sorted(round(t["amount"], 2) for t in src)
                    == sorted(round(t["amount"], 2) for t in got)), f'{r["file"]}: amounts differ'
            for t in src:                      # descriptions survive clean_desc intact
                assert any(t["description"] == g["desc"] for g in got), \
                    f'{r["file"]}: lost description {t["description"]!r}'

        # ---- the CSV mode asserts a category per row; parse.py derives one from CATS.
        #      If those drift, the demo teaches something the real pipeline does not do ----
        for t in txns:
            assert parse.categorize(t["description"]) == t["category"], \
                f'{t["description"]!r}: demo says {t["category"]}, CATS says ' \
                f'{parse.categorize(t["description"])}'

        newest = months[-1]

        # ---- multi-card attribution: CIMB carries two cards on one statement ----
        _, cimb = parsed[f"cimb_demo_{newest}.pdf"]
        assert {t["card"] for t in cimb} == {"0002", "0003"}, \
            f'cimb cards {sorted({t["card"] for t in cimb})}'
        for t in cimb:                          # each row attributed to the card it was written under
            src = [x for x in txns if x["bank"] == "cimb" and x["statement_month"] == newest
                   and x["description"] == t["desc"]]
            assert src and src[0]["card_last4"] == t["card"], f'cimb {t["desc"]!r} -> card {t["card"]}'

        # ---- SC prints the due date ABOVE the statement date; the tight "Statement
        #      Date" anchor is what keeps the statement in the right month ----
        sc_meta, _ = parsed[f"sc_demo_{newest}.pdf"]
        assert sc_meta["due"][:7] != sc_meta["smonth"], \
            "SC fixture must put the due date in a later month or it tests nothing"
        assert sc_meta["smonth"] == newest, f'SC filed in {sc_meta["smonth"]}, not {newest}'
        assert {t["card"] for t in parsed[f"sc_demo_{newest}.pdf"][1]} == {"0004"}, \
            "SC last4 must come from the masked card number"

        # ---- CIMB-i: the ":0/MM" principal memo is a deferred posting, excluded from
        #      the month's debit; the ":NN/MM" monthly charges are kept ----
        oldest = months[0]
        _, first_cimb = parsed[f"cimb_demo_{oldest}.pdf"]
        memo = [t for t in first_cimb if ":0/12" in t["desc"]]
        assert len(memo) == 1 and memo[0]["excl"], "the :0/12 principal memo must be flagged excl"
        assert all(t["inst"] for t in first_cimb if "INSTL" in t["desc"]), \
            "installment rows must be flagged inst so they are force-categorized"

        # ---- Alliance: dates on the line above, and a virtual card sitting in credit.
        #      Without the CR sign flip the recon is out by exactly twice that balance ----
        al_meta, al = parsed[f"alliance_demo_{newest}.pdf"]
        assert al, "alliance date-above-row pairing produced no transactions"
        assert _close(al_meta["prev"] + al_meta["debit"] - al_meta["credit"], al_meta["cur"])

        # ---- CIMB is genuinely paginated: summary page, then transaction pages ----
        pages = {p for p, _, _ in parse.all_rows(os.path.join(d, f"cimb_demo_{newest}.pdf"))}
        assert len(pages) > 1, f"cimb statement should span pages, got {len(pages)}"

        # ---- the duplicate is recognised as the same statement, not a second one ----
        a, _ = parsed[f"maybank_demo_{newest}.pdf"]
        b, _ = parse.parse_statement(os.path.join(d, f"maybank_demo_{newest}_copy.pdf"))
        key = lambda m: (m["bank"], m["sdate"], m["prev"], m["cur"], m["debit"], m["credit"], m["n"])
        assert key(a) == key(b), "the duplicate must share the dedup fingerprint"
        assert a["file"] != b["file"]

        # ---- prev -> cur chain continuity per bank: a break means a misdated statement ----
        for bank in demo.BANKS:
            chain = [parsed[r["file"]][0] for r in recon if r["bank"] == bank]
            for prev_m, cur_m in zip(chain, chain[1:]):
                assert _close(prev_m["cur"], cur_m["prev"]), \
                    f'{bank}: {prev_m["smonth"]} closed at {prev_m["cur"]}, ' \
                    f'{cur_m["smonth"]} opened at {cur_m["prev"]}'

        # ---- a locked statement parses identically to its unlocked twin ----
        try:
            import pypdf
        except ImportError:
            print("SKIP encrypted-statement case (pypdf not installed)")
        else:
            import io
            src = os.path.join(d, f"hsbc_demo_{newest}.pdf")
            w = pypdf.PdfWriter(clone_from=io.BytesIO(open(src, "rb").read()))
            w.encrypt("s3cret")
            locked = os.path.join(d, "hsbc_locked.pdf")
            w.write(locked)
            os.environ["CC_PW_HSBC"] = "s3cret"
            try:
                lm, lt = parse.parse_statement(locked)
                um, ut = parsed[f"hsbc_demo_{newest}.pdf"]
                assert lm["status"] == "VERIFIED" and lm["cur"] == um["cur"] and len(lt) == len(ut), \
                    "locked statement must parse identically to its unlocked twin"
            finally:
                os.environ.pop("CC_PW_HSBC", None)

    _cli_dedups_and_reconciles()
    print("OK")


def _cli_dedups_and_reconciles():
    """Run parse.py the way a user does. The per-statement checks above call
    parse_statement directly, which never sees main()'s duplicate handling — and a
    duplicate that is NOT dropped double-counts a month in every chart while each
    file still reconciles VERIFIED, which is precisely the failure that hides."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "pdfs")
        months, txns, recon = _generate(src)
        env = {**os.environ, "STMT_SRC": src, "STMT_CACHE": os.path.join(d, "cache")}
        r = subprocess.run([sys.executable, os.path.abspath("parse.py")],
                           cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, f"parse.py failed:\n{r.stderr[-2000:]}"

        with open(os.path.join(d, "reconciliation.csv"), encoding="utf-8-sig") as fh:
            got = list(csv.DictReader(fh))
        status = {}
        for row in got:
            status[row["status"]] = status.get(row["status"], 0) + 1
        assert status == {"VERIFIED": len(recon), "DUPLICATE": 1}, f"statuses: {status}"

        with open(os.path.join(d, "transactions.csv"), encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == len(txns), \
            f"{len(rows)} transactions written, {len(txns)} generated — the duplicate leaked in"
        assert not any(t["category"] == "Other" for t in rows), \
            "a demo merchant fell through CATS into Other"


if __name__ == "__main__":
    main()
