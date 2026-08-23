"""Tests for fetch_mail.py — bank detection + the attachment walk + the mark-seen rule.
/ingest is stubbed and IMAP is never touched; no test needs a mailbox or a server."""
import imaplib
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


class _FakeIMAP:
    """The four IMAP calls main() makes, and a record of what it asked for."""

    def __init__(self, msgs):
        self.raw = [m.as_bytes() for m in msgs]
        self.selected = self.criteria = None
        self.stored = []
        self.fetched = []

    def __call__(self, host):        # stands in for imaplib.IMAP4_SSL(host)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, user, password):
        pass

    def select(self, mailbox, readonly=False):
        self.selected = (mailbox, readonly)

    def search(self, charset, criteria):
        self.criteria = criteria
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.raw)))]

    def fetch(self, num, spec):
        self.fetched.append(spec)
        return "OK", [(num, self.raw[int(num) - 1], b")")]

    def store(self, num, flag, value):
        self.stored.append((num, flag, value))


def _run(msgs, **kw):
    """main() against a fake mailbox. -> (fake connection, stat dict)."""
    fake = _FakeIMAP(msgs)
    real_imap, real_creds, real_ingest = imaplib.IMAP4_SSL, fetch_mail.creds, fetch_mail.ingest
    imaplib.IMAP4_SSL = fake
    fetch_mail.creds = lambda: ("me@example.com", "app-pw", "CC", "imap.example.com")
    fetch_mail.ingest = lambda c, b, url=None: {"recon": {"VERIFIED": 1}}
    try:
        return fake, fetch_mail.main(**kw)
    finally:
        imaplib.IMAP4_SSL, fetch_mail.creds, fetch_mail.ingest = real_imap, real_creds, real_ingest


def test_the_polling_pass_is_unseen_writable_and_marks_seen():
    msgs = [_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]),
            _msg(frm="y@hsbc.com.my", pdfs=[("b.pdf", b"B")])]
    fake, stat = _run(msgs)
    assert fake.criteria == "UNSEEN"
    assert fake.selected == ('"CC"', False)          # writable: the retry flag is ours
    assert len(fake.stored) == 2 and fake.stored[0][1:] == ("+FLAGS", "\\Seen")
    assert (stat["total"], stat["ingested"], stat["skipped"], stat["failed"]) == (2, 2, 0, 0)


def test_a_backfill_searches_all_selects_readonly_and_never_marks_seen():
    """THE constraint of #91. \\Seen is the polling loop's retry signal, and setting it
    across a year of mail cannot be undone — so a backfill must not write it, and must
    not even be able to: the mailbox is selected readonly."""
    msgs = [_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]) for _ in range(3)]
    fake, stat = _run(msgs, criteria="ALL")
    assert fake.criteria == "ALL"
    assert fake.selected == ('"CC"', True)
    assert fake.stored == []                          # nothing marked, ever
    assert all(spec == "(BODY.PEEK[])" for spec in fake.fetched)
    assert stat["ingested"] == 3 and stat["total"] == 3


def test_a_backfill_counts_and_names_the_mail_it_could_not_place():
    """No unread pile to nag from, so an unknown bank is visible exactly once."""
    msgs = [_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]),
            _msg(frm="a@b.com", subj="Your statement", pdfs=[("b.pdf", b"B")]),
            _msg(frm="y@rhbgroup.com", subj="newsletter")]
    fake, stat = _run(msgs, criteria="ALL")
    assert stat["unknown"] == ["Your statement"], stat["unknown"]
    assert (stat["ingested"], stat["skipped"], stat["failed"]) == (1, 2, 0)
    assert fake.stored == []


def test_a_dry_run_stays_readonly_whatever_the_criteria():
    fake, stat = _run([_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")])], dry=True)
    assert fake.selected == ('"CC"', True) and fake.stored == []
    assert stat["ingested"] == 1                      # "would ingest" counts as one


if __name__ == "__main__":
    test_detect_bank_across_the_six()
    test_no_match_returns_none_rather_than_guessing()
    test_sender_outranks_subject_and_subject_outranks_body()
    test_attachment_walk_finds_pdfs_by_type_and_by_name()
    test_handle_ingests_every_pdf_and_marks_seen()
    test_a_failed_ingest_leaves_the_message_unread()
    test_skips_never_mark_seen_and_never_ingest()
    test_the_polling_pass_is_unseen_writable_and_marks_seen()
    test_a_backfill_searches_all_selects_readonly_and_never_marks_seen()
    test_a_backfill_counts_and_names_the_mail_it_could_not_place()
    test_a_dry_run_stays_readonly_whatever_the_criteria()
    print("OK")
