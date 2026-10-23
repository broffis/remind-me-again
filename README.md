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

Requires **Python 3.9+ on macOS or Linux**, and Copilot CLI.
No pip packages are needed. Windows is not currently supported.

1. Download the ZIP from [GitHub Releases](https://github.com/broffis/session-summary-skill/releases)
   and unzip it. Releases will appear there once published.
2. Open a terminal in the extracted `session-summary-skill` folder and run:

   ```sh
   python3 install.py
   ```

3. In Copilot CLI, run `/skills reload`, then `/skills info session-summary`.

This copies the skill and all Python helpers into `~/.copilot/skills/session-summary`.
You can delete the downloaded/extracted files afterward. Autosave and autoread
remain off unless previously enabled; installation never changes those settings.
Do not use `copilot skill add <SKILL.md URL>` for this skill: that command installs
only the Markdown file and would omit the required Python helpers.

Until the first release is published, download the repository's source ZIP
from [GitHub](https://github.com/broffis/session-summary-skill) (Code > Download ZIP),
or clone it, and run the same `python3 install.py` command in the repository root.

### Alternative: install with npm/npx

The npm package is prepared but **not published yet**. Once published, users
with Node.js 18+ and npm can install without manually downloading a ZIP:

```sh
npx @broffis/session-summary-skill install
```

This is an alternative entry point to the **same Python installer**, not a
different installation format. Python 3.9+ on macOS or Linux is still required.
It copies the bundled skill and every helper into `~/.copilot/skills/session-summary`;
no repository clone or permanent npm installation is needed. Afterward, run
`/skills reload` and `/skills info session-summary` inside Copilot CLI.
Autosave and autoread settings are not changed.

Update or uninstall with:

```sh
npx @broffis/session-summary-skill@latest update
npx @broffis/session-summary-skill@latest uninstall
```

The same safety rules below apply, including disabling/removing hook
registrations **before uninstalling**. An install made from a ZIP can be updated
or uninstalled through npx, and vice versa. Pass `--skills-dir <directory>` to
any action for a custom installation parent.

To select a reviewed release explicitly, use
`npx @broffis/session-summary-skill@0.1.0 install` once that version is published.
Downloading an npm package alone does not install the skill or enable hooks;
the explicit `install`, `update`, or `uninstall` action performs the operation.

### ZIP installation: update or uninstall

From a freshly downloaded release folder:

```sh
python3 install.py --update
```

The installer refuses accidental overwrites, locally modified installations,
unknown existing folders, and development symlinks. Back up local modifications
and resolve conflicts manually instead of forcing an update. Updating preserves
the installed path used by hooks and does not change opt-in settings.

Before uninstalling, disable automation and remove this skill's
`session-info.json` hook registrations from every configured repo and the global
hooks directory. Disabling settings alone leaves hook commands registered.
Then, from an extracted release folder, run:

```sh
python3 install.py --uninstall
```

Only the unmodified managed skill is removed. Saved summaries and settings are
preserved. `--skills-dir <directory>` selects a different installation parent
for either operation; default is `~/.copilot/skills`.

### Development installation

For a live development checkout, symlink the skill instead:

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

Downloading this workspace does not install the skill automatically. Skills run when
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

### Optional project-bound MCP writer

Shell checkpoint commands remain the default. For narrower automatic approval,
the bundled `scripts/checkpoint_mcp.py` provides a local stdio MCP server with
two tools: read-only `get_checkpoint_context(session_id)` and
`save_checkpoint(session_id, token, summary)`. It uses the existing
checkpoint writer and has no third-party dependencies or network listener.
The server accepts no commands, working-directory overrides, or output paths
from tool calls. It can append summaries and update checkpoint state only for
its configured working directory, subject to autosave opt-in and current tokens.
It cannot enable automation, register itself, or grant tool approval.

#### One-command setup

After installing/updating the skill, close Copilot sessions for this project
and run this from the directory where you will use Copilot:

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/setup_mcp.py" --approve
```

Or use the installed npm package's command:

```sh
session-summary-skill setup-mcp --approve
```

This explicit setup registers the installed writer in the repository's
`.mcp.json`, installs repo hooks, enables repo autosave, and selects MCP
transport. `--cwd /path/to/project` selects another working directory.
For a custom installation, the npm command accepts `--skills-dir /path/to/skills`.
Use `--dry-run` to validate and preview which files would change without writing.
Setup preserves unrelated configuration and rejects conflicting server/hook
definitions. Rerunning the same setup is safe. Generated paths are personal:
keep `.mcp.json`, `.github/hooks/session-info.json`, and
`.github/session-info.json` local rather than committing them for other users.

**`--approve` is a separate, explicit permission grant.** It saves only
`session-summary/get_checkpoint_context` and `session-summary/save_checkpoint`
for this repository in Copilot's documented
`permissions-config.json` schema, preserving all other approvals and directory
grants. Linked worktrees use the main repository's permission scope. It never
approves Python, shell commands, all MCP tools, or filesystem access generally.
Omit this flag to leave approval to Copilot's prompts. Close Copilot first
because it also manages this file; editing it during a session can lose changes.
Legacy permission files must be migrated by Copilot first.

Start Copilot normally afterward—no `--allow-tool` flag is needed when the
saved approval is supported and loaded by your CLI. An older CLI that does not
support saved MCP approvals may still prompt; setup never weakens permissions
to compensate. CLI deny rules and organization policies remain authoritative.
The writer remains bound to the exact setup directory, including subdirectories.

To revoke the saved approval, use Copilot's permission controls or, with Copilot
closed, remove only the matching MCP approval from this repository's entry in
`permissions-config.json`. Uninstall does not revoke approvals or remove the
project's MCP registration/hooks; remove those explicitly too.

#### Manual setup

Alternatively, explicitly register the server through
`/mcp add`: name **session-summary**, type **STDIO**, command:

```sh
python3 -B /absolute/path/to/.copilot/skills/session-summary/scripts/checkpoint_mcp.py --cwd /absolute/path/to/project
```

Enable only `get_checkpoint_context` and `save_checkpoint`. Use the same exact working directory as
your Copilot session, including any subdirectory: storage is mapped by working
directory, not Git root. This server intentionally serves only one such
directory. Do not reuse its registration in sessions for other projects.
If you use `COPILOT_HOME`, explicitly pass it in the server's environment too,
so the writer reads the same global opt-in settings as your hooks.
Registration is separate from approval; use the CLI's supported approval
controls or explicitly start a session with:

```sh
copilot --allow-tool='session-summary(get_checkpoint_context)' \
  --allow-tool='session-summary(save_checkpoint)'
```

This permission allows summary writes through that tool, not arbitrary Python
or shell execution. Approve only a server definition and installation you trust.
Then select MCP transport for this repository (this does not enable autosave):

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" \
  configure-transport --cwd "$PWD" --mode mcp
```

The repository's `.github/session-info.json` stores `checkpoint_transport`;
missing means `shell`. This setting is repo-scoped, not global. Because the
writer is bound to one directory, sessions using MCP transport in this repo
must use that same directory. MCP hook requests display exactly
"Session-summary autosave requested". The agent uses its trusted runtime
session UUID for a read-only lookup of that session's pending checkpoint, then
composes the summary and saves with the returned token. No session is selected
by recency or by scanning for pending work. A new user turn invalidates the
returned token; the agent must not refresh it to retry an outdated summary.
Session IDs and tokens may still appear in MCP tool details; they are omitted
from the hook message, not hidden from the protocol or treated as authentication.
If either tool is
unavailable, denied, or fails, the agent reports it without falling back to
shell or changing permissions. To restore the default:

```sh
python3 "$HOME/.copilot/skills/session-summary/scripts/autosave.py" \
  configure-transport --cwd "$PWD" --mode shell
```

Installation and updates alone never register this server, select MCP mode, or
pre-approve tools; only the separate setup command performs those opt-in actions.
When uninstalling, also remove its explicit MCP registration.

### How it works

| Event | Action |
| --- | --- |
| `sessionStart` | For autosave, records the start date. For autoread, injects saved context. |
| `userPromptSubmitted` | Tracks a new user turn using a hash, without storing the prompt; ignores the exact pending checkpoint continuation. |
| `agentStop` | Requests at most one extra agent turn to save a checkpoint, unless already saved. |
| `sessionEnd` | Reports outstanding unsaved progress; does not invoke a model or create an exit summary. |

Global and repo hook registrations can coexist. Per-project/session locks,
turn tokens, and append markers deduplicate their calls and checkpoint retries.
Hook-requested continuations are guarded against recursion. State lives in the
project's `.autosave/` folder beside `raw summaries` and `rollup`; it contains
dates and hashes, not a second copy of the conversation. Raw summaries are
append-only and rollups stay manual.

Some CLI versions submit the hook's checkpoint request through
`userPromptSubmitted` before the agent handles it. An exact match to the
currently pending request preserves its token instead of invalidating itself.
Modified requests and genuine new user turns still invalidate older tokens;
stale-token checks are never bypassed during saving.

MCP checkpoint requests contain only the short status message; shell requests
retain the required command and token. Detailed guidance stays in the skill.
Existing MCP registrations must enable the lookup tool before using the new
hook: rerun setup (with Copilot closed if using `--approve`), or add
`get_checkpoint_context` through `/mcp`. Setup upgrades an otherwise identical
save-only registration without replacing unrelated definitions. Reload the
server and skill to load the new tool and instructions.
After a successful save,
the agent responds "Session-summary autosave executed." Failures are reported
instead of displaying that success message.

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

## Building a downloadable release

From the repository root, choose the intended release version:

```sh
python3 build_release.py --version v0.1.0
```

This creates `dist/session-summary-skill-v0.1.0.zip` and its `.zip.sha256`
checksum. The ZIP contains only the skill, required helpers, installer, README,
and license; it excludes tests, local summaries, caches, and Git metadata.
Existing artifacts are not overwritten.

Publish those two files as assets on a GitHub Release for
`broffis/session-summary-skill` after reviewing and merging the code.
Building locally does not push, tag, or publish anything. Users can verify a
download on macOS/Linux with `shasum -a 256 -c <archive>.zip.sha256`.

### Building the npm package

The npm entry point in `bin/session-summary-skill.cjs` calls `install.py` with
argument arrays (no shell interpolation). The package has no npm dependencies
or install lifecycle scripts. `package.json` explicitly includes the skill
and Python helpers while excluding tests and local artifacts.

```sh
npm test
npm pack
```

`npm pack` creates `broffis-session-summary-skill-0.1.0.tgz` locally.
To try it without publishing, use an isolated installation directory:

```sh
npm exec --package=./broffis-session-summary-skill-0.1.0.tgz -- \
  session-summary-skill install --skills-dir /path/to/temporary-skills
```

Publishing is a separate, explicit action requiring npm authorization for the
`@broffis` scope. Neither building nor running tests publishes the package.
The package version is maintained in `package.json`; coordinate it with the
intended GitHub Release version.

## CI/CD and releases

See [RELEASE_FLOW.md](https://github.com/broffis/session-summary-skill/blob/main/RELEASE_FLOW.md)
for verification, versioning, administrator setup, publishing, and recovery.

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
