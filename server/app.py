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

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server import pipeline


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
        app.mount("/", StaticFiles(directory=str(web), html=True), name="spa")
    return app


app = create_app()
