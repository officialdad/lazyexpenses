#!/usr/bin/env python3
"""Optional local LLM for the `Other` bucket — suggest mode. Off unless configured.

`CATS` in parse.py stays primary and stays first. This only ever sees descriptions
that `categorize()` already gave up on; a keyword hit is never overridden and never
even generates a request. Nothing here is imported by parse.py, so with no config
the pipeline is exactly as deterministic as it was.

    python llm_cats.py --suggest-cats            # reads transactions.csv
    python llm_cats.py --suggest-cats other.csv

It reads the `Other` rows out of transactions.csv, asks a LOCAL llama.cpp server for
a category per distinct merchant, and writes `suggested_cats.csv` (merchant, proposed
category, confidence, occurrences, RM total) plus a paste-ready `CATS` block. Nothing
is applied: you paste the keywords you agree with into parse.py yourself, and from
then on that merchant costs zero inference forever.

Transport is `urllib` against llama.cpp's OpenAI-compatible /v1/chat/completions with
a `response_format: json_schema` whose category is an `enum` of the 15 names — llama.cpp
turns that into a GBNF grammar and decodes under it, so the model *cannot* answer outside
the taxonomy. That is the mechanism, not a filter after the fact. No new dependency, no
hosted provider, no key.

Env: LLM_URL (http://localhost:8080), LLM_MODEL (local), LLM_ENABLED.
Unset LLM_URL and unset LLM_ENABLED = the feature is absent. See docs/DEPLOY.md.
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.request

from insights import norm_merchant
from parse import CATS, categorize

URL = os.environ.get("LLM_URL", "http://localhost:8080")
MODEL = os.environ.get("LLM_MODEL", "local")
OUT = "suggested_cats.csv"

CATEGORIES = [c for c, _ in CATS]          # the 15 names, in CATS order

# One line each. Malaysian merchant strings are opaque abbreviations ("PSS-",
# "MPC2004"); a bare list of 15 names tells a 0.5B model nothing about what they mean.
GLOSS = {
    'Transfers/Payments': "money moved, not spent: card bill payments, DuitNow, IBG, fund transfers",
    'Fees/Charges': "bank fees and interest: service tax, late payment, finance charge, annual fee",
    'Rebate/Cashback': "money coming back from the bank: cashback, rebates, reward redemptions",
    'Installments/BT': "financing plans: balance transfers, easy-payment/installment plan charges",
    'Vehicle': "getting around: petrol, tolls, parking, ride-hailing, trains, workshops",
    'Groceries': "supermarkets, hypermarkets, minimarts and convenience stores",
    'F&B': "eating and drinking: restaurants, cafes, fast food, bakeries, bubble tea",
    'Telco/Utilities': "mobile, broadband, electricity, water, sewerage bills",
    'Travel': "flights, hotels, and travel booking sites",
    'Health/Insurance': "clinics, hospitals, dentists, pharmacies, opticians, insurance premiums",
    'Subscriptions': "recurring digital services: streaming, SaaS, cloud, app stores",
    'Shopping': "retail goods: marketplaces, electronics, furniture, clothing, department stores",
    'Entertainment': "leisure: cinemas, games, gyms, karaoke, play centres",
    'Certifications': "professional bodies, licences and certification fees",
    'Charity': "donations, zakat, waqf",
}

SYSTEM = ("You categorize Malaysian credit-card merchant names into a fixed taxonomy. "
          "Many are abbreviated or truncated. Pick the single best category. "
          "Answer with JSON only.")


def taxonomy(cats=None):
    """The prompt's taxonomy block: name, gloss, and real examples lifted from CATS."""
    keep = set(cats or CATEGORIES)
    out = []
    for cat, kws in CATS:
        if cat not in keep:
            continue
        egs = ", ".join(k.strip() for k in kws[:6])
        out.append(f"- {cat}: {GLOSS[cat]}. e.g. {egs}")
    return "\n".join(out)


def prompt(merchant):
    """-> chat messages for one merchant. Pure."""
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content":
            f"Categories:\n{taxonomy()}\n\n"
            f"Merchant: {merchant}\n\n"
            'Reply as {"category": "<one of the categories above>", '
            '"confidence": "high"|"medium"|"low"}.'},
    ]


def response_format(cats=None):
    """The constraint. llama.cpp compiles this JSON schema to a GBNF grammar and decodes
    under it, so an invented category is impossible — this is not a check on the way back.
    `response_format` is the documented constrained-decoding field for /chat/completions
    (a raw `grammar` field is the /completion endpoint's spelling)."""
    return {"type": "json_schema", "json_schema": {
        "name": "merchant_category", "strict": True, "schema": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "category": {"type": "string", "enum": list(cats or CATEGORIES)},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["category", "confidence"]}}}


def parse_response(payload, cats=None):
    """-> (category, confidence) from a /v1/chat/completions body. Pure.

    The schema already guarantees the shape; this raises rather than trusts, because
    "LLM_URL points at something that is not llama-server" is a real failure mode and
    a garbage answer must not end up in the proposal file looking like a suggestion.
    """
    txt = payload["choices"][0]["message"]["content"]
    d = json.loads(txt)
    cat, conf = d["category"], d["confidence"]
    if cat not in (cats or CATEGORIES):
        raise ValueError(f"not a category: {cat!r}")
    return cat, conf


def classify(merchant, url=None, model=None, timeout=120):
    """The only function here that touches the network. Tests do not cross this line."""
    body = json.dumps({
        "model": model or MODEL,
        "messages": prompt(merchant),
        "response_format": response_format(),
        "temperature": 0,
        "max_tokens": 64,
    }).encode()
    req = urllib.request.Request(
        (url or URL).rstrip("/") + "/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_response(json.load(r))


def enabled():
    """Off unless explicitly configured. LLM_ENABLED wins both ways; otherwise the
    feature exists only if LLM_URL was set by hand."""
    v = os.environ.get("LLM_ENABLED")
    if v is not None:
        return v.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(os.environ.get("LLM_URL"))


def unmatched(rows):
    """Distinct merchants CATS gave up on -> [{merchant, n, rm}], biggest RM first.

    CATS is re-run on every description, not just trusted from the CSV column: it is
    the primary classifier and the only gate on what reaches the model. A row a
    keyword matches never becomes a request.
    """
    agg = {}
    for r in rows:
        if r.get("category") != "Other" or categorize(r["description"]) != "Other":
            continue
        m = norm_merchant(r["description"])
        if not m:
            continue
        d = agg.setdefault(m, {"merchant": m, "n": 0, "rm": 0.0})
        d["n"] += 1
        d["rm"] += float(r["amount"] or 0)
    for d in agg.values():
        d["rm"] = round(d["rm"], 2)
    return sorted(agg.values(), key=lambda d: (-d["rm"], d["merchant"]))


def suggest(merchants, url=None, model=None):
    """Ask about each merchant. -> (proposals, notes).

    A missing or broken model never fails the run: those merchants simply keep no
    proposal and stay `Other`, and `notes` is what the user gets told about it.
    """
    out, notes, bad = [], [], 0
    for d in merchants:
        try:
            cat, conf = classify(d["merchant"], url, model)
        except (urllib.error.URLError, TimeoutError) as e:
            # The server is down or wedged; it will not come back mid-loop, and
            # hammering a dead port once per merchant just makes the wait longer.
            notes.append(f"{url or URL} unreachable ({e}) - stopped after {len(out)}; "
                         f"{len(merchants) - len(out)} merchant(s) left as Other")
            break
        except Exception as e:
            bad += 1
            notes.append(f"skipped {d['merchant']}: {e}")
            continue
        out.append(dict(d, category=cat, confidence=conf))
    if bad:
        notes.append(f"{bad} merchant(s) got an unusable answer and stay Other")
    return out, notes


def paste_block(proposals):
    """The point of the whole thing: keywords to paste into CATS, grouped by category
    in CATS order, so a merchant the model got right costs zero inference next time."""
    lines = ["# paste into CATS in parse.py (review first - a 0.5B model guesses):"]
    for cat in CATEGORIES:
        ms = [p["merchant"] for p in proposals if p["category"] == cat]
        if ms:
            lines.append(f"    ({cat!r}, {ms!r}),")
    return "\n".join(lines)


def main(argv=()):
    args = [a for a in argv if not a.startswith("-")]
    if "--suggest-cats" not in argv:
        print(__doc__.strip().splitlines()[0])
        print("usage: python llm_cats.py --suggest-cats [transactions.csv]")
        return
    if not enabled():
        print("LLM_URL / LLM_ENABLED not set - the local classifier is off "
              "(see docs/DEPLOY.md). Nothing to do.")
        return
    path = args[0] if args else "transactions.csv"
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    todo = unmatched(rows)
    if not todo:
        print(f"{path}: no Other rows - CATS covered every merchant.")
        return
    print(f"{path}: {len(todo)} distinct unmatched merchant(s) -> {URL}")
    props, notes = suggest(todo)
    for n in notes:
        print(n)
    if not props:
        # Nothing came back — don't overwrite a good proposal file with an empty one.
        print("no proposals; every unmatched merchant stays Other.")
        return
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["merchant", "category", "confidence", "n", "rm"])
        w.writeheader()
        w.writerows({k: p[k] for k in w.fieldnames} for p in props)
    print(f"wrote {OUT}: {len(props)} proposal(s). Nothing was applied.")
    if props:
        print(paste_block(props))


if __name__ == "__main__":
    main(sys.argv[1:])
