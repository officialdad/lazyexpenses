# CC Statement Parser (deterministic)

Parses unlocked credit-card statement PDFs in `cc-statements/` into CSVs.
No LLM — `pdfplumber` word-geometry + per-bank rules. Re-runnable on new statements.

## Run
```
python -m pip install pdfplumber
python parse.py          # PDFs -> CSVs + reconciliation report
python dashboard.py      # transactions.csv -> dashboard.html (interactive, offline)
```

## Outputs
| File | Contents |
|------|----------|
| `transactions.csv` | Every line item: bank, card_last4, statement_month, statement_date, post_date, txn_date, description, amount, type (debit/credit), category, source_file |
| `summary_card_category_month.csv` | **Core cube** — spend per card × category × month |
| `summary_card_month.csv` | Total discretionary spend per card × month |
| `summary_category_month.csv` | Total per category × month |
| `reconciliation.csv` | Per-statement integrity check + status |
| `dashboard.html` | Self-contained interactive dashboard (no deps, opens offline) |

## Dashboard (`dashboard.html`)
Single self-contained file — data embedded inline, charts hand-rolled in SVG + vanilla JS, **no libraries / no network**. Two views via the top toggle:
- **Overview** — all months: monthly stacked-by-category trend, spend-by-card (click to filter), category donut, card×category heatmap, top-20 merchants, and **cashback/rebates earned** (by card + by month, green).
- **Monthly** — one month at a time (defaults to the **latest** statement month; `‹ Prev / Next ›` or the dropdown to move). Shows month total with **Δ vs previous month** (%), biggest txn, top category, **cashback earned**; per-card + category breakdown; a **change-vs-previous-month** diverging bar (red = spent more, green = less); and a **sortable table of every transaction** that month.

Cashback/rebates are **credits** (money in), so they're excluded from every spend chart by design — the dedicated green panels (and the Monthly KPI + the credit rows in the Monthly table) are where they show.

Global controls apply to both views: **Discretionary ↔ All** toggle (Discretionary drops the financing/contra categories) and per-card chips.

## Refreshing with new statements
When new monthly statements land in Gmail (label `CC`):
1. **n8n** — run the `compile-cc-statements` workflow (manual trigger) → it pulls *all* label-`CC` mail, unlocks the PDFs, zips them, and Telegrams the zip. (It re-exports the **full history** each run, not just the new ones.)
2. **Drop the PDFs in** — unzip into `cc-statements/`. Because the zip is the full set, the clean move is to **replace the folder contents** (delete + extract fresh) so there are no stale/duplicate files. Keep the `<bank>_…​.pdf` name prefix — `parse.py` derives the bank from it (the `_N` index is meaningless).
3. **Re-run** — `python parse.py && python dashboard.py`.
4. **Sanity-check** — glance at the reconciliation report. It should stay all-VERIFIED; if a new statement shows `REVIEW`/`NO_BALANCE`, the bank tweaked its template — debug with `python probe.py cc-statements/<that>.pdf`.
5. **View** — open `dashboard.html`; the Monthly view auto-lands on the newest month and the Δ-vs-previous bar highlights what changed.

A new `statement_month` or bank/card appears in both views automatically — nothing else to wire.

## How it works
1. **Row reconstruction** — words grouped by y-coordinate (not `pdftotext -layout`, which mis-aligns the amount column on SC/CIMB).
2. **Per-bank parsers** — maybank/cimb/sc/hsbc/rhb: `date date desc amount[CR]`; alliance: date row precedes desc+amount row. Multi-card banks (cimb/rhb/alliance) attribute rows to the card section they fall under.
3. **Categorization** — keyword map → standard taxonomy (Groceries, F&B, Shopping, Vehicle, Telco/Utilities, Travel, Health/Insurance, Entertainment, Subscriptions, Certifications, Charity, Fees/Charges, Installments/BT, Transfers/Payments, Rebate/Cashback, Other). **Vehicle** merges fuel, transport/parking, tolls and auto/workshop spend.
4. **Reconciliation** — `previous_balance + Σdebits − Σcredits ≈ current_balance`. Status VERIFIED (≤RM0.02) / REVIEW / NO_BALANCE.

## Accuracy: 69/69 unique statements VERIFIED to the cent
- 73 PDFs in, **4 dropped as exact duplicates** (the n8n export re-sends the full history, so the same statement arrives under several filenames; dedup keeps one — without it those months double/triple-count).
- Statement month is read from a **tight `Statement Date` anchor** — fixes SC templates that print the *payment due date* before the statement date (had silently mis-bucketed 3 SC months).
- Cross-check beyond per-statement reconciliation: the **prev→cur balance chain** is continuous per bank. Only gap: **hsbc Aug 2025 is missing** (that statement was never collected) — worth re-downloading if you want a complete series.
- Spend is **net of refunds**: a credit under a merchant category (e.g. a cancelled `…-REV` booking, a Shopee refund) subtracts from that category, matching what you actually spent.

## CIMB-i installment handling
CIMB-i uses Islamic "Bank's Sale Price" accounting. A new installment plan posts a `:0/MM` line for the **full** purchase as a deferred memo (billed across later months), plus `:01/MM`-style lines for the actual monthly charges. The parser drops the `:0/MM` principal from the month's debit total but keeps the monthly charges, and force-categorizes every `:NN/MM` row as `Installments/BT` (so a merchant-named plan doesn't leak into Groceries/Shopping).

## Credit (`CR`) balances
A balance printed with a trailing `CR` is a credit (negative) balance. CIMB and alliance both do this (alliance's virtual card often sits in credit); the parser negates them. Without this the affected statement reconciles off by exactly 2× the credit balance.

## Spend definition
`total_spend` excludes **Installments/BT, Transfers/Payments, Rebate/Cashback** (financing/contra, not consumption). The category summaries show *all* categories so nothing is hidden.

⚠️ Installment plans recur monthly across statements — the `Installments/BT` category is inflated by repetition and should not be read as monthly consumption.

## Per-bank PDF password (for re-downloading/unlocking)
Each bank derives its default PDF password from the cardholder's DOB/IC. **Not committed** — set per-bank on the n8n instance via env vars `CC_PW_<BANK>` (`CC_PW_MAYBANK`, `CC_PW_CIMB`, `CC_PW_SC`, `CC_PW_ALLIANCE`, `CC_PW_HSBC`, `CC_PW_RHB`).

`probe.py <pdf>` dumps reconstructed rows — handy when adding a new bank/template.
