# lazyexpenses

Got a wallet full of credit cards? lazyexpenses turns the password-locked statement PDFs your banks email you into a spending dashboard you run yourself. It reads every transaction and checks each statement against its own printed balance, so the numbers are trustworthy. Your data never leaves your machine. No bank logins to hand over.

It handles six Malaysian banks today: Maybank, CIMB, Standard Chartered, Alliance, HSBC, and RHB. Banking elsewhere? Add a parser, see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it does for you

- A spending dashboard you run yourself. One self-contained HTML file, or an installable web app. Every card and every month, broken down by category.
- A leak finder. It surfaces subscriptions you forgot you were paying for, categories that are quietly creeping up, and big one-off spends, ranked by what each one costs you per year.
- A debt tracker. Installment plans and balance transfers, with how many months are left on each.
- A heads-up on bills. The web app lists your upcoming statement balances and turns a bill red when it is due within three days.
- A "use next" card pick. It points you at the card with the longest interest-free runway that you haven't been leaning on.

## How accurate is it

Every statement gets checked the boring way: previous balance, plus what you spent, minus what you paid, should land on the new balance. On my own statements that is 69 of them, every one matching to within two cents. If a bank quietly changes its layout and a statement stops adding up, you get a flag instead of a wrong number you never notice.

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

## The automatic version (optional)

The manual loop is short: unlock the PDFs, drop them in a folder, run two scripts. If you would rather it happen on its own, there is an n8n pipeline that runs the whole thing the moment a statement arrives in Gmail:

1. A Gmail trigger picks up mail tagged `CC`.
2. Stirling-PDF unlocks the attachment using the per-bank password, which lives in n8n environment variables and never in the repo.
3. The unlocked PDF is posted to a small FastAPI service that re-runs the parser and rebuilds the dashboard data on a stored volume.
4. A daily job reads those due dates and sends a Telegram reminder three days out. This reminder is part of the n8n workflow, which is not in the repo.

This half is wired to my own setup, so the workflow files stay out of the repo. The parser and the web app are the parts meant to travel.

## Run it as a service (Docker)

The dashboard above is a file you open. If you would rather run the web app as a real service, the same one the n8n flow posts statements to, there is a Dockerfile that builds it. The image bundles the PWA and a small FastAPI server.

```bash
docker build -t lazyexpenses .
docker run --rm -p 8000:8000 -v "$PWD/data:/data" lazyexpenses
```

The server keeps its data in `/data`, which you mount as a volume so your statements live outside the image. That volume starts empty, so there is no `app.json` to serve until you put one there. You have two ways to fill it:

- Copy in an `app.json` you already built with `python export_data.py` (it writes to `web/static/data/app.json`).
- Or post an unlocked PDF to the ingest endpoint and let the server build it for you:
  ```bash
  curl -F "file=@cc-statements/maybank_x.pdf" -F "bank=maybank" http://localhost:8000/ingest
  ```

Open the app before `/data` has an `app.json` and the page loads but the data request returns 404. That is a fresh empty volume, not a bug. Once the file is there, visit http://localhost:8000.

## Status

Working, and in daily use on my own statements. The parser, the dashboard, the leak finder, the bills-due panel, and the card picker are all done. Hosting the web app properly and shipping a sample dataset for a public demo are still on the list.

## License

MIT. See [LICENSE](LICENSE). Do what you like with it.
