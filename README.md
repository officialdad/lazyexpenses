# lazyexpenses

Your banks email you a locked PDF every month and you never open it. lazyexpenses reads
those PDFs and turns them into a dashboard of what you actually spend. It runs on your
own machine. There is no bank login to hand over, and nothing leaves the box.

<!-- Refresh these five (#88): they are captured, not hand-shot, so a UI change updates them
     in one pass. From the repo root, with demo data already exported to web/static/data:
       cd web && npm run build && npm run preview -- --port 4173 --strictPort &
       AUDIT_BASE=http://localhost:4173 node web/audit-responsive.mjs
       cp web/audit-shots/readme-*.png docs/img/
     audit-responsive.mjs writes readme-<route>.png at 390x844 for the mobile tier.
     audit-shots/ is gitignored, so the copy into docs/img/ is the step that commits them. -->
<table>
  <tr>
    <td align="center" width="33%"><img src="docs/img/readme-home.png" width="240" alt="Home: what is free to spend this month against the ceiling, which card to reach for next, and the bills coming due"><br><sub><b>Home</b>: free to spend, use-next card, bills due</sub></td>
    <td align="center" width="33%"><img src="docs/img/readme-trends.png" width="240" alt="Trends: monthly spend as a bar per month, and a category donut with the yearly total per category"><br><sub><b>Trends</b>: month by month, and by category</sub></td>
    <td align="center" width="33%"><img src="docs/img/readme-cuts.png" width="240" alt="Cuts: subscriptions, installments, balance transfers and creeping categories, each with an annual cost"><br><sub><b>Cuts</b>: the leak finder, ranked by yearly cost</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="docs/img/readme-fees.png" width="240" alt="Fees and waivers: every card with its annual fee, late-fee and interest charges"><br><sub><b>Fees</b>: annual fees and what to call the bank about</sub></td>
    <td align="center"><img src="docs/img/readme-settings.png" width="240" alt="Settings: upload a statement, store statement passwords, and turn on the hourly Gmail fetch"><br><sub><b>Settings</b>: the screen a new install opens on</sub></td>
    <td></td>
  </tr>
</table>

*Every screenshot runs on the repository's synthetic demo data: invented merchants, `000N`
card numbers. Real statements never enter this repository.*

## Start it

```bash
cp .env.example .env
docker compose up -d
```

Open <http://localhost:8000> and sign in with `changeme@123`. **That password is in a
public repository, so change it.** It is the `APP_PASSWORD` line in your `.env`, and
[docs/DEPLOY.md](docs/DEPLOY.md#locking-it-with-a-password) has the details.

The app opens on a setup page asking for one statement. Choose the bank it came from,
upload the PDF exactly as it arrived, and the page becomes a dashboard. If the PDF is
locked, it asks for the password right there. The bank derives that password from
something like your IC or date of birth, and the covering email says which.

That is the whole install. The password is the only thing in `.env` you have to set,
and there is nothing to schedule.

## What you get

- **A spending dashboard**, every card and every month, broken down by category.
- **A leak finder**: subscriptions you forgot about, categories creeping up and big
  one-offs, each ranked by what it costs you per year.
- **A debt tracker** for installment plans and balance transfers, with the months left on
  each read off the bank's own printed counter, and marked as an estimate where there is
  no counter to read.
- **Bills**, which turn red when one is due within three days, with a mark-paid toggle
  that syncs across your devices.
- **An annual-fee tracker**, a "use next" card pick, a monthly ceiling with what is
  actually free to spend once committed debt is out, and search across every transaction.
- **A place to file the merchants it could not name.** Anything unrecognised lands in
  `Other`; pick its category once under **Settings** and it sticks, for every statement
  past and future.

## Which banks

Six Malaysian banks: **Maybank, CIMB, Standard Chartered, Alliance, HSBC, RHB**. CIMB,
Alliance and RHB put several cards on one statement, and each transaction still lands on
the right card.

**Everything else is unsupported.** Each of these six needed its own rules, because
Maybank prints its address between a balance label and the balance, HSBC runs the words
together as `YourPreviousStatementBalance`, Alliance dates a transaction on the line above
it in Malay, and CIMB-i marks installments with a `:NN/MM` ratio. A statement from another
bank matches none of that. Amounts are RM throughout and nothing is converted.

Adding a bank is one branch in one function, and [CONTRIBUTING.md](CONTRIBUTING.md)
walks through it.

## How accurate is it

Every statement is checked the boring way: previous balance, plus what you spent, minus
what you paid, has to land on the new balance. On my own statements that is 82 of them,
each matching to the cent. If a bank changes its layout and a statement stops adding up,
you get a flag rather than a wrong number you never notice.

## Statements arriving on their own

Label your statement mail `CC` in Gmail and the app checks for new ones every hour, so you
never upload another by hand. Turn it on under **Settings**. It needs a Gmail app
password rather than your Google password, and there is a Test button that tells you
whether it worked. [docs/DEPLOY.md](docs/DEPLOY.md#fetching-statements-from-gmail) covers
getting that app password.

## Bill reminders

Press **Remind me** next to the bills and allow notifications. You get one notification
when a statement lands, with the amount and the due date, and another a few days before
it is due. There are no accounts or tokens to set up anywhere. It needs `https://` or
`http://localhost` to work, and on an iPhone you have to add the app to the Home Screen
first. Telegram is still there as a fallback for a desktop you never install the app on;
see [docs/DEPLOY.md](docs/DEPLOY.md#bill-reminders).

## Your data

Everything lives in one Docker volume: the statement PDFs as they arrived, the numbers
read out of them, and what you typed in Settings. Nothing leaves the box except the mail
it fetches for you and the reminders you asked it to send.

Anything you set in `.env` wins over the same setting in the app, and shows there as
locked. Passwords only ever go in; the app never hands one back, not even masked.

Three files on that volume are worth backing up beyond the PDFs: `settings.json` (what
you typed in Settings), `vapid.json` (losing it silently stops every reminder until each
device presses **Remind me** again) and `cats.json` (the merchant categories you
confirmed). Everything else rebuilds itself from the statements.

There is one password and no user accounts, so you cannot lock it down per person. Run
it on your own machine or a private network, not on the open internet.

## Prefer to run it yourself?

You do not have to run a server. The parser and the offline single-file dashboard are
plain scripts with one dependency:

```bash
python -m pip install pdfplumber
python parse.py        # reads cc-statements/*.pdf, writes CSVs, prints a reconciliation report
python dashboard.py    # builds dashboard.html, which opens offline in any browser
```

Every statement in that report should say `VERIFIED`. `REVIEW` means the numbers did not
add up and something was misread; `NO_BALANCE` means the balances were not found at all.

With no statements to hand, the repo can invent a year of them, one per bank per month.
Everything downstream runs on the fake ones exactly as it would on real data, and it is
the same invented dataset the screenshots above show:

```bash
python dev/make_demo_data.py --pdfs   # obviously fake statements into cc-statements/
python parse.py && python dashboard.py
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the rest: the tests, the demo data generator and
how to add a bank. [docs/DEPLOY.md](docs/DEPLOY.md) is the full hosting reference: every
setting, putting it on your network, upgrading and backing up.

## Status

Working, and in daily use on my own statements. The parser opens locked PDFs itself,
and the mail fetch and the reminders are timers inside the app, so one container is the
whole deployment. It used to lean on two self-hosted services, n8n for the automation
and Stirling-PDF just to strip statement passwords. Both are gone.

## License

MIT. See [LICENSE](LICENSE). Do what you like with it.
