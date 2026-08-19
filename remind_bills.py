"""Bill reminders without n8n: which bills are due soon, and Telegram about them.

Two ways in, same logic:
  - `python remind_bills.py` — standalone, reads /bills over HTTP, for cron or a
    machine that is not running the server.
  - `server.app` calls run() on a timer, reading the PVC directly (no self-HTTP).

At most ONE message per bill (bank+statement_month), tracked in a state file next to
paid.json/waivers.json — so a second run in the same day sends nothing, and a server
restart cannot re-send.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BILLS_URL, PAID_URL, REMIND_STATE,
REMIND_DAYS, REMIND_TEMPLATE.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

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


def send(text):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
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
