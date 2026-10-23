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
| `Use the /remind-me-again skill: configure --feature autoread --scope repo --mode on` | Enable autoread for the current repository. |

For `configure`, choose `--feature autosave|autoread`, `--scope repo|global`,
and `--mode on|off|inherit`. Each feature defaults to off.

These are skill invocation prompts, not built-in slash commands. Saving and
review synthesis need the agent; the Python helpers only handle files.

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
