"""Prepare incremental rollup input and save an agent-written synthesis."""

import argparse
from datetime import date
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from uuid import UUID

from storage import project_directory, validate_date


PREFIX = "<!-- session-rollup: "
SUFFIX = " -->"
BODY_MARKER = "\n<!-- summary -->\n"
SESSION_HEADER = re.compile(
    r"^## Session ([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$", re.MULTILINE
)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def read_metadata(content, path):
    """Decode the persisted consumption checkpoints and related sessions."""
    first = content.split("\n", 1)[0]
    if not first.startswith(PREFIX) or not first.endswith(SUFFIX):
        raise ValueError(f"Missing rollup tracking metadata: {path}")
    try:
        metadata = json.loads(first[len(PREFIX):-len(SUFFIX)])
        if metadata["version"] != 1 or BODY_MARKER not in content:
            raise ValueError("Unsupported format")
        for filename, checkpoint in metadata["sources"].items():
            validate_date(Path(filename).stem)
            if filename != f"{Path(filename).stem}.md":
                raise ValueError("Invalid source filename")
            if type(checkpoint["bytes"]) is not int or checkpoint["bytes"] < 0:
                raise ValueError("Invalid source offset")
            if not re.fullmatch(r"[0-9a-f]{64}", checkpoint["sha256"]):
                raise ValueError("Invalid source digest")
        for session in metadata["sessions"]:
            validate_date(session["date"])
            UUID(session["id"])
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ValueError(f"Invalid rollup metadata in {path}: {error}") from error
    return metadata


def read_rollup_history(rollup_directory, rollup_date):
    """Collect consumed offsets, file fingerprints, and today's existing summary."""
    sources = {}
    rollups = {}
    sessions = set()
    existing_summary = ""
    for path in sorted(rollup_directory.glob("*.md")):
        validate_date(path.stem)
        if path.is_symlink():
            raise ValueError(f"Rollup must not be a symbolic link: {path}")
        if path.stem > rollup_date:
            raise ValueError("Rollup date cannot precede an existing rollup.")
        content = path.read_text(encoding="utf-8")
        metadata = read_metadata(content, path)
        rollups[path.name] = digest(content.encode("utf-8"))
        for filename, checkpoint in metadata["sources"].items():
            previous_offset = sources.get(filename, {"bytes": -1})["bytes"]
            if checkpoint["bytes"] >= previous_offset:
                sources[filename] = checkpoint
        if path.stem == rollup_date:
            existing_summary = content.split(BODY_MARKER, 1)[1].strip()
            sessions.update((item["date"], item["id"]) for item in metadata["sessions"])
    return sources, rollups, sessions, existing_summary


def read_uncovered_raw(raw_directory, sources):
    """Verify consumed prefixes and return only bytes appended after them."""
    for filename in sources:
        if not (raw_directory / filename).is_file():
            raise ValueError(f"Previously summarized raw file is missing: {filename}")

    pending = []
    checkpoints = dict(sources)
    sessions = set()
    for path in sorted(raw_directory.glob("*.md")):
        validate_date(path.stem)
        if path.is_symlink():
            raise ValueError(f"Raw summary must not be a symbolic link: {path}")
        with path.open("rb") as source:
            fcntl.flock(source, fcntl.LOCK_SH)
            content = source.read()
        prior = sources.get(path.name, {"bytes": 0, "sha256": digest(b"")})
        offset = prior["bytes"]
        if len(content) < offset or digest(content[:offset]) != prior["sha256"]:
            raise ValueError(f"Previously summarized raw content changed: {path}")
        if len(content) == offset:
            continue
        text = content[offset:].decode("utf-8")
        session_ids = SESSION_HEADER.findall(text)
        if not session_ids:
            raise ValueError(f"New raw content has no session ID: {path}")
        sessions.update((path.stem, session_id) for session_id in session_ids)
        pending.append({"file": path.name, "text": text})
        checkpoints[path.name] = {"bytes": len(content), "sha256": digest(content)}
    return pending, checkpoints, sessions


def prepare(cwd, rollup_date):
    """Build a read-only snapshot that save() later checks for stale input."""
    validate_date(rollup_date)
    working_directory, project = project_directory(cwd)
    sources, rollups, sessions, existing_summary = read_rollup_history(
        project / "rollup", rollup_date
    )
    pending, checkpoints, new_sessions = read_uncovered_raw(
        project / "raw summaries", sources
    )
    sessions.update(new_sessions)
    return {
        "cwd": str(working_directory),
        "date": rollup_date,
        "rollups": rollups,
        "sources": checkpoints,
        "sessions": [
            {"date": day, "id": session_id} for day, session_id in sorted(sessions)
        ],
        "existing_summary": existing_summary,
        "pending": pending,
    }


def render_rollup(plan, summary):
    metadata = {
        "version": 1,
        "sources": plan["sources"],
        "sessions": plan["sessions"],
    }
    rows = "\n".join(
        f"| {session['date']} | `{session['id']}` | "
        f"`copilot --resume={session['id']}` |"
        for session in plan["sessions"]
    )
    return (
        f"{PREFIX}{json.dumps(metadata, sort_keys=True)}{SUFFIX}\n\n"
        f"# Rollup {plan['date']}\n\n"
        "## Related sessions\n\n"
        "| Session date | Session ID | Resume |\n"
        "| --- | --- | --- |\n"
        f"{rows}\n\n## Summary\n"
        f"{BODY_MARKER}{summary.strip()}\n"
    )


def replace_rollup(destination, content):
    """Replace the full Markdown and its tracking metadata in one atomic write."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".rollup-",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def save(plan, summary):
    """Save a synthesis only if its prepared input still matches local history."""
    if not summary.strip():
        raise ValueError("Rollup summary must not be empty.")
    if not plan["pending"]:
        raise ValueError("No new raw summaries to roll up.")
    _, project = project_directory(plan["cwd"])
    rollup_directory = project / "rollup"
    rollup_directory.mkdir(parents=True, exist_ok=True)
    lock_path = rollup_directory / ".lock"
    if lock_path.is_symlink():
        raise ValueError("Rollup lock must not be a symbolic link.")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if prepare(plan["cwd"], plan["date"]) != plan:
            raise ValueError("Source summaries or rollups changed; prepare again.")
        destination = rollup_directory / f"{plan['date']}.md"
        replace_rollup(destination, render_rollup(plan, summary))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--cwd", required=True)
    prepare_command.add_argument("--date", default=date.today().isoformat())
    save_command = commands.add_parser("save")
    save_command.add_argument("--plan", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(json.dumps(prepare(args.cwd, args.date), indent=2))
        else:
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            print(save(plan, sys.stdin.read()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Cannot create rollup: {error}\n")


if __name__ == "__main__":
    main()
