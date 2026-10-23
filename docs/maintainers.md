# Maintainer guide

Back to the [README](../README.md).

## Scripts

Helpers live in `session-summary/scripts/`.

| Script | Responsibility and reading order |
| --- | --- |
| `storage.py` | Validate dates and map a working directory to its project storage. |
| `save_summary.py` | Validate a summary, format its entry, and append under a file lock. |
| `rollup.py` | `prepare` reads rollup history and uncovered raw bytes; `save` checks that snapshot, renders Markdown, and replaces the file atomically. |
| `retrieval.py` | `retrieve` combines rollup sections and uncovered raw sections, then applies the context limit. |
| `autosave.py` | `configure` installs settings/hooks; `handle` dispatches events; `checkpoint` appends progress before recording success. |

Persisted state details:

- Autosave keeps three turn hashes: `turn` (latest user prompt), `requested`
  (turn already given a save continuation), and `saved` (last successful
  checkpoint). They are hashes, not summary text.
- A failed state update can follow a successful raw append; the entry's
  checkpoint marker makes retrying that append safe.
- Rollup `sources` records consumed byte offsets and hashes. `prepare` returns
  prospective checkpoints without persisting them; only `save` commits them.
  Retrieval reuses that logic but never advances it.

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

## Building the npm package

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

- Python 3.9+ on macOS or Linux; no external dependencies.
- Working directories must be below the user's home directory.
- Appends lock each output file so cooperating writers don't interleave entries.
  Rollups are replaced atomically under a separate lock and reject stale plans.
- Helpers use only local files and make no network or model calls. Autosave asks
  the existing Copilot agent to write the checkpoint; no separate CLI or SDK client runs.

```sh
python3 -B -m unittest discover -s tests -v
```
