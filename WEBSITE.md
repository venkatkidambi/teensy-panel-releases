# Download website maintenance

The website uses plain HTML, CSS, and a small vanilla JavaScript file. There are
no runtime dependencies, third-party fonts, analytics, or frontend build tools.
`README.md` is the authoritative installation guide; keep the website's
instructions aligned with it.

## Files

| Path | Purpose |
| --- | --- |
| `docs/index.html` | Download page, installation instructions, firmware steps, inactive screenshot template |
| `docs/styles.css` | Responsive layout, typography, and accessible focus states |
| `docs/app.js` | Renders channel downloads from the static metadata; provides a GitHub fallback |
| `docs/releases.json` | Real release snapshot for local preview; regenerated during deployment |
| `docs/favicon.svg`, `docs/.nojekyll` | Site icon and static hosting marker |
| `scripts/generate_releases.py` | Standard-library Python release discovery, validation, comparison, and fallback |
| `tests/test_releases.py` | Offline release-selection, pagination, recovery, and change-detection tests |
| `.github/workflows/pages.yml` | Dedicated website build and Pages deployment workflow |

Only `docs` is uploaded to Pages. No application source, updater code, release
tags, or release assets are changed by this workflow. Metadata is never committed
back to the repository by Actions.

## Local preview

From the repository root, using Python 3.10 or newer:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Open <http://127.0.0.1:8000>. Stop the server with Ctrl+C. Use HTTP rather than
opening the HTML as a `file://` URL, because the page fetches `releases.json`.
The checked-in snapshot supports preview without API access. To refresh it:

```sh
python3 scripts/generate_releases.py
```

Public API reads work without authentication. If rate limited, provide a
read-only `GITHUB_TOKEN` through your environment. The workflow uses its own
automatic token with `contents: read`; no personal access token is needed.

The minimal layout leaves the screenshot placeholder in an inactive
`screenshot-placeholder` template in `index.html`. When a real screenshot is
available, add it under `docs` and replace the template with a visible figure
and descriptive image alt text. No placeholder or simulated screenshot is
displayed to visitors.

## Release discovery

The generator reads every page of the REST releases endpoint, excludes drafts,
and chooses each channel independently by the newest `published_at` timestamp.
It does not rely on API array order, tag alphabetic order, or commit dates.
For nightlies published in the same second, numeric version identifiers break
ties (for example, `nightly.10` follows `nightly.9`).

- **Stable:** latest published non-prerelease, excluding the exact `nightly` tag.
- **Nightly:** latest published prerelease whose tag is a versioned nightly,
  such as `nightly-0.2.0-nightly.8.1`. The forms `v0.2.0-nightly.8.1` and
  `0.2.0-nightly.8.1` also work. The special `nightly` updater channel and unrelated
  beta/RC prereleases never qualify.
- **Installers:** match the README's architecture prefixes and `.dmg` or
  `setup.exe` suffix. `.sig`, `.app.tar.gz`, JSON, and firmware assets do not
  qualify. Use the exact API `browser_download_url`, never construct filenames.
- Missing platforms show an availability message with no download link. Missing
  stable builds show “Stable release coming soon” above the clearly labeled
  Nightly section. Missing checksum files produce no checksum link.
- An incomplete latest release remains the latest release. Missing platforms
  are not silently filled with older versions. The next refresh discovers late
  uploads. Ambiguous installers fail the refresh rather than guess.

Generated metadata is deterministic. It contains no build timestamp or download
counts. Asset size and update timestamps are included so replacement assets
with unchanged filenames still trigger a refresh.

## Changelog

The page shows the ten most recent stable releases and ten most recent versioned
nightlies, combined in publication order. The newest entry is expanded; older
entries use native disclosure controls. Each includes its version, channel,
publication date, and a link to the original GitHub release.

Notes come directly from release bodies. When a release has a `What changed`
section, the generator extracts it and omits the repeated installation footer
(including the unheaded footer in older nightlies). Other note formats are
preserved. Releases without notes show an explicit empty-state message.
The browser renders paragraphs, lists, headings, bold text, code, and HTTP(S)
links without inserting release HTML or loading external images. Other Markdown
syntax remains readable text; full formatting is available on GitHub.

The changelog shares `docs/releases.json` and the existing deployment workflow.
New stable/nightly releases and edits to displayed change notes change the
metadata comparison, so hourly refreshes deploy them even when installer links
are unchanged. Published releases also trigger the workflow immediately when
GitHub delivers the event. Unchanged runs continue to skip deployment. The
special `nightly` updater channel, drafts, and unrelated prereleases are excluded.

During an API failure, last-deployed changelog data is preserved with the download
metadata. An older snapshot without a changelog remains valid and shows a GitHub
release-notes link until a refresh succeeds. Older history is available through
the page's GitHub links.

## Refreshes and failure recovery

The workflow runs on relevant pushes to `main`, `release: published`, manual
`workflow_dispatch`, and an hourly schedule at minute 17 UTC. Release-triggered
runs explicitly check out `main`, since release tags may refer to old trees.

Before generating metadata, it reads the last successfully deployed
`https://venkatkidambi.github.io/teensy-panel-releases/releases.json`.
The API requests retry transient failures three times with bounded timeouts.

- If a scheduled run produces identical metadata, **artifact upload and the
  entire deployment job are skipped**. See the Actions run summary.
- A push, release event, or manual run can deploy even with identical metadata,
  so website changes and intentional redeployments still work.
- If the API fails and deployed metadata passes validation, that metadata is
  retained. The run emits a warning; scheduled runs skip deployment.
- If both API retrieval and fallback fail, the build fails without overwriting
  its output or deploying. The live site stays untouched. A successful first
  deployment requires API access.
- If the previous site is unavailable but the API works, deployment proceeds
  because there is no trustworthy comparison baseline. The checked-in snapshot
  is deliberately not used as the workflow's fallback: it could roll the live
  website back to obsolete downloads.

The published site is the comparison baseline, rather than a build cache. A
failed deployment therefore cannot incorrectly mark new data as deployed.
The workflow serializes runs to avoid overlapping deployments.

Publishing from a different repository does not inherently suppress release
events; the publishing token and event behavior matter. GitHub generally
suppresses workflow-triggering events created by `GITHUB_TOKEN` (with documented
exceptions). The hourly refresh covers missed events and late asset uploads
without changing the private publishing pipeline. An explicit workflow dispatch
is also available for immediate refreshes. See
[GitHub's workflow-trigger documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow).

Scheduled runs can be delayed or dropped by GitHub. Public-repository schedules
are disabled after 60 days without repository activity. Check the Actions tab
and re-enable the workflow if needed; manual runs remain a recovery option.
See [GitHub's schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

If the site moves to a custom domain or another repository, update the workflow's
`--previous-url` and repository constants in the generator, JavaScript, and page
links together.

## Validate locally

```sh
python3 -m unittest discover -s tests -v
node --check docs/app.js
git diff --check
```

Node is optional, used only for this JavaScript syntax check. The site and Pages
workflow require no Node build pipeline.

To exercise the scheduled comparison without any deployment:

```sh
python3 scripts/generate_releases.py --previous docs/releases.json --output /tmp/teensy-releases-check.json
```

If GitHub's releases are unchanged, the output reports `changed=false`. Tests
also cover changed assets, new releases, a newer updater-channel release,
missing installers, API pagination, and failure recovery.

For offline testing against a saved REST response (a JSON array):

```sh
python3 scripts/generate_releases.py --input /path/to/releases-api.json --previous docs/releases.json --output /tmp/teensy-releases-check.json
```

## Publish the first version

These are manual publishing steps, to perform only when ready to publish. No
Pages settings, pushes, deployments, or release writes are required for local
development or validation.

1. Review the local changes and run the checks above.
2. In `venkatkidambi/teensy-panel-releases`, open **Settings → Pages**. Under
   **Build and deployment → Source**, select **GitHub Actions**. Do not choose
   branch-based `/docs` publishing: that bypasses metadata generation. The
   workflow has `enablement: false` and will not enable Pages itself.
3. Commit the website files and push them to `main` (or merge an approved PR):

   ```sh
   git add .gitignore .github/workflows/pages.yml docs scripts/generate_releases.py tests/test_releases.py WEBSITE.md
   git commit -m "Add Teensy Panel download website and Pages workflow"
   git push origin main
   ```

4. The push starts **Actions → Deploy download website**. Alternatively, select
   **Run workflow → main → Run workflow** after the workflow is on `main`.
   Approve the `github-pages` environment deployment if repository protection
   rules require it. No extra secrets are needed.
5. Wait for the build and deployment jobs to succeed. Visit
   <https://venkatkidambi.github.io/teensy-panel-releases/> and verify all available
   download buttons, release notes, checksums, and installation sections.

If the files are pushed before Pages is enabled, the deployment job will fail
without creating a Pages site. Enable Pages manually, then rerun the workflow.
GitHub's [publishing-source instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
describe the repository settings.

## Test automatic updates after publishing

1. Run the workflow manually to confirm live metadata generation and deployment.
2. Let an hourly run complete with no release changes. Its summary should say
   metadata is unchanged; the upload step and deployment job should be skipped.
3. After the normal publishing pipeline creates its next versioned nightly or
   stable release, check the release-triggered run, or the next hourly run if
   the release event does not trigger it. The site should show the new version,
   publication date, and actual installer URLs. There is no need to create a
   test release or modify the `nightly` updater channel.
4. Confirm the following unchanged hourly run skips deployment again.

Local tests validate the selection and comparison logic; actual Pages permissions,
environment protection, and event delivery can only be verified after publication.
