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


def default_csv():
    """Where transactions.csv lives. In the container the pipeline writes it to
    DATA_DIR, and `docker exec` lands in /app — so cwd is the wrong guess there."""
    d = os.environ.get("DATA_DIR")
    return os.path.join(d, "transactions.csv") if d else "transactions.csv"

CATEGORIES = [c for c, _ in CATS]          # the 15 names, in CATS order

# MEASURED 2026-08-21 (#58): this block is the CATEGORY NAMES AND NOTHING ELSE, and
# that is load-bearing. On the 5 merchants CATS gave up on (Gemma 3 1B it Q4_K_M,
# temperature 0, deterministic over two runs) names-only scores 4/5 at 145 prompt
# tokens. The block this replaced - a one-line gloss plus six real CATS examples per
# category, 715 tokens - scored 1/5, because the model stopped reading the merchant and
# answered one constant category for everything.
#
# It is not length, and it is not the grammar, the system role or truncation (#54
# ablated those three). It is prose describing the categories, anywhere in the prompt:
#
#   names only ............................... 4/5   145 tok   <- shipped
#   names + 5 few-shot examples .............. 4/5   309 tok   longer, no better
#   names, merchant after the instruction .... 3/5   145 tok
#   names + examples, no gloss ............... 2/5   511 tok
#   identify-the-business first, then map .... 2/5   175 tok   and NOT deterministic
#   names + gloss, no examples ............... 1/5   349 tok
#   names + a 26-token line of category prose
#     in the *system* message ................ 1/5   171 tok   collapsed to Shopping x5
#   names + gloss + examples (the old block) . 1/5   715 tok
#
# So: do not re-add descriptions here, and do not describe the categories in SYSTEM
# either. Known cost, measured on a second 10-string probe of bank jargon
# ("SERVICE TAX", "BALANCE TRANSFER 3M"): the old block got 6/10 there, names-only 4/10.
# Accepted, because CATS matches that jargon on fixed strings the banks print and it is
# asked first - what actually reaches the model is merchant names CATS failed on.
#
# MEASURED 2026-08-23 (#77), the real corpus this time: 17 distinct merchants out of the
# production `Other` bucket, same model and prompt. 6 of the 12 a human could actually
# judge were right - 50%, not the pilot's 80%. The other 5 are unknowable from the
# merchant string alone and stay Other, which is correct. Every one of the 17 came back
# `high`, wrong ones included, so confidence is still decoration.
#
# The two failure modes are worth knowing before you trust a proposal:
#   Groceries as a dump bucket for anything edible - THAI CUISINE, SEIROCK-YA (a
#     Japanese restaurant), BINGXUE (bubble tea) all landed there instead of F&B.
#   Fees/Charges for any name carrying SDN. BHD. - DENTARI GLOBAL (dental) went there
#     instead of Health/Insurance.
# It also missed Vehicle on a merchant literally named OTOMOBIL, the biggest row in the
# bucket at RM406. Read every line; the suggest-only design is the point, not caution.

SYSTEM = ("You categorize Malaysian credit-card merchant names into a fixed taxonomy. "
          "Many are abbreviated or truncated. Pick the single best category. "
          "Answer with JSON only.")


def taxonomy(cats=None):
    """The prompt's taxonomy block: the category names, nothing else. See above."""
    keep = set(cats or CATEGORIES)
    return "\n".join(f"- {c}" for c in CATEGORIES if c in keep)


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
    lines = ["# paste into CATS in parse.py (REVIEW EVERY LINE - 4 of 5 right on a "
             "5-merchant pilot, and every answer reads 'high' confidence, wrong ones too):"]
    for cat in CATEGORIES:
        ms = [p["merchant"] for p in proposals if p["category"] == cat]
        if ms:
            lines.append(f"    ({cat!r}, {ms!r}),")
    return "\n".join(lines)


def main(argv=()):
    args = [a for a in argv if not a.startswith("-")]
    if "--suggest-cats" not in argv:
        print(__doc__.strip().splitlines()[0])
        print(f"usage: python llm_cats.py --suggest-cats [{default_csv()}]")
        return
    if not enabled():
        print("LLM_URL / LLM_ENABLED not set - the local classifier is off "
              "(see docs/DEPLOY.md). Nothing to do.")
        return
    path = args[0] if args else default_csv()
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except FileNotFoundError:
        print(f"{path}: not found - run parse.py first, or pass the path as an argument.")
        return 1
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
    out = os.path.join(os.path.dirname(path), OUT) if os.path.dirname(path) else OUT
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["merchant", "category", "confidence", "n", "rm"])
        w.writeheader()
        w.writerows({k: p[k] for k in w.fieldnames} for p in props)
    print(f"wrote {out}: {len(props)} proposal(s). Nothing was applied.")
    if props:
        print(paste_block(props))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
