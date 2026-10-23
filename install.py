"""Install the bundled skill without enabling autosave or autoread."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


SKILL_NAME = "remind-me-again"
MANIFEST = ".remind-me-again-install.json"
PAYLOAD = [
    "SKILL.md",
    "scripts/autosave.py",
    "scripts/retrieval.py",
    "scripts/rollup.py",
    "scripts/save_summary.py",
    "scripts/storage.py",
    "scripts/checkpoint_mcp.py",
    "scripts/setup_mcp.py",
]


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_managed_install(destination):
    """Refuse to remove a symlink, an unknown folder, or locally modified files."""
    if destination.is_symlink():
        raise ValueError("Existing skill is a symbolic link; manage it manually.")
    manifest_path = destination / MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("Existing skill is not a managed installation.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("installer") != SKILL_NAME
        or manifest.get("version") != 1
        or not isinstance(manifest.get("files"), dict)
        or set(manifest["files"]) not in (
            set(PAYLOAD),
            set(PAYLOAD) - {"scripts/setup_mcp.py"},
            set(PAYLOAD) - {"scripts/checkpoint_mcp.py", "scripts/setup_mcp.py"},
        )
    ):
        raise ValueError("Existing skill has an invalid managed-install manifest.")
    expected = set(manifest["files"]) | {MANIFEST}
    for path in destination.rglob("*"):
        relative = path.relative_to(destination)
        if path.is_symlink():
            raise ValueError(f"Installed files changed: {relative}")
        if "__pycache__" in relative.parts:
            continue
        if path.is_file() and relative.as_posix() not in expected:
            raise ValueError(f"Installed files changed: unexpected {relative}")
    for filename, expected_hash in manifest["files"].items():
        path = destination / filename
        if not path.is_file() or fingerprint(path) != expected_hash:
            raise ValueError(f"Installed files changed: {filename}")


def install(source_root, skills_directory, update=False):
    destination = skills_directory / SKILL_NAME
    if destination.is_symlink():
        raise ValueError("Existing skill is a symbolic link; manage it manually.")
    exists = destination.exists()
    if exists:
        if not update:
            raise ValueError("Skill already exists; use --update explicitly.")
        check_managed_install(destination)

    source = source_root / SKILL_NAME
    for filename in PAYLOAD:
        if not (source / filename).is_file():
            raise ValueError(f"Download is incomplete: missing {filename}")
    skills_directory.mkdir(parents=True, exist_ok=True)
    # Stage and back up on the same filesystem so renames are atomic.
    with tempfile.TemporaryDirectory(prefix=".remind-me-again-", dir=skills_directory) as work:
        staging = Path(work) / "new"
        staging.mkdir()
        for filename in PAYLOAD:
            target = staging / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / filename, target)
        manifest = {
            "installer": SKILL_NAME,
            "version": 1,
            "files": {filename: fingerprint(staging / filename) for filename in PAYLOAD},
        }
        (staging / MANIFEST).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        backup = Path(work) / "previous"
        if exists:
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if exists:
                backup.rename(destination)
            raise
    return destination


def uninstall(skills_directory, cwd=None, global_cleanup=False, dry_run=False):
    destination = skills_directory / SKILL_NAME
    if destination.exists() or destination.is_symlink():
        check_managed_install(destination)
    scripts = Path(__file__).resolve().parent / SKILL_NAME / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        spec = importlib.util.spec_from_file_location("session_summary_cleanup", scripts / "setup_mcp.py")
        cleanup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cleanup)
        changes = cleanup.plan_removal(
            Path.cwd() if cwd is None else cwd, destination, global_cleanup
        )
        if not dry_run:
            cleanup.remove_setup(changes)
            if destination.exists():
                shutil.rmtree(destination)
        return [str(path) for path, _ in changes] + [str(destination)]
    finally:
        sys.path.pop(0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--update", action="store_true", help="Replace an unmodified managed install.")
    action.add_argument("--uninstall", action="store_true", help="Remove an unmodified managed install.")
    parser.add_argument("--cwd", type=Path, help="Project to clean on uninstall (default: current directory).")
    parser.add_argument("--global", dest="global_cleanup", action="store_true",
                        help="Also remove this installation's global setup on uninstall.")
    parser.add_argument("--dry-run", action="store_true", help="Preview uninstall without writing.")
    parser.add_argument(
        "--skills-dir", type=Path, default=Path.home() / ".copilot/skills",
        help="Installation parent directory (default: ~/.copilot/skills).",
    )
    args = parser.parse_args()
    if not args.uninstall and (args.global_cleanup or args.dry_run or args.cwd is not None):
        parser.error("--cwd, --global and --dry-run are uninstall options.")
    if sys.version_info < (3, 9) or os.name != "posix":
        parser.exit(1, "Requires Python 3.9+ on macOS or Linux.\n")
    try:
        directory = args.skills_dir.expanduser().absolute()
        if args.uninstall:
            paths = uninstall(directory, args.cwd, args.global_cleanup, args.dry_run)
            print(("Would remove/update" if args.dry_run else "Removed/updated") +
                  ":\n" + "\n".join(paths))
            print("Saved summaries, rollups, and unrelated configuration were preserved.")
            print("Other projects' setup/approvals were not removed. The skill installation is shared.")
            if not args.global_cleanup:
                print("Global setup was retained; use --global to remove it explicitly.")
            print("Run uninstall with Copilot closed to avoid permission-file write conflicts.")
        else:
            destination = install(Path(__file__).resolve().parent, directory, args.update)
            print(f"Installed: {destination}")
            print("In Copilot CLI: /skills reload, then /skills info remind-me-again")
            print("Automation settings were not changed; new installations default to off.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Cannot install/uninstall skill: {error}\n")


if __name__ == "__main__":
    main()
