"""Append a session summary to home-relative, date-organized local storage."""

import argparse
from datetime import datetime
import fcntl
import os
import re
import sys
from uuid import UUID

from storage import project_directory, validate_date


def save_summary(cwd, session_id, session_date, summary, checkpoint_id=None):
    """Append one entry, or reuse an entry with the same checkpoint marker."""
    if str(UUID(session_id)) != session_id.lower():
        raise ValueError("Session ID must be a hyphenated UUID.")
    validate_date(session_date)
    if not summary.strip():
        raise ValueError("Summary must not be empty.")
    if checkpoint_id is not None and not re.fullmatch(r"[0-9a-f]{64}", checkpoint_id):
        raise ValueError("Checkpoint ID must be a SHA-256 hex digest.")

    working_directory, project = project_directory(cwd)
    raw_directory = project / "raw summaries"
    rollup_directory = project / "rollup"
    raw_directory.mkdir(parents=True, exist_ok=True)
    rollup_directory.mkdir(parents=True, exist_ok=True)
    destination = raw_directory / f"{session_date}.md"
    if destination.is_symlink():
        raise ValueError("Summary file must not be a symbolic link.")

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    marker = ""
    if checkpoint_id is not None:
        marker = f"<!-- checkpoint:{session_id}:{checkpoint_id} -->\n"
    entry = (
        f"## Session {session_id}\n\n"
        f"- Saved: {timestamp}\n"
        f"- Working directory: {working_directory}\n"
        f"- Session ID: `{session_id}`\n"
        f"- Resume: `copilot --resume={session_id}`\n\n"
        f"{summary.strip()}\n{marker}"
    )
    with destination.open("a+", encoding="utf-8") as output:
        fcntl.flock(output, fcntl.LOCK_EX)
        if marker:
            output.seek(0)
            # The append may have succeeded before an autosave state update failed.
            if marker in output.read():
                return destination
        output.seek(0, os.SEEK_END)
        if output.tell():
            output.write("\n\n---\n\n")
        output.write(entry)
        output.flush()
        os.fsync(output.fileno())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--session-date", required=True)
    args = parser.parse_args()
    try:
        destination = save_summary(
            args.cwd, args.session_id, args.session_date, sys.stdin.read()
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot save summary: {error}\n")
    print(destination)


if __name__ == "__main__":
    main()
