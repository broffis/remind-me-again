"""Shared validation for home-relative session storage."""

from datetime import date
from pathlib import Path
import re


UUID_PATTERN = (
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
SESSION_HEADER = re.compile(rf"^## Session ({UUID_PATTERN})$", re.MULTILINE)
BLOCK_SEPARATOR = "\n\n---\n\n"
# A separator only counts when the next block starts with a session header.
_BLOCK_SPLIT = re.compile(rf"\n\n---\n\n(?=## Session {UUID_PATTERN}\n)")


def project_directory(cwd):
    """Return the resolved working directory and its home-relative storage path."""
    home = Path.home().resolve()
    working_directory = Path(cwd).expanduser().resolve(strict=True)
    if not working_directory.is_dir():
        raise ValueError("Working directory must be a directory.")
    relative_path = working_directory.relative_to(home)
    if relative_path == Path("."):
        raise ValueError("Working directory must be below the home directory.")
    storage_root = home / ".copilot" / "session-info"
    project = storage_root / relative_path
    for directory in (project, project / "raw summaries", project / "rollup"):
        if not directory.resolve().is_relative_to(storage_root.resolve()):
            raise ValueError("Summary directories must remain inside session-info.")
    return working_directory, project


def validate_date(value):
    """Accept only a real calendar date spelled exactly as YYYY-MM-DD."""
    if date.fromisoformat(value).isoformat() != value:
        raise ValueError("Date must use YYYY-MM-DD.")
    return value


def split_blocks(text):
    """Split a raw summary file into per-session blocks, preserving their bytes."""
    if not text:
        return []
    blocks = _BLOCK_SPLIT.split(text)
    for block in blocks:
        if not re.match(rf"## Session {UUID_PATTERN}\n", block):
            raise ValueError("Raw summary content has no session ID.")
    return blocks


def block_session_id(block):
    return SESSION_HEADER.match(block).group(1).lower()
