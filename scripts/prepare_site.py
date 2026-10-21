#!/usr/bin/env python3
"""Bundle validated release metadata with the page that displays it."""

import hashlib
import json
from pathlib import Path
import re

from scripts.generate_releases import validate


def prepare_site(directory):
    data = validate(json.loads((directory / "releases.json").read_text()))
    # Release notes are untrusted text. Escape HTML delimiters even in a JSON script.
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    app = (directory / "app.js").read_bytes()
    filename = f"app.{hashlib.sha256(app).hexdigest()[:16]}.js"
    html = (directory / "index.html").read_text()
    html, count = re.subn(
        r'<script id="release-data" type="application/json">.*?</script>',
        lambda _: f'<script id="release-data" type="application/json">{payload}</script>',
        html, flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("Expected one release-data script in index.html")
    html, count = re.subn(
        r'<script src="\./app(?:\.[a-f0-9]+)?\.js" defer></script>',
        f'<script src="./{filename}" defer></script>', html,
    )
    if count != 1:
        raise ValueError("Expected one app script in index.html")
    (directory / filename).write_bytes(app)
    (directory / "index.html").write_text(html)


if __name__ == "__main__":
    prepare_site(Path("docs"))
