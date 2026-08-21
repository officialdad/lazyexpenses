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
- [Locking it with a password](#locking-it-with-a-password)
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
release, so no Python, no Node, no toolchain.

**One service does everything.** The server is the only long-running thing here and it
already knows where your data lives, so the mail fetch and the bill reminders are timers
inside it rather than separate containers, cron entries or CronJobs. There is one thing
to deploy, one log to read, and one `.env`.

Leave a section of `.env` blank and that part simply does nothing: no Gmail details means
nothing is fetched, no Telegram token means no reminders. Nothing crash-loops because you
only wanted half of it.

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
| `APP_PASSWORD` | — | blank means no login; set it and the app asks for it once per device |
| `CC_PW_MAYBANK` … `CC_PW_RHB` | — | statement passwords, one per bank, named after the filename prefix. Set only the banks you hold |
| `GMAIL_USER` | — | the mailbox to poll |
| `GMAIL_APP_PASSWORD` | — | a Google app password, never your login password |
| `GMAIL_LABEL` | `CC` | the label statement mail is filed under |
| `FETCH_POLL` | `3600` | seconds between mail checks |
| `TELEGRAM_BOT_TOKEN` | — | reminders are off unless both this and the chat id are set |
| `TELEGRAM_CHAT_ID` | — | |
| `REMIND_DAYS` | `3` | how far ahead to look |
| `REMIND_HOUR` | `9` | earliest local hour to send |
| `REMIND_TEMPLATE` | the message below | Telegram HTML plus the placeholders below |

Passwords and tokens live in `.env` and nowhere else — never in a filename, never in the
repo, never in a log line.

## Fetching statements from Gmail

The server checks your mailbox every hour and posts every PDF attachment it finds to
`/ingest`. Gmail exposes labels as IMAP mailboxes, so a label is just a mailbox to open,
and `imaplib` and `email` both ship with Python — there is nothing to install and nothing
extra to run. The same code is also a standalone script (`fetch_mail.py`) if you would
rather drive it from cron.

Set it up once:

1. **Turn on 2-Step Verification** on the Google account
   ([myaccount.google.com/security](https://myaccount.google.com/security)). App passwords
   do not exist without it.
2. **Generate an app password** at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). You get
   a 16-character string, shown once. That is what goes in `.env`.
3. **Label your statement mail.** Make a Gmail filter that applies a label — `CC` is the
   default — to mail from your banks. The script only ever looks in that one mailbox, and
   only at unread messages in it.

There is no IMAP switch to find. Google no longer offers one: *Settings → Forwarding and
POP/IMAP* now shows only behaviour options under *IMAP access* — auto-expunge, folder size
limits — and the defaults are all fine. If your account is old enough to still show an
*Enable IMAP* radio, pick it.

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

## Locking it with a password

By default there is no login. Set `APP_PASSWORD` to any password you like and there is
one:

```
APP_PASSWORD=something-only-you-know
```

Restart, open the app, and it asks for that password once. It is stored as a cookie your
browser keeps, so you type it once per device and not again for a month. There are no
accounts and no usernames — one password for the whole app, because there is one of you
and one pile of statements.

What the password covers is everything that carries your data: the statement data, the
bills, the paid and waiver marks, and `/ingest`. What it deliberately does **not** cover:

- **`/healthz`**, so a container platform can still tell whether the app is alive.
- **the web app's own files** — the HTML and JavaScript, which contain none of your data
  and have to load before the browser can ask you for anything.

**The mail fetch keeps working.** The server's hourly fetch posts statements to its own
`/ingest`, and it sends `APP_PASSWORD` along with them, so turning the gate on does not
lock the app out of itself. If you run `python fetch_mail.py` yourself, set the same
`APP_PASSWORD` in its environment — otherwise it gets a `401` and the mail stays unread.
(`--dry-run` posts nothing, so it never needs it.)

Changing the password logs every device out; there is nothing to clean up. And a password
over plain HTTP is a password anyone on the network can read, so this pairs with the HTTPS
note below rather than replacing it.

## Suggesting categories with a local model (optional, off by default)

Every merchant the keyword table in `parse.py` does not recognise lands in `Other`. That
table was hand-written against one person's statements, so on yours `Other` starts out
larger than it should be, and the fix is to read the source and add keywords for your own
merchants. This is a way to get a first draft of those keywords instead of doing all of it
by eye.

It is off unless you configure it, and it is local only — there is no hosted option and no
API key. A list of everything you buy is exactly the data you would least want to send to
someone else's server.

What it actually costs you:

- **A model download.** An instruct-tuned GGUF under 1 GB is enough. The one wired into
  `compose.yaml` is
  [`ggml-org/gemma-3-1b-it-GGUF` at Q4_K_M](https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF),
  **~800 MB**. You do not have to choose one, and the choice was measured rather than
  guessed — see the accuracy note below.
- **A server to run.** [llama.cpp](https://github.com/ggml-org/llama.cpp)'s `llama-server`,
  on your own machine, for as long as the run takes.
- **A real accuracy ceiling, and today it is the prompt's fault rather than the model's.**
  Measured on this profile against 5 merchants the keyword table could not name — which is
  the honest population, since the model only ever sees what `CATS` already failed on:

  | Model | Size | Score, as shipped | Same merchants, asked in plain English |
  |---|---|---|---|
  | Qwen2.5-0.5B-Instruct Q4_K_M | 469 MB | **0 / 5** | ~1 / 5 — genuinely does not know them |
  | **Gemma 3 1B it Q4_K_M** (default) | 806 MB | **1 / 5** | **4 / 5 — it knows them fine** |

  Both were deterministic across two runs and reported `high` confidence on **every**
  answer, right or wrong, so the confidence column is decoration — do not filter on it.

  The interesting part is the last column. Ask Gemma *"what kind of business is K S S
  OTOMOBIL SDN BHD"* and it says "auto parts supplier"; `PERODUA SERVIS` → "auto repair";
  `DOMINOS MALAYSIA` → "pizza restaurant". It knows. Hand it our 717-token taxonomy block
  and it collapses to answering `Shopping` for all five. Qwen collapses the same way, to
  `Travel`. Ruled out as causes: the JSON-schema grammar (same collapse without it), the
  `system` role Gemma 3 does not have (same collapse with it folded into the user turn),
  and truncation (717 tokens into a 4096 window).

  So: **the taxonomy prompt is the bottleneck, not model size.** Gemma is the default
  because it is the one with the knowledge to unlock. Until the prompt is fixed, **treat
  `suggested_cats.csv` as a list of merchants worth looking at, not as categories worth
  pasting**, and read every line before it goes into `CATS`.

Nothing is applied for you. The run writes `suggested_cats.csv` — merchant, proposed
category, confidence, how many times it appeared, what it came to in ringgit — and prints a
block of keywords to paste into `CATS`. You decide what goes in. Once a keyword is in the
table, that merchant costs nothing forever after.

### Running it from source

```bash
# in another terminal. Note -hf, not -mu: current llama-server builds start in "router
# mode" and silently ignore --model-url, leaving you a healthy server with no model.
llama-server --port 8080 -hf ggml-org/gemma-3-1b-it-GGUF:Q4_K_M
export LLM_URL=http://localhost:8080
python parse.py                     # unchanged; no model involved
python llm_cats.py --suggest-cats   # reads transactions.csv, writes suggested_cats.csv
```

### Running it with `docker compose`

`compose.yaml` carries a second service, `llm`, behind a **compose profile**. A plain
`docker compose up -d` does not start it, pull it, or download its model — the default
deployment is one container, exactly as before. Turn it on only when you want it:

```bash
docker compose --profile llm up -d           # first start downloads ~800 MB
docker compose exec -e LLM_ENABLED=1 -e LLM_URL=http://llm:8080 \
  app python llm_cats.py --suggest-cats      # writes /data/suggested_cats.csv
docker compose --profile llm down            # stop it again; the weights are kept
```

`http://llm:8080` is the service name on the compose network, so nothing is published to
the host and there is no platform-specific hostname involved. `LLM_MODEL` can stay at its
default — the server holds exactly one model and answers whatever name you send. The
weights live on their own named volume (`models`), so stopping the profile — or
`docker compose down` — does not throw away the download. `docker compose down -v` does.

The model is CPU-only on purpose. If you have a GPU, override `image:` with
`ghcr.io/ggml-org/llama.cpp:server-cuda` and add `--gpus all` yourself; that path is not
tested here.

> **If you would rather run `llama-server` on the host machine** and reach it from the
> container, be aware that `host.docker.internal` **does not resolve on plain Linux
> Docker** — it is a Docker Desktop convenience. On Linux you must add
> `extra_hosts: ["host.docker.internal:host-gateway"]` to the `app` service yourself
> before that hostname works. The `llm` profile above avoids the whole question, which is
> why it is the documented path.

| Variable | Default | |
|---|---|---|
| `LLM_URL` | — | where `llama-server` is listening: `http://llm:8080` with the compose profile, `http://localhost:8080` from source. Unset means the feature is not there at all |
| `LLM_MODEL` | `local` | model name sent with the request; `llama-server` serves one model and ignores it |
| `LLM_ENABLED` | — | set to `0` to force it off even with `LLM_URL` set |

These are for the command you run by hand, not for the container — the server never talks
to a model.

Two things are worth knowing about how it works. The keyword table is asked first and always
wins: a description it matches is never sent anywhere, so the model only ever sees merchants
that were already going to be `Other`. And the reply is constrained as it is generated — the
request carries a JSON schema whose category is an `enum` of the fifteen category names, which
llama.cpp compiles into a grammar, so the model cannot answer with a sixteenth category or a
paragraph of explanation.

`parse.py` never calls a model, configured or not. Categorisation during a parse is the
keyword table and nothing else, so the same statements always produce the same CSVs. If the
server is down, `llm_cats.py` says so in one line and stops; those merchants stay `Other`
and nothing else notices.

## Putting it on your network

> **Set `APP_PASSWORD` before this leaves your own machine.** With it blank there is no
> login at all: anyone who can reach the port sees every transaction, every balance and
> every card. With it set, they need the password — see
> [Locking it with a password](#locking-it-with-a-password).
>
> A password is not the same as being safe on the open internet. Do not port-forward this.
> A single shared password over a public domain is one guessed string away from your whole
> financial history, and over plain HTTP it is readable in transit — so if it has to be
> reachable from outside, put it behind HTTPS and something of your own (a VPN, a private
> mesh, a proxy that authenticates) rather than relying on this alone.

The other thing worth knowing before you move it off localhost: **installing the web app
needs a secure context.** Over a plain `http://192.168.x.x` address the browser silently
downgrades it to a bookmark-style shortcut — no install, no offline cache — and
everything looks almost right, which is what makes it confusing.

**On the machine it runs on, there is nothing to do.** `http://localhost:8000` already
counts as a secure context, so the app installs and caches offline as-is.

**From your phone or another machine, you need HTTPS with a certificate that device
already trusts.** Any reverse proxy in front of port 8000 does it, and whichever one you
already run is the right one — this repo does not ship a proxy or prefer a vendor. A
private-network mesh with its own certificates is the least fiddly route, because a
self-signed certificate means installing your own CA on every device that should trust it.

Whatever you put in front, the security note above still applies. A tunnel that gives you
a public hostname also gives it to everyone else.

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
| the log says "nothing to fetch" | `GMAIL_USER` / `GMAIL_APP_PASSWORD` are blank in `.env` |
| Reminders never arrive | both Telegram variables set? Did you message the bot first? |
| It keeps asking for the password | `APP_PASSWORD` changed, or the cookie expired after a month — type it again |
| `fetch_mail.py` says `HTTP Error 401` | you set `APP_PASSWORD` on the server but not in the shell you ran the script from |
| No install prompt | you are on plain HTTP from another machine — see [above](#putting-it-on-your-network) |

Logs for everything, in one place: `docker compose logs -f`.
