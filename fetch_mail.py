"""Fetch statement mail over IMAP and POST each PDF attachment to /ingest.

This is the last thing n8n was still doing: watch Gmail for statement mail and hand
the attachment onward. Gmail exposes labels as IMAP mailboxes, so the `CC` label is
just a mailbox to select, and `imaplib` + `email` are both stdlib — no dependency.

Run it on a schedule (cron, a k8s CronJob, whatever). It is a script, not a daemon:
no IDLE, no long-lived connection.

  python fetch_mail.py --dry-run    # list what it would fetch, touch nothing
  python fetch_mail.py

A message is marked \\Seen ONLY after every attachment in it ingested cleanly, so a
failure — or an unknown bank, or a mail with no PDF — stays unread and shows up again
next run. That is deliberate: a skipped mail nagging every run is how you notice it.

Env: GMAIL_USER, GMAIL_APP_PASSWORD (app password, needs 2FA), GMAIL_LABEL (CC),
INGEST_URL (http://localhost:8000/ingest), IMAP_HOST (imap.gmail.com),
APP_PASSWORD (only if the server has its password gate on - sent as X-App-Password).
"""
import email
import imaplib
import json
import os
import re
import sys
import urllib.request
import uuid
from email import policy

HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
LABEL = os.environ.get("GMAIL_LABEL", "CC")
INGEST_URL = os.environ.get("INGEST_URL", "http://localhost:8000/ingest")

# First match wins. Keys are the parser's bank keys (= the statement filename prefix);
# `sc` is Standard Chartered. Patterns are deliberately narrow: a misattributed
# statement parses against the wrong bank's rules and produces confidently wrong
# numbers, which is far worse than skipping it.
BANKS = (
    ("maybank", r"maybank"),
    ("cimb", r"cimb"),
    ("hsbc", r"hsbc"),
    ("rhb", r"\brhb"),
    ("alliance", r"\balliance"),
    ("sc", r"standard\s*-?\s*chartered|\bsc\.com\b"),
)


def detect_bank(text):
    """-> 'maybank'|'cimb'|'sc'|'alliance'|'hsbc'|'rhb', or None. Pure."""
    t = (text or "").lower()
    for bank, pat in BANKS:
        if re.search(pat, t):
            return bank
    return None


def _text(msg):
    """Every text/* part, decoded. Charset-safe, policy-independent."""
    out = []
    for part in msg.walk():
        if part.get_content_maintype() == "text":
            raw = part.get_payload(decode=True)
            if raw:
                out.append(raw.decode(part.get_content_charset() or "utf-8", "replace"))
    return "\n".join(out)


def bank_of(msg):
    """Sender, then subject, then body — most trustworthy first."""
    return (detect_bank(msg.get("From", ""))
            or detect_bank(msg.get("Subject", ""))
            or detect_bank(_text(msg)))


def pdf_attachments(msg):
    """[(filename, bytes)] — content type OR a .pdf name; some banks send octet-stream.

    The filename is for logging only. It arrived in an email: never build a path from
    it. /ingest names what it stores by content hash and ignores what we send.
    """
    out = []
    for part in msg.walk():
        name = part.get_filename() or ""
        if part.get_content_type() == "application/pdf" or name.lower().endswith(".pdf"):
            body = part.get_payload(decode=True)
            if body:
                out.append((name or "(unnamed).pdf", body))
    return out


def ingest(content, bank, url=None, timeout=600):
    """POST one PDF as multipart. Long timeout: /ingest reparses the whole corpus."""
    b = uuid.uuid4().hex
    # Filename is ours, not the mail's — the server ignores it, and a header built from
    # untrusted text is a quoting problem nobody needs.
    body = (
        f'--{b}\r\nContent-Disposition: form-data; name="bank"\r\n\r\n{bank}\r\n'
        f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{bank}.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + content + f"\r\n--{b}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={b}"}
    # If the server has its password gate on (APP_PASSWORD set, #51), /ingest needs
    # either a session cookie or this header. A cookie means a login dance and a cookie
    # jar; the header means one line and works the same in-process on the loopback and
    # standalone against a remote INGEST_URL. Unset here = gate off there, so nothing
    # is sent and nothing changes.
    if os.environ.get("APP_PASSWORD"):
        headers["X-App-Password"] = os.environ["APP_PASSWORD"]
    req = urllib.request.Request(url or INGEST_URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def handle(msg, dry=False, url=None):
    """Ingest every PDF in one message. -> (mark_seen, [log lines]).

    mark_seen is False unless everything ingested — including for the no-PDF and
    unknown-bank skips, so nothing quietly disappears into the read pile.
    """
    subj = (msg.get("Subject") or "")[:80]
    pdfs = pdf_attachments(msg)
    if not pdfs:
        return False, [f"skip: no PDF attachment: {subj}"]
    bank = bank_of(msg)
    if not bank:
        return False, [f"skip: bank not recognised: {subj}"]
    lines, ok = [], not dry
    for name, content in pdfs:
        if dry:
            lines.append(f"would ingest {bank}: {name} ({len(content)} bytes)")
            continue
        try:
            res = ingest(content, bank, url)
            warn = " WARNING " + json.dumps(res.get("problems")) if res.get("warning") else ""
            lines.append(f"ingested {bank}: {name} {json.dumps(res.get('recon'))}{warn}")
        except Exception as e:
            ok = False
            lines.append(f"FAILED {bank}: {name}: {e}")
    return ok, lines


def main(dry=False):
    # Off unless both are set, same as the reminders: a compose stack with the mail
    # half unconfigured should say so and exit 0, not crash-loop on a KeyError.
    user, password = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and password):
        print("GMAIL_USER / GMAIL_APP_PASSWORD not set - nothing to fetch")
        return
    seen = 0
    with imaplib.IMAP4_SSL(HOST) as M:
        M.login(user, password)
        # readonly on a dry run: the server cannot change a flag even if we ask.
        M.select(f'"{LABEL}"', readonly=dry)
        nums = M.search(None, "UNSEEN")[1][0].split()
        print(f"{LABEL}: {len(nums)} unread{' (dry run)' if dry else ''}")
        for n in nums:
            # PEEK — a plain FETCH sets \Seen by itself, which would defeat the retry.
            raw = M.fetch(n, "(BODY.PEEK[])")[1][0][1]
            msg = email.message_from_bytes(raw, policy=policy.default)
            mark, lines = handle(msg, dry)
            for line in lines:
                print(line, flush=True)
            if mark:
                M.store(n, "+FLAGS", "\\Seen")
                seen += 1
    print(f"marked {seen} message(s) seen")


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
