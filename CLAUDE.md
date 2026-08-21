# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A personal pipeline for processing Malaysian credit-card e-statements (6 banks: maybank, cimb, sc/Standard Chartered, alliance, hsbc, rhb). It has **two loosely-coupled halves**:

1. **n8n workflows** (`*.json`) — cloud automation that pulls statement emails from Gmail (label `CC`), unlocks the password-protected PDF attachments, and (in the original) extracts info via Gemini.
2. **Local Python parser** (`parse.py`) — deterministic extraction of the unlocked PDFs in `cc-statements/` into transaction/spend CSVs. **No LLM.**

The handoff between halves is manual: the n8n `compile-cc-statements` workflow zips unlocked PDFs and sends them via Telegram; the user downloads/unzips into `cc-statements/`, then runs `parse.py`.

## Active work — deployment for beginners (last touched 2026-08-21)

**n8n and Stirling-PDF are both out of the code path** (#20 closed). The automated refresh pipeline
is **live in production**, not a plan. `lazyexpense.opariffazman.com`
runs `ghcr.io/officialdad/lazyexpenses/app:0.9.1` on k3s, serving the PWA, re-running
`parse.py → insights.py → export_data.py` over a 5Gi PVC on every `/ingest`, **and sending the bill
reminders itself**. 86 statements on the volume, **82 VERIFIED / 4 DUPLICATE**, 1383 transactions,
7 cards, 2025-06 → 2026-08. `Recreate` strategy (the volume is RWO).

**Infra lives in a separate repo:** `~/repo/infrastructure`, manifests in `k3s/lazyexpense/`
(`deployment.yml`, `service.yml`, `persistentvolumeclaim.yml`, `secret.yml.example`). Ingress is a
single shared object — `k3s/traefik/ingress-local.yml`, host `lazyexpense.opariffazman.com` → svc
`lazyexpense:8000`. Images are digest-pinned for Renovate. Push to `main` auto-deploys changed
`k3s/` dirs. `kubectl` is a mise shim, so run it **from inside that repo** or it fails to resolve.
Its `CLAUDE.md` has the conventions.

**n8n is fully retired** — the Gmail trigger was the last job, `fetch_mail.py` (#12) replaces it, and
the workflows were **disabled on 2026-08-21**. The n8n instance itself is still Running in the
cluster (`k3s/n8n/`, other workflows live there); only the credit-card workflows are off. The
`CC_PW_*` values still sitting on the n8n PVC are now stale copies — the k8s Secret
`lazyexpense-secrets` is the source of truth, so clearing them is housekeeping worth doing.

| n8n job | Status |
|---|---|
| Unlock via Stirling-PDF + "set password" Code node | **Dead** since #11 — `parse.py` opens locked PDFs itself |
| Daily reminder cron (Gemini + Google Tasks + Telegram) | **Replaced** by the in-process reminder, 0.5.0/0.6.0 (#13) |
| Gmail trigger on label `CC` | **Replaced and proven** — `fetch_mail.py` (#12) took a real statement mail unassisted on 2026-08-21 |

**`fetch_mail.py`** (#12): `imaplib.IMAP4_SSL` → select `GMAIL_LABEL` (`CC`) → `UNSEEN` → `BODY.PEEK[]`
(a plain FETCH would set `\Seen` itself and defeat the retry) → POST each PDF part to `INGEST_URL` as
hand-rolled multipart (`urllib`, no `requests`) → `+FLAGS \Seen` **only if every attachment ingested**.
`detect_bank(text)` is pure (first-match over `BANKS` regexes), called on From, then Subject, then body;
`None` skips the mail rather than guessing. Skips (unknown bank, no PDF) and `--dry-run`
(`select(readonly=True)`) never mark seen — so a skipped mail nags every run on purpose. The multipart
filename is `<bank>.pdf`, **never** the mail's (untrusted, and `pipeline.save_pdf` names by content hash
anyway). IMAP lives only in `main()`, which is the boundary `test_fetch_mail.py` does not cross.
Verified end to end against a live server on a synthetic CIMB mail; the IMAP loop itself was smoke-run
against a fake `IMAP4_SSL` (not committed) — **untested against a real mailbox**.

### Deployment for other people (done — #15)

`compose.yaml` + `.env.example` are the documented path; **the k3s setup stays out of the repo**
(it is mine, it does not generalise). **One service**, the *published* image, no build. The mail
fetch is a timer in the web process (`_fetch_loop`, `FETCH_POLL`, default 3600s) for the same reason
the reminders are — the server is already the long-running thing that knows `DATA_DIR`, so it is one
container to deploy instead of two. 0.7.0 shipped a second compose service and a k8s CronJob for
this; **0.8.0 deleted both.** Named volume `data`, not a bind mount. Both halves are
**off-unless-configured** — the loop only starts when `GMAIL_USER` *and* `GMAIL_APP_PASSWORD` are
set, exactly like the reminders and `TELEGRAM_*`, and `fetch_mail.main()` additionally no-ops if
they vanish.

**`_fetch_loop` deliberately goes back out through `/ingest` over the loopback**, unlike
`_reminder_tick` which reads the PVC directly. Reading a file and running the pipeline are not the
same problem: `/ingest` holds the lock, saves the PDF and reparses the corpus, so routing through it
keeps one copy of that. The cost is knowing our own port — that is what `INGEST_URL` is for. `.env` is gitignored; `.env.example` is not.

Docs split by audience: **README = user-facing** (what it is, banks, demo, quick start, one short
`docker compose up` section), **`docs/DEPLOY.md`** = the whole hosting/automation reference (env
table, Gmail app-password onboarding, reminder template, secure-context, upgrade/backup,
troubleshooting), **CONTRIBUTING.md** = adding a bank + the test suite (moved out of README).

Verified locally: `docker build` → `docker compose up -d` → `/healthz` 200, `curl -F` ingest of a
synthetic HSBC statement → `{"VERIFIED":1}`, `app.json` 200, survives `docker compose restart`,
`server/test_app.py::test_fetch_loop_runs_only_when_gmail_is_configured` covers the on/off contract
(mutation-checked: forcing the loop on makes it fail). On the secure-context question `docs/DEPLOY.md` names **no vendor and ships no proxy** —
`localhost` is the one tested answer, everything past it is "put your own reverse proxy in front",
because untested instructions for someone else's product are exactly what #15 said not to write.

**Prod as of 0.9.1 (rolled out 2026-08-20).** The bump carried #31's `parse.py` edit, so
`PARSE_VER` changed and the whole cache was invalidated — the in-pod warm took **108.9s** (the
~109s the note below predicts), and the run right after it **0.51s**. Corpus came through the
rollout unchanged: 84 PDFs, 1364 transactions, 80 VERIFIED / 4 DUPLICATE, `reminded.json` still
`["hsbc|2026-08"]`, 83 cache entries. **#31 confirmed on the live host** — `bank=mybank` returns
400 naming the six and the volume stays at 84 (that request writes nothing, which is what makes it
safe to run against prod). `llm_cats.py` is in the image and reports itself off.

**Both timers verified live (2026-08-20):** `GMAIL_*` is in the k8s Secret and
the fetch loop **has run against the real mailbox**, hourly on the dot, 11 ticks logging
`CC: 0 unread` / `marked 0 message(s) seen` — so IMAP login, mailbox select and the unread search all
work in prod. The reminder timer **fired on its own for the first time** the same morning:
`reminder sent: hsbc 2026-08` at 09:08:55 MYT, with `/data/reminded.json` now holding
`["hsbc|2026-08"]`. Neither had ever been exercised before.

**The end-to-end is now proven (2026-08-21).** A real CIMB statement mail flowed
label → IMAP → `/ingest` → VERIFIED with nothing else touching it:

```
CC: 1 unread
ingested cimb: 2220260819202608210052170081440.PDF {"VERIFIED": 82, "DUPLICATE": 4}
marked 1 message(s) seen
```

4.8s for the whole path, and the attachment was a **genuinely encrypted** CIMB PDF — multi-card,
`:NN/MM` installment memos, opened with `CC_PW_CIMB` and no Stirling anywhere. n8n had already
ingested the same mail earlier that day, so this run was **idempotent** and proved it: 86 PDFs and
md5 `606dc0f7…` identical before and after, because `save_pdf` names by content hash. Re-running
`fetch_mail.py` on an already-ingested statement is therefore safe.

`kubectl logs deploy/lazyexpense | grep -E 'unread|ingested'` — note the log is mostly healthz
probes, so `--tail` will hide these; grep the whole thing.

### Next: the deployment has to be beginner-usable

**Handoff state (2026-08-21).** Prod runs 0.9.1 and everything the pipeline does has now been
exercised in production at least once — parse, reconcile, ingest, both timers, and the full
mail-to-VERIFIED path. Nothing is half-finished and nothing is blocked on evidence any more; what
remains is feature work, and it is a chain rather than a menu:

**#39 → #40 → #44.** #40's notification step needs #39 to exist; #44 says in its own text to wait for
both or expect a second pass. **#39 is the one to start**, and its one open design question is
already decided — VAPID signing uses `cryptography` (a 5th server dep, hand-rolled JWT +
`aes128gcm`), **not** `pywebpush`, because `hashlib`/`hmac` cannot do P-256 and pywebpush would pull
four packages to save ~80 lines. The "one runtime dependency" rule is about `parse.py`/`pdfplumber`,
not the server.

Two more are filed but off the critical path: **#51** (the app has no auth, and #40 turns that from
"reads your spending" into "reconfigures where your statements come from" — decide before #40 ships,
not after) and **#52** (nothing checks that a documented command exists in the image, which is how
0.9.0 shipped a `docs/DEPLOY.md` line that could not run).

**Known-unverified, needs hardware not code:** #29's live model path. No `llama-server` has ever
answered it — only a fake HTTP server in a scratch dir. The 86-statement corpus would double as a
free labelled eval set for whether a 0.5B is good enough.

The stated goal now is the simplest possible deployment for someone who is not the author. Two
issues frame it, both filed to be picked up cold:

- **#39 — Web Push as the default reminder transport**, Telegram demoted to fallback. Kills two
  secrets and six manual @BotFather steps from the getting-started path. Watch for: Web Push needs a
  secure context (same gate as PWA install), iOS only allows it for an installed PWA, and VAPID
  signing may not be doable with stdlib alone — **this repo has one runtime dependency and should
  stay that way**, so a `pywebpush` would be a deliberate decision.
- **#40 — first-run setup in the web UI**, so getting started is not "edit `.env` and restart".
  Upload a statement from the browser, answer for a locked PDF's password in context, configure mail
  and reminders with test buttons. The crux is where values live: `/data/settings.json` with **env
  vars taking precedence**, secrets **write-only** over the API. Note this sharpens the no-auth
  exposure — the app would then hold credentials, and that may finally justify a login.

**Shipped in 0.9.0/0.9.1** (2026-08-20), so the only open issues left are #39, #40 and #44:

- **#31 — `/ingest` validates the bank.** `BANKS` lives in `parse.py` beside the dispatch it
  mirrors; the server strips + lowercases, then 400s naming the six **before** `file.read()`. A
  mixed-case `HSBC` works and is stored lowercase, because the filename is what carries the bank
  forward.
- **#27 — CI runs the web suite.** A third job, `web`. It deliberately skips `--pdfs`: the suite
  only needs `app.json`, and `make_demo_data.py` + `export_data.py` are stdlib-only, so the job has
  **no pip install** and takes 0.02s instead of ~30s to build its data.
- **#29 — `llm_cats.py --suggest-cats`.** Suggest mode only; the live parse-time fallback was
  deliberately not built. Off unless `LLM_URL`/`LLM_ENABLED`; byte-identical parse output proven by
  a cold-cache reparse diff. **The live model path was answered on 2026-08-21 by #54's `llm`
  compose profile** — a real `llama-server` (Qwen2.5-0.5B Q4_K_M) served it end to end. Two things
  came out of it. (1) `LLAMA_ARG_MODEL_URL`, which upstream's own compose example still shows, is
  **silently ignored** by the current `ghcr.io/ggml-org/llama.cpp:server` image: it starts in
  *router mode*, loads zero models, and `/health` still returns `ok`. `LLAMA_ARG_HF_REPO` is what
  works. (2) **Quality is bad, and `llm_cats.py`'s prompt is why** — not model size. Measured on
  the 5 merchants `CATS` failed on (the honest population), deterministic over two runs, `high`
  confidence on every answer right or wrong:

  | Model | Size | As shipped | Asked in plain English |
  |---|---|---|---|
  | Qwen2.5-0.5B-Instruct Q4_K_M | 469 MB | 0/5 | ~1/5 — really does not know them |
  | **Gemma 3 1B it Q4_K_M** (now the default) | 806 MB | 1/5 | **4/5 — knows them fine** |

  Gemma free-form calls `K S S OTOMOBIL` an "auto parts supplier" and `DOMINOS MALAYSIA` a "pizza
  restaurant", then answers `Shopping` for all five once handed the **717-token taxonomy block**;
  Qwen collapses the same way to `Travel`. **Ablated and ruled out:** the JSON-schema grammar (same
  collapse without it), Gemma 3's missing `system` role (same collapse folded into the user turn),
  and truncation (717 tokens in a 4096 window). So the next move on #29 is **shortening/restructuring
  the prompt**, not a bigger model — and `gemma-3-270m` was deliberately not run, because model size
  is not the variable that is failing. Until then `suggested_cats.csv` is a worklist, not answers.
- **0.9.1** fixed what testing the published 0.9.0 image found: `llm_cats.py` was missing from
  `Dockerfile`'s COPY list entirely, and once added, defaulted to a cwd-relative
  `transactions.csv` — wrong inside a container, where `docker exec` lands in `/app` and the CSVs
  live on `DATA_DIR`. **Lesson worth keeping: a new root-level module is not in the image unless
  `Dockerfile:15` names it,** and `docs/DEPLOY.md` had shipped a command that could not run.

#20 (tracking) is closed — every issue it tracked is done.

### Bill reminders (done — #13, shipped 0.5.0/0.6.0)

`remind_bills.py` holds the logic; **`server/app.py` runs it on a timer inside the web process** —
deliberately not a k8s CronJob or a cron line, because the server is already the long-running thing
that knows `DATA_DIR`, so this is one container to deploy instead of two. The same file is still
runnable standalone (`python remind_bills.py --dry-run`), where it reads `/bills` over HTTP instead
of the volume, for anyone not running the container.

- **Off unless `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set** (both live in
  `lazyexpense-secrets`, which `envFrom`s into the pod). Loop starts in the FastAPI `lifespan`.
- **Polls (`REMIND_POLL`, 1800s) and sends once past `REMIND_HOUR` (9) local**, rather than sleeping
  until 09:00. The per-bill state file `/data/reminded.json` is what prevents duplicates, so an extra
  tick is a no-op and a restart cannot re-send — that is why the schedule can be this crude.
- **One message per bill**, recorded immediately after its own send, so a failure partway through
  keeps what went out and retries only the rest. Wording is `REMIND_TEMPLATE` (Telegram HTML;
  placeholders `bank/amount/due/days/when/month`), defaulting to the message the n8n workflow sent.
- Bills marked paid in the PWA (`/data/paid.json`, key `bank|statement_month`) are skipped, as are
  null `payment_due_date`/`current_balance` — `parse.py` emits `None` rather than guessing.
- **ponytail: assumes a single instance** (replicas:1 + RWO volume + `Recreate`). Two replicas would
  each hold their own view of `reminded.json` and could double-send.
- **Verified end to end in prod on 2026-08-20**: the timer fired by itself at 09:08:55 MYT and sent
  `reminder sent: hsbc 2026-08`; `/data/reminded.json` now exists and holds `["hsbc|2026-08"]`, which
  is also the proof that the dedupe survives. Nothing left to exercise here.

### Stirling-PDF — gone (2026-08-21)

Torn down, and this time verified rather than reported: no pods, no service, no ingress object, no
`stirling-pdf` namespace, and `k3s/stirlingpdf/` deleted. The gate that had blocked it — evidence a
**genuinely locked** statement flowed end to end — was met the same day; `/Encrypt` matches **2 of
86** on the volume (it read 0 of 84 while this was blocked) and both reconcile to the cent with
`parse.py` doing the unlocking:

```
cimb_5ae639f1.pdf,cimb,2026-08,11,1005.47,0.0,VERIFIED
sc_b0d14611.pdf, sc, 2026-08, 8, 165.87,0.0,VERIFIED
```

**The teardown left two things behind**, worth knowing because the first is the kind that bites
later: `k3s/traefik/ingress-local.yml` still declared `local-ingress-stirling-pdf` in a namespace
that no longer existed, so the cluster looked clean only because the object had been deleted
directly — the next apply of that directory would have tried to recreate it. Removed in
infrastructure `c6573d3`. The `pdf.opariffazman.com` **DNS record still resolves** to
192.168.50.220; deleting it is the last step and does not affect anything.

**Lesson, and it has now happened twice:** a teardown reported as done was not done. Check
`kubectl get pods,svc,ingress -A | grep <name>` *and* grep the manifests — deleting a live object
does not delete the file that recreates it.

### Sharp edges

- **`bank` on `/ingest` is load-bearing — validated since 0.9.0 (#31), but only against the six.**
  It still selects the password, the parser branch, and the filename *permanently*, because
  `parse.py` re-derives the bank from that filename on every later run. An unknown value is now a
  400 that writes nothing; a **wrong-but-valid** one (`hsbc` for a CIMB statement) still lands and
  still misparses forever.
- **Editing `parse.py` invalidates the whole parse cache** (`PARSE_VER` = hash of the file). On the
  0.4.0 rollout the full 84-PDF reparse took **109s**, versus 0.5s warm. Long enough to trip an
  ingest HTTP timeout, so warm it in-pod after any deploy that touches the parser:
  `kubectl exec deploy/lazyexpense -- sh -c 'cd /app && python -c "from server import pipeline; pipeline.run_pipeline(\"/data\")"'`
  (0.5.0 and 0.6.0 did not touch `parse.py`, so those rollouts kept the cache — 83 entries.)
- **Telegram will not let a bot message first.** A misconfigured reminder returns `400 Bad Request`
  whose body says `chat not found`; `send()` now keeps that description, because the status line
  alone is useless in an unattended log. Fix is to message the bot once from the target chat.
- **PWA runtime-refresh gate** (carried from Plan 2, still unverified in prod): the vite-pwa service
  worker must serve `/data/app.json` **NetworkFirst** (`web/vite.config.ts` `globIgnores` +
  `runtimeCaching`, cache `app-data`). Without it an installed PWA precaches the data cache-first and
  never sees a refresh until a rebuild. Verify by swapping `app.json` on the PVC and reloading.
- **No venv on this machine and `python` is not on PATH** — use `python3`, and `python3 -m venv` is
  broken (no `python3-venv`). `uv venv` works: that is how the `server/` pytest suite gets run.
- **`docs/superpowers/` is gitignored and absent on this machine.** Earlier specs, plans and the
  cutover runbook that older notes referenced are not available; do not send anyone to them.

## Commands

```bash
python -m pip install pdfplumber      # only dependency
python parse.py                       # parse all cc-statements/*.pdf -> CSVs + prints reconciliation report (per-file cache in cache/, keyed by PDF content hash — only new/changed PDFs are reparsed; STMT_CACHE overrides the dir)
python test_parse_cache.py            # plain-assert tests for cached_parse (hit/miss, version-bust, corrupt-fallback; prints OK)
python insights.py                    # transactions.csv -> recommendations.csv + prints leak summary (deterministic, no LLM)
python dashboard.py                   # transactions.csv -> dashboard.html (self-contained, offline; embeds insights.compute())
python test_insights.py               # plain-assert tests for insights.py (prints OK)
python remind_bills.py --dry-run      # bill reminders: print what would be Telegrammed, send nothing (BILLS_URL/PAID_URL point at a running server; in prod the server runs this itself on a timer)
python test_remind_bills.py           # plain-assert tests for remind_bills.py (window/nulls/paid, template rendering, per-bill state dedupe; prints OK)
python fetch_mail.py --dry-run        # IMAP: list unread statement mail in GMAIL_LABEL + what it would POST to /ingest, touching nothing (env: GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_LABEL=CC, INGEST_URL, IMAP_HOST)
python test_fetch_mail.py             # plain-assert tests for fetch_mail.py (detect_bank x6 + no-match, From>Subject>body precedence, attachment walk, mark-seen only on success; prints OK)
python llm_cats.py --suggest-cats     # OPTIONAL, off unless LLM_URL/LLM_ENABLED is set: reads the `Other` rows of transactions.csv, asks a LOCAL llama-server for a category per distinct merchant, writes suggested_cats.csv + a paste-ready CATS block next to its input. Never edits parse.py, never runs during a parse. Input defaults to $DATA_DIR/transactions.csv when DATA_DIR is set (i.e. /data in the container, cwd otherwise) — 0.9.1, because `docker exec` lands in /app (env: LLM_URL=http://localhost:8080, LLM_MODEL, LLM_ENABLED)
python test_llm_cats.py               # plain-assert tests for llm_cats.py (prompt/taxonomy, the response_format enum, CATS-wins-first with zero requests, unreachable-server and garbage-answer paths; prints OK)
docker compose up -d                  # the documented deployment: ONE service (web+API+reminders+hourly IMAP fetch, all timers in-process), published image, named volume `data`; needs `cp .env.example .env` first
node smoke_dashboard.mjs              # smoke-test dashboard.html: DOM-shim render + view-switch without throwing (prints SMOKE OK); run AFTER dashboard.py
node audit.mjs                        # Playwright visual audit of dashboard.html: console/page errors, horizontal overflow, sub-11px text across 3 views x desktop/mobile; screenshots -> audit-shots/ (needs: npm i -D playwright && npx playwright install chromium)
python probe.py <path-to.pdf>         # debug: dump y-reconstructed rows of one PDF (use when adding a bank/template)
python make_demo_data.py --pdfs       # synthetic statement PDFs -> cc-statements/ (one per bank per month + 1 deliberate duplicate); parse.py then produces the CSVs itself
python test_demo_pdfs.py              # round-trip check for the above: parse.py must re-derive every figure the generator printed (prints OK) - the ONLY automated coverage parse.py has
# Hosted PWA (web/) — see "Hosted PWA build" below:
python export_data.py                 # transactions.csv -> web/static/data/app.json (served at /data/app.json, fetched by the PWA at runtime); also emits a `cycles` map (per-card statement closing-day) consumed by the Overview "Use next" card picker (`cardpick.ts` + `CardPick.svelte`), and a `bills[]` array (newest statement per bank: current_balance + deterministic `payment_due_date` from parse.py) for the bills-due reminder (Plan 2/3)
cd web && npm run build               # build static PWA -> web/build/ (prerenders /, /trends, /cuts)
node web/audit-responsive.mjs         # Playwright responsive audit of the BUILT+served PWA: overflow / sub-11px text / console errors + desktop scroll-spy, at 390/834/1440 across all routes; screenshots -> web/audit-shots/ (run after `npm run build` + `npm run preview -- --port 4173`)
```

There is no build/lint/test suite — these are standalone scripts. CI has three jobs: `python` (fixture-only tests, empty `cc-statements/`), `parser` (generates synthetic statements, then runs `test_demo_pdfs.py` + `test_parse.py` + `parse.py`'s reconciliation gate + insights/export/parity + the server suite, whose end-to-end `/ingest` test only runs when statements are present), and `web` (`make_demo_data.py` + `export_data.py` for the `app.json` the web suite imports, then `npm ci && npm run check && npm test` in `web/` — no `--pdfs`, no pip install, since that half is stdlib-only). `parse.py`'s own reconciliation report (`status=VERIFIED/REVIEW/NO_BALANCE/DUPLICATE`, printed and written to `reconciliation.csv`) is the correctness check. Target: a parser change must not lower the VERIFIED count (currently **78 unique statements all VERIFIED to the cent**, out of 82 files — 4 are dropped duplicates). Beyond per-statement reconciliation, a stronger cross-statement check is **prev→cur chain continuity** per bank (each month's `previous_balance` should equal the prior month's `current_balance`); a break flags a misdated or missing statement. The only known gap is hsbc **2025-08 missing** (statement never collected — chain steps 07→09).

## parse.py architecture (the non-obvious parts)

- **Row reconstruction by y-coordinate** (`rows_of`/`all_rows`) is the core trick. `pdftotext -layout` mis-aligns the amount column on SC/CIMB (amounts land on the wrong visual line); grouping pdfplumber words by `top` within `ytol` rebuilds true rows. Don't replace this with plain text extraction.
- **Generic transaction rule:** a row is a transaction if it has a leading date and a trailing `[\d,]+\.\d{2}(CR)?` amount. `CR` (suffix or separate token) = credit. `find_amount` takes the rightmost money token.
- **Per-bank dispatch** in `parse_statement`. maybank/cimb/sc/hsbc/rhb share `parse_dated` (rows are `date date desc amount`); **alliance is special** (`parse_alliance`) — its date sits on the line *above* the description+amount, so it pairs a date-only row with the immediately-following row (adjacency is required, which also rejects rewards/marketing lines that merely carry a number).
- **Multi-card attribution:** cimb/rhb/alliance statements cover several cards; the parser tracks the "current card" by scanning for card-number header lines. maybank/sc/hsbc are single-card (last4 filled from a fallback regex; SC's number is masked `5520-40XX-XXXX-XXXX`).
- **Bank-specific balance extraction** (`recon_balances`) is where most fragility lives — each bank labels previous/current balance differently and reading-order text varies (e.g. HSBC has no spaces: `YourPreviousStatementBalance`; maybank interleaves the address between label and value). Multi-card banks sum per-card balances.
- **Statement month** comes from the PDF's statement date, NOT the filename (the `_N` suffix is meaningless). `stmt_month` is **ordered**: (1) tight `Statement Date` label + `dd Mon yyyy`, (2) alliance Malay `Tarikh Penyata dd/mm/yy`, (3) loose first-`dd Mon yyyy` after the word "Statement", (4) alliance English numeric, (5) first-`dd Mon yyyy` anywhere. The tight label anchor (1) matters because **some SC templates print the Payment Due Date *before* the statement date** — a loose anchor grabbed the due date and landed the statement in the wrong month (this silently mis-bucketed 3 SC statements until fixed).
- **Payment due date** (`due_date`, per-bank like `recon_balances`): emits ISO `due` on each reconciliation row. sc/hsbc are inline after the label; alliance/rhb are `dd/mm/yy(yy)`; maybank/cimb print statement-date then due-date as two adjacent `dd Mon` tokens (due = 2nd). `None` if not found — never guessed.
- **Duplicate statements** are dropped in `main()` by a content fingerprint `(bank, sdate, prev, cur, debit, credit, n)` — keep first, mark the rest `DUPLICATE`, exclude their transactions. The n8n compile workflow re-exports the **full** label-CC history each run, so the same statement routinely arrives under several filenames; without dedup every chart double/triple-counts those months (per-file reconciliation still shows VERIFIED, hiding it).
- **Synthetic statements** (`make_demo_data.py --pdfs`) are the only way `parse.py` is tested — real statements can never enter the repo or CI. `_pdf()` places text at absolute coordinates (a generalisation of `test_parse_password.py::_minimal_pdf`, still zero-dependency), and one renderer per bank reproduces the quirk that makes that branch exist: Alliance's date-above-the-row, HSBC's run-together labels, CIMB's per-card summary + separate detail page + `:0/MM` memo, SC's due-date-above-statement-date and masked card number, RHB's due date on the line below its label, Maybank's interleaved address. Amounts are written 1pt off the shared baseline so `rows_of` has to use its y-tolerance rather than an exact match. Balances come from `reconcile()`, so a generated statement reconciles for the same reason a real one does. **When you add a bank or change a layout rule, add/extend its renderer** — `test_demo_pdfs.py` is a round trip and will not catch a rule that nothing prints. It was mutation-tested: 12 deliberate breaks of `parse.py` (each per-bank balance label, the CR sign flips, multi-card tracking, `ytol`, alliance adjacency, `find_amount`'s rightmost rule, `clean_desc`'s `:NN/MM`, the `:0/MM` exclusion, `main()`'s dedup) all turn it red.
- **Per-file parse cache** (`cached_parse`, wraps `parse_statement` in the `main()` loop). `parse_statement` is pure given the PDF bytes, so its `(meta, txns)` is memoized to `<STMT_CACHE>/<sha256-of-bytes>.json` (env `STMT_CACHE`, default `cache/`; the runner points it at `<pvc>/cache`). On a miss it parses + writes (atomic `os.replace`); on a hit it loads and **re-derives `file` from the current path** (same bytes can arrive under a different filename — `source_file`/dedup must follow this run). This makes ingest O(1) in corpus size: adding 1 statement to an N-PDF volume reparses only the new file (~1.5 s vs ~100 s full reparse — see issue #1). **Cache-busting:** `PARSE_VER` = sha256 of `parse.py` itself is stored in each entry; any edit to `parse.py` invalidates the whole cache (one full reparse next run), so a parser-rule change never serves stale rows. Corrupt/missing/old-version entries silently reparse. Keyed by content hash, **not** the filename's `sha8` (the local `cc-statements/` corpus isn't content-addressed). Dedup/ordering/CSV output are unchanged → `app.json` stays byte-identical to a full rebuild (`cache/` is gitignored; tested by `test_parse_cache.py`).

### Known accounting quirks baked into the code
- **maybank balance-transfer-in**: a `BALANCE TFER ... T/F ER IN` line is a contra memo excluded from the month's debit total (flagged `excl`); installments say full `TRANSFER` and are kept.
- **CIMB-i installments** (`parse_dated`, gated to `bank=='cimb'`): rows carry a `:NN/MM` ratio. The `:0/MM` row is the **full plan principal** posted as a deferred memo (billed in later months) → flagged `excl`, dropped from the month's debit total; `:01/MM`+ rows are the actual monthly charges → kept. Every installment row (any `:NN/MM`) is flagged `inst` and force-categorized `Installments/BT` so a merchant-named plan (e.g. `LOTUS'S ...-3M`) doesn't leak into Groceries and double-count against its own monthly charge.
- **Credit (`CR`) balances**: a trailing `CR` on a balance label = credit (negative) balance. `recon_balances` flips the sign for CIMB (`PREVIOUS BALANCE`, card-table `STATEMENT BALANCE`) and alliance (per-card `PREVIOUS STATEMENT BALANCE` / `CURRENT BALANCE`, via `sum_signed` — the virtual card often sits in credit). Without this the recon is off by exactly 2× the credit balance.

### Dashboard
`dashboard.py` reads `transactions.csv` and emits `dashboard.html` — one self-contained file (data embedded inline, charts hand-rolled in SVG + vanilla JS, no libraries/CDN, opens offline). It also `import insights` and embeds `insights.compute(rows)` in the page payload (`D.recs`) — so a `dashboard.py` build depends on `insights.py`. Re-run after `parse.py`. Defaults to a **Discretionary** spend definition (drops the `NON_SPEND` financing/contra categories, same set as `parse.py`); an "All" toggle re-includes them; per-card chips filter all views. Three views (tab order: **This Month · Overview · Recommendations**; the page lands on **This Month** by default — `let view="monthly"`):
- **This Month** (one month, defaults to the latest `statement_month`) — the **monthly-ritual hero** (Bucket 2). Built by `heroBand(m)` at the top of `#view-monthly`: a **spend-vs-prior headline** (netted discretionary total + Δ RM/% vs prior month, red↑/green↓), **cashback earned**, **top movers** (`movers(m)`: ≤3 categories that rose most vs prior month + the single biggest drop; each row click-expands a per-merchant prior→current delta table via `monthCatMerchants`), and **cut candidates this month** (`cutCandidates(m)`: leaks from `D.recs` filtered by `cutTouchesMonth` — subs with `evidence[].m===m`, one-offs with `month===m`, creep when `m∈D.months.slice(-3)` — ranked by `rmAnnual`, top 4; clicking a `.cutrow` calls `gotoRecs()` to jump to the Recommendations tab). Below the hero: trimmed 3-KPI strip (`#mkpis`: Transactions / Biggest txn / Top category — total+cashback live in the hero now), per-card + donut, the diverging change-vs-previous-month bar (`mom()`, the full detail behind the hero's movers summary), and a sortable transaction table. Hero follows `curMonth`, `selCards`, and the Disc/All `mode`. Shared `#hero` click/keydown listeners disambiguate `.cutrow` (→`gotoRecs`) vs `.mvrow` (→`toggleMv` expand). Month-scoping is all client-side — **no `insights.py` change**.
- **Overview** (all months): monthly stacked-by-category trend, spend-by-card (click to filter), category donut, card×category heatmap, top-20 merchants, and cashback/rebates-earned panels.
- **Recommendations** (cut-spend leak finder, see below): 5-KPI strip + five grouped, ranked, click-to-expand cards. Card markup is `recCard`/`instCard`/`xferCard` → `.rec` (header row + hidden `.detail`); one `#recgrid` delegation listener toggles `.open`+`aria-expanded` on click/Enter/Space (keyboard-accessible). Cards filter by the same card chips via their `evidence[].c`.

Spend charts are all debit-only (`r.t===0`). Cashback/rebates are **credits** in the `Rebate/Cashback` category, so they're invisible to every spend chart by design — presented separately via the green cashback panels (`cbRows()`), the hero/Monthly cashback figure, and the credit rows in the Monthly table. The Discretionary/All toggle does not touch them.

There is no browser dependency to *test* it either: it's hand-rolled DOM, so a tiny `document`/`createElementNS` shim in Node (`smoke_dashboard.mjs`) loads the built `dashboard.html`, evals its inline `<script>`, runs the initial `render()`, and fires each view button — asserting the page renders + switches views without throwing (`SMOKE OK`). Run it after every `dashboard.py` build. (Limitation: the shim's `closest()` returns null, so click/expand *behaviors* — mover expand, cut-row → Recs nav — aren't exercised; they're verified by reading.)

**Accessibility floor (a11y).** Every chart element is made keyboard- and touch-reachable through one helper, `tip(node, html, onClick?)` — it sets `tabindex`, `aria-label` (= `plain(html)`, the tooltip text with tags stripped), and binds `mousemove`/`mouseleave` **plus** `focus`/`blur` and `touchstart`. With `onClick` the element becomes `role=button` (Enter/Space activate, e.g. the clickable card-filter bars); without it, `role=img`. Tooltip positioning has two paths: `show(ev,…)` follows the pointer, `showAt(node,…)` derives an anchor from `getBoundingClientRect()` for focus/touch (guarded — the smoke shim has no `getBoundingClientRect`). A document-level `touchstart→hide` dismisses the tooltip on tap-elsewhere; `.tt` is `aria-hidden` (content is re-announced via each element's `aria-label`, so no double-read). `swap(id,svg)` tags each chart `<svg>` `role=group` + `aria-label` taken from its `.card h2`. Sortable `th`s are keyboard-operable (tabindex + Enter/Space + `aria-sort`). Global `:focus-visible` ring on all controls (+ a white ring for focused SVG nodes); a `prefers-reduced-motion` block kills transitions. Contrast was checked with a real WCAG calc, not by eye: `--mut #8b97a6` **passes** AA (5.3–6.3 on the panels) — but red **text** `#ef4444` failed on `--panel2` (4.16), so small red/green *text* uses the `--red #f87171` / `--green #34d399` tokens while large bar/rect **fills** keep the saturated `#ef4444`/`#34d399` (large-text AA is 3.0). When adding a chart, route every interactive node through `tip()` rather than wiring `mousemove` by hand — that's what keeps it accessible.

**Icons & numerals (identity, Bucket 4).** Categories carry inline **Material Design Icons** — `dashboard.py` holds a `CAT_ICON` map (category → MDI name) and `MDI` dict (name → verbatim 24×24 path `d`), both shipped in the payload (`D.catIcon`/`D.icons`). They're **inlined, not a webfont/CDN** (keeps the single-file offline guarantee). JS helpers: `svgIcon(name,cls)` (raw, inherits `currentColor`) and `catIcon(g)` (wraps in a span tinted to the category colour). Icons are **site-wide**: tabs + reset button (injected at init), every chart **`<h2>` card header** (via a `data-ic="<mdi-name>"` attribute + an init loop that prepends `svgIcon(h.dataset.ic,"h2ic")`), all three **KPI strips** (Overview/Monthly/Recs — the K-arrays carry an icon name/HTML; "Top category" KPIs use the live category's icon), the **hero subheads** (wallet/cash-plus/swap-vertical/content-cut), category legends, movers, the monthly table tag, rec catchips, and rec section headers. `.mdi{display:inline-block;width:1.05em;fill:currentColor}` deliberately **overrides** the global `svg{width:100%}` (class beats element) — don't remove it or every icon balloons to full width. `.card h2` is `display:flex;align-items:center` with the trailing sub-`<span>` pushed right via `margin-left:auto` (NOT `justify-content:space-between`, which would split the prepended icon from its title). **When adding a new category, add both a `COLORS` and a `CAT_ICON` entry** (unmapped categories fall back to the `shape-outline` icon); adding a new chart card, give its `<h2>` a `data-ic`. Money/count cells use a `--mono` tabular stack. Mobile: a 560px breakpoint **plus** `.grid>*{min-width:0}` — the latter is load-bearing (without it the transactions-table card refuses to shrink below its content width and forces horizontal scroll on phones; caught by `audit.mjs`).

**SVG chart gotcha (`viewBox` width ⇒ rendered text size).** Charts set a `viewBox` and `width:100%`, so the svg scales to its card and **font size scales with it**: a big `viewBox` W in a half-width card shrinks 11px text to unreadable (the cashback `hbar` used `W=1180` → ~4px; fixed to `W=470`). Rule of thumb: keep a half-width card's chart `viewBox` W in the ~400–560 range so labels render near their nominal px. The donut legend additionally **clamps** category names (`>17` chars → ellipsis) and right-anchors the `%` at the viewBox edge so long names like "Health/Insurance" never collide with their percentage. Diverging bars (`mom()`) place a decrease's value label to the right of the centre axis (its row's right zone is empty) so it can't overlap the left-gutter category label.

## insights.py — leak detection & the Recommendations tab

`insights.py` is a **deterministic, offline, stdlib-only** leak detector (no LLM at runtime). It consumes the same row dicts `dashboard.load()` builds (`{c:bank·last4, m:YYYY-MM, g:category, a:amount, t:0 debit/1 credit, d:desc}`), and `compute(rows)` returns `{recs:[…], savingsAnnual, installments:[…], transfers:[…], counts:{sub,installment,transfer,creep,oneoff}}`. Runnable standalone (writes `recommendations.csv` for review); imported by `dashboard.py`. Tested by `test_insights.py` (plain asserts on synthetic fixtures, prints `OK`). **Goal anchor:** the tab exists to drive one decision — *cut discretionary spend* on a monthly-ritual cadence.

The **"LLM polish" is a build-time human-in-the-loop step, not embedded**: after a real run, Claude Code reads `recommendations.csv`, sanity-checks the detected leaks against the actual data, and tunes thresholds / the merchant override lists. Several real-data passes already hardened the detectors (each guard below exists because a specific false-positive showed up).

### Detectors (and the non-obvious guards)
- **Subscriptions** (`find_subs`): a merchant (by `norm_merchant`, which strips trailing ref/date/number tokens) is a sub if it recurs in **≥4 distinct months**, **≤1.3 charges/month**, and is **price-stable**. Stability + monthly price are measured on a **recent window (last ≤4 charges), not whole history** — so a tier-stepped sub (e.g. Claude.ai RM85→RM410 after an upgrade) still qualifies, reported at its *current* price. Restricted to an **allowlist `SUB_CATS = {Subscriptions, Telco/Utilities}`** (kills F&B/grocery/fuel coincidences like the Akmal Squared café). BNPL rows (`_is_bnpl`: `SPAYLATER|REPAYMENT`) excluded. A sub is flagged **`stale`** (hint → "Already cancelled?") if its last charge is ≥2 months before the newest statement month.
- **Creeping categories** (`find_creep`): per discretionary category, **mean(last 3 mo) ÷ mean(prior 3 mo) > 1.2** with a **prior-mean > RM50 floor** (avoids divide-by-near-zero), ≥6 months of data. Carries a **per-merchant breakdown** (`_cat_merchant_breakdown`, prev-3 vs last-3 by merchant) so "Telco +RM105" expands into which bills drove it.
- **Big one-offs** (`find_oneoffs`): debit in the **latest 2 months** above **P95 of discretionary debits** or **>3× that category's median**, excluding Installments/Transfers, BNPL, and — crucially — **any merchant seen in ≥2 months** (recurrence guard; stops recurring insurance/SaaS like AIA/Claude from masquerading as a one-time splurge).
- **Installments & balance transfers** (`find_installments`): re-derives structure from the `Installments/BT` rows **plus override merchants** `INSTALLMENT_MERCHANTS = {SENHENG, HOME PRODUCT}` (real installments that SC/maybank print with no marker, so `parse.py` categorized them `Shopping`). Splits **balance transfers** (`_is_bt`: `BALANCE TRANSFER|BAL TRANSFER|BALANCE TFER|SMART MOVE|T/F ER IN`) from **purchase plans**. Drops **principal-memo** rows (`_is_memo`: a `0/NN` zero-numerator ratio, or `T/F ER IN`) so the deferred principal isn't counted as a monthly charge. Groups by **`_plan_key`** (strips `INSTL ` prefix / trailing `:`-segment / ` NN OF MM` / counter — keeps Harvey-Norman-24M vs -36M as distinct plans; do NOT collapse on the override keyword or you merge unrelated plans, e.g. CIMB Grand-Senheng-12M with SC Senheng). Per plan: monthly (= sum of non-memo charges in its latest active month, so concurrent sub-charges add up), term, progress, remaining/end/remaining-balance. **Progress/term come from the bank's printed installment counter** via `_counter`: `:NN/MM` (maybank/cimb/rhb — `parse.py`'s `clean_desc` now **keeps** this ratio in the description so insights can read it) or `NN OF MM` (alliance). The counter is **trusted only when its total (denominator) is constant across the plan's months and current ≤ total** — this rejects reversed `total/current` layouts, stray colon-dates, and other unseen formats, which fall back to the estimate rather than a confident wrong number. **Honesty rule:** exact only where such a counter is printed; otherwise term comes from the `-NNM`/`E36` name suffix and remaining is an `est=True` estimate (`term − distinct-months-seen`) — valid only for a plan that began inside the collected window; one that started earlier reads high (the bug the `:NN/MM` counter fixes). The UI labels estimates `~est` and never shows a fake-precise end date. `_disp` cleans display names (leading `%%`, trailing ` -`).

### Ranking, savings & the tab
Subs/creep/one-offs are ranked into `recs` by **annual RM impact** (`severity`); installments/transfers are separate top-level arrays sorted by monthly. **`savingsAnnual` = cancellable subs + creep only** — installments and balance transfers are committed debt, never counted as "savings" (and Akmal-style false subs were the reason the number kept moving during tuning). The tab renders five groups: Subscriptions → Installments → Balance transfers → Creep → One-offs, each card category-badged with click-to-expand drill-down (charge history / merchant-delta / txn detail). Design specs live in `docs/superpowers/specs/2026-06-21-*.md`.

### Hosted PWA build (web/)
After `parse.py`: `python export_data.py` regenerates `web/src/lib/data/app.json`,
then `cd web && npm run build` produces the static PWA in `web/build/`.
Full refresh: `python parse.py && python insights.py && python export_data.py && python verify_parity.py && cd web && npm run build`.
Then gate the build: `npm run preview -- --port 4173 &` and `node audit-responsive.mjs` — must print `AUDIT OK` (no overflow / sub-11px / console errors at 390/834/1440, and `#overview` is the active scroll-spy link at top on desktop).
(Hosting/auto-deploy = Spec 2, see docs/superpowers/backlog.md.)

**PWA install/SW registration is wired by hand in `src/app.html`** (a `<link rel="manifest">` + a one-line `navigator.serviceWorker.register('/sw.js')`). `@vite-pwa/sveltekit` *generates* `sw.js`/`manifest.webmanifest`/`registerSW.js` fine, but its auto-inject **silently no-ops** on this Vite 8 + SvelteKit build — nothing referenced them, so there was no manifest link and no SW → Chrome/Firefox offered only an "Add to Home screen" shortcut (never **Install**) and the Workbox offline cache never populated. Don't remove those `app.html` lines expecting the plugin to re-inject. Verify after a dep bump: `grep -oE 'rel="manifest"|serviceWorker.register' build/index.html` must hit (the served file is the adapter-static **fallback** `index.html`, which is built from `app.html`). Install needs HTTPS *or* localhost (secure context); a plain-HTTP LAN IP downgrades to a non-installable shortcut even with all of the above correct.

The PWA fetches its data at **runtime**: `data.svelte.ts` (a runed store, re-exported
through the `data.ts` barrel so `import { app } from '$lib/data'` is unchanged)
`fetch('/data/app.json')` on mount and fills `app` in place; `+layout.svelte` gates all
views behind a loading skeleton (`[data-loading]`) / error / ready state, and the all-time
aggregates are precomputed once into `agg` after the fetch. `export_data.py` writes
`web/static/data/app.json` (served at `/data/app.json` locally; in prod the runner serves
it from the PVC) — so a data refresh needs **no rebuild**. The Overview view also renders a
**bills-due panel** (`BillsDue.svelte` + pure `bills.ts`): `app.bills[]` sorted by due date,
red when `< 3` days out (KL-time today via `todayMYT()`).

The PWA is responsive across 3 tiers: <768px mobile (routed, BottomNav, 1-col),
768-1024px tablet (routed, 2-col panels), >=1024px desktop (TopBar + unified
Dashboard rendering all three Views in anchored sections, capped max-w-7xl).
+layout.svelte renders two CSS-toggled subtrees (lg:hidden routed / hidden
lg:block Dashboard) — both mount at all widths, but all-time chart aggregates
are precomputed once into `agg` in `data.svelte.ts` after the fetch so the double-render adds no compute.
Acceptance gate: build, `npm run preview -- --port 4173`, then
`node web/audit-responsive.mjs` (checks 390/834/1440 for overflow/sub-11px/
console errors; screenshots -> web/audit-shots/).

The Overview view also renders a "Use next" card picker (`CardPick.svelte` →
`cardpick.ts`): ranks cards by a 50/50 blend of interest-free float runway
(days until each card's statement closing-day, from `app.json` `cycles`) and
inverse trailing-3-month net-spend share, filtering cards dormant >6 months.
"Today" is resolved in Asia/Kuala_Lumpur (GMT+8) client-side; the ranking
logic is pure/tested in `cardpick.test.ts`.

### Refresh loop (adding new statements)
New statements → run the n8n `compile-cc-statements` workflow (re-exports the **full** label-`CC` history, not just new mail) → unzip into `cc-statements/`, replacing contents (keep the `<bank>_…` filename prefix; the `_N` index is meaningless) → `python parse.py && python test_insights.py && python insights.py && python dashboard.py && node smoke_dashboard.mjs && node audit.mjs` → check the reconciliation report stays all-VERIFIED, and that `audit.mjs` prints no ISSUES (overflow / sub-11px text — e.g. a new long card name or category could overflow a chart) (a new `REVIEW` means the bank changed its template — debug with `probe.py`) and skim `recommendations.csv` for new false-positives (a new unseen recurring merchant may need an `INSTALLMENT_MERCHANTS` / category-allowlist tweak). New months/cards surface in all dashboard views automatically.

### Categorization & spend definition
Keyword map (`CATS`, ordered — first match wins) → standard taxonomy. The back-catalogue is hand-mapped to merchant-specific keywords, so `Other` stays small — but it is **not empty**: as of 2026-08-20 the production corpus has **15 rows / RM958** in it, all one-off merchants that appeared after the last hand-mapping pass (`K S S OTOMOBIL`, `Dominos Malaysia`, `Miniso Winky`, …). `Other` is the safety fallback for new/unseen merchants and is meant to be watched — it surfaces in the dashboard donut and during the refresh-loop check. Most entries are a one-line `CATS` addition; `llm_cats.py --suggest-cats` (#29, suggest mode only) drafts those lines with an optional local model. **`Vehicle`** is a merged bucket — fuel + ride-hail/transport + tolls/parking + auto/workshop (the old separate `Fuel`/`Transport` categories were folded in). Other custom categories: `Certifications` (MBOT etc.), `Charity` (donations/zakat). `total_spend` excludes the non-consumption categories `NON_SPEND = {Installments/BT, Transfers/Payments, Rebate/Cashback}`. The `Installments/BT` total is inflated by monthly recurrence — never treat it as monthly consumption.

**Spend is netted**: in the summaries, consumption categories use signed amounts (debit `+`, credit `−`) so a **refund/reversal** (a credit sitting under a merchant category — e.g. a cancelled `…-REV` booking) subtracts from that category. `NON_SPEND` categories stay debit-only/gross (their credits are bill payments & cashback, not negative spend). The dashboard mirrors this exactly via its `val(r)` helper. Net cells can occasionally go slightly negative (a refund whose original purchase was a different month) — charts guard against it; the reconciliation is unaffected (it nets all debits/credits globally regardless of category).

## n8n workflows

> **Note:** the workflow JSONs (`*-cc-statement*.json`, `reminder-bills.json`) and their tests are **gitignored / kept local for now** — not part of the public repo. Descriptions below document the live local instance.

- `process-cc-statement.json` — original: Gmail trigger (unread, label `CC`) → get bank → set password → unlock via Stirling-PDF (`pdf.opariffazman.com`) → split/extract → Gemini info extraction → Google Tasks reminder + Telegram. **Nothing in it is still needed**, and it is **disabled as of 2026-08-21**: the unlock is dead (#11), the reminder is the server's own timer (#13, seen firing on its own), and the Gmail trigger is `fetch_mail.py` (#12, proven on a real mail). Its last act was ingesting the 2026-08 CIMB statement hours before `fetch_mail.py` re-took the same mail idempotently. `reminder-bills.json` must stay disabled too, or the same bill gets messaged twice.
- `compile-cc-statements.json` — derived: manual trigger → Gmail `getAll` (all label-`CC` mail) → get bank → set password → unlock → combine → zip → Telegram. Stops after unlock; used to bulk-collect the PDFs that `parse.py` consumes.

Passwords stored inside the workflow on the n8n PVC should be cleared as the unlock nodes go — the k8s Secret `lazyexpense-secrets` is the source of truth now.

Both share a per-bank PDF password map (each bank derives its default from cardholder DOB/IC). **Passwords are NOT committed** — the workflow Code node reads them from n8n env vars `CC_PW_<BANK>` (`CC_PW_MAYBANK`, `CC_PW_CIMB`, `CC_PW_SC`, `CC_PW_ALLIANCE`, `CC_PW_HSBC`, `CC_PW_RHB`); set them on the n8n instance. Bank detection keys off the bank name appearing in the email text/PDF.

When editing a workflow JSON, credential references (`credentials.*.id`) point at the live n8n instance — preserve them on import.
