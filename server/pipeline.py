"""Subprocess-driven pipeline helpers for the statement-app runner.

Runs the EXISTING CLI scripts (parse.py / insights.py / export_data.py) over a
PVC bucket without importing or modifying their logic. The scripts live at the
repo root (REPO); the bucket is `data_dir` (the PVC mount, e.g. /data):
  <data_dir>/pdfs/        accumulating unlocked PDFs (STMT_SRC)
  <data_dir>/app.json     served data file (STMT_OUT, written atomically)
  <data_dir>/*.csv        intermediate transactions/reconciliation (cwd=data_dir)
"""
import csv
import hashlib
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from server import settings

REPO = Path(__file__).resolve().parent.parent  # repo root / /app in the image
SCRIPTS = ("parse.py", "insights.py", "export_data.py")


def save_pdf(data_dir: "str | Path", bank: str, content: bytes) -> Path:
    sha8 = hashlib.sha256(content).hexdigest()[:8]
    pdfs = Path(data_dir) / "pdfs"
    pdfs.mkdir(parents=True, exist_ok=True)
    dest = pdfs / f"{bank}_{sha8}.pdf"
    if not dest.exists():
        dest.write_bytes(content)
    return dest


def needs_password(path: "str | Path", bank: str) -> bool:
    """Did this statement fail to open because it is encrypted and we lack the key? (#40)

    Asked of the FILE and not of reconciliation.csv on purpose: pdfplumber raises
    PdfminerException wrapping PDFPasswordIncorrect, and `str()` of that is the empty
    string — so the ERROR row parse.py writes carries no reason at all. Opening the one
    file we just received is cheaper than making parse.py's error strings a contract
    (and editing parse.py would bust the whole parse cache).

    /Encrypt is what separates "locked" from "corrupt": both raise, only one is a
    question worth asking the user.
    """
    import pdfplumber  # local: only reached on the error path, and only in the server

    try:
        with pdfplumber.open(str(path), password=settings.get(f"CC_PW_{bank.upper()}", "")):
            return False
    except Exception:
        return b"/Encrypt" in Path(path).read_bytes()


def recon_summary(data_dir: "str | Path") -> dict:
    recon = Path(data_dir) / "reconciliation.csv"
    if not recon.exists():
        return {}
    counts: Counter = Counter()
    with open(recon, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            status = (row.get("status") or "").strip()
            if status:
                counts[status] += 1
    return dict(counts)


def run_pipeline(data_dir: "str | Path") -> dict:
    data_dir = Path(data_dir)
    env = {
        **os.environ,
        # Statement passwords typed into the UI reach parse.pw_for() the only way it
        # reads them: as CC_PW_<BANK> in this subprocess's environment (#40). settings.env()
        # yields only names os.environ does not already define, so the environment wins.
        **settings.env(),
        "STMT_SRC": str(data_dir / "pdfs"),
        "STMT_OUT": str(data_dir / "app.json"),
        "STMT_CACHE": str(data_dir / "cache"),  # per-PDF parse memo, persists on the PVC
    }
    for script in SCRIPTS:
        subprocess.run(
            [sys.executable, str(REPO / script)],
            cwd=str(data_dir),
            env=env,
            check=True,
        )
    return recon_summary(data_dir)
