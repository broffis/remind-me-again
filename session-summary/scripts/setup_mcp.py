"""Explicit one-command setup for project-scoped MCP autosave."""

import argparse
from pathlib import Path
import subprocess
import sys

from autosave import (
    EVENTS, copilot_home, hook_configuration, read_json, regular_path, repository,
    settings, write_json,
)
from storage import project_directory


SERVER = "session-summary"
APPROVAL = {"kind": "mcp", "serverName": SERVER, "toolName": "save_checkpoint"}
CONTEXT_APPROVAL = {
    "kind": "mcp", "serverName": SERVER, "toolName": "get_checkpoint_context"
}


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
        "tools": ["get_checkpoint_context", "save_checkpoint"],
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
        previous = dict(server, tools=["save_checkpoint"])
        if servers[SERVER] != previous:
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
        if CONTEXT_APPROVAL not in approvals:
            approvals.append(dict(CONTEXT_APPROVAL))
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


def plan_removal(cwd, installation, global_cleanup=False):
    """Validate all targeted configuration before removing any of it."""
    cwd = Path(cwd).expanduser().resolve(strict=True)
    installation = Path(installation).resolve()
    root = repository(cwd)
    changes = []

    def remove_server(path, project):
        config = existing_object(path)
        servers = config.get("mcpServers", config)
        if not isinstance(servers, dict):
            raise ValueError(f"Expected an MCP server map: {path}")
        if SERVER not in servers:
            return
        server = servers[SERVER]
        script = str(installation / "scripts/checkpoint_mcp.py")
        if not isinstance(server, dict):
            raise ValueError(f"Cannot identify owned MCP server: {path}")
        args = server.get("args", [])
        if (
            server.get("type") not in ("local", "stdio")
            or not isinstance(args, list) or len(args) != 4
            or args[:3] != ["-B", script, "--cwd"]
            or not isinstance(args[3], str)
            or not isinstance(server.get("command"), str)
            or server.get("tools") not in (
                ["save_checkpoint"], ["get_checkpoint_context", "save_checkpoint"]
            )
            or set(server) - {"type", "command", "args", "env", "tools"}
        ):
            raise ValueError(f"Refusing to remove an unrecognized MCP server: {path}")
        if project is not None and repository(Path(args[3])) != project:
            raise ValueError(f"MCP server is bound to another project: {path}")
        del servers[SERVER]
        if "mcpServers" in config and not servers:
            del config["mcpServers"]
        changes.append((path, config or None))

    def remove_hooks(path):
        regular_path(path)
        if not path.exists():
            return
        config = read_json(path)
        hooks = config.get("hooks")
        if config.get("version") != 1 or not isinstance(hooks, dict):
            raise ValueError(f"Refusing to remove an unrecognized hook: {path}")
        script = str(installation / "scripts/autosave.py")
        changed = False
        for event in EVENTS:
            entries = hooks.get(event, [])
            if not isinstance(entries, list):
                raise ValueError(f"Invalid hook entries: {path}")
            remaining = []
            for entry in entries:
                if (
                    isinstance(entry, dict)
                    and entry.get("args") == [script, "hook", event]
                    and entry.get("type") == "command"
                    and isinstance(entry.get("exec"), str)
                    and entry.get("timeoutSec") == 10
                    and not set(entry) - {"type", "exec", "args", "timeoutSec"}
                ):
                    changed = True
                else:
                    remaining.append(entry)
            if entries and not remaining:
                del hooks[event]
            elif remaining:
                hooks[event] = remaining
        if not changed:
            raise ValueError(f"Refusing to remove an unrecognized hook: {path}")
        if not hooks:
            del config["hooks"]
        changes.append((path, None if config == {"version": 1} else config))

    def remove_settings(path):
        regular_path(path)
        if not path.exists():
            return
        config = settings(path)
        original = dict(config)
        for name in ("autosave", "autoread", "checkpoint_transport"):
            config.pop(name, None)
        if config != original:
            changes.append((path, None if config == {"version": 1} else config))

    if root is not None:
        remove_server(root / ".mcp.json", root)
        remove_server(root / ".github/mcp.json", root)
        remove_hooks(root / ".github/hooks/session-info.json")
        remove_settings(root / ".github/session-info.json")
        permissions_path = copilot_home() / "permissions-config.json"
        if not permissions_path.exists() and permissions_path.with_suffix("").exists():
            raise ValueError("Legacy permissions-config exists; migrate it in Copilot first.")
        permissions = existing_object(permissions_path)
        locations = permissions.get("locations", {})
        if not isinstance(locations, dict):
            raise ValueError("Permission locations must be an object.")
        location = locations.get(permission_location(cwd), {})
        if not isinstance(location, dict):
            raise ValueError("Saved permission location must be an object.")
        approvals = location.get("tool_approvals", [])
        if not isinstance(approvals, list) or any(
            not isinstance(approval, dict) for approval in approvals
        ):
            raise ValueError("Saved tool approvals must be an array of objects.")
        remaining = [
            approval for approval in approvals
            if approval not in (APPROVAL, CONTEXT_APPROVAL)
        ]
        if remaining != approvals:
            location["tool_approvals"] = remaining
            changes.append((permissions_path, permissions))
    if global_cleanup:
        remove_server(copilot_home() / "mcp-config.json", None)
        remove_hooks(copilot_home() / "hooks/session-info.json")
        remove_settings(copilot_home() / "session-info-settings.json")
    return changes


def remove_setup(changes):
    completed = []
    try:
        for path, value in changes:
            if value is None:
                regular_path(path).unlink()
            else:
                write_json(path, value)
            completed.append(str(path))
    except (OSError, ValueError) as error:
        raise OSError(
            f"Cleanup incomplete: {error}. Already updated: "
            f"{', '.join(completed) or 'none'}. Rerun uninstall after correcting the error."
        ) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument(
        "--approve", action="store_true",
        help="Explicitly persist this repository's checkpoint lookup/save approvals. "
             "Close Copilot sessions first; no shell or Python approval is granted.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing.")
    args = parser.parse_args()
    try:
        paths = setup(args.cwd, args.approve, args.dry_run)
        print(("Would update" if args.dry_run else "Updated") + ":\n" + "\n".join(paths))
        if args.approve:
            print("Approval scope: this repository's session-summary checkpoint lookup/save only.")
        else:
            print("No tool approval granted. Approve save_checkpoint in Copilot when prompted.")
        print("Restart Copilot from the configured working directory to load the setup.")
        print("Keep .mcp.json and .github/session-info.json local: they contain personal paths/settings.")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Cannot set up MCP autosave: {error}\n")


if __name__ == "__main__":
    main()
