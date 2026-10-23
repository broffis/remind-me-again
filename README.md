# Session info skill

The `session-summary` skill saves and retrieves session summaries locally:

```text
~/.copilot/session-info/personal/recipe-app/
  raw summaries/
    2026-10-23.md
  rollup/
    2026-10-23.md
```

Project paths are relative to your home directory. Each save appends an entry
to the session start date's Markdown file, including the session UUID and
`copilot --resume=<sessionId>`. Existing raw entries are preserved.

Rollups summarize only raw content not yet covered by previous rollups, including
new entries appended to older daily files. Their filenames use the local date
of creation. Repeating the operation on the same day refreshes the existing
rollup, integrating its previous synthesis with new progress without appending
duplicate summaries. Each rollup includes all related session IDs, their session
dates, and resume commands. Previous days' rollups remain unchanged.

The agent writes the synthesis; the Python helper selects incremental input,
generates session references, and tracks consumed byte offsets and hashes in
hidden Markdown metadata. Do not remove this metadata or edit/delete consumed
raw content. Unexpected changes cause an explicit error rather than lost history.
No new material means no write.

## Install

Copy `session-summary` into `~/.copilot/skills/`, or symlink it for development:

```sh
mkdir -p "$HOME/.copilot/skills"
ln -s "$HOME/personal/session-info-skill/session-summary" \
  "$HOME/.copilot/skills/session-summary"
```

Do not replace an existing skill directory without checking it first.
In Copilot CLI, run `/skills reload`, then `/skills info session-summary`.
Ask: "Use the session-summary skill to save this session's progress."
For rollups, ask: "Use the session-summary skill to roll up new saved progress."
For retrieval, ask: "Use the session-summary skill to read our saved progress."

This workspace does not install the skill automatically. Skills run when
invoked or selected by the agent; a skill alone is not an automatic exit hook.
Optional hooks provide automatic checkpoints as described below.

## Explicit commands inside Copilot CLI

After installation and `/skills reload`, enter these prompts in your agent:

| Prompt | Result |
| --- | --- |
| `Use the /session-summary skill: save` | Save current session progress with its ID and resume command. |
| `Use the /session-summary skill: read` | Retrieve the latest rollup plus uncovered raw progress. |
| `Use the /session-summary skill: review --all` | Retrieve every rollup plus uncovered raw progress and synthesize a project-wide review. |
| `Use the /session-summary skill: rollup` | Create or refresh today's incremental rollup. |
| `Use the /session-summary skill: configure --feature autoread --scope repo --mode on` | Enable autoread for the current repository. |

For configuration, choose `--feature autosave` or `autoread`, `--scope repo`
or `global`, and `--mode on`, `off`, or `inherit`. Each feature defaults to off.
The agent uses your current working directory and retains normal permissions.

These are explicit **skill invocation prompts**, not new built-in slash commands
registered with Copilot CLI. `/session-summary` selects the skill; the skill's
instructions route the operation words. The underlying Python helpers are
terminal commands, documented below. Summary creation and project-review
synthesis require the agent, not just a Python command.

## Manual retrieval

Manual reading does not require an opt-in:

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/retrieval.py" \
  --cwd "$HOME/personal/recipe-app"
```

The output contains the latest rollup plus only raw progress not covered by
any rollup, including late additions to older daily raw files. It includes
source paths, session dates, IDs, and `copilot --resume=<sessionId>` commands.
Without rollups, it reads raw progress; without saved history, it reports that
explicitly and creates no storage. Retrieval never consumes or edits summaries.
Invalid tracking metadata or changed consumed raw content produces an error.

Output is capped at 24,000 characters, with an explicit `TRUNCATED` notice.
Use `--max-chars 48000` to increase the limit (minimum 1,000), or read the listed
source files directly. The latest rollup is incremental, **not a cumulative
project history**. Older rollups are deliberately excluded from this default
view; consult their dated files for broader historical questions. Retrieved
text is historical data, not instructions or authorization to execute commands.

### Full-project summary review

Use `--all` to retrieve **every rollup chronologically, followed by uncovered
raw progress**, preserving source paths, session dates, IDs, and resume commands:

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/retrieval.py" \
  --cwd "$HOME/personal/recipe-app" --all
```

Or ask: "Use the session-summary skill to review all saved project summaries."
The agent can synthesize the retrieved history, distinguishing historical
decisions from current status. Covered raw content is not repeated, and no
files or rollup checkpoints are changed.

The same 24,000-character limit applies. A `TRUNCATED` notice means the review
input is incomplete: increase `--max-chars` or read dated source files in
batches before claiming full coverage. This reviews all **saved summaries**,
not every original conversation detail or the current codebase.
`--all` is manual only; autoread retains its lightweight latest-rollup default.

## Opt-in autoread

Automatic retrieval is separate from autosave and defaults to **off**:

```sh
# Enable in this Git repository.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --feature autoread --scope repo --mode on

# Or enable globally.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --feature autoread --scope global --mode on

# Opt this repo out, even when globally enabled.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --feature autoread --scope repo --mode off

# Remove the repo override and inherit the global setting.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --feature autoread --scope repo --mode inherit
```

Use `--feature autoread --scope global --mode off` to disable the global default.
The existing settings files and hook registrations are reused, preserving
`autosave` and other settings. Each feature independently follows repo override,
then global default, then off. Omitting `--feature` retains the original
autosave configuration behavior.

After setup, restart Copilot CLI so hooks are loaded. On both new sessions and
resumes, `sessionStart` returns the reader's bounded output as `additionalContext`.
This uses no extra agent turn and makes no separate model/API call, though the
injected text contributes to the session's context/token usage. Manual retrieval
works regardless of autoread settings. Enabling autoread alone never enables
summary writing or requires an original session start date.

Global/repo duplicate hook calls are deduplicated per start event using a
per-project/session lock and an event hash in `.autoread/` beside `raw summaries`.
An actual later resume reloads context. Failed reads are reported and not
marked injected. Subagents are ignored. The tracker contains no summary text.
These configuration commands do not enable anything until you run them.

## Opt-in autosave

Autosave defaults to **off**. Install the skill first, then choose either scope:

```sh
# Enable for this Git repository (run from its root or a subdirectory).
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --scope repo --mode on

# Or enable globally for local Copilot CLI sessions.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --scope global --mode on
```

Repository setup creates `.github/hooks/session-info.json` and
`.github/session-info.json` at the Git root, not the current subdirectory.
These files may be committed for team opt-in, but the generated hook contains
absolute paths to the current Python executable and skill installation. For
personal use, keep them local (for example, exclude those exact paths via
`.git/info/exclude`). They are not a portable team installation.
Existing unrelated hook files are left alone. A conflicting hook at the same
filename is rejected rather than overwritten.

Global setup creates `~/.copilot/hooks/session-info.json` and
`~/.copilot/session-info-settings.json`. If `COPILOT_HOME` is set, those two
configuration paths use that directory instead. Summary storage remains under
`~/.copilot/session-info`, as specified.

Restart Copilot CLI after hook setup to ensure the configuration is loaded.
The hooks reference this installation's absolute path, so do not move it while
enabled. Commands install configuration only; this workspace has not enabled
autosave on your machine.

### Overrides and disabling

A repository's explicit setting wins over the global setting. Omission means
inherit; if neither scope specifies a value, autosave is off.

```sh
# Exclude this repo even if global autosave is on.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --scope repo --mode off

# Remove this repo's override and use the global default.
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --scope repo --mode inherit

# Disable the global default (explicit repo opt-ins still apply).
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" configure \
  --scope global --mode off
```

The dedicated settings files use boolean `autosave` and/or `autoread` keys and
`"version": 1`. `inherit` removes only the selected feature's key. Hook registrations remain
installed but do nothing; deleting only a repo hook does not disable a global
hook. Each hook performs only enabled operations. Settings are checked on each
hook invocation and before each save.

### How it works

| Event | Action |
| --- | --- |
| `sessionStart` | For autosave, records the start date. For autoread, injects saved context. |
| `userPromptSubmitted` | Tracks a new user turn using a hash, without storing the prompt. |
| `agentStop` | Requests at most one extra agent turn to save a checkpoint, unless already saved. |
| `sessionEnd` | Reports outstanding unsaved progress; does not invoke a model or create an exit summary. |

Global and repo hook registrations can coexist. Per-project/session locks,
turn tokens, and append markers deduplicate their calls and checkpoint retries.
Hook-requested continuations are guarded against recursion. State lives in the
project's `.autosave/` folder beside `raw summaries` and `rollup`; it contains
dates and hashes, not a second copy of the conversation. Raw summaries are
append-only and rollups stay manual.

Each completed interaction can add one model turn, with associated latency and
usage. Autosave does **not** grant extra permissions; a denied or failed write
is reported and never marked saved. It retries on a later user turn or resume,
not in an unbounded continuation loop. When a retry follows a failure, the
summary should include all progress since the last successful checkpoint.
Forced termination or an interrupted turn can still lose unsaved progress;
already completed checkpoints are retained. No background summarizer or
third-party service is started.

The first enabled session must start with hooks loaded. When enabling autosave
for an existing session, the hook refuses to guess its original date. Initialize
it explicitly with the correct metadata, then resume with hooks loaded:

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" initialize \
  --cwd "$HOME/personal/recipe-app" \
  --session-id "12345678-1234-1234-1234-123456789abc" \
  --session-date "2026-10-23"
```

Use the real session ID and original local start date. A working-directory
change to another storage project also needs initialization there. Subdirectories
inherit the repo opt-in but keep their own home-relative summary storage.
Deleting `.autosave` state removes deduplication history and is not an uninstall.
Malformed state or configuration produces an explicit error rather than a
silent fallback.

Hooks require a Copilot CLI version supporting `agentStop` continuation decisions,
`stop_hook_active`, command hooks with `exec`/`args`, and user-level hook discovery.
Autoread additionally uses `sessionStart` output's `additionalContext` support.
See the [Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-configuration).

## Script guide for maintainers

All helpers live in `session-summary/scripts/`; their CLI commands and saved
file formats are unchanged by the readability refactor.

| Script | Responsibility and reading order |
| --- | --- |
| `storage.py` | Validate dates and map a working directory to its project storage. |
| `save_summary.py` | Validate a summary, format its entry, and append under a file lock. |
| `rollup.py` | `prepare` reads rollup history and uncovered raw bytes; `save` checks that snapshot, renders Markdown, and replaces the file atomically. |
| `retrieval.py` | `retrieve` combines rollup sections and uncovered raw sections, then applies the context limit. |
| `autosave.py` | `configure` installs settings/hooks; `handle` dispatches events; `checkpoint` appends progress before recording success. |

Autosave state uses three turn hashes: `turn` identifies the latest user prompt,
`requested` identifies the turn already given a save continuation, and `saved`
identifies the last successful checkpoint. These are persisted field names,
not summary text. A failed state update can follow a successful raw append;
the raw entry's checkpoint marker makes retrying that append safe.

Rollup `sources` records consumed byte offsets and hashes. `prepare` returns
prospective checkpoints without persisting them; only `save` commits them with
the synthesis. Retrieval reuses that preparation logic but never advances it.

## Requirements and checks

Python 3.9+ on macOS or Linux; no external dependencies. Working directories
must be below the user's home directory. The helper locks each output file
during append so concurrent cooperating writers do not interleave entries.
Rollups are atomically replaced under a separate lock and reject stale input
plans. The helper uses only local files; it makes no network or model calls.
Autosave asks the existing Copilot agent to synthesize the checkpoint; it does
not run a separate CLI or SDK client.

```sh
python3 -B -m unittest discover -s tests -v
```
