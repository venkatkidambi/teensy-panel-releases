#!/usr/bin/env python3
"""Generate static download metadata using only the Python standard library."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


REPOSITORY = "venkatkidambi/teensy-panel-releases"
NIGHTLY_TAG = re.compile(
    r"^(?:nightly-|v)?(?P<version>\d+\.\d+\.\d+-nightly(?:[.-][0-9A-Za-z]+)+)$"
)
PLATFORMS = {
    "macos_arm64": ("aarch64-apple-darwin-", ".dmg"),
    "macos_x64": ("x86_64-apple-darwin-", ".dmg"),
    "windows_x64": ("x86_64-pc-windows-msvc-", "setup.exe"),
}
CHANGELOG_PER_CHANNEL = 10


def publication_order(item):
    """Newest publication first, with numeric nightly versions breaking ties."""
    version_key = ()
    match = NIGHTLY_TAG.fullmatch(item["tag_name"])
    if match:
        base, identifiers = match.group("version").split("-nightly", 1)
        version_key = (*map(int, base.split(".")), tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in re.split(r"[.-]", identifiers.lstrip(".-"))
        ))
    return timestamp(item["published_at"]), version_key, item["tag_name"]


def change_notes(body):
    """Keep published change notes, excluding this repo's installation boilerplate."""
    if body is None:
        return ""
    if not isinstance(body, str):
        raise ValueError("Invalid release notes")
    body = body.replace("\r\n", "\n").strip()
    section = re.search(r"^##\s+What changed\s*$", body, re.MULTILINE | re.IGNORECASE)
    if not section:
        return body  # Preserve unfamiliar release-note formats rather than guess.
    notes = body[section.end():]
    # Earlier releases had an unheaded installation footer after the change notes.
    end = re.search(
        r"^(?:#{1,2}\s|Nightly development build |Source commit: |Windows: download )",
        notes, re.MULTILINE,
    )
    return notes[:end.start()].strip() if end else notes.strip()


def changelog_entry(release, channel, repository):
    tag = release["tag_name"]
    return {
        "tag": tag,
        "version": NIGHTLY_TAG.fullmatch(tag).group("version") if channel == "nightly" else tag.removeprefix("v"),
        "channel": channel,
        "published_at": release["published_at"],
        "url": checked_url(release["html_url"], repository, f"tag/{quote(tag, safe='')}"),
        "notes": change_notes(release.get("body")),
    }


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Missing publication/asset timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp must include a time zone")
    return result


def read_json(url, token=None):
    """Bounded retries; credentials are sent only to the GitHub API."""
    headers = {"User-Agent": "teensy-panel-download-site", "Cache-Control": "no-cache"}
    if urlsplit(url).netloc == "api.github.com":
        headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            headers["Authorization"] = f"Bearer {token}"
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=25) as response:
                return json.load(response)
        except HTTPError as error:
            error.close()
            if error.code not in (403, 429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)
    raise RuntimeError("Unreachable retry state")


def fetch_releases(repository, token=None):
    releases = []
    page = 1
    while True:
        batch = read_json(
            f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}", token
        )
        if not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch):
            raise ValueError("GitHub returned an invalid releases list")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def checked_url(value, repository, path):
    if not isinstance(value, str):
        raise ValueError("Missing release URL")
    url = urlsplit(value)
    if (url.scheme != "https" or url.netloc != "github.com"
            or not url.path.startswith(f"/{repository}/releases/{path}")
            or url.query or url.fragment):
        raise ValueError("Unexpected release URL")
    return value


def asset_metadata(asset, repository, tag):
    name = asset["name"]
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid asset name")
    if type(asset.get("size")) is not int or asset["size"] <= 0:
        raise ValueError("Invalid asset size")
    timestamp(asset["updated_at"])
    return {
        "name": name,
        "url": checked_url(asset["browser_download_url"], repository, f"download/{quote(tag, safe='')}/"),
        "size": asset["size"],
        "updated_at": asset["updated_at"],
    }


def release_metadata(release, repository, nightly=False):
    tag = release["tag_name"]
    # Extensions are anchored: updater archives, signatures and JSON never match.
    assets = [asset for asset in release["assets"] if asset.get("state") == "uploaded"]
    installers = {}
    for platform, (prefix, suffix) in PLATFORMS.items():
        matches = [asset for asset in assets
                   if asset["name"].startswith(prefix) and asset["name"].lower().endswith(suffix)]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous {platform} installers in {tag}; refusing to guess")
        installers[platform] = asset_metadata(matches[0], repository, tag) if matches else None
    checksums = [asset for asset in assets if asset["name"] == "SHA256SUMS.txt"]
    if len(checksums) > 1:
        raise ValueError(f"Ambiguous checksums in {tag}")
    version = NIGHTLY_TAG.fullmatch(tag).group("version") if nightly else tag.removeprefix("v")
    return {
        "tag": tag,
        "version": version,
        "published_at": release["published_at"],
        "url": checked_url(release["html_url"], repository, f"tag/{quote(tag, safe='')}"),
        "installers": installers,
        "checksums": asset_metadata(checksums[0], repository, tag) if checksums else None,
    }


def generate(releases, repository=REPOSITORY):
    if not isinstance(releases, list):
        raise ValueError("Expected a releases array")
    stable, nightly = [], []
    for release in releases:
        if not isinstance(release, dict) or type(release.get("draft")) is not bool:
            raise ValueError("Invalid release record")
        if release["draft"]:
            continue
        tag = release["tag_name"]
        if not isinstance(tag, str) or not tag:
            raise ValueError("Invalid release tag")
        # The mutable updater-channel release is excluded even if its flags change.
        if tag == "nightly":
            continue
        if type(release.get("prerelease")) is not bool:
            raise ValueError("Invalid prerelease flag")
        timestamp(release["published_at"])
        if not release["prerelease"]:
            stable.append(release)
        elif NIGHTLY_TAG.fullmatch(tag):
            nightly.append(release)

    def latest(candidates, is_nightly=False):
        if not candidates:
            return None
        selected = max(candidates, key=publication_order)
        return release_metadata(selected, repository, is_nightly)

    history = [
        (item, channel)
        for channel, candidates in (("stable", stable), ("nightly", nightly))
        for item in sorted(candidates, key=publication_order, reverse=True)[:CHANGELOG_PER_CHANNEL]
    ]
    history.sort(key=lambda pair: publication_order(pair[0]), reverse=True)
    data = {"schema_version": 1, "repository": repository,
            "stable": latest(stable), "nightly": latest(nightly, True),
            "changelog": [changelog_entry(item, channel, repository) for item, channel in history]}
    validate(data, repository)
    return data


def validate(data, repository=REPOSITORY):
    """Validate both fresh data and last-deployed data before trusting a fallback."""
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("repository") != repository):
        raise ValueError("Invalid release metadata schema or repository")
    for channel in ("stable", "nightly"):
        release = data[channel]
        if release is None:
            continue
        if not isinstance(release, dict) or not isinstance(release.get("tag"), str):
            raise ValueError("Invalid channel metadata")
        tag = release["tag"]
        if not tag or tag == "nightly" or not isinstance(release.get("version"), str) or not release["version"]:
            raise ValueError("Invalid version")
        if channel == "nightly" and not NIGHTLY_TAG.fullmatch(tag):
            raise ValueError("Nightly metadata must describe a versioned nightly")
        timestamp(release["published_at"])
        checked_url(release["url"], repository, f"tag/{quote(tag, safe='')}")
        for platform, (prefix, suffix) in PLATFORMS.items():
            asset = release["installers"][platform]
            if asset is not None:
                asset_metadata({**asset, "browser_download_url": asset["url"]}, repository, tag)
                if not asset["name"].startswith(prefix) or not asset["name"].lower().endswith(suffix):
                    raise ValueError("Installer has wrong architecture or extension")
        if release["checksums"] is not None:
            asset = release["checksums"]
            asset_metadata({**asset, "browser_download_url": asset["url"]}, repository, tag)
            if asset["name"] != "SHA256SUMS.txt":
                raise ValueError("Unexpected checksum asset")
    # Older deployed metadata remains usable during an API outage on upgrade.
    if "changelog" in data:
        if not isinstance(data["changelog"], list):
            raise ValueError("Invalid changelog")
        for entry in data["changelog"]:
            if not isinstance(entry, dict) or entry.get("channel") not in ("stable", "nightly"):
                raise ValueError("Invalid changelog channel")
            tag = entry["tag"]
            if not isinstance(tag, str) or not tag or tag == "nightly":
                raise ValueError("Invalid changelog tag")
            if entry["channel"] == "nightly" and not NIGHTLY_TAG.fullmatch(tag):
                raise ValueError("Changelog requires a versioned nightly")
            if not isinstance(entry["version"], str) or not entry["version"] or not isinstance(entry["notes"], str):
                raise ValueError("Invalid changelog content")
            timestamp(entry["published_at"])
            checked_url(entry["url"], repository, f"tag/{quote(tag, safe='')}")
    return data


def read_previous(args):
    try:
        if args.previous_url:
            if urlsplit(args.previous_url).scheme != "https":
                raise ValueError("Previous metadata must use HTTPS")
            data = read_json(args.previous_url)  # Never send GITHUB_TOKEN to Pages.
        elif args.previous:
            data = json.loads(args.previous.read_text())
        else:
            return None
        return validate(data, args.repository)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Previous deployed metadata unavailable: {error}", file=sys.stderr)
        return None


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=REPOSITORY)
    parser.add_argument("--output", type=Path, default=Path("docs/releases.json"))
    parser.add_argument("--input", type=Path, help="Read a saved GitHub API array instead of the network")
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--previous", type=Path, help="Last successfully deployed metadata (for local testing)")
    previous.add_argument("--previous-url", help="Public URL of last successfully deployed metadata")
    parser.add_argument("--github-output", type=Path, help="Append changed/source step outputs")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repository):
        parser.error("Invalid repository")
    previous_data = read_previous(args)
    source = "api"
    try:
        releases = json.loads(args.input.read_text()) if args.input else fetch_releases(
            args.repository, os.environ.get("GITHUB_TOKEN")
        )
        data = generate(releases, args.repository)
    except (OSError, ValueError, KeyError, TypeError) as error:
        if previous_data is None:
            print(f"Release refresh failed; no valid deployed fallback. Output left untouched: {error}", file=sys.stderr)
            return 1
        print(f"::warning::Release refresh failed; retaining last deployed metadata: {error}", file=sys.stderr)
        data, source = previous_data, "fallback"
    changed = data != previous_data
    atomic_write(args.output, data)
    print(f"Release metadata: source={source}, changed={str(changed).lower()}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"changed={str(changed).lower()}\nsource={source}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
