"""Plain-assert tests for password-protected PDF parsing (parse.pw_for + open sites).

Builds a tiny PDF by hand (no reportlab), encrypts it with pypdf, and asserts the
locked file reads identically to its unlocked twin. pypdf is test-only: without it
the encryption cases are skipped and the rest still runs.

Run: python tests/test_parse_password.py   ->  OK
"""
import csv, io, os, tempfile, parse

MARK = "STATEMENT BALANCE 1,234.56"


def _minimal_pdf(text=MARK):
    """Smallest valid single-page PDF containing `text`. Offsets computed, not guessed."""
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, xref)
    return bytes(out)


def _recon_row(src):
    """parse.main() over one source dir, in a scratch cwd. -> its single recon row.

    main() writes its CSVs to the working directory, so it gets one of its own.
    """
    cwd, osrc, ocache = os.getcwd(), parse.SRC, parse.CACHE
    try:
        with tempfile.TemporaryDirectory() as out:
            parse.SRC, parse.CACHE = src, os.path.join(out, "cache")
            os.chdir(out)
            parse.main()
            with open("reconciliation.csv", encoding="utf-8-sig") as fh:
                return next(csv.DictReader(fh))
    finally:
        os.chdir(cwd)
        parse.SRC, parse.CACHE = osrc, ocache


def main():
    plain = _minimal_pdf()

    with tempfile.TemporaryDirectory() as d:
        # pw_for keys off the filename prefix, exactly like parse_statement's bank
        p = os.path.join(d, "maybank_x.pdf")
        os.environ.pop("CC_PW_MAYBANK", None)
        assert parse.pw_for(p) is None, "unset env must give None, not ''"
        os.environ["CC_PW_MAYBANK"] = "s3cret"
        assert parse.pw_for(p) == "s3cret"
        assert parse.pw_for(os.path.join(d, "hsbc_y.pdf")) is None, "wrong bank must not leak"

        # a password handed to an UNencrypted PDF is ignored -> one code path for both
        open(p, "wb").write(plain)
        assert MARK.split()[0] in parse.full_text(p)
        assert parse.all_rows(p), "row reconstruction must work on the unlocked file"

        try:
            import pypdf
        except ImportError:
            print("SKIP encryption cases (pypdf not installed)")
            print("OK")
            return

        unlocked_text = parse.full_text(p)
        for algo in ("RC4-128", "AES-128", "AES-256"):
            w = pypdf.PdfWriter(clone_from=io.BytesIO(plain))
            w.encrypt("s3cret", algorithm=algo)
            locked = os.path.join(d, "maybank_locked.pdf")
            w.write(locked)
            assert parse.full_text(locked) == unlocked_text, f"{algo}: locked != unlocked twin"
            assert parse.all_rows(locked), f"{algo}: no rows"

            # wrong password must fail loudly, not silently return empty rows
            os.environ["CC_PW_MAYBANK"] = "wrong"
            try:
                parse.full_text(locked)
            except Exception:
                pass
            else:
                raise AssertionError(f"{algo}: wrong password should not open the file")
            os.environ["CC_PW_MAYBANK"] = "s3cret"

        # ...and the ERROR row parse.main() writes for it names the exception and the
        # bank (#93). str() of the PdfminerException wrapping PDFPasswordIncorrect is
        # EMPTY, so the one cell holding the reason used to be blank, under bank '?'.
        src = os.path.join(d, "src")
        os.makedirs(src)
        w = pypdf.PdfWriter(clone_from=io.BytesIO(plain))
        w.encrypt("s3cret", algorithm="AES-128")
        w.write(os.path.join(src, "maybank_x.pdf"))
        os.environ["CC_PW_MAYBANK"] = "wrong"
        row = _recon_row(src)
        assert row["status"] == "ERROR", row
        assert row["bank"] == "maybank", "the bank comes from the filename, not '?'"
        assert row["sdate"].split(":")[0].isidentifier() and row["sdate"], (
            f"the ERROR row must name its exception type, got {row['sdate']!r}")

    print("OK")


if __name__ == "__main__":
    main()
