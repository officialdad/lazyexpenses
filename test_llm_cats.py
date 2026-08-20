"""Tests for llm_cats.py — the CATS-wins-first rule, the prompt, the constraint,
and what happens when the model is missing.

No server and no model: `classify` is the boundary that touches HTTP and no test
crosses it, exactly like IMAP lives only in fetch_mail.main().
"""
import contextlib
import io
import tempfile
import os
import urllib.error

import llm_cats
from llm_cats import (CATEGORIES, enabled, parse_response, paste_block, prompt,
                      response_format, suggest, taxonomy, unmatched)


def _row(desc, cat, amt="10.00"):
    return {"description": desc, "category": cat, "amount": amt, "type": "debit"}


def test_prompt_carries_the_taxonomy_not_just_the_names():
    p = prompt("K S S OTOMOBIL")
    assert [m["role"] for m in p] == ["system", "user"]
    user = p[1]["content"]
    assert "K S S OTOMOBIL" in user
    for cat in CATEGORIES:
        assert cat in user, cat                       # all 15 names
    assert "petrol, tolls, parking" in user           # the gloss
    assert "PETRONAS" in user and "SHOPEE" in user    # real examples lifted from CATS
    # examples are capped so a 300-keyword table does not become the prompt
    assert len(taxonomy().splitlines()) == 15


def test_the_schema_pins_the_answer_to_the_fifteen_categories():
    rf = response_format()
    schema = rf["json_schema"]["schema"]
    enum = schema["properties"]["category"]["enum"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert enum == CATEGORIES and len(enum) == 15
    # the model cannot invent a synonym, and cannot answer "Other" either
    assert "Food & Drink" not in enum and "Other" not in enum
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["category", "confidence"]
    assert schema["properties"]["confidence"]["enum"] == ["high", "medium", "low"]
    # and a caller may narrow it further, never widen it by accident
    assert response_format(["F&B"])["json_schema"]["schema"]["properties"]["category"]["enum"] == ["F&B"]


def _reply(content):
    return {"choices": [{"message": {"content": content}}]}


def test_parse_response_reads_a_constrained_reply():
    assert parse_response(_reply('{"category": "F&B", "confidence": "high"}')) == ("F&B", "high")


def test_parse_response_raises_on_anything_it_cannot_trust():
    for bad in (_reply("I think this is food, honestly"),          # not JSON
                _reply('{"category": "Food & Drink", "confidence": "high"}'),  # not a category
                _reply('{"category": "F&B"}'),                     # missing field
                {"error": "model not loaded"}):                    # not llama-server
        try:
            parse_response(bad)
        except Exception:
            continue
        raise AssertionError(f"accepted garbage: {bad}")


def test_unmatched_aggregates_distinct_merchants_by_normalized_name():
    rows = [_row("MINISO WINKY", "Other", "35.50"),          # first seen, smaller total
            _row("K S S OTOMOBIL 123456", "Other", "80.00"),
            _row("K S S OTOMOBIL 998877", "Other", "20.00")]
    got = {d["merchant"]: (d["n"], d["rm"]) for d in unmatched(rows)}
    # the trailing reference token is noise to a classifier — norm_merchant strips it
    assert got == {"K S S OTOMOBIL": (2, 100.0), "MINISO WINKY": (1, 35.5)}
    assert [d["merchant"] for d in unmatched(rows)][0] == "K S S OTOMOBIL"   # biggest RM first


def test_cats_wins_first_and_never_generates_a_request():
    rows = [_row("PETRONAS STN KLANG", "Vehicle"),          # keyword hit
            _row("NETFLIX.COM", "Subscriptions"),           # keyword hit
            # a keyword hit mislabelled Other in the CSV is STILL not asked about:
            # CATS is re-run here and it is the only gate on what reaches the model
            _row("STARBUCKS KLCC", "Other"),
            _row("DOMINOS MALAYSIA", "Other")]              # the one CATS gave up on
    assert [d["merchant"] for d in unmatched(rows)] == ["DOMINOS MALAYSIA"]

    calls = []
    real = llm_cats.classify
    llm_cats.classify = lambda m, url=None, model=None: calls.append(m) or ("F&B", "high")
    try:
        props, notes = suggest(unmatched(rows))
    finally:
        llm_cats.classify = real
    assert calls == ["DOMINOS MALAYSIA"], calls      # one request, for one merchant
    assert len(calls) == 1 and notes == []
    assert props[0]["category"] == "F&B" and props[0]["confidence"] == "high"


def test_an_unreachable_server_completes_the_run_and_leaves_the_rest_other():
    tried = []

    def refused(m, url=None, model=None):
        tried.append(m)
        raise urllib.error.URLError("Connection refused")

    real = llm_cats.classify
    llm_cats.classify = refused
    try:
        props, notes = suggest([{"merchant": "A", "n": 1, "rm": 1.0},
                                {"merchant": "B", "n": 1, "rm": 1.0}])
    finally:
        llm_cats.classify = real
    assert props == []                        # nothing proposed, nothing raised
    assert tried == ["A"]                     # a dead port is not retried per merchant
    assert len(notes) == 1 and "unreachable" in notes[0] and "left as Other" in notes[0]


def test_one_garbage_answer_only_costs_that_merchant():
    def flaky(m, url=None, model=None):
        if m == "A":
            raise ValueError("not a category: 'Vibes'")
        return ("Shopping", "low")

    real = llm_cats.classify
    llm_cats.classify = flaky
    try:
        props, notes = suggest([{"merchant": "A", "n": 1, "rm": 1.0},
                                {"merchant": "B", "n": 1, "rm": 1.0}])
    finally:
        llm_cats.classify = real
    assert [p["merchant"] for p in props] == ["B"]        # the run completed
    assert any("skipped A" in n for n in notes) and any("stay Other" in n for n in notes)


def test_off_unless_configured():
    keep = {k: os.environ.pop(k, None) for k in ("LLM_URL", "LLM_ENABLED")}
    try:
        assert enabled() is False                    # no config at all: feature absent
        os.environ["LLM_URL"] = "http://localhost:8080"
        assert enabled() is True
        os.environ["LLM_ENABLED"] = "0"              # explicit off wins over a set URL
        assert enabled() is False
        del os.environ["LLM_URL"]
        os.environ["LLM_ENABLED"] = "1"
        assert enabled() is True
    finally:
        for k, v in keep.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def test_paste_block_is_keywords_grouped_in_cats_order():
    block = paste_block([{"merchant": "MINISO WINKY", "category": "Shopping"},
                         {"merchant": "DOMINOS MALAYSIA", "category": "F&B"},
                         {"merchant": "KEDAI KOPI X", "category": "F&B"}])
    lines = block.splitlines()
    assert lines[0].startswith("#")
    assert lines[1:] == ["    ('F&B', ['DOMINOS MALAYSIA', 'KEDAI KOPI X']),",
                         "    ('Shopping', ['MINISO WINKY']),"], lines


def test_default_csv_follows_data_dir_so_the_container_finds_it():
    # `docker exec` lands in /app, but the pipeline writes transactions.csv to
    # DATA_DIR. Guessing cwd there is how the documented command came up empty.
    old = os.environ.pop("DATA_DIR", None)
    try:
        assert llm_cats.default_csv() == "transactions.csv"
        os.environ["DATA_DIR"] = "/data"
        assert llm_cats.default_csv() == "/data/transactions.csv"
    finally:
        os.environ.pop("DATA_DIR", None)
        if old is not None:
            os.environ["DATA_DIR"] = old


def test_a_missing_csv_is_one_line_not_a_traceback():
    env = {"LLM_ENABLED": "1", "LLM_URL": "http://127.0.0.1:9", "DATA_DIR": tempfile.mkdtemp()}
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = llm_cats.main(["--suggest-cats"])
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    assert rc == 1, rc
    assert "not found" in buf.getvalue(), buf.getvalue()
    assert "Traceback" not in buf.getvalue()



if __name__ == "__main__":
    test_prompt_carries_the_taxonomy_not_just_the_names()
    test_the_schema_pins_the_answer_to_the_fifteen_categories()
    test_parse_response_reads_a_constrained_reply()
    test_parse_response_raises_on_anything_it_cannot_trust()
    test_unmatched_aggregates_distinct_merchants_by_normalized_name()
    test_cats_wins_first_and_never_generates_a_request()
    test_an_unreachable_server_completes_the_run_and_leaves_the_rest_other()
    test_one_garbage_answer_only_costs_that_merchant()
    test_off_unless_configured()
    test_paste_block_is_keywords_grouped_in_cats_order()
    test_default_csv_follows_data_dir_so_the_container_finds_it()
    test_a_missing_csv_is_one_line_not_a_traceback()
    print("OK")
