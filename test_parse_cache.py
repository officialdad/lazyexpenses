"""Plain-assert tests for parse.cached_parse (the per-PDF memo). No real PDF / pdfplumber.

Monkeypatches parse_statement so we test the cache wrapper in isolation:
hit/miss, content-hash key, filename re-derivation, version-bust, corrupt-entry fallback.
"""
import os, json, tempfile, parse

calls = {"n": 0}


def fake_parse_statement(path):
    calls["n"] += 1
    # mimic the real shape; 'file' is the basename (cached_parse must re-derive it)
    return ({"file": os.path.basename(path), "bank": "x", "n": 1}, [{"a": 1.5, "credit": False}])


def main():
    parse.parse_statement = fake_parse_statement
    with tempfile.TemporaryDirectory() as d:
        parse.CACHE = os.path.join(d, "cache")
        pdf = os.path.join(d, "maybank_aaa.pdf")
        with open(pdf, "wb") as fh:
            fh.write(b"%PDF fake bytes")

        # miss then hit: second call must NOT reparse
        m1, t1 = parse.cached_parse(pdf)
        assert calls["n"] == 1
        m2, t2 = parse.cached_parse(pdf)
        assert calls["n"] == 1, "second call should hit cache"
        assert (m1, t1) == (m2, t2)

        # same bytes under a different filename -> cache hit, but 'file' re-derived
        pdf2 = os.path.join(d, "maybank_bbb.pdf")
        with open(pdf2, "wb") as fh:
            fh.write(b"%PDF fake bytes")
        m3, _ = parse.cached_parse(pdf2)
        assert calls["n"] == 1, "identical content must reuse the cache entry"
        assert m3["file"] == "maybank_bbb.pdf", "file must reflect the current path, not the cached one"

        # locate the single cache file (content-addressed)
        cf = os.path.join(parse.CACHE, os.listdir(parse.CACHE)[0])

        # stale parser version -> reparse + rewrite with current ver
        with open(cf) as fh:
            c = json.load(fh)
        c["ver"] = "STALE"
        with open(cf, "w") as fh:
            json.dump(c, fh)
        parse.cached_parse(pdf)
        assert calls["n"] == 2, "version mismatch must reparse"
        assert json.load(open(cf))["ver"] == parse.PARSE_VER, "stale entry must be rewritten"

        # corrupt entry -> reparse, no crash
        with open(cf, "w") as fh:
            fh.write("{ not json")
        parse.cached_parse(pdf)
        assert calls["n"] == 3, "corrupt entry must reparse"
        json.load(open(cf))  # valid JSON again

    print("OK")


if __name__ == "__main__":
    main()
