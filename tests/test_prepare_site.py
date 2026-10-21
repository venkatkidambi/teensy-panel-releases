from pathlib import Path
import json
import re
import tempfile
import unittest

from scripts.generate_releases import generate
from scripts.prepare_site import prepare_site
from test_releases import release


class PrepareSiteTests(unittest.TestCase):
    def test_page_bundles_current_data_and_versions_script(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            for name in ("index.html", "app.js"):
                (site / name).write_bytes((Path("docs") / name).read_bytes())
            notes = '</script><script>alert("untrusted notes")</script> & text'
            data = generate([release(body=notes)])
            (site / "releases.json").write_text(json.dumps(data))
            prepare_site(site)
            html = (site / "index.html").read_text()
            embedded = re.search(r'<script id="release-data" type="application/json">(.*?)</script>', html).group(1)
            self.assertNotIn("<", embedded)
            self.assertEqual(json.loads(embedded), data)
            app = re.search(r'src="\./(app\.[a-f0-9]+\.js)"', html).group(1)
            self.assertEqual((site / app).read_bytes(), (site / "app.js").read_bytes())
            prepare_site(site)
            self.assertEqual((site / "index.html").read_text(), html)
            # A later release replaces the snapshot; changed JS gets a new URL.
            data = generate([release("nightly-0.2.0-nightly.13.3")])
            (site / "releases.json").write_text(json.dumps(data))
            (site / "app.js").write_text("// changed application")
            prepare_site(site)
            updated = (site / "index.html").read_text()
            self.assertIn("0.2.0-nightly.13.3", updated)
            self.assertNotIn(f'./{app}', updated)

    def test_invalid_metadata_does_not_change_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            (site / "index.html").write_text("unchanged")
            (site / "releases.json").write_text("{}")
            with self.assertRaises(ValueError):
                prepare_site(site)
            self.assertEqual((site / "index.html").read_text(), "unchanged")
