"""Explicit one-command setup for project-scoped MCP autosave."""

import argparse
from pathlib import Path
import subprocess
import sys

from autosave import (
    copilot_home, hook_configuration, read_json, regular_path, repository,
    settings, write_json,
)
from storage import project_directory


SERVER = "session-summary"
APPROVAL = {"kind": "mcp", "serverName": SERVER, "toolName": "save_checkpoint"}


def permission_location(cwd):
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--git-common-dir"],
        text=True, capture_output=True, check=True,
    )
    common = (cwd / result.stdout.strip()).resolve(strict=True)
    if common.name != ".git":
        raise ValueError(
            "Cannot safely determine permission scope for a separate Git directory. "
            "Use Copilot's interactive approval instead."
        )
    return str(common.parent)


def existing_object(path):
    regular_path(path)
    return read_json(path) if path.exists() else {}


def plan_setup(cwd, approve=False):
    cwd = Path(cwd).expanduser().resolve(strict=True)
    project_directory(cwd)
    root = repository(cwd)
    if root is None:
        raise ValueError("MCP setup requires a Git repository.")
    script = Path(__file__).resolve().parent / "checkpoint_mcp.py"
    if not script.is_file():
        raise ValueError("Install or update the skill before setting up MCP.")
    server = {
        "type": "stdio", "command": sys.executable,
        "args": ["-B", str(script), "--cwd", str(cwd)],
        "tools": ["save_checkpoint"],
        "env": {"COPILOT_HOME": str(copilot_home().resolve())},
    }
    mcp_path = root / ".mcp.json"
    mcp = existing_object(mcp_path)
    if not mcp:
        mcp = {"mcpServers": {}}
    servers = mcp.get("mcpServers", mcp)
    if not isinstance(servers, dict):
        raise ValueError(f"Expected an MCP server map: {mcp_path}")
    if SERVER in servers and servers[SERVER] != server:
        raise ValueError(f"Refusing to replace an existing {SERVER} server: {mcp_path}")
    servers[SERVER] = server

    hook_path = root / ".github/hooks/session-info.json"
    hooks = hook_configuration()
    if hook_path.exists() and existing_object(hook_path) != hooks:
        raise ValueError(f"Refusing to overwrite an existing hook: {hook_path}")
    regular_path(hook_path)
    config_path = root / ".github/session-info.json"
    config = settings(config_path)
    config.update(autosave=True, checkpoint_transport="mcp")
    writes = [(mcp_path, mcp), (hook_path, hooks), (config_path, config)]

    if approve:
        permissions_path = copilot_home() / "permissions-config.json"
        legacy = permissions_path.with_suffix("")
        if not permissions_path.exists() and legacy.exists():
            raise ValueError(
                "Legacy permissions-config exists. Let Copilot migrate it before "
                "using --approve, or approve the MCP tool interactively."
            )
        permissions = existing_object(permissions_path)
        locations = permissions.setdefault("locations", {})
        if not isinstance(locations, dict):
            raise ValueError("Permission locations must be an object.")
        location = locations.setdefault(permission_location(cwd), {})
        if not isinstance(location, dict):
            raise ValueError("Saved permission location must be an object.")
        approvals = location.setdefault("tool_approvals", [])
        if not isinstance(approvals, list) or any(
            not isinstance(approval, dict) for approval in approvals
        ):
            raise ValueError("Saved tool approvals must be an array of objects.")
        if APPROVAL not in approvals:
            approvals.append(dict(APPROVAL))
        writes.append((permissions_path, permissions))
    return writes


def setup(cwd, approve=False, dry_run=False):
    writes = plan_setup(cwd, approve)
    if not dry_run:
        completed = []
        try:
            for path, value in writes:
                write_json(path, value)
                completed.append(str(path))
        except (OSError, ValueError) as error:
            raise OSError(
                f"Setup incomplete: {error}. Files already written: "
                f"{', '.join(completed) or 'none'}. Correct the error and rerun setup."
            ) from error
    return [str(path) for path, _ in writes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--approve", action="store_true",
        help="Explicitly persist this repository's save_checkpoint approval. "
             "Close Copilot sessions first; no shell or Python approval is granted.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing.")
    args = parser.parse_args()
    try:
        paths = setup(args.cwd, args.approve, args.dry_run)
        print(("Would update" if args.dry_run else "Updated") + ":\n" + "\n".join(paths))
        if args.approve:
            print("Approval scope: this repository's session-summary/save_checkpoint only.")
        else:
            print("No tool approval granted. Approve save_checkpoint in Copilot when prompted.")
        print("Restart Copilot from the configured working directory to load the setup.")
        print("Keep .mcp.json and .github/session-info.json local: they contain personal paths/settings.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Cannot set up MCP autosave: {error}\n")


if __name__ == "__main__":
    main()
