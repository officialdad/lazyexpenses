One container: the PWA, the parser, the hourly Gmail fetch and the bill reminders.

```bash
docker run -d -p 8000:8000 -v lazyexpenses:/data \
  -e APP_PASSWORD=pick-your-own \
  ghcr.io/officialdad/lazyexpenses/app:VERSION
```

Or clone the repo, `cp .env.example .env`, and `docker compose up -d`. Either way, open <http://localhost:8000> and upload one statement — the setup page takes it from there.

The image is built from this tag and refuses to publish unless it reports that same version, in both the server and the shell. Check yours at the bottom of Settings.

`APP_PASSWORD` is the only setting you have to pick. Everything else is a form in the app.
