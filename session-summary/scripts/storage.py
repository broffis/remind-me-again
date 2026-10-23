"""Shared validation for home-relative session storage."""

from datetime import date
from pathlib import Path


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
