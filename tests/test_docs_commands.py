"""Every `python <name>.py` the docs hand a hoster must exist in the image.

v0.9.0 shipped a docs/DEPLOY.md line telling people to run `python llm_cats.py
--suggest-cats` against a container that had no llm_cats.py in it, because the file
was added to the repo and the docs but not to Dockerfile's explicit COPY list. This
is the grep that would have caught it: no Docker daemon, no image build, just the
docs read against that one line.

The COPY list stays explicit on purpose — `COPY *.py ./` would drag in whatever
lands at the root next. The list is not the problem; nothing checking it was."""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent   # this file lives in tests/
# CONTRIBUTING.md is in here for the same reason the other two are: it hands out
# `python <name>.py` lines, and a contributor running them inside the container hits the
# same missing-module wall v0.9.0 shipped. It is also where the dev-only scripts are
# documented properly, which is what keeps README free to be a user document (#73).
DOCS = ("docs/DEPLOY.md", "README.md", "CONTRIBUTING.md")

# Optional leading path covers the crontab block's `python /path/to/fetch_mail.py`, and
# since #89 the `dev/` and `tests/` prefixes too. The capture is always the bare name.
CMD = re.compile(r"\bpython3?\s+(?:[\w./-]*/)?(\w+\.py)\b")

# Dev-only scripts the docs mention but that no hoster ever runs against the container.
# They live in dev/ since #89, but the regex above drops the directory, so this stays a
# list of bare names — and it stays written out rather than inferred from the path,
# because the thing being checked is what a script is for, not where it sits.
# test_*.py is a prefix rule because there are eleven of them and there will be more.
DEV_ONLY = {"make_demo_data.py", "probe.py", "verify_parity.py"}


def documented():
    """Every `<name>.py` invoked from a fenced code block in the docs.

    Fenced blocks only: prose mentions a file to explain it (README points at
    `python probe.py <file.pdf>` mid-sentence), a code block tells you to run it."""
    found = set()
    for doc in DOCS:
        fenced = False
        for line in (ROOT / doc).read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fenced = not fenced
            elif fenced:
                found.update(CMD.findall(line))
    return found


def copied():
    """Root-level modules the image ships — the COPY lines landing in ./ (WORKDIR
    /app). server/ and web/ arrive as whole directories and are not this check's
    business."""
    shipped = set()
    for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["COPY"] and parts[-1:] == ["./"]:
            shipped.update(p for p in parts[1:-1] if p.endswith(".py"))
    return shipped


def test_every_documented_command_ships_in_the_image():
    want = {f for f in documented()
            if f not in DEV_ONLY and not f.startswith("test_")
            and (ROOT / f).exists()}          # only root-level modules; a path we do
    missing = sorted(want - copied())         # not ship is not ours to police
    assert not missing, (
        f"documented in {' / '.join(DOCS)} but missing from Dockerfile's COPY list: "
        + ", ".join(missing))


def test_the_scan_actually_finds_commands():
    # Without this the check above passes for free the day the regex or the fence
    # tracking breaks. llm_cats.py is here because it is the bug that started this.
    assert {"parse.py", "llm_cats.py", "fetch_mail.py", "remind_bills.py"} <= documented()
    assert "llm_cats.py" in copied()


def test_dev_only_scripts_do_not_trip_it():
    # These two really are invoked from fenced blocks and really are absent from the
    # image, so the exclusion above is load-bearing, not decoration. If one of them
    # ever gets shipped, drop it from DEV_ONLY rather than leaving a lie here.
    #
    # Both live in CONTRIBUTING.md, which is why that file is in DOCS. Before #73 this
    # assertion pinned them to README, so deleting the README demo block turned CI red
    # and verify_parity.py — a parity checker no user will ever run — had to stay in a
    # document aimed at someone who just wants a dashboard.
    demo = {"make_demo_data.py", "verify_parity.py"}
    assert demo <= documented(), sorted(demo - documented())
    assert not demo & copied(), sorted(demo & copied())


if __name__ == "__main__":
    test_every_documented_command_ships_in_the_image()
    test_the_scan_actually_finds_commands()
    test_dev_only_scripts_do_not_trip_it()
    print("OK")
