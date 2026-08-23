# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A personal pipeline for processing Malaysian credit-card e-statements (6 banks: maybank, cimb, sc/Standard Chartered, alliance, hsbc, rhb). One deployment does the whole thing end to end:

1. **`fetch_mail.py`** — IMAP over the Gmail label `CC`, POSTing each password-protected PDF attachment to `/ingest`.
2. **`parse.py`** — deterministic extraction of those PDFs (it opens the locked ones itself) into transaction/spend CSVs. **No LLM.**

`/ingest` chains `parse.py → insights.py → export_data.py`, so a statement that arrives in the mailbox is on the dashboard without anyone touching it. `cc-statements/` is the local corpus for parser work only.

## How it runs today

**Open work lives in GitHub issues, not in this file.** `gh issue list` is the source of truth for
what is next; this file is for how the thing works and what will bite you. Do not re-add status,
handoff notes or per-release changelogs here — file an issue or write a release note.

The live deployment runs `ghcr.io/officialdad/lazyexpenses/app` on k3s behind Traefik: one
container serving the PWA, re-running `parse.py → insights.py → export_data.py` over a 5Gi PVC on
every `/ingest`, fetching statement mail over IMAP on a timer, and sending the bill reminders
itself.
`Recreate` strategy — the volume is RWO and the code **assumes a single instance** (two replicas
would each hold their own `reminded.json` and could double-send).

**Infra lives in a separate private repo, not this one** — the Deployment, the PVC and the
Ingress are all over there, and the Ingress is a single object shared with the cluster's other
services. Images are digest-pinned for Renovate; a push to that repo's `main` auto-deploys the
manifest dirs that changed. **`kubectl` is a mise shim there, so run it from inside that repo**
or it fails to resolve. A release is a `v*` tag — `docker.yml` builds,
gates the push on the image reporting the version it was tagged with, then you bump the digest in
the infra repo.

### The pieces, and why they are shaped that way

- **`fetch_mail.py`** — IMAP → select `GMAIL_LABEL` → `UNSEEN` → **`BODY.PEEK[]`** (a plain FETCH
  would set `\Seen` itself and defeat the retry) → POST each PDF to `INGEST_URL` as hand-rolled
  multipart → `+FLAGS \Seen` **only if every attachment ingested**. `detect_bank()` is pure, tried
  against From, then Subject, then body; `None` skips the mail rather than guessing, so a skipped
  mail nags every run on purpose. The multipart filename is `<bank>.pdf`, **never** the mail's —
  it is untrusted, and `pipeline.save_pdf` names by content hash anyway. That hashing is also why
  re-ingesting an already-seen statement is idempotent and safe.
- **Both timers live in the web process**, not in a CronJob — the server is already the
  long-running thing that knows `DATA_DIR`, so it is one container to deploy instead of two. Loop
  config is read **per tick**, so a settings edit takes effect without a restart.
- **`_fetch_loop` deliberately goes back out through `/ingest` over the loopback**, unlike
  `_reminder_tick` which reads the PVC directly. `/ingest` holds the lock, saves the PDF and
  reparses the corpus; routing through it keeps one copy of that. The cost is knowing our own port,
  which is what `INGEST_URL` is for.
- **Two events per bill (#83)**: `run()` says "due soon", `announce()` says "this arrived".
  `/ingest` diffs `bills[]` **before and after** the pipeline run and announces only keys
  that appeared — "an upload happened" is the wrong trigger, because `save_pdf` names by
  content hash and a `fetch_mail` retry re-posts the same bytes on purpose. State lives in
  the same `reminded.json` under a **different namespace** (`arrived|<bank>|<month>`); the
  bare key is the due reminder's, and sharing it would silence that reminder forever. A
  bill that was already there, or older than last month, is **recorded without being
  sent** — that is the seed that stops a backfill firing a burst.
- **Reminders**: `remind_bills.py` holds the logic and still runs standalone. Web Push is the
  default transport and needs no configuration; Telegram is the opt-in fallback. **The split is in
  `send()`, not in the server**, so `reminded.json` stays keyed by *bill*, not by transport — both
  configured is still one message per bill. `send()` raises only when *nothing* got through, which
  is exactly when the bill must not be recorded. The reminder loop has **no env gate**: it always
  starts and checks `transports_configured()` per tick, because a browser can subscribe hours after
  startup.
- **Web Push crypto is hand-rolled** on `cryptography` (RFC 8291 + 8292), function-local imports so
  `remind_bills.py` still runs with only `pdfplumber`. The one-runtime-dependency rule is about
  `parse.py`; `pywebpush` would pull four packages to save ~80 lines. The service worker seam is
  `workbox.importScripts: ['/push-sw.js']` — `generateSW` cannot be given a `push` handler, and
  switching to `injectManifest` would rewrite the fragile PWA wiring.
- **Settings** live in `/data/settings.json` and **the environment always wins**. Env-owned names
  come back in `locked[]` and **a POST to a locked name is ignored** rather than written, so
  removing the env var later restores the volume copy. **Secrets are write-only** — `public()`
  returns a bool per secret, never a value, not even masked. Setting names are a **whitelist**
  because they are merged into the `parse.py` subprocess environment, where an arbitrary name is
  arbitrary env injection (`LD_PRELOAD`, `PYTHONPATH`). **`APP_PASSWORD` is deliberately absent**:
  the gate must not be settable through the thing it gates.
- **Auth** is an optional shared password (`APP_PASSWORD`), off unless set, enforced in
  `@app.middleware("http")`. `/healthz` and `/api/login` stay open; `/ingest` also accepts an
  `X-App-Password` header. `.env.example` ships `changeme@123` so the compose path is closed by
  default, and the server warns loudly at startup while that is still the value.
- **Docs split by audience**: README is user-facing, `docs/DEPLOY.md` is the hosting and automation
  reference, `CONTRIBUTING.md` covers adding a bank and the test suite. Keep them that way.

**Backup-critical files on the volume**, none of them regenerable: `settings.json` (mode 0600, not
encrypted), `vapid.json` (replacing it silently orphans every stored push subscription),
`cats.json` (#82 — hand-confirmed merchant categories, and nothing else knows them), and
`reminded.json`/`paid.json`/`push_subs.json`.

## Sharp edges

- **A deployed shell can sit stale — fixed by #67 in 0.13.0, but never for the release that
  introduces the fix.** `registerType: 'autoUpdate'` configures the generated `registerSW.js`, the
  thing that *reloads the page* on new content, and **that file is never loaded**: auto-inject
  no-ops on this build and the SW is hand-registered in `app.html`. `skipWaiting`/`clientsClaim`
  really are in the deployed `sw.js`, so the new worker activates and claims clients — but an
  already-loaded document keeps its old assets, and an installed PWA resumed from the background
  may never navigate at all. **0.13.0 adds the missing reloader** (a "New version / Reload" banner
  in `app.html`, plus `reg.update()` on an interval and on resume), so from **0.14.0 onward** an
  open tab is told. A browser holding a **pre-0.13.0** shell has no reloader in it and still needs
  one manual reload. Same blind spot as **#62's version line, which cannot render on a shell that
  predates it** — nothing shown reads as "no such feature", not "you are stale"; that works from
  0.12.0 onward. **If the UI looks like the previous release, hard-reload before debugging the
  server.**

- **`bank` on `/ingest` is load-bearing — validated since 0.9.0 (#31), but only against the six.**
  It still selects the password, the parser branch, and the filename *permanently*, because
  `parse.py` re-derives the bank from that filename on every later run. An unknown value is now a
  400 that writes nothing; a **wrong-but-valid** one (`hsbc` for a CIMB statement) still lands and
  still misparses forever.
- **Editing `parse.py` invalidates the whole parse cache** (`PARSE_VER` = hash of the file). On the
  0.4.0 rollout the full 84-PDF reparse took **109s**, versus 0.5s warm. Long enough to trip an
  ingest HTTP timeout, so warm it in-pod after any deploy that touches the parser:
  `kubectl exec deploy/<name> -- sh -c 'cd /app && python -c "from server import pipeline; pipeline.run_pipeline(\"/data\")"'`
  (0.5.0 and 0.6.0 did not touch `parse.py`, so those rollouts kept the cache — 83 entries.)
  **The #82 release touches `parse.py`** (it grows the override lookup), so it pays that
  full reparse once — warm it in-pod straight after the deploy. Every run *after* that is
  warm again, including the one `POST /api/cats` triggers, which is the whole reason the
  override is applied outside `parse_statement`.
- **Telegram will not let a bot message first.** A misconfigured reminder returns `400 Bad Request`
  whose body says `chat not found`; `send()` now keeps that description, because the status line
  alone is useless in an unattended log. Fix is to message the bot once from the target chat.
- **PWA runtime-refresh gate** (carried from Plan 2, still unverified in prod): the vite-pwa service
  worker must serve `/data/app.json` **NetworkFirst** (`web/vite.config.ts` `globIgnores` +
  `runtimeCaching`, cache `app-data`). Without it an installed PWA precaches the data cache-first and
  never sees a refresh until a rebuild. Verify by swapping `app.json` on the PVC and reloading.
- **`app.json` lives on the PVC and a deploy does NOT rewrite it.** The icon table ships inside it,
  so a newly added MDI icon renders as `Icon.svelte`'s visible `square-outline` fallback in prod
  until a pipeline run. Two releases in a row needed the manual warm above (#64's bell, #66's cog).
  Confirm afterwards that the icon count went up and the name is present.
- **The password gate must be middleware, not a route dependency.** A `StaticFiles` mount is not an
  `APIRoute`, so a global route dependency never runs for it — and `web/build/data/` lives inside
  that mount. `//data/app.json`, `/data/app.json/`, `/./data/app.json`, `/data//app.json`,
  `/x/../data/app.json` and `/DATA/app.json` all served real data while `/data/app.json` correctly
  401'd. `@app.middleware("http")` runs before routing and sees mount traffic;
  `posixpath.normpath("/" + path.lstrip("/"))` closes the variants, and the `lstrip` is
  load-bearing because `normpath` preserves a leading `//`. **Do not write that regression test
  with `TestClient` — httpx normalises 3 of the 5 variants client-side and it passes with the hole
  wide open.** Build the ASGI scope by hand.
- **A new root-level module is not in the image unless `Dockerfile`'s COPY line names it.** 0.9.1
  shipped a documented command that could not run for exactly this reason. CI now greps fenced code
  blocks in the docs against that COPY list.
- **`ARG` does not cross a `FROM`.** The version must be re-declared in *both* build stages, or the
  shell and the server disagree — which is precisely what the UI's `0.13.0 · server 0.14.0` line
  exists to reveal.
- **A teardown reported as done was not done — this has now happened twice.** Check
  `kubectl get pods,svc,ingress -A | grep <name>` *and* grep the manifests. Deleting a live object
  does not delete the file that recreates it on the next apply.
- **Parallel worktrees are cheap only if you write down file ownership first.** Name who owns which
  file before spawning; the collision zone is `server/app.py` + `web/`. Done that way, a four-way
  wave merged with zero conflicts. **And assign preview ports** — parallel `npm run preview` walks
  4173→4174→4175 without failing, so `audit-responsive.mjs` will happily print `AUDIT OK` against a
  sibling's build. Use `--strictPort`, set `AUDIT_BASE`, and grep the served output for something
  unique to your change.
- **`llm_cats.py`'s prompt is the category names and nothing else, and that is load-bearing.** Prose
  describing the categories — anywhere in the prompt, even one sentence — collapses the model to a
  single answer; length is not the variable (a *longer* few-shot prompt scores the same). Measured
  1/5 → 4/5. `test_llm_cats.py::test_the_prompt_is_the_category_names_and_nothing_else` guards it.
  Confidence is decoration: `high` comes back on wrong answers too.
- **`urllib` capitalises header names**, so Web Push requests carry `Ttl:` and `Content-encoding:`.
  Services accept them (headers are case-insensitive), but do not grep for `TTL`.
- **An internal hostname resolves to a private IP, so off-LAN access needs a tailnet Split DNS
  entry** pointing that domain at the LAN's resolver. When it is missing, a foreign network's
  resolver refuses the private address: Chrome reports "can't find" — a *resolution* failure, not a
  timeout — while an installed PWA keeps rendering happily from its offline cache and merely looks
  out of date. **Do not read that as a bad deploy.** Hit the ingress by raw LAN IP from the phone:
  any response, even a 404 from Traefik, proves the route works and isolates it to DNS.
- **No venv on this machine and `python` is not on PATH** — use `python3`, and `python3 -m venv` is
  broken (no `python3-venv`). `uv venv` works: that is how the `server/` pytest suite gets run.
- **`docs/superpowers/` is gitignored and absent on this machine.** Earlier specs, plans and the
  cutover runbook that older notes referenced are not available; do not send anyone to them.

## Commands

```bash
python -m pip install pdfplumber      # only dependency
python parse.py                       # parse all cc-statements/*.pdf -> CSVs + prints reconciliation report (per-file cache in cache/, keyed by PDF content hash — only new/changed PDFs are reparsed; STMT_CACHE overrides the dir)
python tests/test_parse_cache.py      # plain-assert tests for cached_parse (hit/miss, version-bust, corrupt-fallback; prints OK)
python insights.py                    # transactions.csv -> recommendations.csv + prints leak summary (deterministic, no LLM)
python dashboard.py                   # transactions.csv -> dashboard.html (self-contained, offline; embeds insights.compute())
python tests/test_insights.py         # plain-assert tests for insights.py (prints OK)
python remind_bills.py --dry-run      # bill reminders: print what would be Telegrammed, send nothing (BILLS_URL/PAID_URL point at a running server; in prod the server runs this itself on a timer)
python tests/test_remind_bills.py     # plain-assert tests for remind_bills.py (window/nulls/paid, template rendering, per-bill state dedupe; prints OK)
python fetch_mail.py --dry-run        # IMAP: list unread statement mail in GMAIL_LABEL + what it would POST to /ingest, touching nothing (env: GMAIL_USER, GMAIL_APP_PASSWORD, GMAIL_LABEL=CC, INGEST_URL, IMAP_HOST)
python tests/test_fetch_mail.py       # plain-assert tests for fetch_mail.py (detect_bank x6 + no-match, From>Subject>body precedence, attachment walk, mark-seen only on success; prints OK)
python llm_cats.py --suggest-cats     # OPTIONAL, off unless LLM_URL/LLM_ENABLED is set: reads the `Other` rows of transactions.csv, asks a LOCAL llama-server for a category per distinct merchant, writes suggested_cats.csv + a paste-ready CATS block next to its input. Never edits parse.py, never runs during a parse. Input defaults to $DATA_DIR/transactions.csv when DATA_DIR is set (i.e. /data in the container, cwd otherwise) — 0.9.1, because `docker exec` lands in /app (env: LLM_URL=http://localhost:8080, LLM_MODEL, LLM_ENABLED)
python tests/test_web_push.py         # plain-assert tests for web_push.py (RFC 8291 test vector byte-for-byte, VAPID JWT signature verified with the public key, 410 drops the subscription, the two-transport fan-out; prints OK)
python tests/test_llm_cats.py         # plain-assert tests for llm_cats.py (prompt/taxonomy, the response_format enum, CATS-wins-first with zero requests, unreachable-server and garbage-answer paths; prints OK)
docker compose up -d                  # the documented deployment: ONE service (web+API+reminders+hourly IMAP fetch, all timers in-process), published image, named volume `data`; needs `cp .env.example .env` first
node smoke_dashboard.mjs              # smoke-test dashboard.html: DOM-shim render + view-switch without throwing (prints SMOKE OK); run AFTER dashboard.py
node audit.mjs                        # Playwright visual audit of dashboard.html: console/page errors, horizontal overflow, sub-11px text across 3 views x desktop/mobile; screenshots -> audit-shots/ (needs: npm i -D playwright && npx playwright install chromium)
python dev/probe.py <path-to.pdf>     # debug: dump y-reconstructed rows of one PDF (use when adding a bank/template)
python dev/make_demo_data.py --pdfs   # synthetic statement PDFs -> cc-statements/ (one per bank per month + 1 deliberate duplicate); parse.py then produces the CSVs itself
python tests/test_demo_pdfs.py        # round-trip check for the above: parse.py must re-derive every figure the generator printed (prints OK) - the ONLY automated coverage parse.py has
# Hosted PWA (web/) — see "Hosted PWA build" below:
python export_data.py                 # transactions.csv -> web/static/data/app.json (served at /data/app.json, fetched by the PWA at runtime); also emits a `cycles` map (per-card statement closing-day) consumed by the Overview "Use next" card picker (`cardpick.ts` + `CardPick.svelte`), and a `bills[]` array (newest statement per bank: current_balance + deterministic `payment_due_date` from parse.py) for the bills-due reminder (Plan 2/3)
cd web && npm run build               # build static PWA -> web/build/ (prerenders /, /trends, /cuts)
node web/audit-responsive.mjs         # Playwright responsive audit of the BUILT+served PWA: overflow / sub-11px text / console errors + desktop scroll-spy, at 390/834/1440 across all routes; screenshots -> web/audit-shots/ (run after `npm run build` + `npm run preview -- --port 4173`)
```

The tree is three parts (#89): the eight runtime scripts plus `server/` and `web/` at the root, every `test_*.py` in `tests/`, and `probe.py`/`make_demo_data.py`/`verify_parity.py` in `dev/`. **Run everything from the repo root, and the tests need `PYTHONPATH=.`** — they import `parse` / `insights` / `web_push` by bare name, and `python tests/x.py` puts `tests/` on `sys.path[0]`, not the root. The two `dev/` scripts that import root modules locate the root themselves, so they need no such thing. Nothing that moved is in `Dockerfile`'s COPY list, which is why the move left `parse.py` byte-identical and the parse cache warm.

There is no build/lint/test suite — these are standalone scripts. CI has three jobs: `python` (fixture-only tests, empty `cc-statements/`), `parser` (generates synthetic statements, then runs `tests/test_demo_pdfs.py` + `tests/test_parse.py` + `parse.py`'s reconciliation gate + insights/export/parity + the server suite, whose end-to-end `/ingest` test only runs when statements are present), and `web` (`make_demo_data.py` + `export_data.py` for the `app.json` the web suite imports, then `npm ci && npm run check && npm test` in `web/` — no `--pdfs`, no pip install, since that half is stdlib-only). `parse.py`'s own reconciliation report (`status=VERIFIED/REVIEW/NO_BALANCE/DUPLICATE`, printed and written to `reconciliation.csv`) is the correctness check. Target: a parser change must not lower the VERIFIED count (currently **78 unique statements all VERIFIED to the cent**, out of 82 files — 4 are dropped duplicates). Beyond per-statement reconciliation, a stronger cross-statement check is **prev→cur chain continuity** per bank (each month's `previous_balance` should equal the prior month's `current_balance`); a break flags a misdated or missing statement. The only known gap is hsbc **2025-08 missing** (statement never collected — chain steps 07→09).

## parse.py architecture (the non-obvious parts)

- **Row reconstruction by y-coordinate** (`rows_of`/`all_rows`) is the core trick. `pdftotext -layout` mis-aligns the amount column on SC/CIMB (amounts land on the wrong visual line); grouping pdfplumber words by `top` within `ytol` rebuilds true rows. Don't replace this with plain text extraction.
- **Generic transaction rule:** a row is a transaction if it has a leading date and a trailing `[\d,]+\.\d{2}(CR)?` amount. `CR` (suffix or separate token) = credit. `find_amount` takes the rightmost money token.
- **Per-bank dispatch** in `parse_statement`. maybank/cimb/sc/hsbc/rhb share `parse_dated` (rows are `date date desc amount`); **alliance is special** (`parse_alliance`) — its date sits on the line *above* the description+amount, so it pairs a date-only row with the immediately-following row (adjacency is required, which also rejects rewards/marketing lines that merely carry a number).
- **Multi-card attribution:** cimb/rhb/alliance statements cover several cards; the parser tracks the "current card" by scanning for card-number header lines. maybank/sc/hsbc are single-card (last4 filled from a fallback regex; SC's number is masked `5520-40XX-XXXX-XXXX`).
- **Bank-specific balance extraction** (`recon_balances`) is where most fragility lives — each bank labels previous/current balance differently and reading-order text varies (e.g. HSBC has no spaces: `YourPreviousStatementBalance`; maybank interleaves the address between label and value). Multi-card banks sum per-card balances.
- **Statement month** comes from the PDF's statement date, NOT the filename (the `_N` suffix is meaningless). `stmt_month` is **ordered**: (1) tight `Statement Date` label + `dd Mon yyyy`, (2) alliance Malay `Tarikh Penyata dd/mm/yy`, (3) loose first-`dd Mon yyyy` after the word "Statement", (4) alliance English numeric, (5) first-`dd Mon yyyy` anywhere. The tight label anchor (1) matters because **some SC templates print the Payment Due Date *before* the statement date** — a loose anchor grabbed the due date and landed the statement in the wrong month (this silently mis-bucketed 3 SC statements until fixed).
- **Payment due date** (`due_date`, per-bank like `recon_balances`): emits ISO `due` on each reconciliation row. sc/hsbc are inline after the label; alliance/rhb are `dd/mm/yy(yy)`; maybank/cimb print statement-date then due-date as two adjacent `dd Mon` tokens (due = 2nd). `None` if not found — never guessed.
- **Duplicate statements** are dropped in `main()` by a content fingerprint `(bank, sdate, prev, cur, debit, credit, n)` — keep first, mark the rest `DUPLICATE`, exclude their transactions. The same statement routinely arrives under several filenames (a whole-label backfill re-imports mail that was already ingested, and `save_pdf` names by content hash, not by the mail's filename); without dedup every chart double/triple-counts those months (per-file reconciliation still shows VERIFIED, hiding it).
- **Synthetic statements** (`dev/make_demo_data.py --pdfs`) are the only way `parse.py` is tested — real statements can never enter the repo or CI. `_pdf()` places text at absolute coordinates (a generalisation of `test_parse_password.py::_minimal_pdf`, still zero-dependency), and one renderer per bank reproduces the quirk that makes that branch exist: Alliance's date-above-the-row, HSBC's run-together labels, CIMB's per-card summary + separate detail page + `:0/MM` memo, SC's due-date-above-statement-date and masked card number, RHB's due date on the line below its label, Maybank's interleaved address. Amounts are written 1pt off the shared baseline so `rows_of` has to use its y-tolerance rather than an exact match. Balances come from `reconcile()`, so a generated statement reconciles for the same reason a real one does. **When you add a bank or change a layout rule, add/extend its renderer** — `test_demo_pdfs.py` is a round trip and will not catch a rule that nothing prints. It was mutation-tested: 12 deliberate breaks of `parse.py` (each per-bank balance label, the CR sign flips, multi-card tracking, `ytol`, alliance adjacency, `find_amount`'s rightmost rule, `clean_desc`'s `:NN/MM`, the `:0/MM` exclusion, `main()`'s dedup) all turn it red.
- **Per-file parse cache** (`cached_parse`, wraps `parse_statement` in the `main()` loop). `parse_statement` is pure given the PDF bytes, so its `(meta, txns)` is memoized to `<STMT_CACHE>/<sha256-of-bytes>.json` (env `STMT_CACHE`, default `cache/`; the runner points it at `<pvc>/cache`). On a miss it parses + writes (atomic `os.replace`); on a hit it loads and **re-derives `file` from the current path** (same bytes can arrive under a different filename — `source_file`/dedup must follow this run). This makes ingest O(1) in corpus size: adding 1 statement to an N-PDF volume reparses only the new file (~1.5 s vs ~100 s full reparse — see issue #1). **Cache-busting:** `PARSE_VER` = sha256 of `parse.py` itself is stored in each entry; any edit to `parse.py` invalidates the whole cache (one full reparse next run), so a parser-rule change never serves stale rows. Corrupt/missing/old-version entries silently reparse. Keyed by content hash, **not** the filename's `sha8` (the local `cc-statements/` corpus isn't content-addressed). Dedup/ordering/CSV output are unchanged → `app.json` stays byte-identical to a full rebuild (`cache/` is gitignored; tested by `tests/test_parse_cache.py`).

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

`insights.py` is a **deterministic, offline, stdlib-only** leak detector (no LLM at runtime). It consumes the same row dicts `dashboard.load()` builds (`{c:bank·last4, m:YYYY-MM, g:category, a:amount, t:0 debit/1 credit, d:desc}`), and `compute(rows)` returns `{recs:[…], savingsAnnual, installments:[…], transfers:[…], counts:{sub,installment,transfer,creep,oneoff}}`. Runnable standalone (writes `recommendations.csv` for review); imported by `dashboard.py`. Tested by `tests/test_insights.py` (plain asserts on synthetic fixtures, prints `OK`). **Goal anchor:** the tab exists to drive one decision — *cut discretionary spend* on a monthly-ritual cadence.

The **"LLM polish" is a build-time human-in-the-loop step, not embedded**: after a real run, Claude Code reads `recommendations.csv`, sanity-checks the detected leaks against the actual data, and tunes thresholds / the merchant override lists. Several real-data passes already hardened the detectors (each guard below exists because a specific false-positive showed up).

### Detectors (and the non-obvious guards)
- **Subscriptions** (`find_subs`): a merchant (by `norm_merchant`, which strips trailing ref/date/number tokens) is a sub if it recurs in **≥4 distinct months**, **≤1.3 charges/month**, and is **price-stable**. Stability + monthly price are measured on a **recent window (last ≤4 charges), not whole history** — so a tier-stepped sub (e.g. Claude.ai RM85→RM410 after an upgrade) still qualifies, reported at its *current* price. Restricted to an **allowlist `SUB_CATS = {Subscriptions, Telco/Utilities}`** (kills F&B/grocery/fuel coincidences like the Akmal Squared café). BNPL rows (`_is_bnpl`: `SPAYLATER|REPAYMENT`) excluded. A sub is flagged **`stale`** (hint → "Already cancelled?") if its last charge is ≥2 months before the newest statement month.
- **Creeping categories** (`find_creep`): per discretionary category, **mean(last 3 mo) ÷ mean(prior 3 mo) > 1.2** with a **prior-mean > RM50 floor** (avoids divide-by-near-zero), ≥6 months of data. Carries a **per-merchant breakdown** (`_cat_merchant_breakdown`, prev-3 vs last-3 by merchant) so "Telco +RM105" expands into which bills drove it.
- **Big one-offs** (`find_oneoffs`): debit in the **latest 2 months** above **P95 of discretionary debits** or **>3× that category's median**, excluding Installments/Transfers, BNPL, and — crucially — **any merchant seen in ≥2 months** (recurrence guard; stops recurring insurance/SaaS like AIA/Claude from masquerading as a one-time splurge).
- **Installments & balance transfers** (`find_installments`): re-derives structure from the `Installments/BT` rows **plus override merchants** `INSTALLMENT_MERCHANTS = {SENHENG, HOME PRODUCT}` (real installments that SC/maybank print with no marker, so `parse.py` categorized them `Shopping`). Splits **balance transfers** (`_is_bt`: `BALANCE TRANSFER|BAL TRANSFER|BALANCE TFER|SMART MOVE|T/F ER IN`) from **purchase plans**. Drops **principal-memo** rows (`_is_memo`: a `0/NN` zero-numerator ratio, or `T/F ER IN`) so the deferred principal isn't counted as a monthly charge. Groups by **`_plan_key`** (strips `INSTL ` prefix / trailing `:`-segment / ` NN OF MM` / counter — keeps Harvey-Norman-24M vs -36M as distinct plans; do NOT collapse on the override keyword or you merge unrelated plans, e.g. CIMB Grand-Senheng-12M with SC Senheng). Per plan: monthly (= sum of non-memo charges in its latest active month, so concurrent sub-charges add up), term, progress, remaining/end/remaining-balance. **Progress/term come from the bank's printed installment counter** via `_counter`: `:NN/MM` (maybank/cimb/rhb — `parse.py`'s `clean_desc` now **keeps** this ratio in the description so insights can read it) or `NN OF MM` (alliance). The counter is **trusted only when its total (denominator) is constant across the plan's months and current ≤ total** — this rejects reversed `total/current` layouts, stray colon-dates, and other unseen formats, which fall back to the estimate rather than a confident wrong number. **Honesty rule:** exact only where such a counter is printed; otherwise term comes from the `-NNM`/`E36` name suffix and remaining is an `est=True` estimate (`term − distinct-months-seen`) — valid only for a plan that began inside the collected window; one that started earlier reads high (the bug the `:NN/MM` counter fixes). The UI labels estimates `~est` and never shows a fake-precise end date. `_disp` cleans display names (leading `%%`, trailing ` -`).

### Ranking, savings & the tab
Subs/creep/one-offs are ranked into `recs` by **annual RM impact** (`severity`); installments/transfers are separate top-level arrays sorted by monthly. **`savingsAnnual` = cancellable subs + creep only** — installments and balance transfers are committed debt, never counted as "savings" (and Akmal-style false subs were the reason the number kept moving during tuning). The tab renders five groups: Subscriptions → Installments → Balance transfers → Creep → One-offs, each card category-badged with click-to-expand drill-down (charge history / merchant-delta / txn detail).

### Hosted PWA build (web/)
After `parse.py`: `python export_data.py` regenerates `web/static/data/app.json` (override with `STMT_OUT`),
then `cd web && npm run build` produces the static PWA in `web/build/`.
Full refresh: `python parse.py && python insights.py && python export_data.py && python dev/verify_parity.py && cd web && npm run build`.
Then gate the build: `npm run preview -- --port 4173 &` and `node audit-responsive.mjs` — must print `AUDIT OK` (no overflow / sub-11px / console errors at 390/834/1440, and `#overview` is the active scroll-spy link at top on desktop).

**PWA install/SW registration is wired by hand in `src/app.html`** (a `<link rel="manifest">` + a one-line `navigator.serviceWorker.register('/sw.js')`). `@vite-pwa/sveltekit` *generates* `sw.js`/`manifest.webmanifest`/`registerSW.js` fine, but its auto-inject **silently no-ops** on this Vite 8 + SvelteKit build — nothing referenced them, so there was no manifest link and no SW → Chrome/Firefox offered only an "Add to Home screen" shortcut (never **Install**) and the Workbox offline cache never populated. Don't remove those `app.html` lines expecting the plugin to re-inject. Verify after a dep bump: `grep -oE 'rel="manifest"|serviceWorker.register' build/index.html` must hit (the served file is the adapter-static **fallback** `index.html`, which is built from `app.html`). Install needs HTTPS *or* localhost (secure context); a plain-HTTP LAN IP downgrades to a non-installable shortcut even with all of the above correct.

The PWA fetches its data at **runtime**: `data.svelte.ts` (a runed store, re-exported
through the `data.ts` barrel so `import { app } from '$lib/data'` is unchanged)
`fetch('/data/app.json')` on mount and fills `app` in place; `+layout.svelte` gates all
views behind a loading skeleton (`[data-loading]`) / error / ready state, and the all-time
aggregates are precomputed once into `agg` after the fetch. `export_data.py` writes
`web/static/data/app.json` (served at `/data/app.json` locally; in prod the runner serves
it from the PVC) — so a data refresh needs **no rebuild**. The Overview view also renders a
**bills-due panel** (`BillsDue.svelte` + pure `bills.ts`): `app.bills[]` sorted by due date,
red when `< 3` days out (KL-time today via `todayMYT()`). **`paid` suppresses urgency, and it
does so in `sortBills` (#85)** — not in the component — so every caller inherits it; `BillsDue`
then guards `over` and the status branch the same way, or a settled overdue bill prints `-5d`.

The PWA is responsive across 3 tiers: <768px mobile (routed, BottomNav, 1-col),
768-1024px tablet (routed, 2-col panels), >=1024px desktop (TopBar + unified
Dashboard rendering all three Views in anchored sections, capped max-w-7xl).

**`+layout.svelte` is ONE shell (#86), not the pair it used to be**: `TopBar` behind
`hidden lg:block`, `children()` **exactly once**, `BottomNav` behind `lg:hidden`. `/settings`
is the only route the Dashboard does not render as a section, and rendering it *outside* that
structure is what dropped its navigation at every width — three times now (#40, #74, #86). It
cannot simply join the dashboard subtree either: **that pair really does mount twice at every
width**, which is fine for charts and fatal for a form, because duplicate element ids mean every
`<label for>` in `Setup.svelte` binds to whichever copy the browser saw first. So the double
mount lives *inside* the dashboard arm of an exclusive `{#if}`, and all-time chart aggregates are
precomputed once into `agg` in `data.svelte.ts` so it costs no compute. The width toggles **must**
stay `display:none` (`lg:hidden` / `hidden lg:block`) — only that removes the inert subtree from
the accessibility tree.

**One content width, owned by the layout (#87):** `const WIDTH = 'mx-auto px-4 md:max-w-3xl'`
at `+layout.svelte:38`. Full-bleed on a phone — the old `max-w-md` cap gutters a 600px window —
then a 768px cap all the way up, because a single-column form stretched to the desktop grid is
unreadable. Leaf components do **not** set their own: `Setup` keeps `max-w-xl` only for the
standalone `first={true}` mount, and `Dashboard.svelte` keeps `max-w-7xl` because it is a
multi-column grid and `TopBar` is sized to match it. The **auth and error screens deliberately
opt out** with `max-w-md` — standalone full-page states, same category as first-run `Setup`.

Acceptance gate: build, `npm run preview -- --port 4173`, then
`node web/audit-responsive.mjs` (checks 390/834/1440 for overflow/sub-11px/
console errors, **and that the nav is present on every route including `/settings`**;
screenshots -> web/audit-shots/). It also writes `readme-<route>.png` at 390x844 for the
README — `docs/img/` is not gitignored but `audit-shots/` is, so the copy step is explicit
(the command is an HTML comment above the README's screenshot table).

The Overview view also renders a "Use next" card picker (`CardPick.svelte` →
`cardpick.ts`): ranks cards by a 50/50 blend of interest-free float runway
(days until each card's statement closing-day, from `app.json` `cycles`) and
inverse trailing-3-month net-spend share, filtering cards dormant >6 months.
"Today" is resolved in Asia/Kuala_Lumpur (GMT+8) client-side; the ranking
logic is pure/tested in `cardpick.test.ts`.

### Refresh loop (adding new statements)
In production this is automatic: the mail arrives, `fetch_mail.py` posts it to `/ingest`, and the
server reparses and republishes. Nothing to run. You can also drag a statement in from the
settings/setup screen.

**Locally** (`cc-statements/`, for parser work): drop the PDFs in, keeping the `<bank>_…` filename
prefix — the `_N` index is meaningless but the bank prefix is load-bearing — then
`python parse.py && python tests/test_insights.py && python insights.py && python dashboard.py && node smoke_dashboard.mjs && node audit.mjs`. Check the reconciliation report stays all-VERIFIED
(a new `REVIEW` means the bank changed its template — debug with `dev/probe.py`), that `audit.mjs`
prints no ISSUES (a new long card name or category can overflow a chart), and skim
`recommendations.csv` for new false-positives (an unseen recurring merchant may need an
`INSTALLMENT_MERCHANTS` or category-allowlist tweak). New months/cards surface in all dashboard views automatically.

### Categorization & spend definition
Keyword map (`CATS`, ordered — first match wins) → standard taxonomy. The back-catalogue is hand-mapped to merchant-specific keywords, so `Other` stays small — but it is never empty, and is not meant to be: it collects one-off merchants that appeared after the last hand-mapping pass. `Other` is the safety fallback for new/unseen merchants and is meant to be watched — it surfaces in the dashboard donut and during the refresh-loop check. Most entries are a one-line `CATS` addition; `llm_cats.py --suggest-cats` (#29, suggest mode only) drafts those lines with an optional local model.

**Confirming one in the UI is the other way in (#82).** Settings step 5 lists what fell into `Other` (`app.json`'s `other[]`, from `export_data.build_other`) with a dropdown of the whole taxonomy (`allCats`); a pick writes `{merchant: category}` to `cats.json` on the PVC via `POST /api/cats`, which then re-runs the pipeline so the answer is on screen. **The apply point is `parse.py`'s `main()` loop, AFTER `cached_parse` — never inside `categorize()`.** `categorize()` runs inside `parse_statement`, which is memoized per PDF and keyed on `PARSE_VER`; an override read from in there would not bust that cache, so a confirmation would silently do nothing until something else edited the parser. Applied after the cache boundary it lands on the next run with **no reparse at all** (~0.5s warm). Keys are `insights.norm_merchant()` on **both** sides, or a trailing ref token makes one merchant two. An **override beats `CATS`** (a human confirmed it), so a later `CATS` keyword cannot correct a bad one — clearing the row in the UI is the only undo. `t['inst']` still beats both: that is printed structure, not a guess. The dropdown is built from `dashboard.COLORS` while `/api/cats` validates against `parse.CATS`; `test_parse.py::test_every_category_has_a_colour_and_an_icon` is what keeps those two the same taxonomy. **`Vehicle`** is a merged bucket — fuel + ride-hail/transport + tolls/parking + auto/workshop (the old separate `Fuel`/`Transport` categories were folded in). Other custom categories: `Certifications` (MBOT etc.), `Charity` (donations/zakat). `total_spend` excludes the non-consumption categories `NON_SPEND = {Installments/BT, Transfers/Payments, Rebate/Cashback}`. The `Installments/BT` total is inflated by monthly recurrence — never treat it as monthly consumption.

**Spend is netted**: in the summaries, consumption categories use signed amounts (debit `+`, credit `−`) so a **refund/reversal** (a credit sitting under a merchant category — e.g. a cancelled `…-REV` booking) subtracts from that category. `NON_SPEND` categories stay debit-only/gross (their credits are bill payments & cashback, not negative spend). The dashboard mirrors this exactly via its `val(r)` helper. Net cells can occasionally go slightly negative (a refund whose original purchase was a different month) — charts guard against it; the reconciliation is unaffected (it nets all debits/credits globally regardless of category).
