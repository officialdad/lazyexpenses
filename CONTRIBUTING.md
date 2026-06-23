# Contributing

The most useful thing you can add here is a parser for your own bank. This page walks through it. The nice part: the parser has a built-in honesty check, so you always know when you have it right.

## How the parsing works

`parse.py` does three things. It rebuilds each statement's rows from the position of words on the page, because several banks misalign the amount column under plain text extraction, so the parser groups words by their vertical coordinate instead. It then runs a small per-bank parser to turn those rows into transactions. Finally it checks each statement against its own printed balance, so a parser that drops a row or counts one twice shows up as a mismatch instead of a believable wrong number.

The bank is read straight from the filename. A file named `maybank_june.pdf` is parsed as Maybank. Everything before the first underscore is the bank key.

## What you need

- One unlocked sample statement from the bank you want to add. A single PDF is enough to start.
- Python with `pdfplumber` installed.
- The real previous and current balance off that statement, so you can confirm the parser agrees with the bank.

## Adding a bank, step by step

1. Drop your sample into `cc-statements/`, named `<bank>_anything.pdf`. Pick a short lowercase key, for example `pbb` for Public Bank.

2. See what the parser sees:
   ```bash
   python probe.py cc-statements/pbb_sample.pdf
   ```
   This prints the rebuilt rows. Look at how one transaction line is laid out: where the date sits, where the amount sits, and whether a credit is marked with a trailing `CR`.

3. Pick a parser shape. Open `parse_statement` in `parse.py`. Most banks print each transaction as `date date description amount`, and those reuse `parse_dated` with a date pattern. Alliance is the odd one out, because it prints the date on the line above the amount, so it has its own `parse_alliance`. If your bank looks like the common case, add it to the `parse_dated` branch with the right date regex. If the date floats above the amount, model it on `parse_alliance`.

4. Teach it the balances. `recon_balances(bank, text)` is where each bank's previous and current balance get pulled out, and it is the part that varies most between banks. Every bank labels these differently, and the reading order is not always what you would expect. HSBC prints the label with no spaces, and Maybank slips the mailing address between the label and the number. Add a branch for your bank that finds both numbers. If a balance prints with a trailing `CR`, it is a credit balance and the sign flips.

5. Optional extras. For bill reminders on this bank, add a branch to `due_date(bank, text)` that reads the payment due date. If a statement lists several cards, track which card each row belongs to by watching for the card-number header lines, the way the cimb and rhb branches already do.

## The acceptance test

Run the parser:
```bash
python parse.py
```
At the end it prints a reconciliation report. Find your statement in it. It needs to say `VERIFIED`, which means previous balance plus debits minus credits matched the printed current balance to within two cents. `REVIEW` means the numbers do not add up yet, usually a missed row or a balance read wrong. `NO_BALANCE` means `recon_balances` could not find the balances at all.

One rule matters above the rest: your change must not turn any existing `VERIFIED` statement into a `REVIEW`. The current count is 69 verified statements, and the bar is to keep every one of them passing while your new bank joins them.

When a statement will not reconcile, go back to `probe.py` and read the rows until you find the line the parser is mishandling.

## Categories

Categories come from `CATS` near the top of `parse.py`, a keyword map checked in order where the first match wins. If a merchant from your statement lands in `Other`, add a keyword for it next to the category it belongs in. `Other` is meant to stay empty, so a merchant showing up there is your cue to add a rule.

## Before you open a PR

- Your statement reconciles `VERIFIED`, and no existing statement dropped to `REVIEW`.
- `python test_insights.py` still prints `OK`.
- No personal data in the diff. Do not commit statement PDFs (the `cc-statements/` folder is gitignored), real passwords (those belong in n8n environment variables, not the code), or the generated CSVs.
- A short note on which bank you added and where the sample came from, so the next person can retrace it.

Thanks for adding a bank. Each one makes this useful to more people.
