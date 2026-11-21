# lazyexpenses Strategy

## Vision

<!-- vision: UNAPPROVED round-1 draft, no author verdicts yet. Do not treat as policy until author-approved. -->

`lazyexpenses` exists so that someone carrying several credit cards knows what they spend, where it leaks, what they owe and when it is due, without ever typing a transaction.
It serves one person with cards from Malaysian banks, and it turns the statement PDFs those banks already email into a dashboard, a leak finder and bill reminders.
It owns exactly one thing: reading a bank's own statement correctly.

### The statement is the only source

The bank's statement is the only input, because the bank already recorded every charge and signed off on the total.
Nothing asks the user to log, tag or total a transaction by hand, so the numbers stay true even in the month the user stops paying attention.
Statements arrive on their own from the mailbox; a manual upload exists for a first run or a backfill, not as a habit.
The one question the app may ask is the category of a merchant it cannot name, and one answer covers every statement past and future.
The app never holds a bank login and never scrapes a banking site.

### Correct to the cent, or flagged

Every statement reconciles: previous balance plus charges minus payments must land on the printed new balance.
A statement that does not reconcile is flagged, never shown as a believable wrong number.
Anything the app cannot read for certain, such as an unknown bank or a missing due date, stays unknown rather than guessed.
A figure the statement does not print is labelled an estimate, never given false precision.
The reconciliation report is the bar for every parser change: turning a VERIFIED statement into anything else is a regression.
Each supported bank has a synthetic statement that reproduces its quirks, so its parser is tested in CI without real data.

### Deterministic numbers, optional models

Parsing, reconciliation, categorization and the leak finder are deterministic: the same PDFs give the same numbers on every run.
A language model may only suggest a category for a merchant the keyword table gave up on, and a human confirms it before it counts.
Any model is off by default, runs on the user's own machine, and sees merchant names only.
No hosted model or API key is ever a default or a documented path.

### One person, one box

Everything lives on one volume on hardware the user controls.
Nothing leaves that box except the mail it fetches and the reminders the user asked for.
There is one optional shared password and no user accounts, roles or sharing.
It runs on a private network, not on the open internet.
Secrets go in and never come back out, and the environment always wins over the settings screen.
Real statements, generated data and credentials never enter the repository; demos and screenshots run on obviously synthetic data.
Because it holds a person's finances, its supply chain is part of that boundary: actions and images are pinned, and dependencies are watched.

### Small enough to run without help

One container is the whole deployment, with its timers inside it, so there is nothing else to host or schedule.
Getting started needs no terminal beyond starting the container: setup, statement passwords, mail fetch and reminders all live in the app.
Defaults are safe and loud: the shipped password is public, so the app warns until it is changed.
A new dependency has to beat the standard library, and the parser keeps exactly one runtime dependency.

### Scope

lazyexpenses reads credit-card statements from six Malaysian banks: Maybank, CIMB, Standard Chartered, Alliance, HSBC and RHB.
Amounts are ringgit and nothing is converted.
A new bank is welcome when it arrives with a redacted sample, a parser that reconciles it and a synthetic renderer for CI.
It is not a manual expense tracker, not a bank aggregator, not a multi-user or hosted service, and not a general PDF-to-CSV tool.

A change aligns when it makes the path from statement to insight more correct, more automatic or easier for a non-programmer to run, and every number it adds traces back to a statement line.
A change should be resisted when it asks the user to enter data by hand, sends financial data off the box, lets a model decide a number, weakens reconciliation, or adds a service, account system or dependency the one-container deployment does not need.
