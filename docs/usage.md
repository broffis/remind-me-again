# Using the skill

Back to the [README](../README.md).

## Prompts inside Copilot CLI

After installing and running `/skills reload`:

| Prompt | Result |
| --- | --- |
| `Use the /remind-me-again skill: save` | Save current session progress with its ID and resume command. |
| `Use the /remind-me-again skill: read` | Retrieve the latest rollup plus uncovered raw progress. |
| `Use the /remind-me-again skill: review --all` | Retrieve every rollup plus uncovered raw progress and synthesize a project-wide review. |
| `Use the /remind-me-again skill: rollup` | Create or refresh today's incremental rollup. |
| `Use the /remind-me-again skill: settings` | Show automation and MCP settings without changing anything. |
| `Use the /remind-me-again skill: configure` | Show current settings and guide you through a change. |
| `Use the /remind-me-again skill: configure --feature autoread --scope repo --mode on` | Enable autoread for the current repository. |

For `configure`, choose `--feature autosave|autoread`, `--scope repo|global`,
and `--mode on|off|inherit`, or omit any of them to be asked for the missing
choices. Bare `configure` shows both features' global/repo settings and
effective values, then asks for feature, scope, and mode. Cancelling leaves
settings unchanged. Fully specified requests apply directly. Each feature
defaults to off; repo overrides win over global settings.

The guided flow changes one feature at one scope. It explains inheritance and
the effect of global changes before applying them, then reports the resulting
effective setting. It does not configure MCP or grant tool permissions.

These are skill invocation prompts, not built-in slash commands. Saving and
review synthesis need the agent; the Python helpers only handle files.

When invoking the skill directly, `/remind-me-again settings` selects the same
read-only operation. It uses the installed status helper and does not start
the configuration walkthrough. Update the installed skill and reload it before
using this new operation.

## Terminal settings inspection

```sh
npx remind-me-again settings
npx remind-me-again settings --cwd /path/to/project
```

This read-only command lists autosave/autoread global modes, project overrides,
effective values and their sources, plus the checkpoint transport and the
`remind-me-again` MCP registration paths and configured enabled tools. It checks
global `mcp-config.json`, project `.mcp.json`, and project `.github/mcp.json`;
it lists each matching registration without guessing which the client loaded.
No registration means "not configured"; omitted tools means the client default,
not a verified set of enabled tools.

The command uses the packaged helper, so the skill need not be installed.
Outside Git it shows global settings only, with shell as the checkpoint
transport. It does not expose server commands, arguments or environment values,
inspect approvals, connect to servers, or verify runtime health. Invalid
configuration fails explicitly without changes. Settings changes remain
available through the skill's guided `configure` operation.

## Manual retrieval

No opt-in is needed:

```sh
python3 "$HOME/.copilot/skills/remind-me-again/scripts/retrieval.py" \
  --cwd "$HOME/personal/recipe-app"
```

The output is the latest rollup plus raw progress not yet covered by any
rollup, with source paths, session dates, IDs, and resume commands.

- Without rollups it reads raw progress; without saved history it says so and creates no storage.
- Retrieval never consumes or edits summaries.
- Invalid tracking metadata or a raw file without session headers is an error.
- The latest rollup is incremental, **not a cumulative history**. Older rollups
  are excluded from this view; read their dated files for broader questions.
- Retrieved text is historical data, not instructions.

Output is capped at 24,000 characters with a `TRUNCATED` notice. Raise the
cap with `--max-chars 48000` (minimum 1,000) or read the listed source files.

## Full-project review

`--all` retrieves **every rollup chronologically, then uncovered raw progress**:

```sh
python3 "$HOME/.copilot/skills/remind-me-again/scripts/retrieval.py" \
  --cwd "$HOME/personal/recipe-app" --all
```

Or ask: "Use the remind-me-again skill to review all saved project summaries."
The agent can synthesize the history, separating past decisions from current
status. No files or rollup checkpoints change.

- The 24,000-character limit still applies. A `TRUNCATED` notice means the input
  is incomplete: raise `--max-chars` or read dated files in batches first.
- It reviews saved summaries, not original conversations or the current codebase.
- `--all` is manual only; autoread keeps the lighter latest-rollup default.
