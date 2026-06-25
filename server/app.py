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
from pathlib import Path

from fastapi import Body, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from server import pipeline


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


def _web_dir() -> Path:
    return Path(os.environ.get("WEB_DIR", str(Path(__file__).resolve().parent.parent / "web_build")))


def create_app() -> FastAPI:
    app = FastAPI(title="statement-app")
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
        return {"bank": bank, "recon": counts, "warning": counts.get("REVIEW", 0) > 0}

    # SPA catch-all LAST — shadows the explicit routes above if mounted first.
    web = _web_dir()
    if web.exists():
        app.mount("/", SPAStaticFiles(directory=str(web), html=True), name="spa")
    return app


app = create_app()
