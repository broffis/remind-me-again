# Autoread and autosave

Back to the [README](../README.md). Both features are **off by default** and
enabled only by the commands below. For the optional narrower-permission
transport, see [mcp-setup.md](mcp-setup.md).

All commands use the installed helper:

```sh
AUTOSAVE="$HOME/.copilot/skills/remind-me-again/scripts/autosave.py"
```

## Settings and precedence

For a guided change inside Copilot, use
`Use the /remind-me-again skill: configure`. It shows current settings and asks
for any missing feature, scope, and mode; cancellation makes no changes.
Fully specified prompts still work directly. This is a skill conversation,
not a new npm CLI command.

Inspect settings without changing anything:

```sh
python3 "$AUTOSAVE" status --cwd "$PWD"
```

The JSON output includes configured global/repo modes, effective values and
their sources. Outside Git, repo settings are unavailable (`null`), but global
settings can still be inspected and configured. Invalid configuration reports
an error instead of being treated as disabled.

- Each feature (`autosave`, `autoread`) is configured independently.
- A repo's explicit setting wins over the global one; with neither, the feature is off.
- `inherit` removes only that feature's key from the settings file.
- Omitting `--feature` configures autosave (the original behavior).
- Settings files hold boolean `autosave`/`autoread` keys and `"version": 1`,
  and are checked on every hook call and before every save.
- Hook registrations stay installed when a feature is off; they just do nothing.
  Deleting only a repo hook does not disable a global hook.

| Goal | Command |
| --- | --- |
| Enable for this repo | `python3 "$AUTOSAVE" configure --feature <autosave\|autoread> --scope repo --mode on` |
| Enable globally | `... --scope global --mode on` |
| Opt this repo out | `... --scope repo --mode off` |
| Use the global default | `... --scope repo --mode inherit` |
| Disable the global default | `... --scope global --mode off` |

Explicit repo opt-ins still apply when the global default is off. Restart
Copilot CLI after setup so hooks load.

## Autoread

On new sessions and resumes, `sessionStart` injects the reader's bounded output
as `additionalContext`. It uses no extra agent turn or model call, though the
text counts toward context usage.

- Manual retrieval works regardless of this setting.
- Autoread alone never enables writing or needs a session start date.
- Duplicate global/repo hook calls are deduplicated per start event with a
  lock and event hash in `.autoread/` beside `raw summaries` (no summary text).
- A real later resume reloads context. Failed reads are reported, not marked injected. Subagents are ignored.

### Saved-content safety

The Python reader reads summaries as text; it does not evaluate Python, invoke
a shell, or execute embedded scripts. Retrieved history is quoted and labeled
as untrusted data, including text that imitates system messages, tool calls,
autosave requests, or approvals. The skill instructs the agent not to act on
such text without authorization from the current user.

These are prompt-injection defenses, not an execution sandbox or a guarantee
that a model cannot be misled. Normal tool permissions remain the execution
boundary; avoid broad shell approvals when reading untrusted content. For
projects whose saved history you do not trust, keep autoread off and review
the files outside the agent before requesting retrieval.

## Autosave

```sh
python3 "$AUTOSAVE" configure --scope repo --mode on     # or --scope global
```

**Repo setup** writes `.github/hooks/session-info.json` and
`.github/session-info.json` at the Git root. The hook contains absolute paths
to your Python and skill install, so keep these files local (for example via
`.git/info/exclude`) rather than committing them for a team. Unrelated hook
files are left alone; a conflicting hook at the same filename is rejected.

**Global setup** writes `~/.copilot/hooks/session-info.json` and
`~/.copilot/session-info-settings.json` (under `COPILOT_HOME` if set). Summaries
always stay under `~/.copilot/session-info`.

Do not move the skill installation while hooks reference it.

### Enabling for an existing session

The hook will not guess a session's original date. Initialize it explicitly,
then resume with hooks loaded:

```sh
python3 "$AUTOSAVE" initialize \
  --cwd "$HOME/personal/recipe-app" \
  --session-id "12345678-1234-1234-1234-123456789abc" \
  --session-date "2026-10-23"
```

Use the real ID and original local start date. A working-directory change to
another storage project needs its own initialization; subdirectories inherit
the repo opt-in but keep separate storage.

## How it works

| Event | Action |
| --- | --- |
| `sessionStart` | Autosave records the start date; autoread injects saved context. |
| `userPromptSubmitted` | Tracks a new user turn by hash (prompt not stored); ignores the exact pending checkpoint continuation. |
| `agentStop` | Requests at most one extra agent turn to save a checkpoint, unless already saved. |
| `sessionEnd` | Reports outstanding unsaved progress; no model call or exit summary. |

- Global and repo hooks can coexist. Locks, turn tokens, and checkpoint markers
  deduplicate calls and retries; continuations are guarded against recursion.
- State lives in `.autosave/` beside `raw summaries` and `rollup`. It holds
  dates and hashes, not conversation text. Each checkpoint replaces the
  session's raw block with a cumulative summary; rollups stay manual.
- Some CLI versions route the checkpoint request through `userPromptSubmitted`.
  An exact match to the pending request keeps its token; modified requests and
  genuine new turns invalidate older tokens, and saves always check for staleness.
- MCP requests include the exact session ID from the hook event so saving does
  not depend on the agent having runtime session metadata. See
  [MCP checkpoint behavior](mcp-setup.md#how-mcp-checkpoints-behave) for fallback
  and mismatch handling.
- After a successful save the agent says "Remind-me-again autosave executed."
  Failures are reported instead.

Costs and limits:

- Each completed interaction can add one model turn, with latency and usage.
- Autosave grants no extra permissions. A denied or failed write is reported
  and never marked saved; it retries on a later turn or resume with a cumulative
  summary of the whole session so far.
- Forced termination or an interrupted turn can lose unsaved progress. No
  background summarizer or third-party service runs.
- Deleting `.autosave` state removes deduplication history; it is not an uninstall.
- Malformed state or configuration raises an explicit error.

Requires a Copilot CLI supporting `agentStop` continuation decisions,
`stop_hook_active`, command hooks with `exec`/`args`, and user-level hook
discovery; autoread also needs `additionalContext` from `sessionStart`. See the
[hooks reference](https://docs.github.com/en/copilot/reference/hooks-configuration).
