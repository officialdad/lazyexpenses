"""statement-app: one FastAPI process serving the PWA + data + ingest/bills.

ROUTE ORDER IS LOAD-BEARING. A StaticFiles mount at "/" is a catch-all that
shadows sibling routes, so the explicit API routes (/healthz, /data/app.json,
/bills, /ingest) are registered FIRST and the SPA mount LAST. /data/app.json is
served from the writable PVC (DATA_DIR), never the baked build/ copy, so data and
code stay decoupled (runtime refresh, no rebuild).
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import fetch_mail
import remind_bills
from server import pipeline

# Reconciliation statuses that are NOT a problem. VERIFIED is the goal; DUPLICATE is
# routine (the mail history re-exports the same statement under several filenames,
# which is why parse.py fingerprint-dedups). Everything else — REVIEW, NO_BALANCE,
# ERROR — means a statement did not reconcile and the caller should know.
RECON_OK = {"VERIFIED", "DUPLICATE"}


class SPAStaticFiles(StaticFiles):
    """try_files: exact file -> "<path>.html" (prerendered route) -> SPA shell index.html.

    StaticFiles(html=True) only maps "/" -> index.html and serves *exact* files, so the
    extensionless prerendered routes (/trends, /cuts) 404. That 404 is fatal twice: a direct
    /trends load 404s online, AND the Workbox SW precaches those routes — one 404 during
    `install` rejects the whole precache, so the service worker never activates and the PWA
    has no offline. Resolving routes the way `vite preview` / a static host does fixes both.
    """

    async def get_response(self, path, scope):
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
# one container to deploy instead of two. Off unless both Telegram vars are set.
# remind_bills.py stays runnable standalone for anyone not running the server.
REMIND_HOUR = int(os.environ.get("REMIND_HOUR", "9"))       # earliest local hour to send
REMIND_POLL = int(os.environ.get("REMIND_POLL", "1800"))    # seconds between checks

# The mail fetch rides in this process for the same reason, and is off unless the two
# GMAIL_* vars are set. One container runs the whole pipeline; there is no CronJob and
# no second compose service.
FETCH_POLL = int(os.environ.get("FETCH_POLL", "3600"))      # seconds between mail checks


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
            if datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).hour >= REMIND_HOUR:
                # off-loop: the tick does blocking file IO and a blocking Telegram POST
                for b in await asyncio.to_thread(_reminder_tick):
                    print(f"reminder sent: {b['bank']} {b['statement_month']}", flush=True)
        except Exception as e:  # a bad token or a Telegram outage must not kill the app
            print(f"reminder failed: {e}", flush=True)
        await asyncio.sleep(REMIND_POLL)


async def _fetch_loop():
    """Poll the mailbox and post whatever arrived, on a timer inside the web process.

    Unlike the reminder tick - which reads the PVC directly rather than calling our own
    /bills - this deliberately goes back out through /ingest over the loopback. Reading
    a file and running the pipeline are not the same problem: /ingest holds the lock,
    saves the PDF and reparses the corpus, and going through the route keeps exactly one
    copy of that. The cost is knowing our own port, which is what INGEST_URL is for.

    No state of its own is needed: fetch_mail marks a message \\Seen only once every
    attachment ingested, so anything that failed is simply still unread next tick.
    """
    while True:
        try:
            # off-loop: IMAP and the ingest POST both block, and the POST is answered by
            # this very event loop
            await asyncio.to_thread(fetch_mail.main)
        except Exception as e:  # a mailbox outage must not kill the app
            print(f"fetch failed: {e}", flush=True)
        await asyncio.sleep(FETCH_POLL)


@asynccontextmanager
async def _lifespan(app):
    tasks = []
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        tasks.append(asyncio.create_task(_reminder_loop()))
    if os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"):
        tasks.append(asyncio.create_task(_fetch_loop()))
    yield
    for t in tasks:
        t.cancel()


def _web_dir() -> Path:
    return Path(os.environ.get("WEB_DIR", str(Path(__file__).resolve().parent.parent / "web_build")))


def create_app() -> FastAPI:
    app = FastAPI(title="statement-app", lifespan=_lifespan)
    lock = asyncio.Lock()  # serialize the pipeline: no concurrent parse runs

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

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

    @app.post("/ingest")
    async def ingest(file: UploadFile, bank: str = Form(...)):
        content = await file.read()
        data_dir = _data_dir()
        async with lock:
            try:
                pipeline.save_pdf(data_dir, bank, content)
                counts = await asyncio.to_thread(pipeline.run_pipeline, data_dir)
            except Exception as e:  # old app.json kept (atomic write); surface failure
                raise HTTPException(status_code=500, detail=f"pipeline failed: {e}")
        # `problems` tells the caller WHICH statuses are bad; `warning` stays a plain
        # bool for backwards compatibility with the existing n8n flow.
        problems = {k: v for k, v in counts.items() if k not in RECON_OK and v}
        return {"bank": bank, "recon": counts, "problems": problems, "warning": bool(problems)}

    # SPA catch-all LAST — shadows the explicit routes above if mounted first.
    web = _web_dir()
    if web.exists():
        app.mount("/", SPAStaticFiles(directory=str(web), html=True), name="spa")
    return app


app = create_app()
