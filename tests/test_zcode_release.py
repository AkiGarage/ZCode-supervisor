import tempfile
import unittest
from pathlib import Path

from tools.zcode_eval.zcode_release import latest_release, main, parse_releases


FIXTURE_CHANGELOG = """
<html><body>
<h1>Releases & Updates</h1>
<p>3.1.2 Released Jun 18, 2026</p>
<h2>Release v3.1.2</h2>
<h2>New Features</h2>
<li>You can now set a custom certificate for desktop proxy connections.</li>
<li>On Windows, you can choose which shell the app uses.</li>
<h2>Bug Fixes</h2>
<li>Fixed resumed tasks losing or using the wrong thinking level.</li>
<li>Fixed the issue where the sse|http MCP http header transmission was ineffective.</li>
<p>3.1.1 Released Jun 16, 2026</p>
<h2>Release v3.1.1</h2>
<h2>New Features</h2>
<li>HTML files now open directly in the built-in browser.</li>
<h2>Bug Fixes</h2>
<li>Starting plans is more reliable when the app is busy.</li>
<p>3.1.0 Released Jun 16, 2026</p>
<h2>ZCode 3.1.0 Update</h2>
<li>A new usage and quota entry point lets you check your current availability.</li>
</body></html>
"""


class ZCodeReleaseTests(unittest.TestCase):
    def test_parse_latest_release(self):
        release = latest_release(FIXTURE_CHANGELOG, "fixture")

        self.assertEqual(release.version, "3.1.2")
        self.assertIn("custom certificate", release.notes[0])
        self.assertIn("MCP http header", " ".join(release.notes))

    def test_check_reports_update_against_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            changelog = root / "changelog.html"
            baseline = root / "baseline.json"
            output = root / "release.json"
            changelog.write_text(FIXTURE_CHANGELOG, encoding="utf-8")
            baseline.write_text('{"version":"3.1.1"}\n', encoding="utf-8")

            exit_code = main(
                [
                    "check",
                    "--html-file",
                    str(changelog),
                    "--baseline",
                    str(baseline),
                    "--json-out",
                    str(output),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn('"update_available": true', output.read_text(encoding="utf-8"))

    def test_parse_releases_keeps_usage_note(self):
        releases = parse_releases(FIXTURE_CHANGELOG, "fixture")

        self.assertEqual(len(releases), 3)
        self.assertIn("usage and quota", " ".join(releases[2].notes))


if __name__ == "__main__":
    unittest.main()
