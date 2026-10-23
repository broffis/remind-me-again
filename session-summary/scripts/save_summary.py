"""Append a session summary to home-relative, date-organized local storage."""

import argparse
from datetime import datetime
import fcntl
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from uuid import UUID

from storage import (
    BLOCK_SEPARATOR, block_session_id, project_directory, split_blocks, validate_date,
)


def save_summary(cwd, session_id, session_date, summary, checkpoint_id=None):
    """Write the session's single block, replacing its previous summary if present.

    A repeated checkpoint with the same marker leaves the file unchanged.
    """
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
    lock_path = raw_directory / ".lock"
    if lock_path.is_symlink():
        raise ValueError("Raw summary lock must not be a symbolic link.")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing = destination.read_text(encoding="utf-8") if destination.exists() else ""
        blocks = split_blocks(existing)
        owned = [
            index for index, block in enumerate(blocks)
            if block_session_id(block) == session_id
        ]
        # The write may have succeeded before an autosave state update failed.
        if marker and owned and marker in blocks[owned[-1]]:
            return destination
        if owned:
            blocks[owned[-1]] = entry
        else:
            blocks.append(entry)
        replace_file(destination, BLOCK_SEPARATOR.join(blocks), existing != "")
    return destination


def replace_file(destination, content, keep_mode):
    """Atomically replace the daily file so readers never see a partial write."""
    if keep_mode:
        mode = stat.S_IMODE(destination.stat().st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=".raw-", delete=False,
        ) as output:
            temporary_path = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


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
