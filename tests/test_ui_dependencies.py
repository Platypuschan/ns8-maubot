"""Keep the native-addon build tooling off vulnerable Undici releases."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiDependencyTests(unittest.TestCase):
    def test_native_build_undici_has_security_floor(self):
        package = json.loads((ROOT / "ui/package.json").read_text())
        self.assertEqual(
            package.get("resolutions", {}).get("node-gyp/undici"), "^8.12.2"
        )
        versions = re.findall(
            r'^"undici@[^\n]+:\n  version: ([^\n]+)',
            (ROOT / "ui/yarn.lock").read_text(),
            re.MULTILINE,
        )
        self.assertTrue(versions, "Undici must remain covered in the lockfile")
        for version in versions:
            with self.subTest(version=version):
                self.assertGreaterEqual(tuple(map(int, version.split("."))), (8, 12, 2))
                self.assertEqual(version.split(".")[0], "8")
