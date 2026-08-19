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

Running it as a service instead? The same six names go in your `.env` — see
[docs/DEPLOY.md](docs/DEPLOY.md).

## Just want a look first

You do not need any statements to try it. This generates an obviously-fake dataset — invented merchants, `000N` card numbers, a year of months — and everything downstream runs on it exactly as it would on real data:

```bash
python make_demo_data.py    # writes synthetic transactions.csv + reconciliation.csv
python insights.py && python export_data.py && python dashboard.py
```

Open `dashboard.html`, or run the web app as below. The demo is shaped to trip every detector, so the Cuts view actually has something in it: live subscriptions, a cancelled one, a subscription that stepped up in price, an installment plan, a balance transfer, a creeping category, a big one-off, a refund, and cashback. Nothing it writes is committable — the generated CSVs, `dashboard.html` and `app.json` are all gitignored, real data or fake.

That generates CSVs, so it exercises everything from `insights.py` onward. To run the
parser too, generate statement PDFs instead and let `parse.py` produce the CSVs itself:

```bash
python make_demo_data.py --pdfs   # writes fake statement PDFs into cc-statements/
python parse.py                   # every one should reconcile VERIFIED
```

Same data, one layer lower. The PDFs are built to each bank's real layout — Alliance
dates a transaction on the line above it, HSBC runs its labels together, CIMB spreads
several cards across one statement — so the parser has to do the same work it does on
a real statement. Nothing about them is real except the shape.

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

Installing it as a real app needs HTTPS or localhost. Over a plain-HTTP LAN address the browser quietly downgrades it to a bookmark-style shortcut — [docs/DEPLOY.md](docs/DEPLOY.md#putting-it-on-your-network) has a working fix.

## Run it as a service

Everything above is manual: drop a file in a folder, run a script, open the result. That
loop is short enough that automating it is genuinely optional. But if you would rather it
kept itself up to date, there is a container that does the whole job:

```bash
cp .env.example .env    # fill in what you have
docker compose up -d
```

Open <http://localhost:8000>. That gets you:

- **the web app, always on**, so any device on your network can open it;
- **statements fetched for you** — it watches a Gmail label, and each statement your bank
  emails goes straight in, still locked, without you touching it;
- **a Telegram message** once a day for any bill due within three days.

Fill in only the parts you want. No Gmail details means nothing is fetched, no Telegram
token means nothing is messaged, and neither one breaks anything else.

**[docs/DEPLOY.md](docs/DEPLOY.md) is the full guide**: every setting, how to get a Gmail
app password, how to make the app properly installable from your phone, and the security
note that matters — **there is no login**, so this belongs on your own machine or a
private network, never on the open internet.

## Adding your own bank

The parser covers six banks because each one needed its own rules. Adding a seventh is a
branch in one dispatch function, and the reconciliation report tells you when you have it
right. [CONTRIBUTING.md](CONTRIBUTING.md) walks through it, and covers the test suite too.

## Status

Working, and in daily use on my own statements. The parser, both dashboards, the leak
finder, bills, fee waivers, the card picker, the Telegram reminders and the mail fetch are
all done, and my own copy runs as a container behind HTTPS.

It used to lean on two self-hosted services — n8n for the automation and Stirling-PDF just
to strip statement passwords. Both are gone: the parser opens locked PDFs itself, the
reminders run inside the server, and the mail fetch is a script in this repo. What is left
is Python, its one dependency, and the standard library.

## License

MIT. See [LICENSE](LICENSE). Do what you like with it.
