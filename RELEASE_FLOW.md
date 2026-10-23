# CI/CD and releases

## Verification

`verify.yml` checks pull requests, can be run manually, and is reused by the
release workflow before any release operation. It runs Python tests, npm tests
(including packed-installer checks), ZIP creation/checksum validation, and an
npm package-content dry run (without registry publication checks). The matrix
covers Python 3.9 / Node 18 on Ubuntu 22.04 and
Python 3.14 / Node 24 on Linux and macOS. PR titles must use Conventional Commits.
There are no runtime dependency installs or publishing credentials in PR jobs.

In branch protection, require `Workflow lint`, `Conventional PR title`, and all three
verification matrix checks. Use squash merges with the PR title as the commit
subject so release intent stays explicit.

## Versioning

`release.yml` runs on `main` after verification succeeds. Release Please uses
Conventional Commits to open/update a version PR, updating `package.json`,
`.release-please-manifest.json`, and `CHANGELOG.md`. Merge that PR to approve
the version and create its `vX.Y.Z` GitHub Release and tag.

Use `feat: ...` for a minor version and `fix: ...` for a patch. Breaking-change
markers produce a major bump after 1.0; while pre-1.0, they produce a minor bump.
Docs/chore/test/refactor-only work does not normally produce a release.
Do not manually bump package versions or create release tags in feature PRs.
The initial manifest tracks the existing `0.1.0`; bootstrap history begins after
the initial implementation merge, so it does not republish that version.

## One-time administrator setup

1. Create a GitHub App installed on `broffis/remind-me-again` with repository
   **Contents**, **Pull requests**, and **Issues** read/write permissions. Add its
   app ID and private key as repository Actions secrets named `APP_ID` and
   `APP_PRIVATE_KEY`. App-created release PRs trigger ordinary PR verification;
   the default `GITHUB_TOKEN` would not trigger those checks.
2. Create the GitHub environment **`npm`**. Restrict it to `main` and add required
   reviewers if desired. Both automatic publication and manual retries use this
   environment. Allow the Actions permissions needed for release PRs and releases.
3. If the npm package does not yet exist, publish the initial `0.1.0` manually
   from a reviewed, merged checkout using `npm login`, `npm publish --dry-run`,
   then `npm publish --access public`. The registry returned
   404 when this automation was prepared; trusted publishing cannot be configured
   until the package exists.
4. In that npm package's **Settings > Trusted publishing**, add GitHub Actions:
   owner **`broffis`**, repository **`remind-me-again`**, workflow filename
   **`release.yml`**, environment **`npm`**. Permit direct **`npm publish`**
   (not just staged publishing). No `NPM_TOKEN` secret is required.

New trusted-publisher configurations currently expire if their first successful
publish does not happen within two days; configure this close to the first
automated release. See [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).
Publishing uses Node 24 with npm 11.5.1+ and `id-token: write` for OIDC/provenance.
The GitHub App's short-lived token is used only for Release Please, not npm.

## Publication and recovery

When Release Please creates a release, the **same workflow run** checks out its
exact commit, validates the tag/version and ancestry on `main`, publishes npm,
and uploads the release ZIP and checksum to the GitHub Release. The workflows
use pinned action revisions and read-only permissions except in release jobs.
No `release.published` or tag-triggered workflow is needed.

If publication fails after the release is created, fix the underlying credentials
or environment configuration, then run **Actions > Release > Run workflow** on
`main` with the existing tag (for example `v0.1.1`). This verifies the tagged
code again and retries publication without generating a new version.
Existing immutable npm versions are skipped; ZIP assets are replaced to finish
an interrupted upload. Only a registry 404 is treated as an unpublished version;
authentication/network errors stop the workflow. A retry skips an existing
version rather than verifying its contents, so do not publish different code
under the same version manually.

The workflows and local tests have not been exercised on GitHub yet. Adding
these files locally does not configure the App, npm publisher, environment, or
branch protection, and does not publish anything.
