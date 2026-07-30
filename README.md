# lazyexpenses

Got a wallet full of credit cards? lazyexpenses turns the statement PDFs your banks email you into a spending dashboard you run yourself. It reads every transaction and checks each statement against its own printed balance, so the numbers are trustworthy. Your data never leaves your machine. No bank logins to hand over.

It handles six Malaysian banks today: Maybank, CIMB, Standard Chartered, Alliance, HSBC, and RHB. Banking elsewhere? Add a parser, see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does for you

- **A spending dashboard.** Either a single self-contained `dashboard.html` you open offline, or an installable web app with four views: Overview, Trends, Cuts, and Fees. Every card and every month, broken down by category.
- **A leak finder.** It surfaces subscriptions you forgot you were paying for, categories that are quietly creeping up, and big one-off spends, ranked by what each one costs you per year.
- **A debt tracker.** Installment plans and balance transfers, with how many months are left on each — read off the bank's own printed counter where there is one, and clearly marked as an estimate where there isn't.
- **A heads-up on bills.** Upcoming statement balances, turning red when one is due within three days, with a mark-paid toggle that syncs across your devices.
- **An annual-fee tracker.** Per-card fees and a waiver status you can cycle as you work through calling the bank.
- **A "use next" card pick.** It points you at the card with the longest interest-free runway that you haven't been leaning on.
- **A headroom figure.** Set a monthly ceiling and see what is actually free to spend once committed debt is taken out.
- **Search.** Across every transaction you have parsed.

## How accurate is it

Every statement gets checked the boring way: previous balance, plus what you spent, minus what you paid, should land on the new balance. On my own statements that is 78 of them, every one matching to within two cents. If a bank quietly changes its layout and a statement stops adding up, you get a flag instead of a wrong number you never notice.

## What you need

Python 3, `pdfplumber`, and your statement PDFs **already unlocked**.

That last part matters. The parser does not take a password today, so an encrypted PDF fails to parse — and banks email these locked. Unlock them first with any PDF tool; [qpdf](https://qpdf.sourceforge.io/) is a one-liner:

```bash
qpdf --password='your-bank-password' --decrypt statement.pdf cc-statements/maybank_2026-06.pdf
```

Name each file `<bank>_anything.pdf` and drop it in `cc-statements/`. Everything before the first underscore is the bank key (`maybank`, `cimb`, `sc`, `alliance`, `hsbc`, `rhb`), and that is how the parser picks which rules to apply. The rest of the name is ignored.

## Quick start

```bash
python -m pip install pdfplumber
python parse.py        # reads cc-statements/*.pdf, writes CSVs, prints a reconciliation report
python dashboard.py    # builds dashboard.html, which opens offline in any browser
```

Open `dashboard.html`. That is the whole thing.

Read the reconciliation report before trusting the charts. Every statement should say `VERIFIED`. A `REVIEW` means the numbers did not add up and something was misread; `NO_BALANCE` means the balances were not found at all. Either one is your cue to look closer with `python probe.py <file.pdf>`.

Parsing is cached per file, keyed by the PDF's content hash, so adding one statement to a large folder reparses only that file. Editing `parse.py` invalidates the whole cache automatically, so a rule change never serves stale rows.

## The web app

The single-file dashboard is the fastest path. If you want the installable version instead:

```bash
python insights.py      # writes recommendations.csv (the leaks)
python export_data.py   # builds web/static/data/app.json, the file the web app reads
python verify_parity.py # checks both dashboards agree on the shared numbers
cd web && npm install && npm run build
```

The app fetches its data at runtime rather than baking it in, so refreshing your numbers means re-running `export_data.py` — no rebuild.

Installing it as a real app needs HTTPS or localhost. Over a plain-HTTP LAN address the browser downgrades it to a bookmark-style shortcut.

## Run it as a service (Docker)

The dashboard above is a file you open. To run the web app as a service instead, there is an image bundling the PWA and a small FastAPI server. Prebuilt images are published on every release, so you do not have to build anything:

```bash
docker run --rm -p 8000:8000 -v "$PWD/data:/data" ghcr.io/officialdad/lazyexpenses/app:latest
```

Or build it yourself from source:

```bash
docker build -t lazyexpenses .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" lazyexpenses
```

The server keeps everything in `/data`, mounted as a volume so your statements live outside the image. That volume starts empty, so there is nothing to serve until you put some data there. Two ways to fill it:

- Copy in an `app.json` you already built with `python export_data.py` (it writes to `web/static/data/app.json`).
- Or post an unlocked PDF and let the server build it for you:
  ```bash
  curl -F "file=@cc-statements/maybank_x.pdf" -F "bank=maybank" http://localhost:8000/ingest
  ```
  It saves the PDF, re-runs the pipeline over everything accumulated so far, and replies with the reconciliation tally, for example `{"bank":"maybank","recon":{"VERIFIED":12},"warning":false}`. Read that tally — a locked or unparseable PDF still returns HTTP 200 and simply shows up as an `ERROR` count.

Open the app before `/data` has an `app.json` and the page loads but the data request returns 404. That is a fresh empty volume, not a bug. Once the file is there, visit http://localhost:8000.

Besides `/ingest`, the server exposes `/healthz`, `/data/app.json`, `/bills` (upcoming balances as JSON, handy for wiring your own reminder), and small `/api/paid` and `/api/waivers` endpoints backing the cross-device mark-paid and fee-waiver state.

## Automating it

Everything above is manual: unlock, drop in a folder, run a script or post it. That loop is short enough that automating it is genuinely optional.

I do automate my own copy, but **that half is not in this repo**. It is an n8n instance wired to my Gmail and a self-hosted Stirling-PDF: it watches for statement mail, unlocks the attachment with a per-bank password held in n8n environment variables, posts the result to `/ingest`, and sends a Telegram reminder three days before a bill is due. Those workflow files stay local because they are full of credentials and references to my own instance, and they would not import cleanly anywhere else.

So treat n8n and Stirling-PDF as one example of how to feed `/ingest`, not as a dependency. Anything that can fetch mail and POST a file does the same job, and replacing that stack with a small script in this repo is next on the list.

## Tests

No test runner to install. The root tests are plain asserts that print `OK` when they pass. These run on a fresh clone with no statements:

```bash
python test_parse_cache.py    # the per-PDF parse cache
python test_insights.py       # leak detection
python test_export_data.py    # the web app's data file
```

The server tests use pytest, and also pass with no statements (the end-to-end one skips itself when there is no sample PDF):

```bash
python -m pytest server/
```

Two more need your own parsed statements on disk, because they check the real corpus rather than fixtures — `python test_parse.py` (due-date extraction) and `python verify_parity.py` (both dashboards agreeing). Run those after `parse.py`.

The built dashboards have their own checks: `node smoke_dashboard.mjs` after `dashboard.py`, and `node web/audit-responsive.mjs` against a built and served PWA.

The bar for any parser change is simple: it must not turn a `VERIFIED` statement into a `REVIEW`.

## Status

Working, and in daily use on my own statements. The parser, both dashboards, the leak finder, bills, fee waivers, and the card picker are all done.

Still on the list: teaching the parser to open password-protected PDFs directly so Stirling-PDF is not needed, replacing the n8n mail fetch with a small script in this repo, hosting the web app properly, and shipping a sample dataset so there is something to look at without your own statements.

## License

MIT. See [LICENSE](LICENSE). Do what you like with it.
