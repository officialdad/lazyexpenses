"""Bill reminders without n8n: read /bills, Telegram what is due soon.

Run daily (cron / k8s CronJob). At most ONE message per bill (bank+statement_month),
tracked in a state file on the data volume next to paid.json/waivers.json — so
running the job twice in a day does not send twice.

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, BILLS_URL, PAID_URL, REMIND_STATE, REMIND_DAYS.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

BILLS_URL = os.environ.get("BILLS_URL", "http://localhost:8000/bills")
PAID_URL = os.environ.get("PAID_URL", "http://localhost:8000/data/paid.json")
STATE = os.environ.get("REMIND_STATE", "/data/reminded.json")
REMIND_DAYS = int(os.environ.get("REMIND_DAYS", "3"))
API = "https://api.telegram.org/bot{}/sendMessage"


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


def message(bills, today):
    lines = ["\U0001f4b3 Credit card bills due:"]
    for b in bills:
        left = (date.fromisoformat(b["payment_due_date"]) - today).days
        when = "today" if left == 0 else (f"{-left}d OVERDUE" if left < 0 else f"in {left}d")
        lines.append(
            f"{b['bank'].upper()} RM{b['current_balance']:,.2f}"
            f" — due {b['payment_due_date']} ({when})"
        )
    return "\n".join(lines)


def _get_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def send(text):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    with urllib.request.urlopen(API.format(token), data=body, timeout=30) as r:
        r.read()


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError):
        return set()   # missing or corrupt state only costs one duplicate message


def save_state(keys):
    os.makedirs(os.path.dirname(STATE) or ".", exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted(keys), fh)
    os.replace(tmp, STATE)   # atomic on POSIX


def main(dry=False):
    today = today_myt()
    bills = _get_json(BILLS_URL)
    paid = set(_get_json(PAID_URL))
    sent = load_state()
    todo = due_soon(bills, today, REMIND_DAYS, paid, sent)
    if not todo:
        print(f"{today}: nothing due within {REMIND_DAYS}d")
        return
    text = message(todo, today)
    if dry:
        print(text)
        return
    send(text)
    save_state(sent | {bill_key(b) for b in todo})
    print(f"{today}: reminded {len(todo)} bill(s)")


if __name__ == "__main__":
    main(dry="--dry-run" in sys.argv)
