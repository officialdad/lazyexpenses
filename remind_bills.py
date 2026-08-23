"""Bill reminders: which bills are due soon, and who to tell about them.

Two ways in, same logic:
  - `python remind_bills.py` — standalone, reads /bills over HTTP, for cron or a
    machine that is not running the server.
  - `server.app` calls run() on a timer, reading the PVC directly (no self-HTTP).

TWO TRANSPORTS, ONE MESSAGE PER BILL (#39). Web Push is the default and needs no
configuration at all — the keypair and the browser subscriptions live on the volume.
Telegram is the fallback and behaves exactly as it always has when its two variables
are set. send() fans out to whichever are configured; the per-bill state file is keyed
by bill, NOT by transport, so having both does not double up.

At most ONE message per bill (bank+statement_month), tracked in a state file next to
paid.json/waivers.json — so a second run in the same day sends nothing, and a server
restart cannot re-send.

TWO EVENTS PER BILL (#83). run() says "this is due soon"; announce() says "this arrived",
the moment /ingest turns a statement into a new bills[] entry. Same transports, same
state file, DIFFERENT key namespace (`arrived|<bank>|<month>`) — see ARRIVED_PREFIX.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BILLS_URL, PAID_URL, REMIND_STATE,
REMIND_DAYS, REMIND_TEMPLATE. Since #40 everything but the two URLs and REMIND_STATE may
equally come from the Settings UI (settings.json on the volume) - env first, always - and
they are read PER CALL rather than at import, so a change takes effect on the next tick
instead of on the next restart.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

import web_push
from server import settings

BILLS_URL = os.environ.get("BILLS_URL", "http://localhost:8000/bills")
PAID_URL = os.environ.get("PAID_URL", "http://localhost:8000/data/paid.json")
STATE = os.environ.get("REMIND_STATE", "/data/reminded.json")
API = "https://api.telegram.org/bot{}/sendMessage"

# One message per bill, rendered from this template. Telegram HTML is on, so <b>/<code>
# work; every field below is derived by us (bank keys, ISO dates, formatted money), so
# there is no user-supplied text to escape.
DEFAULT_TEMPLATE = (
    "<b>Automated Credit Card Payment Reminder</b>\n\n"
    "\U0001f4b3 Pay {bank} statement amount of RM <code>{amount}</code>\n\n"
    "\u231b By {due} to avoid late charges"
)
FIELDS = "bank, amount, due, days, when, month"


def today_myt():
    """Statements, due dates and the user are all in GMT+8; the container may not be."""
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()


def bill_key(b):
    """Same identity the PWA marks paid with (`/api/paid`)."""
    return f"{b['bank']}|{b['statement_month']}"


def remind_days():
    """How far ahead to look. Read per call, not at import (#40): the Settings UI can
    change it while the server's reminder loop is running."""
    return settings.get_int("REMIND_DAYS", 3)


def template():
    """The message wording, same story — env first, then settings.json, then the default."""
    return settings.get("REMIND_TEMPLATE") or DEFAULT_TEMPLATE


def due_soon(bills, today, days=None, paid=(), sent=()):
    """Bills due within `days` (overdue included), soonest first.

    Pure. A null due date or null balance is SKIPPED, never defaulted to today —
    parse.py emits None when it could not find one rather than guessing."""
    days = remind_days() if days is None else days
    out = []
    for b in bills:
        due, bal = b.get("payment_due_date"), b.get("current_balance")
        if not due or bal is None:
            continue
        k = bill_key(b)
        if k in paid or k in sent:
            continue
        left = (date.fromisoformat(due) - today).days
        if left <= days:
            out.append((left, b))
    return [b for _, b in sorted(out, key=lambda p: p[0])]


def message(bill, today, tmpl=None):
    """Render one bill. Placeholders: bank, amount, due, days, when, month."""
    left = (date.fromisoformat(bill["payment_due_date"]) - today).days
    fields = {
        "bank": bill["bank"].upper(),
        "amount": f"{bill['current_balance']:,.2f}",
        "due": bill["payment_due_date"],
        "days": left,
        "when": "today" if left == 0 else (f"{-left}d OVERDUE" if left < 0 else f"in {left}d"),
        "month": bill["statement_month"],
    }
    try:
        return (tmpl or template()).format_map(fields)
    except KeyError as e:
        raise RuntimeError(f"REMIND_TEMPLATE: unknown placeholder {e}; known: {FIELDS}") from None


# ------------------------------------------------------- a statement arrived (#83)
# The SAME bill, a DIFFERENT event. The due reminder consumes `<bank>|<month>`
# (bill_key), so writing that bare key here would read as "already reminded" and the
# due-date message would never fire. Namespaced instead, in the same state file.
ARRIVED_PREFIX = "arrived|"
ARRIVED_TEMPLATE = (
    "<b>New {bank} statement</b>\n\n"
    "\U0001f4b3 RM <code>{amount}</code> for {month}\n\n"
    "\u231b Due {due}"
)
ARRIVED_FIELDS = "bank, amount, due, month"


def arrived_key(b):
    return ARRIVED_PREFIX + bill_key(b)


def arrived_message(bill, tmpl=None):
    """Render one just-arrived statement.

    No `days` field, deliberately: this fires the day the statement lands, so a countdown
    is noise. A missing due date or balance is SAID rather than used to skip the
    statement - parse.py emits None when it found none, and "a statement arrived" is
    still worth hearing without one."""
    bal = bill.get("current_balance")
    fields = {
        "bank": bill["bank"].upper(),
        "amount": f"{bal:,.2f}" if bal is not None else "?",
        "due": bill.get("payment_due_date") or "unknown",
        "month": bill["statement_month"],
    }
    try:
        return (tmpl or ARRIVED_TEMPLATE).format_map(fields)
    except KeyError as e:
        raise RuntimeError(
            f"arrived template: unknown placeholder {e}; known: {ARRIVED_FIELDS}") from None


def prev_month(today):
    """`YYYY-MM` of the month before `today` - the oldest statement month worth saying
    anything about. YYYY-MM sorts lexicographically, so a plain `<` is the comparison."""
    return f"{today.year - 1}-12" if today.month == 1 else f"{today.year}-{today.month - 1:02d}"


def announce(bills, known=(), state_path=None, today=None, tmpl=None, dry=False):
    """One message per statement that has just appeared in `bills`. Returns what it sent.

    `known` is the set of bill_key()s present BEFORE the pipeline ran. Anything already
    in it - or older than last month - is RECORDED WITHOUT BEING SENT. That is the seed
    that keeps the first run after this ships, and a bulk backfill of old statements,
    from firing a burst: only a bill that appeared during this run is news.

    Recorded after each send, like run(): a transport outage must leave the rest
    unrecorded so the next ingest retries exactly those."""
    state_path = state_path or STATE
    today = today or today_myt()
    seen = load_state(state_path)
    floor = prev_month(today)
    done = []
    for b in bills:
        k = arrived_key(b)
        if k in seen:
            continue
        if bill_key(b) in known or (b.get("statement_month") or "") < floor:
            save_state(state_path, load_state(state_path) | {k})
            continue
        text = arrived_message(b, tmpl)
        if dry:
            print(text)
            continue
        send(text)
        done.append(b)
        save_state(state_path, load_state(state_path) | {k})
    return done


def _get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def send_telegram(text):
    """Unchanged since it was written, except that an unset token is now "0 sent"
    rather than a KeyError — it is one transport of two now, not the only one."""
    token, chat = settings.get("TELEGRAM_BOT_TOKEN"), settings.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return 0
    body = urllib.parse.urlencode(
        {"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
    try:
        with urllib.request.urlopen(API.format(token), data=body, timeout=30) as r:
            r.read()
    except urllib.error.HTTPError as e:
        # Telegram explains itself in the RESPONSE BODY ("chat not found",
        # "Unauthorized", ...); the status line alone just says "Bad Request",
        # which is useless in a log nobody is watching. Keep the description.
        raise RuntimeError(f"telegram {e.code}: {e.read().decode(errors='replace')[:300]}") from None
    return 1


_TAGS = re.compile(r"<[^>]+>")


def send_webpush(text):
    """The same rendered message, minus the Telegram HTML a notification cannot show.

    First line becomes the notification title, the rest its body — which lines up with
    the default template (a heading, then the detail) and with any sane custom one."""
    plain = _TAGS.sub("", text).strip()
    title, _, body = plain.partition("\n")
    return web_push.send(title.strip(), body.strip() or title.strip())


def transports_configured():
    """Is anyone listening? Web Push counts the moment a browser subscribes, which can
    happen long after startup — so this is re-checked per tick, not once in lifespan."""
    return bool(web_push.load_subs()) or bool(
        settings.get("TELEGRAM_BOT_TOKEN") and settings.get("TELEGRAM_CHAT_ID"))


def send(text):
    """One bill, one message, on every configured transport.

    A transport that is not configured is skipped silently; one that fails is logged.
    Raises only when NOTHING got through, because that is the case where run() must not
    record the bill and the next tick has to retry it."""
    ok, errs = 0, []
    for name, fn in (("web push", send_webpush), ("telegram", send_telegram)):
        try:
            ok += fn(text)
        except Exception as e:
            errs.append(f"{name}: {e}")
    if not ok:
        raise RuntimeError("; ".join(errs) or "no reminder transport configured")
    if errs:
        # Something else delivered it, so the bill IS reminded and will not be retried.
        print("reminder transport failed - " + "; ".join(errs), flush=True)


def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError):
        return set()   # missing or corrupt state only costs one duplicate message


def save_state(path, keys):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted(keys), fh)
    os.replace(tmp, path)   # atomic on POSIX


def run(bills, paid, state_path=None, today=None, days=None, dry=False, tmpl=None):
    """Send one message per bill due within `days` that is not paid or already reminded,
    recording each as it goes. Returns what it reminded about ([] = nothing to do)."""
    state_path = state_path or STATE
    today = today or today_myt()
    sent = load_state(state_path)
    todo = due_soon(bills, today, remind_days() if days is None else days, paid, sent)
    done = []
    for b in todo:
        text = message(b, today, tmpl)
        if dry:
            print(text)
            continue
        send(text)
        done.append(b)
        # Record after each successful send, not once at the end: a Telegram failure
        # partway through must not lose the bills that already went out, and must
        # leave the rest unrecorded so the next run retries only those.
        save_state(state_path, load_state(state_path) | {bill_key(b)})
    return todo if dry else done


def main(dry=False):
    todo = run(_get_json(BILLS_URL), set(_get_json(PAID_URL)), dry=dry)
    print(f"{today_myt()}: "
          + (f"reminded {len(todo)} bill(s)" if todo and not dry
             else f"nothing due within {remind_days()}d" if not todo else "dry run"))


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
