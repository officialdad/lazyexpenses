"""server/requirements.lock must not drift from server/requirements.txt.

The image installs the lock, not the input file (Dockerfile). So a bump that lands in
requirements.txt alone changes nothing that ships: the vulnerable version keeps being
installed and the deploy looks clean. That is exactly how #114 and #115 can cross —
two branches each bump one line of requirements.txt, and whichever merges first
carries a lock compiled before the other's bump existed.

The check is textual on purpose. Re-running `uv pip compile` here would need the
network and would go red the moment any upstream package publishes a release, which
is noise, not drift. What matters is narrower: every version this repo pins by hand
is the version the lock actually installs, and every locked line carries its hashes.

Regenerate with:
    uv pip compile server/requirements.txt --python-version 3.12 --generate-hashes \
        -o server/requirements.lock
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent   # this file lives in tests/
REQ = ROOT / "server" / "requirements.txt"
LOCK = ROOT / "server" / "requirements.lock"

# `uvicorn[standard]==0.34.0` -> ("uvicorn", "0.34.0"). The lock drops the extras, so
# the name is captured without them and compared normalised (PEP 503).
PIN = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^\s;\\]+)")


def pins(text):
    out = {}
    for line in text.splitlines():
        m = PIN.match(line.strip())
        if m:
            out[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return out


def main():
    assert LOCK.exists(), "server/requirements.lock is missing; the image installs it"
    req, lock = pins(REQ.read_text()), pins(LOCK.read_text())

    assert req, "no pins parsed out of requirements.txt"
    for name, want in req.items():
        assert name in lock, f"{name} is pinned in requirements.txt but absent from the lock"
        assert lock[name] == want, (
            f"lock drift: requirements.txt pins {name}=={want}, "
            f"lock installs {name}=={lock[name]} - recompile the lock"
        )

    # A lock holding only the direct pins would pass the loop above while leaving every
    # transitive floating, which is the thing the lock exists to stop.
    assert len(lock) > len(req), "the lock has no transitives in it"

    # --generate-hashes puts each pin on a continuation line followed by its hashes.
    # Without them pip does not hash-check, and --require-hashes in the Dockerfile fails.
    for line in LOCK.read_text().splitlines():
        if PIN.match(line.strip()):
            assert line.rstrip().endswith("\\"), f"locked line carries no hashes: {line!r}"
    assert "--hash=sha256:" in LOCK.read_text()

    print(f"OK ({len(req)} pinned, {len(lock)} locked, all hashed)")


if __name__ == "__main__":
    main()
