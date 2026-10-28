# Installation, update, and uninstall

Back to the [README](../README.md).

Requires **Python 3.9+ on macOS or Linux** and Copilot CLI. No pip packages
are needed; Windows is not supported.

Installation copies the skill and its Python helpers into
`~/.copilot/skills/remind-me-again`. It never changes autosave or autoread
settings. Do not use `copilot skill add <SKILL.md URL>`: it installs only the
Markdown file and omits the required helpers.

The skill is installed once for the current user and is available across
projects. No `--global` flag is needed or accepted for `install` or `update`.
The `--global` flag is only an uninstall option for cleaning up global
automation setup; it does not control where the skill is installed.

## Install from a ZIP

1. Download the ZIP from [GitHub Releases](https://github.com/broffis/remind-me-again/releases) and unzip it.
   Before a release exists, download the repository's source ZIP or clone it.
2. Run from the extracted folder:

   ```sh
   python3 install.py
   ```

3. In Copilot CLI, run `/skills reload`, then `/skills info remind-me-again`.

You can delete the extracted files afterward.

## Install with npm/npx

Requires Node.js 18+. This is another entry point to the same Python installer
(Python is still required); no clone or permanent npm install is needed.

```sh
npx remind-me-again install
npx remind-me-again update
npx remind-me-again uninstall
```

- No `@latest` suffix is required; unversioned commands use npm's package resolution.
- Pin a reviewed release with `@<version>`, for example `@0.4.0`.
- Use v0.4.0 or newer; earlier releases are not supported. Version-pinned
  downloads remain available, but avoid installing releases older than v0.4.0.
- ZIP and npm installs can update or uninstall each other.
- Pass `--skills-dir <directory>` to installation actions to use a custom installation parent.
- Downloading the package alone installs nothing; the explicit action does.

To keep the npm command on your PATH instead of using `npx`:

```sh
npm install -g remind-me-again
remind-me-again install
```

Here, npm's `-g` installs the command globally; the separate `install` action
copies the skill to the same per-user location as the `npx` command.

## Update

From a fresh release folder:

```sh
python3 install.py --update
```

The installer refuses to overwrite locally modified installations, unknown
folders, and development symlinks. Back up and resolve conflicts manually
rather than forcing an update. Updates keep the installed path used by hooks
and leave opt-in settings unchanged.

## Uninstall

**Close Copilot first**: cleanup edits its saved permission file.

```sh
python3 install.py --uninstall --cwd /absolute/path/to/project
# or
npx remind-me-again uninstall --cwd /absolute/path/to/project
```

This removes the unmodified managed skill and the project's recognized setup:

- this installation's `remind-me-again` server in `.mcp.json` or `.github/mcp.json`
- its generated hooks in `.github/hooks/session-info.json`
- the autosave/autoread/transport keys in `.github/session-info.json`
- the two exact saved MCP approvals in the repository's permission entry

Unrelated servers, hooks, settings, approvals, and allowed directories are
preserved. Linked worktrees share their main repository's approval scope.

Options:

- `--cwd` defaults to the current directory; outside Git, project cleanup is skipped.
- `--dry-run` validates and previews without changing files.
- `--global` also removes this installation's recognized global server, hooks,
  and settings under `COPILOT_HOME` (default `~/.copilot`). It does not touch
  other projects. Without it, global setup remains.
- `--skills-dir <directory>` selects a non-default installation parent.

Things to know:

- **Saved summaries, rollups, and session storage are never deleted.**
- The skill install is shared. Other projects' setup remains and may reference
  the removed skill, so clean them first or reinstall before using them.
- Cleanup can be rerun after the skill is removed.
- Unrecognized or conflicting definitions, symlinks, invalid JSON, and unmigrated
  legacy permissions fail before any write. An I/O failure reports partial
  progress; fix it and rerun.

## Development install

Symlink the skill from a checkout instead of copying it:

```sh
mkdir -p "$HOME/.copilot/skills"
ln -s "$HOME/personal/session-info-skill/remind-me-again" \
  "$HOME/.copilot/skills/remind-me-again"
```

Check for an existing skill directory first; do not replace one blindly. Then
run `/skills reload` and `/skills info remind-me-again` in Copilot CLI.

A skill runs only when invoked or selected by the agent; it is not an exit
hook. For automatic checkpoints, see [automation.md](automation.md).
