# lazyexpenses

Got a wallet full of credit cards? lazyexpenses turns the statement PDFs your banks email you into a spending dashboard you run yourself. It reads every transaction and checks each statement against its own printed balance, so the numbers are trustworthy. Your data never leaves your machine. No bank logins to hand over.

## Which banks

Six Malaysian banks. The parsing rules are written against these banks' Malaysian statement layouts, and the bank key is the part of the filename before the first underscore.

| Bank | Filename key | Cards per statement |
|---|---|---|
| Maybank | `maybank` | one |
| CIMB | `cimb` | several |
| Standard Chartered | `sc` | one |
| Alliance Bank | `alliance` | several |
| HSBC | `hsbc` | one |
| RHB | `rhb` | several |

"Several" means the statement covers more than one card and the parser attributes each transaction to the right one by tracking card-number headers as it reads.

**Everything else is unsupported.** Not by accident — each of these six needed its own rules, because Maybank prints its address between a balance label and the balance, HSBC runs the words together as `YourPreviousStatementBalance`, Alliance dates a transaction on the line above it and labels it in Malay, and CIMB-i marks installments with a `:NN/MM` ratio. A statement from another bank will not match any of that. Amounts are RM throughout and nothing is converted.

Banking somewhere else? A new bank is a new branch in one dispatch function — [CONTRIBUTING.md](CONTRIBUTING.md) walks through adding one, and the table above is where it gets a row.

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

Python 3, `pdfplumber`, and your statement PDFs.

Name each file `<bank>_anything.pdf` and drop it in `cc-statements/`. Everything before the first underscore is the bank key (`maybank`, `cimb`, `sc`, `alliance`, `hsbc`, `rhb`), and that is how the parser picks which rules to apply. The rest of the name is ignored.

### Statement passwords

Banks email these locked. The parser opens them itself, so drop each file in exactly as it arrived — nothing is decrypted to disk, and the stored PDF stays byte-for-byte what the bank sent.

The password comes from an environment variable named after the bank key, so the same filename prefix that picks the parsing rules also picks the password:

```bash
export CC_PW_MAYBANK='your-maybank-password'
# cc-statements/maybank_2026-06.pdf  ->  $CC_PW_MAYBANK
# cc-statements/sc_whatever.pdf      ->  $CC_PW_SC
```

Six names in total: `CC_PW_MAYBANK`, `CC_PW_CIMB`, `CC_PW_SC`, `CC_PW_ALLIANCE`, `CC_PW_HSBC`, `CC_PW_RHB`. Set only the banks you have. Leaving one unset is fine, and an already-unlocked PDF parses whether or not its variable is set — so there is nothing to undo if you decrypted your statements previously.

**One password per bank, not per card.** What is encrypted is the PDF, and a PDF is one statement. CIMB, RHB and Alliance put every card on a single statement behind a single password; cards are told apart afterwards, from the card-number headers inside the text. So one variable covers every card that bank issues you.

Each bank derives your password from something like your IC or date of birth — check the covering email. Passwords live in environment variables and nowhere else: never in a file in this repo, never in a filename, never in a log line.

Running the server in Docker? Pass them through to the container, which forwards them to the parser:

```bash
docker run --rm -p 8000:8000 -v "$PWD/data:/data" \
  -e CC_PW_MAYBANK -e CC_PW_CIMB -e CC_PW_SC \
  ghcr.io/officialdad/lazyexpenses/app:latest
```

Bare `-e NAME` forwards the value from your shell, so it does not end up in your shell history or in `docker inspect`.

## Just want a look first

You do not need any statements to try it. This generates an obviously-fake dataset — invented merchants, `000N` card numbers, a year of months — and everything downstream runs on it exactly as it would on real data:

```bash
python make_demo_data.py    # writes synthetic transactions.csv + reconciliation.csv
python insights.py && python export_data.py && python dashboard.py
```

Open `dashboard.html`, or run the web app as below. The demo is shaped to trip every detector, so the Cuts view actually has something in it: live subscriptions, a cancelled one, a subscription that stepped up in price, an installment plan, a balance transfer, a creeping category, a big one-off, a refund, and cashback. Nothing it writes is committable — the generated CSVs, `dashboard.html` and `app.json` are all gitignored, real data or fake.

It generates CSVs, not PDFs, so it exercises everything from `insights.py` onward. `parse.py` itself still needs real statements.

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
- Or post a PDF — locked or not — and let the server build it for you:
  ```bash
  curl -F "file=@cc-statements/maybank_x.pdf" -F "bank=maybank" http://localhost:8000/ingest
  ```
  It saves the PDF, re-runs the pipeline over everything accumulated so far, and replies with the reconciliation tally:

  ```json
  {"bank":"maybank","recon":{"VERIFIED":12},"problems":{},"warning":false}
  ```

  `warning` is true whenever a statement did not reconcile — `REVIEW`, `NO_BALANCE` or `ERROR` — and `problems` says which. `DUPLICATE` does not warn; the same statement legitimately arrives under several filenames and gets deduplicated. The HTTP status stays 200 either way: the upload itself succeeded, so retrying it would fail identically. Read the body, not the status code.

  A locked PDF whose `CC_PW_<BANK>` is not set on the server lands in `ERROR`, and you will see it.

Open the app before `/data` has an `app.json` and the page loads but the data request returns 404. That is a fresh empty volume, not a bug. Once the file is there, visit http://localhost:8000.

Besides `/ingest`, the server exposes `/healthz`, `/data/app.json`, `/bills` (upcoming balances as JSON, handy for wiring your own reminder), and small `/api/paid` and `/api/waivers` endpoints backing the cross-device mark-paid and fee-waiver state.

## Automating it

Everything above is manual: unlock, drop in a folder, run a script or post it. That loop is short enough that automating it is genuinely optional.

I do automate my own copy, but **that half is not in this repo**. It is an n8n instance wired to my Gmail: it watches for statement mail, posts the attachment to `/ingest`, and sends a Telegram reminder three days before a bill is due. Those workflow files stay local because they are full of credentials and references to my own instance, and they would not import cleanly anywhere else.

It used to run a self-hosted Stirling-PDF alongside it purely to strip statement passwords. That is gone — the parser opens locked PDFs itself now, so the whole decrypt step disappeared.

So treat n8n as one example of how to feed `/ingest`, not as a dependency. Anything that can fetch mail and POST a file does the same job, and replacing it with a small script in this repo is next on the list.

## Tests

No test runner to install. The root tests are plain asserts that print `OK` when they pass. These run on a fresh clone with no statements:

```bash
python test_parse_cache.py       # the per-PDF parse cache
python test_insights.py          # leak detection
python test_export_data.py       # the web app's data file
python test_parse_password.py    # opening password-protected PDFs
```

These four are what CI runs on every push and pull request. `test_parse_password.py` builds and encrypts its own PDF, so it needs no statements; the encryption cases skip themselves if `pypdf` is not installed.

The server tests use pytest, and also pass with no statements (the end-to-end one skips itself when there is no sample PDF):

```bash
pip install pytest httpx    # httpx is what starlette's TestClient imports
python -m pytest server/
```

The web app's own suite needs an `app.json` to exist, which `make_demo_data.py` is enough to produce:

```bash
python make_demo_data.py && python insights.py && python export_data.py
cd web && npm ci && npm run check && npm test
```

Two more need your own parsed statements on disk, because they check the real corpus rather than fixtures — `python test_parse.py` (due-date extraction, which wants at least one `cc-statements/sc_*.pdf`) and `python verify_parity.py` (both dashboards agreeing; the demo data satisfies this one too). Run those after `parse.py`.

The built dashboards have their own checks: `node smoke_dashboard.mjs` after `dashboard.py`, and `node web/audit-responsive.mjs` against a built and served PWA.

The bar for any parser change is simple: it must not turn a `VERIFIED` statement into a `REVIEW`.

## Status

Working, and in daily use on my own statements. The parser, both dashboards, the leak finder, bills, fee waivers, and the card picker are all done.

Still on the list: replacing the n8n mail fetch with a small script in this repo, hosting the web app properly, and shipping a sample dataset so there is something to look at without your own statements.

## License

MIT. See [LICENSE](LICENSE). Do what you like with it.
