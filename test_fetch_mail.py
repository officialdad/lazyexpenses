"""Tests for fetch_mail.py — bank detection + the attachment walk + the mark-seen rule.
/ingest is stubbed and IMAP is never touched; no test needs a mailbox or a server."""
from email.message import EmailMessage

import fetch_mail
from fetch_mail import bank_of, detect_bank, handle, pdf_attachments


def _msg(frm="", subj="", body="", pdfs=(), ctype="application/pdf"):
    m = EmailMessage()
    m["From"], m["Subject"] = frm, subj
    m.set_content(body)
    for name, data in pdfs:
        maint, _, sub = ctype.partition("/")
        m.add_attachment(data, maintype=maint, subtype=sub, filename=name)
    return m


def test_detect_bank_across_the_six():
    cases = {
        "eStatement@maybank2u.com.my": "maybank",
        "no-reply@cimb.com.my": "cimb",
        "Standard Chartered Bank Malaysia": "sc",
        "estatement@sc.com": "sc",
        "AllianceOnline <ebanking@alliancebank.com.my>": "alliance",
        "HSBC Bank Malaysia": "hsbc",
        "RHB Now <ecare@rhbgroup.com>": "rhb",
    }
    for text, want in cases.items():
        assert detect_bank(text) == want, (text, detect_bank(text))


def test_no_match_returns_none_rather_than_guessing():
    for text in ("", None, "Your Netflix receipt", "Public Bank statement"):
        assert detect_bank(text) is None, text


def test_sender_outranks_subject_and_subject_outranks_body():
    assert bank_of(_msg(frm="x@cimb.com.my", subj="hsbc", body="rhb")) == "cimb"
    assert bank_of(_msg(frm="noreply@example.com", subj="Your HSBC eStatement",
                        body="rhb")) == "hsbc"
    assert bank_of(_msg(body="Your RHB credit card statement is ready")) == "rhb"
    assert bank_of(_msg(frm="a@b.com", subj="statement", body="nothing here")) is None


def test_attachment_walk_finds_pdfs_by_type_and_by_name():
    m = _msg(pdfs=[("stmt.pdf", b"%PDF-1.4 one")])
    assert pdf_attachments(m) == [("stmt.pdf", b"%PDF-1.4 one")]
    # some banks send the PDF as octet-stream; the .pdf name is the only clue
    m = _msg(pdfs=[("stmt.pdf", b"%PDF-1.4 two")], ctype="application/octet-stream")
    assert pdf_attachments(m) == [("stmt.pdf", b"%PDF-1.4 two")]
    # and a mail with no attachment yields nothing rather than the body
    assert pdf_attachments(_msg(body="no attachment here")) == []


def test_handle_ingests_every_pdf_and_marks_seen():
    calls = []
    real = fetch_mail.ingest
    fetch_mail.ingest = lambda c, b, url=None: calls.append((b, c)) or {"recon": {"VERIFIED": 1}}
    try:
        m = _msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A"), ("b.pdf", b"B")])
        mark, lines = handle(m)
        assert mark is True, lines
        assert calls == [("cimb", b"A"), ("cimb", b"B")], calls
    finally:
        fetch_mail.ingest = real


def test_a_failed_ingest_leaves_the_message_unread():
    real = fetch_mail.ingest

    def boom(c, b, url=None):
        raise RuntimeError("connection refused")

    fetch_mail.ingest = boom
    try:
        mark, lines = handle(_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]))
        assert mark is False
        assert "connection refused" in lines[0]
    finally:
        fetch_mail.ingest = real


def test_skips_never_mark_seen_and_never_ingest():
    real = fetch_mail.ingest

    def boom(c, b, url=None):
        raise AssertionError("must not ingest")

    fetch_mail.ingest = boom
    try:
        # unknown bank: skipping beats posting it against the wrong bank's rules
        mark, lines = handle(_msg(frm="a@b.com", pdfs=[("a.pdf", b"A")]))
        assert mark is False and "bank not recognised" in lines[0]
        # no attachment
        mark, lines = handle(_msg(frm="x@cimb.com.my", body="marketing"))
        assert mark is False and "no PDF attachment" in lines[0]
        # dry run posts nothing and leaves the flag alone
        mark, lines = handle(_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]), dry=True)
        assert mark is False and lines == ["would ingest cimb: a.pdf (1 bytes)"], lines
    finally:
        fetch_mail.ingest = real


if __name__ == "__main__":
    test_detect_bank_across_the_six()
    test_no_match_returns_none_rather_than_guessing()
    test_sender_outranks_subject_and_subject_outranks_body()
    test_attachment_walk_finds_pdfs_by_type_and_by_name()
    test_handle_ingests_every_pdf_and_marks_seen()
    test_a_failed_ingest_leaves_the_message_unread()
    test_skips_never_mark_seen_and_never_ingest()
    print("OK")
