# Running it as a service

The dashboard is a file you open. This page is the other way to run lazyexpenses: as a
small always-on service that keeps itself up to date — it fetches your statement mail,
parses what arrives, serves the web app, and messages you before a bill is due.

Everything here is optional. If a folder of PDFs and `python parse.py` is enough for
you, it is enough. Nothing below is needed to use the parser or the offline dashboard.

- [The quick version](#the-quick-version)
- [What each variable does](#what-each-variable-does)
- [Fetching statements from Gmail](#fetching-statements-from-gmail)
- [Bill reminders on Telegram](#bill-reminders-on-telegram)
- [Putting it on your network](#putting-it-on-your-network) — **read the security note**
- [Without Docker](#without-docker)
- [Upgrading, backing up, troubleshooting](#upgrading-and-backing-up)

## The quick version

```bash
cp .env.example .env    # then open it and fill in what you have
docker compose up -d
```

Open <http://localhost:8000>. That is the whole deployment.

Nothing gets built — [`compose.yaml`](../compose.yaml) uses the image published on every
release, so no Python, no Node, no toolchain. Two services come up:

| Service | What it does |
|---|---|
| `app` | the web app, the API, and the bill reminders (those run inside the server, so there is no third service) |
| `fetch` | checks your mailbox every hour and posts new statements to `app` |

Both are the same image. Both read `.env`. Leave a section of `.env` blank and that part
simply does nothing: no Gmail details means `fetch` says so and goes back to sleep, no
Telegram token means no reminders. Nothing crash-loops because you only wanted half of it.

A fresh volume is empty, so the page loads but the data request returns 404 until the
first statement lands. That is not a bug. Post one by hand if you do not want to wait:

```bash
curl -F "file=@cc-statements/maybank_june.pdf" -F "bank=maybank" http://localhost:8000/ingest
```

It replies with the reconciliation tally, which is the honest answer about whether the
statement was understood:

```json
{"bank":"maybank","recon":{"VERIFIED":12},"problems":{},"warning":false}
```

`warning` is true whenever a statement did not reconcile — `REVIEW`, `NO_BALANCE` or
`ERROR` — and `problems` says which. `DUPLICATE` does not warn: the same statement
legitimately arrives under several filenames and gets deduplicated. The HTTP status stays
200 either way, because the upload itself succeeded and retrying it would fail
identically. Read the body, not the status code.

A locked PDF whose `CC_PW_<BANK>` is not set lands in `ERROR`, and you will see it there.

## What each variable does

All of it lives in `.env`, which is gitignored. [`.env.example`](../.env.example) is the
committed copy with placeholders — copy it, do not edit it.

| Variable | Default | |
|---|---|---|
| `PORT` | `8000` | port on the host |
| `CC_PW_MAYBANK` … `CC_PW_RHB` | — | statement passwords, one per bank, named after the filename prefix. Set only the banks you hold |
| `GMAIL_USER` | — | the mailbox to poll |
| `GMAIL_APP_PASSWORD` | — | a Google app password, never your login password |
| `GMAIL_LABEL` | `CC` | the label statement mail is filed under |
| `FETCH_EVERY` | `3600` | seconds between mail checks |
| `TELEGRAM_BOT_TOKEN` | — | reminders are off unless both this and the chat id are set |
| `TELEGRAM_CHAT_ID` | — | |
| `REMIND_DAYS` | `3` | how far ahead to look |
| `REMIND_HOUR` | `9` | earliest local hour to send |
| `REMIND_TEMPLATE` | the message below | Telegram HTML plus the placeholders below |

Passwords and tokens live in `.env` and nowhere else — never in a filename, never in the
repo, never in a log line.

## Fetching statements from Gmail

`fetch_mail.py` polls one Gmail label over IMAP and posts every PDF attachment to
`/ingest`. Gmail exposes labels as IMAP mailboxes, so a label is just a mailbox to open,
and `imaplib` and `email` both ship with Python — there is nothing to install and nothing
to host. The compose stack runs it for you on a loop; on its own it is a script you can
put in cron.

Set it up once:

1. **Turn on 2-Step Verification** on the Google account
   ([myaccount.google.com/security](https://myaccount.google.com/security)). App passwords
   do not exist without it.
2. **Generate an app password** at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). You get
   a 16-character string, shown once. That is what goes in `.env`.
3. **Check IMAP is on** — Gmail settings → *Forwarding and POP/IMAP* → *Enable IMAP*.
4. **Label your statement mail.** Make a Gmail filter that applies a label — `CC` is the
   default — to mail from your banks. The script only ever looks in that one mailbox, and
   only at unread messages in it.

Then try it before trusting it:

```bash
GMAIL_USER='you@gmail.com' GMAIL_APP_PASSWORD='abcd efgh ijkl mnop' \
  python fetch_mail.py --dry-run
```

`--dry-run` opens the mailbox read-only, so it cannot mark anything read even by
accident, and it posts nothing. It just lists what it found.

Which bank a statement belongs to is read off the sender, then the subject, then the
body, in that order. If none of them names a bank the script says so and moves on: a
statement posted under the wrong bank parses against the wrong rules and produces
confidently wrong numbers, which is worse than skipping it.

A message is marked read **only after every attachment in it ingested cleanly**. So a
server that was down, an unknown bank, or a mail with no PDF all stay unread and come
back on the next run. That is noisy on purpose — a statement that quietly vanishes into
the read pile is one you never notice is missing. Re-running straight away does nothing,
because everything that worked is already read.

Google still issues app passwords with 2FA on, but has been signalling a move to
OAuth 2.0. If that day comes, the login is four lines in one function.

## Bill reminders on Telegram

The server sends these itself — there is nothing extra to deploy. Set the two Telegram
variables and it starts; unset them and it does not.

The token comes from [@BotFather](https://t.me/BotFather). The chat id is your own chat
with that bot; **message the bot once first**, because Telegram will not let a bot open a
conversation. (If you skip that step, the log says `chat not found`.)

From then on, once a day after 09:00 local, every bill due within three days produces one
message:

> **Automated Credit Card Payment Reminder**
>
> 💳 Pay HSBC statement amount of RM `1,643.65`
>
> ⌛ By 2026-08-23 to avoid late charges

`REMIND_TEMPLATE` replaces that wording. Messages are Telegram HTML, so `<b>`, `<i>` and
`<code>` work, and these placeholders are filled in per bill:

| | |
|---|---|
| `{bank}` | `HSBC` |
| `{amount}` | `1,643.65` |
| `{due}` | `2026-08-23` |
| `{when}` | `in 3d` / `today` / `2d OVERDUE` |
| `{days}` | `3` |
| `{month}` | `2026-08` (the statement month) |

```bash
REMIND_TEMPLATE='⌛ {bank} — RM{amount} due {when}'
```

An unknown placeholder fails loudly with the list of real ones rather than sending a
half-rendered message.

At most **one message per bill**, so restarts and extra checks are free: what has already
been mentioned is recorded in `/data/reminded.json`. A bill you marked paid in the web app
is never reminded about, and a statement whose due date the parser could not find is
skipped rather than guessed at. "Today" is resolved in Asia/Kuala_Lumpur whatever the
host's timezone is, so a UTC machine does not fire a day early.

## Putting it on your network

> **There is no login.** Anyone who can reach the port sees every transaction, every
> balance and every card. That is fine on your own machine, fine on a LAN you trust, fine
> on a tailnet. It is **not** fine on the open internet — do not port-forward this, and do
> not put it behind a plain reverse proxy on a public domain without adding
> authentication of your own.

The other thing worth knowing before you move it off localhost: **installing the web app
needs a secure context.** Over a plain `http://192.168.x.x` address the browser silently
downgrades it to a bookmark-style shortcut — no install, no offline cache — and
everything looks almost right, which is what makes it confusing.

**On the machine it runs on, there is nothing to do.** `http://localhost:8000` already
counts as a secure context, so the app installs and caches offline as-is.

**From your phone or another machine, you need a real certificate.** The least-effort
answer is [Tailscale](https://tailscale.com), because it hands you a genuine
publicly-trusted certificate and a stable hostname without opening a single port:

```bash
tailscale up
tailscale serve --bg 8000    # prints the https:// address it is now serving on
```

Then open that `https://…ts.net` address on any device signed into the same tailnet, and
the install prompt appears. Nothing is exposed to the internet; the tailnet is the
boundary.

Two alternatives, if you already run one of them: **Caddy** in front of the container with
`tls internal` gives HTTPS on a LAN, at the cost of installing its local CA on every
device that should trust it — which is the fiddly part. A **Cloudflare Tunnel** gives a
public HTTPS hostname with no port-forwarding, but re-read the security note above first:
that hostname is on the internet, and this app has no login.

## Without Docker

Both automation pieces are plain scripts and neither needs the container.

```bash
python fetch_mail.py            # INGEST_URL points at your server
python remind_bills.py --dry-run   # prints the message, sends nothing
```

In a crontab:

```
*/30 * * * *  python /path/to/fetch_mail.py
0 9 * * *     python /path/to/remind_bills.py
```

`remind_bills.py` run this way reads `/bills` over HTTP instead of the data volume, so
point `BILLS_URL` and `PAID_URL` (both default to `http://localhost:8000/…`) at your
server. `REMIND_STATE` is where it records what it has already sent — the default is
`/data/reminded.json`, which you will want to change if there is no `/data` on that
machine.

## Upgrading and backing up

```bash
docker compose pull && docker compose up -d
```

Everything that matters is in the `data` volume: the statement PDFs as they arrived, the
parse cache, the CSVs, `app.json`, and your paid/waiver state. `docker compose down`
leaves it alone; `docker compose down -v` deletes it. To back it up, copy `/data` out of
the container — or just keep the original statement PDFs, since every other file in there
is rebuilt from them.

An upgrade that changes the parser re-reads every statement on the next ingest rather than
trusting the cache, so the first run after one is slower. That is deliberate: a parser
change must never serve rows from the old rules.

**Something looks wrong?**

| Symptom | Where to look |
|---|---|
| Page loads, no data | `/data/app.json` does not exist yet — nothing has been ingested |
| A statement shows `ERROR` | locked PDF, and its `CC_PW_<BANK>` is unset or wrong |
| A statement shows `REVIEW` | the bank changed its layout; `python probe.py <file>` shows what the parser sees |
| `fetch` logs "nothing to fetch" | `GMAIL_USER` / `GMAIL_APP_PASSWORD` are blank in `.env` |
| Reminders never arrive | both Telegram variables set? Did you message the bot first? |
| No install prompt | you are on plain HTTP from another machine — see [above](#putting-it-on-your-network) |

Logs for everything: `docker compose logs -f app` and `docker compose logs -f fetch`.
