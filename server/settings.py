"""Settings typed into the web UI, persisted to <DATA_DIR>/settings.json (#40).

Lives next to the other state files on the volume (paid.json, waivers.json,
reminded.json) because the volume is the only writable place a container has.

THE ENVIRONMENT ALWAYS WINS. get() reads os.environ first and only then the file, so an
existing .env / k8s-Secret deployment behaves exactly as it did before this module
existed. A name the environment defines is reported as `locked` so the UI can grey it
out instead of accepting an edit that could never take effect.

SECURITY (#40): this app has NO authentication by default - APP_PASSWORD (#51) is off
unless set, so anyone who can reach it already sees every transaction. Letting them read
a *credential* back out is the line we do not cross: every name in SECRET is write-only
over the API, and public() reports a bool and never a value, not even a masked one.
That exposure is the case for a login, which is filed as its own issue (#65) rather than
built here.

WHY THE NAMES ARE A WHITELIST and not "whatever the browser posts": these values are
merged into the environment of the parse.py subprocess (pipeline.run_pipeline), so an
arbitrary name would be arbitrary environment injection - LD_PRELOAD, PYTHONPATH, PATH.
APP_PASSWORD is deliberately absent too: the gate must not be settable through the thing
it gates.

STDLIB ONLY, deliberately: fetch_mail.py imports this and is the one part of the pipeline
that needs no dependency at all. The bank list therefore comes from parse.BANKS in
server/app.py, which already imports it, rather than from here.
"""
import json
import os
import re
from pathlib import Path

# One per bank, read by parse.pw_for() as CC_PW_<BANK> — which is why the statement
# passwords are named after the environment variable and not after the UI field. Matched
# by shape rather than enumerated: an unknown bank suffix is inert (nothing reads it),
# and the whitelist only exists to keep PATH-shaped names out.
_PW = re.compile(r"CC_PW_[A-Z]+")

# Never leaves the server.
SECRET = {"GMAIL_APP_PASSWORD", "TELEGRAM_BOT_TOKEN"}

# Everything else the UI may write. Anything not here and not a CC_PW_* is a 400.
PLAIN = {"GMAIL_USER", "GMAIL_LABEL", "IMAP_HOST", "FETCH_POLL",
         "TELEGRAM_CHAT_ID", "REMIND_HOUR", "REMIND_DAYS", "REMIND_TEMPLATE"}


def is_secret(name: str) -> bool:
    return name in SECRET or bool(_PW.fullmatch(name))


def allowed(name: str) -> bool:
    return name in PLAIN or is_secret(name)


def _path() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data")) / "settings.json"


def load() -> dict:
    """The volume half only, filtered to the allowed names. {} when missing or corrupt:
    every value here has a working default, so a broken file must not take the app down."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if allowed(k) and isinstance(v, str) and v}
    except (OSError, ValueError, AttributeError):
        return {}


def get(name, default=None):
    """Environment first, then the volume. This precedence IS the contract (#40)."""
    v = os.environ.get(name) or load().get(name)
    return v if v else default


def get_int(name, default):
    """Same precedence, but a typo in a number must not crash a loop that runs forever."""
    try:
        return int(get(name, default))
    except (TypeError, ValueError):
        return default


def env() -> dict:
    """The volume values the environment does not already define — extra env for the
    parse.py subprocess, so a password typed into the UI reaches parse.pw_for()."""
    return {k: v for k, v in load().items() if not os.environ.get(k)}


def save(updates: dict) -> dict:
    """Merge and rewrite atomically; "" (or None) deletes. Returns the new file contents.

    An env-locked name is skipped rather than written: the UI greys it out, and a stale
    tab must not leave a value on the volume that will never be read."""
    bad = sorted(k for k in updates if not allowed(k))
    if bad:
        raise ValueError(f"unknown setting(s): {', '.join(bad)}")
    cur = load()
    for k, v in updates.items():
        if os.environ.get(k):
            continue
        s = "" if v is None else str(v).strip()
        if s:
            cur[k] = s
        else:
            cur.pop(k, None)
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cur, sort_keys=True, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)      # credentials on a volume somebody else may back up
    os.replace(tmp, p)        # atomic on POSIX
    return cur


def public(banks=()) -> dict:
    """What the browser is allowed to know. `banks` comes from parse.BANKS via the caller,
    so this module needs no import of the parser (see the module docstring).

    SECURITY (#40): `secrets` is a configured/not-configured BOOLEAN per name. No secret
    value is ever returned — not truncated, not masked, not last-four. There is no
    authentication in front of this route by default, so a readable secret is a leaked
    one. test_app.py::test_no_endpoint_ever_returns_a_secret_value is the guard.
    """
    on_disk = load()
    secrets = sorted(SECRET | {f"CC_PW_{b.upper()}" for b in banks})
    return {
        "values": {k: (os.environ.get(k) or on_disk.get(k) or "") for k in sorted(PLAIN)},
        "secrets": {k: bool(os.environ.get(k) or on_disk.get(k)) for k in secrets},
        "locked": sorted(k for k in (*PLAIN, *secrets) if os.environ.get(k)),
        "banks": list(banks),
    }
