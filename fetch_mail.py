"""Fetch statement mail over IMAP and POST each PDF attachment to /ingest.

Watch Gmail for statement mail and hand the attachment onward. Gmail exposes labels as
IMAP mailboxes, so the `CC` label is a mailbox to select, and `imaplib` + `email` are
both stdlib — no dependency.

Run it on a schedule (cron, a k8s CronJob, whatever). It is a script, not a daemon:
no IDLE, no long-lived connection.

  python fetch_mail.py --dry-run    # list what it would fetch, touch nothing
  python fetch_mail.py
  python fetch_mail.py --all        # one-time backfill: the WHOLE label, read or not

A message is marked \\Seen ONLY after every attachment in it ingested cleanly, so a
failure — or an unknown bank, or a mail with no PDF — stays unread and shows up again
next run. That is deliberate: a skipped mail nagging every run is how you notice it.

A BACKFILL (#91) NEVER MARKS ANYTHING SEEN, and selects the mailbox readonly so the
server would refuse the write even if asked. That flag IS the retry signal above;
setting it across a year of mail erases it and there is no way to get it back from
here. A backfill needs no dedupe of its own either — /ingest names what it stores by
content hash, so re-posting a statement it already holds changes nothing.

Env: GMAIL_USER, GMAIL_APP_PASSWORD (app password, needs 2FA), GMAIL_LABEL (CC),
INGEST_URL (http://localhost:8000/ingest), IMAP_HOST (imap.gmail.com),
APP_PASSWORD (only if the server has its password gate on - sent as X-App-Password).

Since #40 the first four may equally come from the Settings UI, via settings.json on the
volume - settings.get() is env-first, so nothing changes for an existing .env deployment.
They are read PER CALL rather than at import, because the loop in server/app.py runs for
weeks and the values can be typed in at any point during that.
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

from server import settings   # stdlib-only; importing it does not make this a daemon

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


def _res(kind, line, bank="", locked=False):
    return {"kind": kind, "line": line, "bank": bank, "locked": locked}


def handle(msg, dry=False, url=None):
    """Ingest every PDF in one message. -> (mark_seen, [results]).

    A result is {"kind": "ingested"|"failed"|"skipped", "line", "bank", "locked"}. The
    caller counts `kind` and never re-reads `line`: a statement that lands but does not
    parse still logs an "ingested ..." line, and classifying by that prefix counted it
    as a success and marked the mail \\Seen, so it was never retried (#93). The line
    text itself is unchanged — existing log greps still hold.

    mark_seen is False unless everything ingested — including for the no-PDF and
    unknown-bank skips, so nothing quietly disappears into the read pile.
    """
    subj = (msg.get("Subject") or "")[:80]
    pdfs = pdf_attachments(msg)
    if not pdfs:
        return False, [_res("skipped", f"skip: no PDF attachment: {subj}")]
    bank = bank_of(msg)
    if not bank:
        return False, [_res("skipped", f"skip: bank not recognised: {subj}")]
    out, ok = [], not dry
    for name, content in pdfs:
        if dry:
            out.append(_res("ingested",
                            f"would ingest {bank}: {name} ({len(content)} bytes)", bank))
            continue
        try:
            res = ingest(content, bank, url)
            warn = " WARNING " + json.dumps(res.get("problems")) if res.get("warning") else ""
            line = f"ingested {bank}: {name} {json.dumps(res.get('recon'))}{warn}"
            if res.get("warning"):
                # Stored, but the recon says it did not parse. That is a failure: the
                # retry flag must stay, and `locked` says whether the fix is a password.
                ok = False
                out.append(_res("failed", line, bank, bool(res.get("locked"))))
            else:
                out.append(_res("ingested", line, bank))
        except Exception as e:
            ok = False
            out.append(_res("failed", f"FAILED {bank}: {name}: {e}", bank))
    return ok, out


def creds():
    """(user, app password, label, imap host) — env first, then the Settings UI (#40).
    Resolved per call: the server's fetch loop runs for weeks and these can be typed in
    at any point during that, which is the whole point of not reading them at import."""
    return (settings.get("GMAIL_USER"), settings.get("GMAIL_APP_PASSWORD"),
            settings.get("GMAIL_LABEL", "CC"), settings.get("IMAP_HOST", "imap.gmail.com"))


def _login(M, user, password):
    """Log in, and say which credential was rejected rather than echoing the protocol."""
    try:
        M.login(user, password)
    except Exception as e:
        if "AUTHENTICATIONFAILED" in str(e):
            raise RuntimeError("Gmail rejected that address or app password.") from None
        raise


def _select(M, label, readonly):
    """Select the label, or say the label is missing (#93).

    imaplib.select() does NOT raise on a missing mailbox: it returns ('NO', ...) and
    leaves the connection in state AUTH, so the *next* call is what blows up, with
    `command SEARCH illegal in state AUTH` — and that is what the Settings UI showed.
    """
    typ, _ = M.select(f'"{label}"', readonly=readonly)
    if typ != "OK":
        raise RuntimeError(f'No label named "{label}" in that mailbox. '
                           "Check the exact spelling in Gmail — labels are case-sensitive.")


def check():
    """Log in, select the label, count the unread — and nothing else (#40).

    This is the Settings "Test connection" button. readonly=True so the server cannot
    change a flag even if asked: a test must never consume a statement mail."""
    user, password, label, host = creds()
    if not (user and password):
        raise RuntimeError("Gmail address and app password are not set")
    with imaplib.IMAP4_SSL(host) as M:
        _login(M, user, password)
        _select(M, label, True)
        return {"ok": True, "user": user, "label": label,
                "unread": len(M.search(None, "UNSEEN")[1][0].split())}


def main(dry=False, criteria="UNSEEN", stat=None):
    """Fetch every mail matching `criteria` and ingest its PDFs. -> the counts dict.

    `criteria` is the IMAP search: "UNSEEN" is the polling loop, "ALL" is the one-time
    backfill (#91). Anything other than "UNSEEN" is a backfill and is READONLY — see
    the module docstring for why that flag must not be written across old mail.

    `stat` is an optional dict to fill in place, so a caller watching from another
    thread (the server's backfill route) can read progress while this runs. It is the
    return value either way.
    """
    # Off unless both are set, same as the reminders: a compose stack with the mail
    # half unconfigured should say so and exit 0, not crash-loop on a KeyError.
    user, password, LABEL, host = creds()
    stat = {} if stat is None else stat
    stat.update(total=0, done=0, ingested=0, skipped=0, failed=0, unknown=[], locked=[])
    if not (user and password):
        print("GMAIL_USER / GMAIL_APP_PASSWORD not set - nothing to fetch")
        return stat
    # readonly on a dry run AND on a backfill: the server cannot change a flag even if
    # we ask. Only the UNSEEN pass is allowed to consume mail.
    readonly = dry or criteria != "UNSEEN"
    seen, locked = 0, set()
    with imaplib.IMAP4_SSL(host) as M:
        _login(M, user, password)
        _select(M, LABEL, readonly)
        nums = M.search(None, criteria)[1][0].split()
        stat["total"] = len(nums)
        print(f"{LABEL}: {len(nums)} message(s) matching {criteria}"
              f"{' (dry run)' if dry else ''}")
        for n in nums:
            # PEEK — a plain FETCH sets \Seen by itself, which would defeat the retry.
            raw = M.fetch(n, "(BODY.PEEK[])")[1][0][1]
            msg = email.message_from_bytes(raw, policy=policy.default)
            mark, results = handle(msg, dry)
            for r in results:
                print(r["line"], flush=True)
                stat[r["kind"]] += 1
                if r["locked"]:
                    locked.add(r["bank"])
                    stat["locked"] = sorted(locked)   # visible while a backfill runs
            if any(r["line"].startswith("skip: bank not recognised") for r in results):
                stat["unknown"].append((msg.get("Subject") or "(no subject)")[:120])
            stat["done"] += 1
            if mark and not readonly:
                M.store(n, "+FLAGS", "\\Seen")
                seen += 1
    # A backfill has no unread pile to nag from, so an unrecognised bank is visible
    # exactly once — here. Print it rather than leave it silently uningested.
    if stat["unknown"]:
        print(f"{len(stat['unknown'])} mail(s) with no recognised bank, nothing ingested:")
        for subj in stat["unknown"]:
            print(f"  {subj}", flush=True)
    print(f"marked {seen} message(s) seen")
    return stat


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv,
         criteria="ALL" if "--all" in sys.argv else "UNSEEN")
