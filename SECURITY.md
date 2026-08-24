# Security policy

## Reporting a vulnerability

Report it privately: [open a draft security advisory](https://github.com/officialdad/lazyexpenses/security/advisories/new).

**Do not open a public issue.** An issue is public the moment you file it, and this app holds parsed credit-card statements.

Include the version or image digest, what you did, and what happened. Never attach a real statement — describe the layout, or generate a synthetic PDF with `python dev/make_demo_data.py --pdfs`.

## Scope

In scope:

| Area | Code |
| --- | --- |
| Container image and everything it serves | `Dockerfile`, `server/app.py` |
| Password gate, session cookie, path normalisation | `server/app.py` (`_install_gate`, `_norm`, `_token_ok`) |
| Statement parser, including the password-protected PDF path | `parse.py` |
| Hand-rolled Web Push crypto (RFC 8291 + RFC 8292) | `web_push.py` |
| IMAP fetch and the `/ingest` endpoint it posts to | `fetch_mail.py`, `server/app.py` |

Out of scope:

| Area | Reason |
| --- | --- |
| The bank statement PDFs themselves | They are the bank's format and never enter this repo or CI. A bank's PDF password scheme is not this project's to fix. |
| The private infra repo | The Deployment, PVC, Ingress and cluster Secrets live in a separate private repository. Nothing there is reachable from this one. |
| A misparsed statement | That is an accounting bug, not a vulnerability. File a public issue and quote the `reconciliation.csv` row. |

## What to expect

One person maintains this in spare time. Expect a first reply within about a week, not within 24 hours.

A confirmed fix ships in the next `v*` tag. That can be the same day or several weeks later, depending on the size of the fix.

No bounty and no reward. If a week passes with no reply, comment on your own advisory — GitHub notifies me again.

## Supported versions

| Version | Fixes |
| --- | --- |
| [Latest release](https://github.com/officialdad/lazyexpenses/releases/latest) | Yes |
| Every earlier tag | No — upgrade |

There is one branch and no backports. A fix lands on `main` and goes out in the next `v*` tag, which rebuilds `ghcr.io/officialdad/lazyexpenses/app`. Upgrade with `docker compose pull && docker compose up -d`.

## How this app is meant to run

**On a private network, not on the open internet.** There is one shared password and no user accounts, so access cannot be scoped per person. `docs/DEPLOY.md` says plainly: do not port-forward it.

**`APP_PASSWORD` is the only thing between the internet and your data.** Set it, and every `/api/*` and `/data/*` path needs either the session cookie from `POST /api/login` or an `X-App-Password` header. `/healthz` and `/api/login` stay open on purpose. Leave it blank and there is no login at all: anyone who reaches the port reads every transaction and balance, and can overwrite your mail and reminder credentials.

**`.env.example` ships `APP_PASSWORD=changeme@123`.** That is a placeholder, not a password — it is printed in a public repo, so everyone who has read the repo knows it. It exists so a fresh `docker compose up` is closed rather than wide open. Change it before you start the container.

Leave it and the server prints this on every boot:

```
!!!!!!!!!!!!!!!!!!!! SECURITY: APP_PASSWORD is still the shipped default 'changeme@123' — it is published in .env.example, so anyone who has seen this repo can open your app. Change it in .env and restart. !!!!!!!!!!!!!!!!!!!!
```

Setting no password at all warns just as loudly. Neither warning blocks startup, and the Settings screen keeps a banner up until the value changes.
