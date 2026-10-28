# Project-bound MCP writer

Back to the [README](../README.md). This is an optional part of
[autosave](automation.md). Shell checkpoint commands remain the default.

`scripts/checkpoint_mcp.py` is a local stdio MCP server (no dependencies, no
network listener) with three tools:

- `get_checkpoint_context(session_id)`: read-only lookup of that session's pending checkpoint.
- `save_checkpoint(session_id, token, summary)`: reuses the normal checkpoint writer.
- `get_settings()`: reads automation and MCP configuration without running shell
  commands or changing files; works even with autosave disabled and no session state.

It accepts no commands, working-directory overrides, or output paths, and can
only write for its configured directory, subject to autosave opt-in and current
tokens. It cannot enable automation, register itself, or grant approvals.

## One-command setup

Close Copilot for this project, then run from the directory you'll use it in:

```sh
python3 "$HOME/.copilot/skills/remind-me-again/scripts/setup_mcp.py" --approve
# or, with the npm package
remind-me-again setup-mcp --approve
```

Setup registers the writer in `.mcp.json`, installs repo hooks, enables repo
autosave, and selects MCP transport. It preserves unrelated configuration,
rejects conflicting definitions, and is safe to rerun.

- `--cwd /path/to/project` selects another directory.
- `--skills-dir /path/to/skills` (npm command) supports custom installs.
- `--dry-run` previews changes without writing.
- Keep `.mcp.json`, `.github/hooks/session-info.json`, and
  `.github/session-info.json` local; they contain personal paths.

**`--approve` is a separate permission grant.** It saves only approvals for
`remind-me-again/get_checkpoint_context`, `remind-me-again/save_checkpoint`,
and `remind-me-again/get_settings`
for this repository in Copilot's `permissions-config.json`, keeping all other
approvals and directory grants. It never approves Python, shell commands, all
MCP tools, or general filesystem access. Linked worktrees use the main
repository's scope.

- Omit it to leave approval to Copilot's prompts.
- Close Copilot first; it manages this file and edits during a session can be lost.
- Legacy permission files must be migrated by Copilot first.
- Older CLIs without saved MCP approvals may still prompt; setup never weakens permissions.
- CLI deny rules and organization policies stay authoritative.

Afterward start Copilot normally; no `--allow-tool` flag is needed. The writer
stays bound to the exact setup directory, including subdirectories.

To revoke, use Copilot's permission controls, or with Copilot closed remove only
the matching approvals from this repo's entry. Uninstall also removes them
(see [installation.md](installation.md#uninstall)).

## Manual setup

1. In Copilot, run `/mcp add` with name **remind-me-again**, type **STDIO**, and command:

   ```sh
   python3 -B /absolute/path/to/.copilot/skills/remind-me-again/scripts/checkpoint_mcp.py --cwd /absolute/path/to/project
   ```

2. Enable only `get_checkpoint_context`, `save_checkpoint`, and `get_settings`.
3. Use the exact working directory of your Copilot session, including any
   subdirectory (storage is mapped by working directory, not Git root). The
   server serves only that directory; don't reuse it for other projects.
4. If you use `COPILOT_HOME`, pass it in the server's environment so the writer
   reads the same global settings as your hooks.
5. Approve through the CLI's controls, or start with:

   ```sh
   copilot --allow-tool='remind-me-again(get_checkpoint_context)' \
     --allow-tool='remind-me-again(save_checkpoint)' \
     --allow-tool='remind-me-again(get_settings)'
   ```

   This allows checkpoint operations and settings reads only, not arbitrary Python or
   shell. Approve only servers you trust.
6. Select MCP transport (this does not enable autosave):

   ```sh
   python3 "$HOME/.copilot/skills/remind-me-again/scripts/autosave.py" \
     configure-transport --cwd "$PWD" --mode mcp
   ```

To restore the default, use `--mode shell`. The choice is stored per repo as
`checkpoint_transport` in `.github/session-info.json` (missing means `shell`).

## How MCP checkpoints behave

- The hook message says "Remind-me-again autosave requested" followed by
  `session_id: <UUID>`, using the exact ID from the hook event.
- The agent uses that ID to look up the pending checkpoint, composes the summary,
  then saves with the returned token. Runtime session metadata is a fallback
  only when the hook omits the ID. A malformed hook ID, conflicting IDs, or no
  ID from either source stops the save with an explicit error. No session is
  chosen by recency or scanning.
- A new user turn invalidates the token; the agent must not refresh it to retry
  an outdated summary.
- Session IDs appear in the hook message and tool details; tokens appear only
  in tool details. Neither is a secret or authentication.
- If a tool is unavailable, denied, or fails, the agent reports it without
  falling back to shell or changing permissions.
- Existing two-tool registrations can add settings by updating the installed
  skill, then rerunning setup with Copilot closed if using `--approve`.
  Setup adds `get_settings` only when the previous registration otherwise matches
  exactly; conflicting registrations are rejected. Reload the server and skill
  afterward. `/remind-me-again settings` prefers the MCP tool when available,
  avoiding shell prompts once its narrow approval is saved. CLI deny rules and
  organization policies can still require approval or block the call.

Installing or updating never registers the server, selects MCP mode, or
pre-approves tools. Uninstall cleans recognized project registration; global
registration needs `--global`; custom definitions need manual cleanup.
