"""Bill reminders without n8n: which bills are due soon, and who to tell about them.

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

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BILLS_URL, PAID_URL, REMIND_STATE,
REMIND_DAYS, REMIND_TEMPLATE.
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

BILLS_URL = os.environ.get("BILLS_URL", "http://localhost:8000/bills")
PAID_URL = os.environ.get("PAID_URL", "http://localhost:8000/data/paid.json")
STATE = os.environ.get("REMIND_STATE", "/data/reminded.json")
REMIND_DAYS = int(os.environ.get("REMIND_DAYS", "3"))
API = "https://api.telegram.org/bot{}/sendMessage"

# One message per bill, rendered from this template. Telegram HTML is on, so <b>/<code>
# work; every field below is derived by us (bank keys, ISO dates, formatted money), so
# there is no user-supplied text to escape.
DEFAULT_TEMPLATE = (
    "<b>Automated Credit Card Payment Reminder</b>\n\n"
    "\U0001f4b3 Pay {bank} statement amount of RM <code>{amount}</code>\n\n"
    "\u231b By {due} to avoid late charges"
)
TEMPLATE = os.environ.get("REMIND_TEMPLATE") or DEFAULT_TEMPLATE
FIELDS = "bank, amount, due, days, when, month"


def today_myt():
    """Statements, due dates and the user are all in GMT+8; the container may not be."""
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()


def bill_key(b):
    """Same identity the PWA marks paid with (`/api/paid`)."""
    return f"{b['bank']}|{b['statement_month']}"


def due_soon(bills, today, days=REMIND_DAYS, paid=(), sent=()):
    """Bills due within `days` (overdue included), soonest first.

    Pure. A null due date or null balance is SKIPPED, never defaulted to today —
    parse.py emits None when it could not find one rather than guessing."""
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


def message(bill, today, template=None):
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
        return (template or TEMPLATE).format_map(fields)
    except KeyError as e:
        raise RuntimeError(f"REMIND_TEMPLATE: unknown placeholder {e}; known: {FIELDS}") from None


def _get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def send_telegram(text):
    """Unchanged since it was written, except that an unset token is now "0 sent"
    rather than a KeyError — it is one transport of two now, not the only one."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
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
        os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


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


def run(bills, paid, state_path=None, today=None, days=REMIND_DAYS, dry=False, template=None):
    """Send one message per bill due within `days` that is not paid or already reminded,
    recording each as it goes. Returns what it reminded about ([] = nothing to do)."""
    state_path = state_path or STATE
    today = today or today_myt()
    sent = load_state(state_path)
    todo = due_soon(bills, today, days, paid, sent)
    done = []
    for b in todo:
        text = message(b, today, template)
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
             else f"nothing due within {REMIND_DAYS}d" if not todo else "dry run"))


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
