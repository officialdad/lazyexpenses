"""Every `python <name>.py` the docs hand a hoster must exist in the image.

v0.9.0 shipped a docs/DEPLOY.md line telling people to run `python llm_cats.py
--suggest-cats` against a container that had no llm_cats.py in it, because the file
was added to the repo and the docs but not to Dockerfile's explicit COPY list. This
is the grep that would have caught it: no Docker daemon, no image build, just the
docs read against that one line.

The COPY list stays explicit on purpose — `COPY *.py ./` would drag in the demo
generator, probe.py and nine test files. The list is not the problem; nothing
checking it was."""
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
DOCS = ("docs/DEPLOY.md", "README.md")

# Optional leading path covers the crontab block's `python /path/to/fetch_mail.py`.
CMD = re.compile(r"\bpython3?\s+(?:[\w./-]*/)?(\w+\.py)\b")

# Dev-only scripts the docs mention but that no hoster ever runs against the container.
# There is no structural tell to lean on: README's demo blocks invoke make_demo_data.py
# and verify_parity.py in exactly the shape DEPLOY.md invokes llm_cats.py — a bare
# `python x.py` inside a fenced bash block. The only thing separating the two kinds is
# what they are for, so the list is written out. test_*.py is a prefix rule because
# there are nine of them and there will be more.
DEV_ONLY = {"make_demo_data.py", "probe.py", "verify_parity.py"}


def documented():
    """Every `<name>.py` invoked from a fenced code block in the hoster-facing docs.

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
    demo = {"make_demo_data.py", "verify_parity.py"}
    assert demo <= documented(), sorted(demo - documented())
    assert not demo & copied(), sorted(demo & copied())


if __name__ == "__main__":
    test_every_documented_command_ships_in_the_image()
    test_the_scan_actually_finds_commands()
    test_dev_only_scripts_do_not_trip_it()
    print("OK")
