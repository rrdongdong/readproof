import json
import os
import shutil
import tempfile
import unittest

from readproof import bundle
from readproof import serve


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-bundle-")
        self.web = os.path.join(self.dir, "web")
        os.makedirs(os.path.join(self.web, "src"))
        self.write("src/main.jsx", "console.log('a')\n")
        self.write("index.html", "<div id=root></div>\n")
        self.write("package.json", '{"name":"x"}\n')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, relative, content):
        path = os.path.join(self.web, relative)
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def test_fingerprint_is_stable(self):
        self.assertEqual(
            bundle.source_fingerprint(self.web), bundle.source_fingerprint(self.web)
        )

    def test_fingerprint_changes_with_sources(self):
        before = bundle.source_fingerprint(self.web)
        self.write("src/main.jsx", "console.log('b')\n")
        self.assertNotEqual(before, bundle.source_fingerprint(self.web))

    def test_fingerprint_ignores_files_outside_the_inputs(self):
        before = bundle.source_fingerprint(self.web)
        self.write("README.md", "not an input\n")
        self.assertEqual(before, bundle.source_fingerprint(self.web))


class StalenessTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="readproof-stale-")
        self.web = os.path.join(self.dir, "web")
        self.static = os.path.join(self.dir, "static")
        os.makedirs(os.path.join(self.web, "src"))
        os.makedirs(self.static)
        with open(os.path.join(self.web, "src", "main.jsx"), "w", encoding="utf-8") as handle:
            handle.write("x\n")
        with open(os.path.join(self.static, "index.html"), "w", encoding="utf-8") as handle:
            handle.write("<div id=root></div>\n")
        self._manifest = bundle.MANIFEST
        bundle.MANIFEST = os.path.join(self.static, "BUILD.json")

    def tearDown(self):
        bundle.MANIFEST = self._manifest
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_missing_manifest_is_stale(self):
        stale, message = bundle.staleness(self.web)
        self.assertTrue(stale)
        self.assertIn("never been built", message)

    def test_matching_manifest_is_fresh(self):
        bundle.write_manifest(bundle.source_fingerprint(self.web))
        stale, message = bundle.staleness(self.web)
        self.assertFalse(stale, message)

    def test_changed_source_is_stale(self):
        bundle.write_manifest(bundle.source_fingerprint(self.web))
        with open(os.path.join(self.web, "src", "main.jsx"), "w", encoding="utf-8") as handle:
            handle.write("changed\n")
        stale, message = bundle.staleness(self.web)
        self.assertTrue(stale)
        self.assertIn("stale", message)
        self.assertIn("readproof bundle", message)

    def test_manifest_records_files_and_note(self):
        bundle.write_manifest(bundle.source_fingerprint(self.web))
        with open(bundle.MANIFEST, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertIn("index.html", payload["files"])
        self.assertIn("committed on purpose", payload["note"])


class DiscoveryTests(unittest.TestCase):
    def test_explicit_web_dir_is_authoritative(self):
        self.assertEqual(serve.find_web_dir("/some/where"), "/some/where")

    def test_bundle_is_found_without_arguments(self):
        found = serve.find_web_dir()
        self.assertIsNotNone(found)
        # the repository ships a build, so this must resolve to real files
        self.assertTrue(os.path.isfile(os.path.join(found, "index.html")), found)


class RepoStateTests(unittest.TestCase):
    def test_committed_bundle_matches_the_sources(self):
        """If this fails, web/src changed and the committed build was not refreshed."""
        stale, message = bundle.staleness()
        self.assertFalse(stale, message)


if __name__ == "__main__":
    unittest.main()
