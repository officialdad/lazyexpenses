"""statement-app: one FastAPI process serving the PWA + data + ingest/bills.

ROUTE ORDER IS LOAD-BEARING. A StaticFiles mount at "/" is a catch-all that
shadows sibling routes, so the explicit API routes (/healthz, /data/app.json,
/bills, /ingest) are registered FIRST and the SPA mount LAST. /data/app.json is
served from the writable PVC (DATA_DIR), never the baked build/ copy, so data and
code stay decoupled (runtime refresh, no rebuild).

An optional shared-password gate (APP_PASSWORD, #51) covers every API route and nothing
else - see the block above create_app().
"""
import asyncio
import hashlib
import hmac
import json
import os
import posixpath
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import fetch_mail
import parse  # for BANKS — the dispatch list, not a second copy of it
import remind_bills
import web_push
from server import pipeline, settings

# Reconciliation statuses that are NOT a problem. VERIFIED is the goal; DUPLICATE is
# routine (the mail history re-exports the same statement under several filenames,
# which is why parse.py fingerprint-dedups). Everything else — REVIEW, NO_BALANCE,
# ERROR — means a statement did not reconcile and the caller should know.
RECON_OK = {"VERIFIED", "DUPLICATE"}

# #62: the build this image was made from. Baked by the Dockerfile (ARG -> ENV, fed from
# docker.yml's semver tag), NOT configured by a hoster - a bare `docker build` or a
# `python -m uvicorn` off a checkout honestly says "dev" rather than a stale semver.
VERSION = os.environ.get("APP_VERSION") or "dev"

# What the "Send test message" button sends (#40). Two lines because send_webpush splits
# on the first newline for title/body, and Telegram HTML renders the <b> — so one string
# looks right in both transports, exactly like a real reminder does.
TEST_REMINDER = ("<b>Reminders are working</b>\n\n"
                 "This is what a bill reminder will look like.")

# ---------------------------------------------------------------- password gate (#51)
# Off unless APP_PASSWORD is set - the same off-unless-configured contract the reminders
# (TELEGRAM_*) and the mail fetch (GMAIL_*) use, so an existing deployment that sets
# nothing keeps behaving exactly as it did.
#
# When it IS set, a protected request needs one of:
#   - the session cookie issued by POST /api/login, or
#   - the password in an X-App-Password header (that is how fetch_mail.py posts to
#     /ingest, in-process on the loopback or standalone against INGEST_URL).
# Two things stay open on purpose: /healthz, because the k8s probes call it, and the
# PWA's own assets, because the browser needs them to render the prompt.
#
# ponytail: one shared password, no accounts. One person, one volume - see #51.
#
# #65: .env.example now SHIPS a password, so the documented `docker compose up` path is
# closed rather than open. A shipped default is a known credential - it is in the repo -
# so the only thing that makes it safe is being loud: the server warns once at startup
# and the Settings screen carries a banner until it changes.
#
# #72: "production is unaffected" was the wrong read. lazyexpense-secrets sets no
# APP_PASSWORD, so the gate is OFF on the live host — the one deployment that is actually
# reachable is the one with no login. The fix is a secret in the infrastructure repo, not
# code; what code owes is not being quiet about it, which is _unauthenticated().
DEFAULT_PASSWORD = "changeme@123"
COOKIE = "lx_session"
SESSION_TTL = 30 * 86400                        # seconds; also the cookie Max-Age
AUTH_PUBLIC = {"/healthz", "/api/login"}
# Gated by prefix as well as by route, so a file that somehow ends up under these paths
# inside the static mount is not a way around the routes of the same name.
AUTH_PREFIXES = ("/data/", "/api/")


def _app_password() -> str:
    return os.environ.get("APP_PASSWORD") or ""


def _unauthenticated() -> bool:
    """No APP_PASSWORD at all, so the gate in _install_gate() never fires. #72: this is
    the state `default_password` cannot describe. With no password set it answers False,
    which reads as "the password was changed" and is exactly backwards — it is False
    because there is nothing to change. The write path is what is open: POST
    /api/settings can overwrite the Gmail app password or repoint the Telegram pair, and
    POST /ingest takes a statement from anyone. So this is reported and warned about
    rather than left to be inferred from a bool that means something else."""
    return not _app_password()


def _default_password() -> bool:
    """Is the gate still standing on the password the repo publishes? A BOOLEAN — the
    browser is told the state, never the value, exactly like every secret in
    settings.public(). Deliberately reads the environment only, like _app_password():
    APP_PASSWORD is not on the settings whitelist and must not become settable."""
    return _app_password() == DEFAULT_PASSWORD


def _sign(exp: int, pw: str) -> str:
    """MAC over the expiry. The key is derived from the password, so sessions need no
    server-side store (they survive a restart) and changing the password invalidates
    every outstanding cookie for free."""
    return hmac.new(hashlib.sha256(pw.encode()).digest(),
                    str(exp).encode(), hashlib.sha256).hexdigest()


def _issue_token(pw: str) -> str:
    exp = int(time.time()) + SESSION_TTL
    return f"{exp}.{_sign(exp, pw)}"


def _token_ok(token: str, pw: str) -> bool:
    exp, _, mac = (token or "").partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(mac, _sign(int(exp), pw))


def _is_https(request: Request) -> bool:
    """Behind a reverse proxy the app itself speaks http, so trust the forwarded header
    when it is there - that is the whole point of terminating TLS in front."""
    fwd = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return (fwd or request.url.scheme) == "https"


def _norm(path: str) -> str:
    """Collapse `//`, resolve `.` and `..`, drop the trailing slash.

    The gate matches paths as strings, and `//data/app.json`, `/data/app.json/`,
    `/./data/app.json`, `/data//app.json` and `/x/../data/app.json` all reach the same
    file - so they have to compare equal to `/data/app.json` or they are five bypasses.
    (`lstrip` first because posixpath.normpath preserves a leading `//`.)"""
    return posixpath.normpath("/" + path.lstrip("/"))


def _authed(request: Request, pw: str) -> bool:
    header = request.headers.get("x-app-password")
    # .encode(): compare_digest rejects non-ASCII str, and a password may well be
    if header and hmac.compare_digest(header.encode(), pw.encode()):
        return True
    return _token_ok(request.cookies.get(COOKIE, ""), pw)


def _install_gate(app: FastAPI) -> None:
    """MIDDLEWARE, NOT A ROUTE DEPENDENCY - this is the whole point.

    A dependency only runs for APIRoutes, so a StaticFiles mount is structurally outside
    it. The baked PWA build is mounted at "/", so anything the router hands to that mount
    is public: `//data/app.json` and friends miss the exact `/data/app.json` route, fall
    through to the mount and get served. Middleware runs BEFORE routing, so it sees mount
    traffic too - and normalises the path before matching it.

    `protected` is derived from the router rather than hand-listed, so a route added
    later is gated the day it is added.
    """
    protected = {r.path for r in app.routes if isinstance(r, APIRoute)} - AUTH_PUBLIC

    @app.middleware("http")
    async def gate(request: Request, call_next):
        pw = _app_password()
        p = _norm(request.scope["path"])
        # .lower() on the prefixes only: a case-insensitive filesystem would serve
        # /DATA/app.json out of the mount. Route names stay case-sensitive, and nothing
        # under a differently-cased AUTH_PUBLIC path exists to reach.
        if pw and p not in AUTH_PUBLIC and (p in protected
                                            or p.lower().startswith(AUTH_PREFIXES)):
            if not _authed(request, pw):
                return JSONResponse({"detail": "password required"}, status_code=401)
        return await call_next(request)


IMMUTABLE = "_app/immutable/"


def _cache_control(path: str) -> str:
    """`_app/immutable/*` is content-addressed — the filename changes when the bytes do,
    so it can be cached for a year and never revalidated. Everything else (sw.js,
    index.html, manifest.webmanifest, the icons) is a STABLE url whose contents change on
    every release, so it must revalidate or a client can sit on last month's shell."""
    return ("public, max-age=31536000, immutable"
            if path.replace("\\", "/").startswith(IMMUTABLE) else "no-cache")


class SPAStaticFiles(StaticFiles):
    """try_files: exact file -> "<path>.html" (prerendered route) -> SPA shell index.html.

    StaticFiles(html=True) only maps "/" -> index.html and serves *exact* files, so the
    extensionless prerendered routes (/trends, /cuts) 404. That 404 is fatal twice: a direct
    /trends load 404s online, AND the Workbox SW precaches those routes — one 404 during
    `install` rejects the whole precache, so the service worker never activates and the PWA
    has no offline. Resolving routes the way `vite preview` / a static host does fixes both.
    """

    async def get_response(self, path, scope):
        res = await self._resolve(path, scope)
        # #75: starlette's StaticFiles sets an ETag and Last-Modified but no Cache-Control,
        # so every one of these files was relying on browser defaults. sw.js is the one
        # that matters — it is the mechanism by which every client learns a release
        # happened, and #67's reload banner is built on top of it. `no-cache` is
        # revalidate-every-time, NOT `no-store`: the ETag still turns an unchanged file
        # into a 304 with no body.
        res.headers["cache-control"] = _cache_control(path)
        return res

    async def _resolve(self, path, scope):
        # Starlette may raise HTTPException(404) (html=True, no 404.html) OR return a 404
        # response depending on version — handle both.
        # StaticFiles raises starlette's HTTPException (fastapi's is a subclass), so catch
        # the base; some versions return a 404 response instead, so check status too.
        try:
            res = await super().get_response(path, scope)
            if res.status_code != 404:
                return res
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        for cand in (f"{path}.html", "index.html"):
            try:
                alt = await super().get_response(cand, scope)
                if alt.status_code == 200:
                    return alt
            except StarletteHTTPException:
                continue
        raise HTTPException(status_code=404)


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data"))


# Bill reminders run IN this process rather than as a separate cron/CronJob: the
# server is already the long-running thing that knows DATA_DIR, so a timer here means
# one container to deploy instead of two.
# remind_bills.py stays runnable standalone for anyone not running the server.
#
# READ PER TICK, NOT AT IMPORT (#40). These were module constants, which meant changing
# REMIND_HOUR or FETCH_POLL needed a container restart — fine when the only way to set
# them was .env, useless now that the UI can write them to settings.json while the loop
# is running. settings.get_int() is env-first, so an existing deployment is unaffected.
def _remind_hour():
    return settings.get_int("REMIND_HOUR", 9)       # earliest local hour to send


def _remind_poll():
    return settings.get_int("REMIND_POLL", 1800)    # seconds between checks


# The mail fetch rides in this process for the same reason. One container runs the whole
# pipeline; there is no CronJob and no second compose service.
def _fetch_poll():
    return settings.get_int("FETCH_POLL", 3600)     # seconds between mail checks


def _reminder_tick():
    """One check: read bills + paid state off the PVC and remind about what is due.

    Reads the files directly instead of calling our own /bills over HTTP — same data,
    no dependency on which port/host uvicorn happens to be bound to."""
    d = _data_dir()
    app_json, paid_json = d / "app.json", d / "paid.json"
    if not app_json.exists():
        return []
    bills = json.loads(app_json.read_text(encoding="utf-8")).get("bills", [])
    paid = set(json.loads(paid_json.read_text(encoding="utf-8"))) if paid_json.exists() else set()
    # days/template left to remind_bills, which resolves both per call through settings (#40)
    return remind_bills.run(bills, paid, state_path=str(d / "reminded.json"))


async def _reminder_loop():
    """Poll instead of sleeping until 09:00: the per-bill state file is what prevents
    duplicates, so an extra tick is a no-op and a restart cannot re-send. That makes
    the schedule a plain `is it past REMIND_HOUR yet` check with no timer to lose.

    ponytail: assumes ONE instance (replicas:1 + RWO volume + Recreate). Two replicas
    would each hold their own view of reminded.json and could double-send.
    """
    while True:
        try:
            # transports_configured() is re-checked HERE rather than once in lifespan:
            # Web Push needs no configuration, so a subscription can arrive hours after
            # startup. An unconfigured deployment ticks and does nothing, silently.
            if (datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).hour >= _remind_hour()
                    and remind_bills.transports_configured()):
                # off-loop: the tick does blocking file IO and a blocking Telegram POST
                for b in await asyncio.to_thread(_reminder_tick):
                    print(f"reminder sent: {b['bank']} {b['statement_month']}", flush=True)
        except Exception as e:  # a bad token or a Telegram outage must not kill the app
            print(f"reminder failed: {e}", flush=True)
        await asyncio.sleep(_remind_poll())


async def _fetch_loop():
    """Poll the mailbox and post whatever arrived, on a timer inside the web process.

    Unlike the reminder tick - which reads the PVC directly rather than calling our own
    /bills - this deliberately goes back out through /ingest over the loopback. Reading
    a file and running the pipeline are not the same problem: /ingest holds the lock,
    saves the PDF and reparses the corpus, and going through the route keeps exactly one
    copy of that. The cost is knowing our own port, which is what INGEST_URL is for.

    No state of its own is needed: fetch_mail marks a message \\Seen only once every
    attachment ingested, so anything that failed is simply still unread next tick.

    Like the reminder loop since #39, this always starts and decides PER TICK whether it
    is configured (#40): the credentials can now arrive from the Settings UI hours after
    startup, so an import-time gate would mean "configured it, nothing happened, restart".
    Unconfigured, it wakes up, finds nothing, and says nothing.
    """
    while True:
        try:
            if settings.get("GMAIL_USER") and settings.get("GMAIL_APP_PASSWORD"):
                # off-loop: IMAP and the ingest POST both block, and the POST is answered
                # by this very event loop
                await asyncio.to_thread(fetch_mail.main)
        except Exception as e:  # a mailbox outage must not kill the app
            print(f"fetch failed: {e}", flush=True)
        await asyncio.sleep(_fetch_poll())


@asynccontextmanager
async def _lifespan(app):
    # #65: loud, once, on every boot — and NOT a refusal to start, because the person
    # seeing this is usually mid-setup and locking them out helps nobody. The value is
    # printed because it is already public; hiding it would only hide the problem.
    if _default_password():
        print(f"{'!' * 20} SECURITY: APP_PASSWORD is still the shipped default "
              f"{DEFAULT_PASSWORD!r} — it is published in .env.example, so anyone who has "
              f"seen this repo can open your app. Change it in .env and restart. "
              f"{'!' * 20}", flush=True)
    # #72: same volume, same reason, louder gap — no password means the gate never fires
    # at all, and until now that state was the QUIET one. It is the deployment actually
    # exposed, so it gets the same treatment and still does not block boot.
    elif _unauthenticated():
        print(f"{'!' * 20} SECURITY: no APP_PASSWORD is set, so this app has NO login. "
              f"Anyone who can reach it can upload statements, read your spending, and "
              f"overwrite your mail and reminder credentials. Set APP_PASSWORD and "
              f"restart. {'!' * 20}", flush=True)
    tasks = []
    # Always started since #39: Web Push is the default transport and needs nothing
    # configured, so there is no env var to gate on. The loop itself checks per tick
    # whether any transport exists and stays quiet when none does.
    tasks.append(asyncio.create_task(_reminder_loop()))
    # Always started since #40, for the same reason the reminder loop is: mail credentials
    # can be typed into the Settings UI while this process is running. _fetch_loop checks
    # per tick and no-ops when nothing is configured.
    tasks.append(asyncio.create_task(_fetch_loop()))
    yield
    for t in tasks:
        t.cancel()


def _settings_view() -> dict:
    """What both /api/settings routes answer with. The two gate flags are added HERE and
    not in settings.public() so that module keeps knowing nothing about the gate — it is
    the one place with a hard "never returns a secret value" invariant, and a bool about
    APP_PASSWORD is state, not value.

    They are separate bools, not one tri-state, because they are separate warnings with
    separate fixes: `default_password` says change a known credential, `unauthenticated`
    says there is no credential. Both false is the only good answer."""
    return {**settings.public(parse.BANKS),
            "default_password": _default_password(),
            "unauthenticated": _unauthenticated()}


def _web_dir() -> Path:
    return Path(os.environ.get("WEB_DIR", str(Path(__file__).resolve().parent.parent / "web_build")))


def create_app() -> FastAPI:
    app = FastAPI(title="statement-app", lifespan=_lifespan)
    lock = asyncio.Lock()  # serialize the pipeline: no concurrent parse runs

    @app.get("/healthz")
    def healthz():
        # `version` is additive on purpose: this is the k8s liveness probe and the one
        # unauthenticated endpoint, so the existing {"ok": True} shape must keep working.
        return {"ok": True, "version": VERSION}

    @app.post("/api/login")
    def login(request: Request, body: dict = Body(...)):
        """Exchange the shared password for a signed session cookie.

        `auth: false` when no APP_PASSWORD is configured - the PWA never gets here in
        that case, but a curl user deserves a straight answer rather than a 401."""
        pw = _app_password()
        if not pw:
            return JSONResponse({"ok": True, "auth": False})
        if not hmac.compare_digest(str(body.get("password") or "").encode(), pw.encode()):
            raise HTTPException(status_code=401, detail="wrong password")
        res = JSONResponse({"ok": True, "auth": True})
        res.set_cookie(COOKIE, _issue_token(pw), max_age=SESSION_TTL, path="/",
                       httponly=True, samesite="lax", secure=_is_https(request))
        return res

    @app.get("/data/app.json")
    def data_app_json():
        p = _data_dir() / "app.json"
        if not p.exists():
            raise HTTPException(status_code=404, detail="app.json not generated yet")
        return FileResponse(str(p), media_type="application/json")

    @app.get("/bills")
    def bills():
        p = _data_dir() / "app.json"
        if not p.exists():
            return JSONResponse([])
        data = json.loads(p.read_text(encoding="utf-8"))
        return JSONResponse(data.get("bills", []))

    @app.get("/data/paid.json")
    def data_paid_json():
        # Cross-device paid-bill state, kept OUT of app.json (pipeline regenerates that).
        # Served from the PVC; [] when nothing's been marked yet.
        p = _data_dir() / "paid.json"
        if not p.exists():
            return JSONResponse([])
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))

    @app.post("/api/paid")
    async def set_paid(body: dict = Body(...)):
        k = body.get("key")
        if not isinstance(k, str) or not k:
            raise HTTPException(status_code=400, detail="missing key")
        is_paid = bool(body.get("paid"))
        p = _data_dir() / "paid.json"
        async with lock:  # reuse the pipeline lock — serializes the atomic rewrite
            keys = set(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else set()
            keys.add(k) if is_paid else keys.discard(k)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(sorted(keys)), encoding="utf-8")
            os.replace(tmp, p)  # atomic on POSIX
        return JSONResponse(sorted(keys))

    # ------------------------------------------------------------ web push (#39)
    # Gated by APP_PASSWORD like every other /api route (the gate derives its set from
    # the router), which is right: a subscription is a place to send this person's
    # balances to.
    @app.get("/api/push/key")
    def push_key():
        """The VAPID public key the browser subscribes with, made on first call and kept
        on the volume. Nothing for the user to paste — that is the point of #39."""
        try:
            return {"key": web_push.vapid_keys()[1]}
        except Exception as e:   # no cryptography, read-only volume, ...
            raise HTTPException(status_code=503, detail=f"push unavailable: {e}")

    @app.post("/api/push/subscribe")
    async def push_subscribe(body: dict = Body(...)):
        """Store (or, with no keys, forget) one PushSubscription. Same volume-write
        shape as /api/paid; the endpoint URL is the identity."""
        ep = body.get("endpoint")
        if not isinstance(ep, str) or not ep.startswith("https://"):
            raise HTTPException(status_code=400, detail="missing endpoint")
        keys = body.get("keys") or {}
        async with lock:  # reuse the pipeline lock — serializes the atomic rewrite
            subs = web_push.load_subs()
            if keys.get("p256dh") and keys.get("auth"):
                subs[ep] = {"p256dh": keys["p256dh"], "auth": keys["auth"]}
            else:
                subs.pop(ep, None)   # no keys = the UI's off switch
            web_push.save_subs(subs)
        return {"subscribed": ep in subs, "count": len(subs)}

    @app.get("/data/waivers.json")
    def data_waivers_json():
        # Cross-device annual-fee waiver status (key -> "requested"/"waived"), kept OUT of
        # app.json. Served from the PVC; {} when nothing's been tracked yet.
        p = _data_dir() / "waivers.json"
        if not p.exists():
            return JSONResponse({})
        return JSONResponse(json.loads(p.read_text(encoding="utf-8")))

    @app.post("/api/waivers")
    async def set_waiver(body: dict = Body(...)):
        k = body.get("key")
        if not isinstance(k, str) or not k:
            raise HTTPException(status_code=400, detail="missing key")
        status = body.get("status")  # "requested"/"waived"; None clears (back to default)
        p = _data_dir() / "waivers.json"
        async with lock:  # reuse the pipeline lock — serializes the atomic rewrite
            m = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            if status:
                m[k] = status
            else:
                m.pop(k, None)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(m, sort_keys=True), encoding="utf-8")
            os.replace(tmp, p)  # atomic on POSIX
        return JSONResponse(m)

    # ------------------------------------------------------------ first-run setup (#40)
    # Gated by APP_PASSWORD like every other /api route (the gate derives its set from the
    # router), and write-only for secrets whether the gate is on or not — see
    # server/settings.py. Since #65 the documented compose path SETS that gate, so these
    # routes are closed by default there — but write-only secrets do not depend on it.
    @app.get("/api/settings")
    def read_settings():
        return _settings_view()

    @app.post("/api/settings")
    async def write_settings(body: dict = Body(...)):
        """Merge a patch into settings.json. "" clears a value; env-locked names are
        ignored. The response is public() — so a POST can never echo a secret back."""
        try:
            async with lock:  # reuse the pipeline lock — serializes the atomic rewrite
                settings.save(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return _settings_view()

    @app.post("/api/settings/test-mail")
    async def test_mail():
        """What the Test connection button calls. Read-only: it logs in, selects the
        label and counts the unread, so a wrong password or a missing label is a sentence
        now instead of silence an hour from now."""
        try:
            return await asyncio.to_thread(fetch_mail.check)
        except Exception as e:
            # str() of an imaplib error is a bytes repr; b'...' in the UI is not an answer
            raise HTTPException(status_code=400, detail=str(e).strip("b'\" ") or type(e).__name__)

    @app.post("/api/settings/test-reminder")
    async def test_reminder():
        """Send one message down every configured transport. remind_bills.send() raises
        only when NOTHING got through, which is exactly the failure worth reporting."""
        try:
            await asyncio.to_thread(remind_bills.send, TEST_REMINDER)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/ingest")
    async def ingest(file: UploadFile, bank: str = Form(...)):
        # Reject before anything touches the volume: `bank` picks the password and the
        # parser branch, and the filename keeps it forever (parse.py re-derives it).
        bank = bank.strip().lower()
        if bank not in parse.BANKS:
            raise HTTPException(status_code=400,
                                detail=f"unknown bank {bank!r}; expected one of: {', '.join(parse.BANKS)}")
        content = await file.read()
        data_dir = _data_dir()
        async with lock:
            try:
                saved = pipeline.save_pdf(data_dir, bank, content)
                counts = await asyncio.to_thread(pipeline.run_pipeline, data_dir)
            except Exception as e:  # old app.json kept (atomic write); surface failure
                raise HTTPException(status_code=500, detail=f"pipeline failed: {e}")
        # `problems` tells the caller WHICH statuses are bad. `warning` stays a plain bool
        # next to it because Setup.svelte reads it directly — the one-glance "did this go
        # wrong?" for a caller that does not want to interpret a status map.
        problems = {k: v for k, v in counts.items() if k not in RECON_OK and v}
        # `locked` (#40) turns one of those ERRORs into a question the UI can ask in
        # context — "what is the password for this bank?" — while the covering email is
        # still open. Only asked when something errored, and only of THIS upload.
        locked = bool(problems.get("ERROR")) and pipeline.needs_password(saved, bank)
        return {"bank": bank, "recon": counts, "problems": problems,
                "warning": bool(problems), "locked": locked}

    # SPA catch-all LAST — shadows the explicit routes above if mounted first.
    web = _web_dir()
    if web.exists():
        app.mount("/", SPAStaticFiles(directory=str(web), html=True), name="spa")
    _install_gate(app)   # after the routes: `protected` is read off the router
    return app


app = create_app()
