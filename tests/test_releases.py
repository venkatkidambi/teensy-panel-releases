"""Offline regression tests for release selection and deployment metadata."""

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts import generate_releases as generator


REPO = generator.REPOSITORY
BASE = f"https://github.com/{REPO}/releases"


def asset(tag, name, **overrides):
    return {"name": name, "browser_download_url": f"{BASE}/download/{tag}/{name}",
            "size": 1024, "state": "uploaded", "updated_at": "2026-10-20T12:00:00Z", **overrides}


def release(tag="nightly-0.2.0-nightly.8.1", published="2026-10-20T12:00:00Z", prerelease=True, **overrides):
    names = ["aarch64-apple-darwin-Panel_1_aarch64.dmg", "x86_64-apple-darwin-Panel_1_x64.dmg",
             "x86_64-pc-windows-msvc-Panel_1_x64-setup.exe", "SHA256SUMS.txt",
             "x86_64-pc-windows-msvc-Panel_1_x64-setup.exe.sig",
             "aarch64-apple-darwin-Panel.app.tar.gz", "latest.json"]
    return {"tag_name": tag, "published_at": published, "created_at": "2025-01-01T00:00:00Z",
            "prerelease": prerelease, "draft": False, "html_url": f"{BASE}/tag/{tag}",
            "assets": [asset(tag, name) for name in names], **overrides}


class SelectionTests(unittest.TestCase):
    def test_latest_published_versioned_nightly_excludes_channel_drafts_and_beta(self):
        older = release("nightly-0.2.0-nightly.7.1", "2026-10-19T12:00:00Z")
        newer = release()
        newer["created_at"] = "2020-01-01T00:00:00Z"
        rolling = release("nightly", "2026-10-25T12:00:00Z")
        draft = release("nightly-0.2.0-nightly.100.1", "2026-10-26T12:00:00Z", draft=True)
        beta = release("v0.3.0-beta.1", "2026-10-27T12:00:00Z")
        for candidates in ([older, rolling, draft, newer, beta], [beta, newer, draft, rolling, older]):
            with self.subTest(order=[r["tag_name"] for r in candidates]):
                result = generator.generate(candidates)
                self.assertIsNone(result["stable"])
                self.assertEqual(result["nightly"]["tag"], newer["tag_name"])
                self.assertEqual(result["nightly"]["version"], "0.2.0-nightly.8.1")

    def test_stable_selected_separately_by_publication(self):
        result = generator.generate([release(), release("v0.1.0", prerelease=False),
                                     release("v0.2.0", "2026-10-21T00:00:00Z", prerelease=False)])
        self.assertEqual(result["stable"]["version"], "0.2.0")
        self.assertEqual(result["nightly"]["version"], "0.2.0-nightly.8.1")

    def test_same_second_nightlies_use_numeric_version_tiebreak(self):
        result = generator.generate([release("nightly-0.2.0-nightly.9.1"),
                                     release("nightly-0.2.0-nightly.10.1")])
        self.assertEqual(result["nightly"]["version"], "0.2.0-nightly.10.1")

    def test_rolling_channel_always_excluded_even_with_wrong_flag(self):
        self.assertEqual(generator.generate([release("nightly", prerelease=False)]),
                         {"schema_version": 1, "repository": REPO, "stable": None, "nightly": None, "changelog": []})

    def test_unversioned_nightlies_are_not_download_releases(self):
        self.assertIsNone(generator.generate([release("nightly-latest"), release("nightly-20261020")])["nightly"])

    def test_supported_versioned_nightly_tags(self):
        for tag in ("nightly-0.2.0-nightly.8.1", "v0.2.0-nightly.8.1", "0.2.0-nightly.8.1"):
            with self.subTest(tag=tag):
                self.assertEqual(generator.generate([release(tag)])["nightly"]["version"], "0.2.0-nightly.8.1")

    def test_no_releases(self):
        result = generator.generate([])
        self.assertIsNone(result["stable"])
        self.assertIsNone(result["nightly"])

    def test_architectures_use_exact_api_urls_and_exclude_updater_assets(self):
        source = release()
        result = generator.generate([source])["nightly"]
        for platform, index in (("macos_arm64", 0), ("macos_x64", 1), ("windows_x64", 2)):
            self.assertEqual(result["installers"][platform]["url"], source["assets"][index]["browser_download_url"])
        self.assertEqual(result["checksums"]["name"], "SHA256SUMS.txt")

    def test_missing_installer_does_not_fall_back_to_older_release(self):
        older = release("nightly-0.2.0-nightly.7.1", "2026-10-19T12:00:00Z")
        newer = release()
        del newer["assets"][2]
        result = generator.generate([older, newer])["nightly"]
        self.assertIsNone(result["installers"]["windows_x64"])
        self.assertEqual(result["tag"], newer["tag_name"])

    def test_missing_checksums_and_unfinished_uploads(self):
        source = release()
        source["assets"][0]["state"] = "starter"
        del source["assets"][3]
        result = generator.generate([source])["nightly"]
        self.assertIsNone(result["installers"]["macos_arm64"])
        self.assertIsNone(result["checksums"])

    def test_ambiguous_installer_fails_instead_of_guessing(self):
        source = release()
        source["assets"].append(asset(source["tag_name"], "aarch64-apple-darwin-Other.dmg"))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            generator.generate([source])

    def test_unsafe_or_cross_repository_asset_url_rejected(self):
        for url in ("javascript:alert(1)", "https://evil.example/file.dmg", f"{BASE}/download/nightly/file.dmg"):
            source = release()
            source["assets"][0]["browser_download_url"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                generator.generate([source])

    def test_volatile_api_fields_do_not_change_metadata(self):
        original = release()
        updated = deepcopy(original)
        updated["assets"].reverse()
        for item in updated["assets"]:
            item["download_count"] = 999
        self.assertEqual(generator.generate([original]), generator.generate([updated]))

    def test_replaced_asset_changes_metadata(self):
        original = release()
        updated = deepcopy(original)
        updated["assets"][0]["updated_at"] = "2026-10-21T00:00:00Z"
        self.assertNotEqual(generator.generate([original]), generator.generate([updated]))

    def test_malformed_response_rejected(self):
        for response in ({"message": "API rate limit exceeded"}, [{}], [release(published=None)]):
            with self.subTest(response=response), self.assertRaises((ValueError, KeyError)):
                generator.generate(response)


class ChangelogTests(unittest.TestCase):
    def test_history_includes_both_channels_and_excludes_updater_drafts_and_beta(self):
        result = generator.generate([
            release("nightly", "2026-10-25T00:00:00Z"), release(),
            release("v0.1.0", "2026-10-18T00:00:00Z", prerelease=False),
            release("v1.0.0-beta.1"), release("v2.0.0", prerelease=False, draft=True),
        ])
        self.assertEqual([r["channel"] for r in result["changelog"]], ["nightly", "stable"])
        self.assertEqual(result["changelog"][0]["version"], "0.2.0-nightly.8.1")

    def test_change_section_excludes_modern_and_legacy_installation_footer(self):
        for footer in ("## Downloads and installation\nInstall instructions", "Nightly development build 1.0\nInstall instructions", "Source commit: abc", "Windows: download the installer"):
            body = "## What changed\n\n**New changes**\n\n- Fix USB connection\n\n" + footer
            self.assertEqual(generator.change_notes(body), "**New changes**\n\n- Fix USB connection")

    def test_unfamiliar_notes_are_preserved_and_empty_notes_supported(self):
        body = "# Release highlights\n\n- New feature\n- Fix"
        self.assertEqual(generator.change_notes(body), body)
        self.assertEqual(generator.change_notes(None), "")
        self.assertEqual(generator.generate([release()])["changelog"][0]["notes"], "")

    def test_history_retains_ten_releases_per_channel(self):
        releases = [release(f"nightly-0.2.0-nightly.{n}.1") for n in range(1, 15)]
        releases.append(release("v0.1.0", "2025-01-01T00:00:00Z", prerelease=False))
        history = generator.generate(releases)["changelog"]
        self.assertEqual(len(history), 11)
        self.assertEqual(history[0]["version"], "0.2.0-nightly.14.1")
        self.assertEqual(history[-1]["channel"], "stable")

    def test_older_release_notes_edits_change_metadata(self):
        older = release("nightly-0.2.0-nightly.7.1", "2026-10-19T00:00:00Z", body="Original notes")
        before = generator.generate([release(), older])
        older["body"] = "Corrected notes"
        after = generator.generate([release(), older])
        self.assertEqual(before["nightly"], after["nightly"])
        self.assertNotEqual(before, after)

    def test_legacy_fallback_remains_valid_and_bad_history_rejected(self):
        data = generator.generate([release()])
        del data["changelog"]
        self.assertEqual(generator.validate(data), data)
        for history in ("not a list", [{"channel": "beta"}], [{"channel": "nightly", "tag": "nightly"}]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                generator.validate({**data, "changelog": history})


class NetworkTests(unittest.TestCase):
    @patch.object(generator, "read_json")
    def test_pagination_reads_beyond_first_page(self, read_json):
        first_page = [release("nightly")] * 100
        last_page = [release("v0.1.0", prerelease=False), release()]
        read_json.side_effect = [first_page, last_page]
        releases = generator.fetch_releases(REPO)
        self.assertEqual(len(releases), 102)
        self.assertIsNotNone(generator.generate(releases)["stable"])
        self.assertIn("page=2", read_json.call_args.args[0])

    @patch.object(generator, "read_json", side_effect=[[], {"message": "bad"}])
    def test_empty_array_valid_but_api_error_object_invalid(self, _read):
        self.assertEqual(generator.fetch_releases(REPO), [])
        with self.assertRaises(ValueError):
            generator.fetch_releases(REPO)

    @patch.object(generator.time, "sleep")
    @patch.object(generator, "urlopen")
    def test_transient_failures_retry(self, urlopen, sleep):
        urlopen.side_effect = [URLError("network"), HTTPError("url", 503, "down", {}, None), io.BytesIO(b"[]")]
        self.assertEqual(generator.read_json("https://api.github.com/example"), [])
        self.assertEqual(sleep.call_count, 2)

    @patch.object(generator, "urlopen")
    def test_pages_request_never_contains_token(self, urlopen):
        urlopen.return_value = io.BytesIO(b"{}")
        generator.read_json("https://venkatkidambi.github.io/teensy-panel-releases/releases.json", token="secret")
        self.assertFalse(urlopen.call_args.args[0].has_header("Authorization"))


class RefreshTests(unittest.TestCase):
    def setUp(self):
        # Expected failure cases must not emit misleading GitHub warning annotations.
        for stream in ("stdout", "stderr"):
            capture = patch(f"sys.{stream}", new_callable=io.StringIO)
            capture.start()
            self.addCleanup(capture.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.previous = self.root / "previous.json"
        self.output = self.root / "releases.json"
        self.actions_output = self.root / "actions-output"
        self.data = generator.generate([release()])
        self.previous.write_text(json.dumps(self.data))

    def run_refresh(self):
        return generator.main(["--previous", str(self.previous), "--output", str(self.output),
                               "--github-output", str(self.actions_output)])

    @patch.object(generator, "fetch_releases")
    def test_unchanged_metadata_sets_false_and_is_byte_stable(self, fetch):
        fetch.return_value = [release()]
        self.assertEqual(self.run_refresh(), 0)
        first = self.output.read_bytes()
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(first, self.output.read_bytes())
        self.assertEqual(self.actions_output.read_text(), "changed=false\nsource=api\n" * 2)

    @patch.object(generator, "fetch_releases")
    def test_new_release_sets_changed(self, fetch):
        fetch.return_value = [release("nightly-0.2.0-nightly.9.1", "2026-10-21T00:00:00Z")]
        self.assertEqual(self.run_refresh(), 0)
        self.assertIn("changed=true", self.actions_output.read_text())

    @patch.object(generator, "fetch_releases")
    def test_notes_edit_sets_changed_for_scheduled_refresh(self, fetch):
        fetch.return_value = [release(body="## What changed\n\n- New documented fix")]
        self.assertEqual(self.run_refresh(), 0)
        self.assertIn("changed=true", self.actions_output.read_text())

    @patch.object(generator, "fetch_releases", side_effect=URLError("API unavailable"))
    def test_failure_reuses_previous_without_scheduled_deploy(self, _fetch):
        self.assertEqual(self.run_refresh(), 0)
        self.assertEqual(json.loads(self.output.read_text()), self.data)
        self.assertEqual(self.actions_output.read_text(), "changed=false\nsource=fallback\n")

    @patch.object(generator, "fetch_releases", side_effect=URLError("API unavailable"))
    def test_no_valid_fallback_fails_and_preserves_existing_file(self, _fetch):
        self.previous.write_text("not json")
        self.output.write_text("keep this file")
        self.assertEqual(self.run_refresh(), 1)
        self.assertEqual(self.output.read_text(), "keep this file")
        self.assertFalse(self.actions_output.exists())

    @patch.object(generator, "fetch_releases", side_effect=URLError("API unavailable"))
    def test_incomplete_schema_not_used_as_fallback(self, _fetch):
        self.previous.write_text(json.dumps({"schema_version": 1, "repository": REPO}))
        self.assertEqual(self.run_refresh(), 1)

    @patch.object(generator, "fetch_releases")
    def test_missing_previous_with_fresh_api_is_first_deployment(self, fetch):
        self.previous.unlink()
        fetch.return_value = [release()]
        self.assertEqual(self.run_refresh(), 0)
        self.assertIn("changed=true", self.actions_output.read_text())


if __name__ == "__main__":
    unittest.main()
