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
        mark, results = handle(m)
        assert mark is True, results
        assert [r["kind"] for r in results] == ["ingested", "ingested"], results
        assert calls == [("cimb", b"A"), ("cimb", b"B")], calls
    finally:
        fetch_mail.ingest = real


def test_a_failed_ingest_leaves_the_message_unread():
    real = fetch_mail.ingest

    def boom(c, b, url=None):
        raise RuntimeError("connection refused")

    fetch_mail.ingest = boom
    try:
        mark, results = handle(_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]))
        assert mark is False
        assert results[0]["kind"] == "failed", results
        assert "connection refused" in results[0]["line"]
    finally:
        fetch_mail.ingest = real


def test_skips_never_mark_seen_and_never_ingest():
    real = fetch_mail.ingest

    def boom(c, b, url=None):
        raise AssertionError("must not ingest")

    fetch_mail.ingest = boom
    try:
        # unknown bank: skipping beats posting it against the wrong bank's rules
        mark, results = handle(_msg(frm="a@b.com", pdfs=[("a.pdf", b"A")]))
        assert mark is False and results[0]["kind"] == "skipped"
        assert "bank not recognised" in results[0]["line"]
        # no attachment
        mark, results = handle(_msg(frm="x@cimb.com.my", body="marketing"))
        assert mark is False and results[0]["kind"] == "skipped"
        assert "no PDF attachment" in results[0]["line"]
        # dry run posts nothing and leaves the flag alone
        mark, results = handle(_msg(frm="x@cimb.com.my", pdfs=[("a.pdf", b"A")]), dry=True)
        assert mark is False and len(results) == 1, results
        assert results[0]["line"] == "would ingest cimb: a.pdf (1 bytes)", results
    finally:
        fetch_mail.ingest = real


class _FakeIMAP:
    """The four IMAP calls main() makes, and a record of what it asked for."""

    def __init__(self, msgs, select_typ="OK"):
        self.raw = [m.as_bytes() for m in msgs]
        self.selected = self.criteria = None
        self.select_typ = select_typ
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
        # imaplib returns a status; on a missing mailbox it is NO and it does NOT raise
        return self.select_typ, [b"1" if self.select_typ == "OK" else b"[NONEXISTENT]"]

    def search(self, charset, criteria):
        self.criteria = criteria
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.raw)))]

    def fetch(self, num, spec):
        self.fetched.append(spec)
        return "OK", [(num, self.raw[int(num) - 1], b")")]

    def store(self, num, flag, value):
        self.stored.append((num, flag, value))


def _run(msgs, ingest=None, **kw):
    """main() against a fake mailbox. -> (fake connection, stat dict)."""
    fake = _FakeIMAP(msgs)
    real_imap, real_creds, real_ingest = imaplib.IMAP4_SSL, fetch_mail.creds, fetch_mail.ingest
    imaplib.IMAP4_SSL = fake
    fetch_mail.creds = lambda: ("me@example.com", "app-pw", "CC", "imap.example.com")
    fetch_mail.ingest = ingest or (lambda c, b, url=None: {"recon": {"VERIFIED": 1}})
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


def test_a_warning_response_is_a_failure_and_keeps_the_retry_flag():
    """#93. The PDF landed and did not parse, so /ingest answers `warning: true` — but
    the log line still begins "ingested", and classifying on that prefix counted it as a
    success and marked the mail \\Seen. Nothing ever retried it."""
    def warned(c, b, url=None):
        return {"recon": {"ERROR": 1}, "problems": {"ERROR": 1},
                "warning": True, "locked": True}

    real = fetch_mail.ingest
    fetch_mail.ingest = warned
    try:
        mark, results = handle(_msg(frm="x@maybank2u.com.my", pdfs=[("a.pdf", b"A")]))
        assert mark is False, "a warning must not mark the mail seen"
        assert results[0]["kind"] == "failed", results
        assert results[0]["locked"] is True and results[0]["bank"] == "maybank", results
        assert results[0]["line"].startswith("ingested maybank: a.pdf"), results[0]["line"]
        assert "WARNING" in results[0]["line"]        # log text byte-identical
    finally:
        fetch_mail.ingest = real

    fake, stat = _run([_msg(frm="x@maybank2u.com.my", pdfs=[("a.pdf", b"A")])],
                      ingest=warned)
    assert (stat["ingested"], stat["failed"]) == (0, 1), stat
    assert stat["locked"] == ["maybank"], stat
    assert fake.stored == [], "a statement that did not parse must stay unread"


def test_a_missing_label_says_so_instead_of_the_imap_state_error():
    """imaplib.select() returns ('NO', ...) and leaves the connection in AUTH, so the
    search that follows raised `command SEARCH illegal in state AUTH` — the UI showed
    that instead of the spelling mistake that caused it."""
    fake = _FakeIMAP([], select_typ="NO")
    real_imap, real_creds = imaplib.IMAP4_SSL, fetch_mail.creds
    imaplib.IMAP4_SSL = fake
    fetch_mail.creds = lambda: ("me@example.com", "app-pw", "Cc", "imap.example.com")
    try:
        for call in (fetch_mail.check, fetch_mail.main):
            try:
                call()
            except RuntimeError as e:
                assert 'No label named "Cc"' in str(e), e
                assert "case-sensitive" in str(e), e
            else:
                raise AssertionError(f"{call.__name__} must raise on a missing label")
    finally:
        imaplib.IMAP4_SSL, fetch_mail.creds = real_imap, real_creds


def test_a_rejected_login_names_the_credential():
    fake = _FakeIMAP([])
    fake.login = lambda u, p: (_ for _ in ()).throw(
        imaplib.IMAP4.error("b'[AUTHENTICATIONFAILED] Invalid credentials (Failure)'"))
    real_imap, real_creds = imaplib.IMAP4_SSL, fetch_mail.creds
    imaplib.IMAP4_SSL = fake
    fetch_mail.creds = lambda: ("me@example.com", "nope", "CC", "imap.example.com")
    try:
        try:
            fetch_mail.check()
        except RuntimeError as e:
            assert str(e) == "Gmail rejected that address or app password.", e
        else:
            raise AssertionError("a rejected login must be a sentence, not a protocol dump")
    finally:
        imaplib.IMAP4_SSL, fetch_mail.creds = real_imap, real_creds


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
    test_a_warning_response_is_a_failure_and_keeps_the_retry_flag()
    test_a_missing_label_says_so_instead_of_the_imap_state_error()
    test_a_rejected_login_names_the_credential()
    print("OK")
