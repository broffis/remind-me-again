# Session info skill

The `session-summary` skill saves and retrieves session summaries locally:

```text
~/.copilot/session-info/personal/recipe-app/
  raw summaries/
    2026-10-23.md
  rollup/
    2026-10-23.md
```

Project paths are relative to your home directory.

- **Raw summaries**: each save appends an entry (with session UUID and
  `copilot --resume=<sessionId>`) to the session start date's file. Existing entries are never changed.
- **Rollups**: summarize only raw content not yet covered by earlier rollups,
  named by the local date of creation. Repeating one on the same day refreshes it;
  earlier days' rollups stay unchanged. Each lists its related session IDs, dates, and resume commands.
- **Division of work**: the agent writes the synthesis; the Python helper selects
  new input, generates session references, and tracks consumed bytes and hashes
  in hidden Markdown metadata. Don't remove that metadata or edit consumed raw
  content; changes cause an explicit error instead of lost history.

## Quick start

Requires **Python 3.9+ on macOS or Linux** and Copilot CLI. Download the ZIP
from [GitHub Releases](https://github.com/broffis/session-summary-skill/releases),
unzip it, and run:

```sh
python3 install.py
```

Then in Copilot CLI run `/skills reload` and `/skills info session-summary`.
Autosave and autoread stay off unless you enable them.

| Prompt | Result |
| --- | --- |
| `Use the /session-summary skill: save` | Save current session progress. |
| `Use the /session-summary skill: read` | Retrieve the latest rollup plus uncovered raw progress. |
| `Use the /session-summary skill: review --all` | Review every rollup plus uncovered raw progress. |
| `Use the /session-summary skill: rollup` | Create or refresh today's rollup. |

## Documentation

- [Installation, update, and uninstall](docs/installation.md): ZIP, npm/npx, and development installs.
- [Using the skill](docs/usage.md): commands, manual retrieval, and full-project review.
- [Autoread and autosave](docs/automation.md): opt-in automation, overrides, and hook behavior.
- [Project-bound MCP writer](docs/mcp-setup.md): optional narrower-permission autosave transport.
- [Maintainer guide](docs/maintainers.md): scripts, releases, CI, and tests. See also [RELEASE_FLOW.md](RELEASE_FLOW.md).
