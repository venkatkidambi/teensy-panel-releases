"use strict";

const REPOSITORY = "venkatkidambi/teensy-panel-releases";
const RELEASES_URL = `https://github.com/${REPOSITORY}/releases`;
const PLATFORMS = [
  {
    key: "macos_arm64",
    name: "macOS",
    architecture: "Apple Silicon · ARM64",
    format: "DMG",
    system: "macOS 12+",
  },
  {
    key: "macos_x64",
    name: "macOS",
    architecture: "Intel · x86_64",
    format: "DMG",
    system: "macOS 12+",
  },
  {
    key: "windows_x64",
    name: "Windows",
    architecture: "64-bit · x64",
    format: "Setup EXE",
    system: "Windows 10 / 11",
  },
];

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function safeReleaseURL(value, asset = false) {
  const url = new URL(value);
  const prefix = `/${REPOSITORY}/releases/${asset ? "download/" : "tag/"}`;
  if (
    url.origin !== "https://github.com" ||
    !url.pathname.startsWith(prefix) ||
    url.username ||
    url.password
  ) {
    throw new Error("Unexpected release URL");
  }
  return url.href;
}

function link(text, url, className = "") {
  const node = element("a", className, text);
  node.href = url;
  return node;
}

function renderChannel(channel, release) {
  const nightly = channel === "nightly";
  const label = nightly ? "Nightly" : "Stable";
  const article = element(
    "article",
    `channel${release ? "" : " channel-empty"}`,
  );
  article.setAttribute("aria-labelledby", `${channel}-title`);
  const header = element("div", "channel-header");
  const heading = element("div");
  const title = element("div", "channel-title");
  const h3 = element(
    "h2",
    "",
    release ? label : `${label} release coming soon`,
  );
  h3.id = `${channel}-title`;
  title.append(h3);
  if (release && nightly) {
    title.append(element("span", "pill", "Development build"));
  }
  heading.append(title);
  header.append(heading);
  article.append(header);
  if (!release) return article;

  const meta = element("p", "release-meta");
  const date = new Date(release.published_at);
  if (!Number.isFinite(date.getTime())) throw new Error("Invalid release date");
  const time = element(
    "time",
    "",
    new Intl.DateTimeFormat("en", {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    }).format(date),
  );
  time.dateTime = release.published_at;
  meta.append(element("span", "version", `v${release.version}`), time);
  header.append(meta);

  const grid = element("div", "download-grid");
  for (const platform of PLATFORMS) {
    const card = element("div", "download-card");
    card.append(
      element("h3", "", platform.name),
      element("p", "architecture", platform.architecture),
    );
    const asset = release.installers[platform.key];
    if (asset) {
      const button = link(
        `Download ${platform.format}`,
        safeReleaseURL(asset.url, true),
        "button primary",
      );
      button.setAttribute(
        "aria-label",
        `Download ${label} ${release.version} for ${platform.name} ${platform.architecture} (${platform.format})`,
      );
      const arrow = element("span", "", "↓");
      arrow.setAttribute("aria-hidden", "true");
      button.append(arrow);
      const size = new Intl.NumberFormat("en", {
        maximumFractionDigits: 1,
      }).format(asset.size / 1000000);
      card.append(
        button,
        element("p", "asset-detail", `${platform.system} · ${size} MB`),
      );
    } else {
      card.append(
        element("p", "unavailable", "Not available for this release"),
      );
    }
    grid.append(card);
  }
  const links = element("div", "release-links");
  links.append(link("Release notes", safeReleaseURL(release.url)));
  if (release.checksums)
    links.append(
      link("SHA256 checksums", safeReleaseURL(release.checksums.url, true)),
    );
  article.append(grid, links);
  return article;
}

// A small, text-first Markdown subset. Release HTML is never inserted into the DOM.
function appendNoteText(parent, text) {
  const tokens = /(\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`)/g;
  let start = 0;
  for (const match of text.matchAll(tokens)) {
    parent.append(document.createTextNode(text.slice(start, match.index)));
    if (match[2]) {
      let url;
      try {
        url = new URL(match[3]);
      } catch {
        /* Unsupported links remain readable text. */
      }
      if (
        url &&
        ["http:", "https:"].includes(url.protocol) &&
        !url.username &&
        !url.password
      ) {
        parent.append(link(match[2], url.href));
      } else {
        parent.append(document.createTextNode(match[2]));
      }
    } else {
      parent.append(
        element(match[4] ? "strong" : "code", "", match[4] || match[5]),
      );
    }
    start = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(start)));
}

function renderNotes(notes) {
  const content = element("div", "change-notes");
  if (!notes.trim()) {
    content.append(element("p", "", "No release notes were provided."));
    return content;
  }
  let paragraph = null;
  let list = null;
  let code = null;
  for (const line of notes.replace(/\r\n/g, "\n").split("\n")) {
    if (/^\s*```/.test(line)) {
      if (code) code = null;
      else {
        const pre = element("pre");
        code = element("code");
        pre.append(code);
        content.append(pre);
      }
      paragraph = list = null;
      continue;
    }
    if (code) {
      code.append(document.createTextNode(line + "\n"));
      continue;
    }
    if (!line.trim()) {
      paragraph = list = null;
      continue;
    }
    const heading = line.match(/^#{1,6}\s+(.+)$/);
    const item = line.match(/^\s*(?:([-*+])|\d+[.)])\s+(.+)$/);
    if (heading) {
      const title = element("h3");
      appendNoteText(title, heading[1]);
      content.append(title);
      paragraph = list = null;
    } else if (item) {
      const tag = item[1] ? "ul" : "ol";
      if (!list || list.localName !== tag) {
        list = element(tag);
        content.append(list);
      }
      const li = element("li");
      appendNoteText(li, item[2]);
      list.append(li);
      paragraph = null;
    } else {
      list = null;
      if (!paragraph) {
        paragraph = element("p");
        content.append(paragraph);
      } else paragraph.append(document.createTextNode(" "));
      appendNoteText(paragraph, line);
    }
  }
  return content;
}

function renderChangelog(entries) {
  const container = document.getElementById("changelog-entries");
  // A legacy snapshot can still supply working downloads during an API outage.
  if (entries === undefined) return;
  try {
    if (!Array.isArray(entries)) throw new Error("Invalid changelog");
    const rows = entries.map((entry, index) => {
      if (
        !["stable", "nightly"].includes(entry.channel) ||
        typeof entry.notes !== "string"
      ) {
        throw new Error("Invalid changelog entry");
      }
      const details = element("details", "changelog-entry");
      details.open = index === 0;
      const summary = element("summary");
      summary.append(element("span", "change-version", `v${entry.version}`));
      summary.append(
        element(
          "span",
          "pill",
          entry.channel === "stable" ? "Stable" : "Nightly",
        ),
      );
      const time = element(
        "time",
        "change-date",
        new Intl.DateTimeFormat("en", {
          year: "numeric",
          month: "short",
          day: "numeric",
          timeZone: "UTC",
        }).format(new Date(entry.published_at)),
      );
      time.dateTime = entry.published_at;
      summary.append(time);
      const notes = renderNotes(entry.notes);
      notes.append(
        link(
          "Full release notes on GitHub",
          safeReleaseURL(entry.url),
          "change-source",
        ),
      );
      details.append(summary, notes);
      return details;
    });
    container.replaceChildren(
      ...(rows.length
        ? rows
        : [
            element(
              "p",
              "changelog-fallback",
              "No releases have been published yet.",
            ),
          ]),
    );
  } catch {
    // Keep the static GitHub link if changelog data cannot be rendered.
  }
}

async function loadReleases() {
  const status = document.getElementById("release-status");
  const container = document.getElementById("release-channels");
  try {
    // Deployed pages carry their own snapshot, avoiding a separately cached JSON URL.
    const embedded = document.getElementById("release-data");
    let data = embedded ? JSON.parse(embedded.textContent) : null;
    if (data === null) {
      // Keep an unbuilt local checkout usable for previewing the website.
      const response = await fetch("./releases.json", {
        cache: "no-cache",
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error("Release information unavailable");
      data = await response.json();
    }
    if (
      data.schema_version !== 1 ||
      data.repository !== REPOSITORY ||
      !("stable" in data) ||
      !("nightly" in data)
    ) {
      throw new Error("Invalid release information");
    }
    // Build both sections before replacing the fallback; malformed data never leaves a partial page.
    const sections = [
      renderChannel("stable", data.stable),
      renderChannel("nightly", data.nightly),
    ];
    container.replaceChildren(...sections);
    status.textContent = "";
    renderChangelog(data.changelog);
  } catch {
    status.replaceChildren(
      document.createTextNode("Download information could not be loaded. "),
      link("View available installers on GitHub Releases ↗", RELEASES_URL),
    );
  }
}

loadReleases();
