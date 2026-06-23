# lazyexpenses

If you carry more than a couple of credit cards, you know the problem. Six statement PDFs a month, six different layouts, each one locked behind a password, and nowhere that tells you where the money actually went. The budgeting apps that fix this want your bank logins. This one doesn't.

lazyexpenses reads the statement PDFs your bank already emails you, pulls out every transaction, and builds a spending dashboard you open on your own machine. No login sharing and no LLM. Your data never leaves your computer. And because every number is checked against the statement's own balance, you can actually trust it.

Today it understands six Malaysian banks: Maybank, CIMB, Standard Chartered, Alliance, HSBC, and RHB. Bank somewhere else? You can add a parser. See [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does for you

- A spending dashboard you run yourself. One self-contained HTML file, or an installable web app. Every card and every month, broken down by category.
- A leak finder. It surfaces subscriptions you forgot you were paying for, categories that are quietly creeping up, and big one-off spends, ranked by what each one costs you per year.
- A debt tracker. Installment plans and balance transfers, with how many months are left on each.
- Bill reminders. A Telegram message three days before a payment is due, so you stop feeding the banks late fees.
- A "use next" card pick. It points you at the card with the longest interest-free runway that you haven't been leaning on.

## How accurate is it

Every statement gets checked the boring way: previous balance, plus what you spent, minus what you paid, should land on the new balance. On my own statements that is 69 of them, every one matching to within two cents. If a bank quietly changes its layout and a statement stops adding up, you get a flag instead of a wrong number you never notice.

Nothing is guessed. It is `pdfplumber` reading the position of every word on the page, plus a set of hand-written rules per bank. Run it twice on the same PDF and you get the same answer.

## Quick start

You need Python and your unlocked PDFs. Unlock them with your bank password (or let the n8n flow below do it for you), drop them into `cc-statements/`, then:

```bash
python -m pip install pdfplumber
python parse.py        # reads the PDFs, writes CSVs, prints a reconciliation report
python dashboard.py    # builds dashboard.html, which opens offline in any browser
```

Open `dashboard.html`. That is the whole thing.

If you also want the leak finder and the installable web app:

```bash
python insights.py        # writes recommendations.csv (the leaks)
python export_data.py     # builds the data file the web app reads
cd web && npm run build   # builds the PWA into web/build/
```

## Supported banks

Maybank, CIMB, Standard Chartered, Alliance, HSBC, RHB. Those are the cards I hold, so those are the parsers that exist. Adding another bank is a contained job: dump the PDF's rows with `probe.py`, write the extraction rules, and confirm the statement balances to the cent. [CONTRIBUTING.md](CONTRIBUTING.md) walks through it step by step.

## The automatic version (optional)

The manual loop is short: unlock the PDFs, drop them in a folder, run two scripts. If you would rather it happen on its own, there is an n8n pipeline that runs the whole thing the moment a statement arrives in Gmail:

1. A Gmail trigger picks up mail tagged `CC`.
2. Stirling-PDF unlocks the attachment using the per-bank password, which lives in n8n environment variables and never in the repo.
3. The unlocked PDF is posted to a small FastAPI service that re-runs the parser and rebuilds the dashboard data on a stored volume.
4. A daily job looks for bills due in three days and sends the Telegram reminder.

This half is wired to my own setup, so the workflow files stay out of the repo. The parser and the web app are the parts meant to travel.

## How it works, briefly

- Rows come from word coordinates, not plain text. Some banks print the amount column out of line with `pdftotext`, so the parser groups words by their vertical position to rebuild the real rows.
- Each bank has its own small parser. Most follow `date date description amount`. Alliance prints the date on the line above the amount, so it gets handled separately. Banks that put several cards on one statement attribute each row to the card section it sits under.
- Categories come from a keyword map, so a kopitiam lands in F&B and a Shell station lands in Vehicle.
- Refunds count as negative spend, so a reversed booking subtracts from its category instead of hiding in plain sight.

The genuinely fiddly bits, like CIMB's Islamic installment accounting and the credit-balance sign flips, are documented in the code right where they happen.

## Status

Working, and in daily use on my own statements. The parser, the dashboard, the leak finder, the bill reminder, and the card picker are all done. Hosting the web app properly and shipping a sample dataset for a public demo are still on the list.

## License

No license file yet, which means default copyright applies. If you want to reuse a piece of this, open an issue and ask. I'm friendly about it.
