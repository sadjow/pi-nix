import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("updater", Path(__file__).parents[1] / "scripts/update.py")
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.platforms = {
            "aarch64-darwin": {"asset": "pi-darwin-arm64.tar.gz"},
            "x86_64-linux": {"asset": "pi-linux-x64.tar.gz"},
        }
        (self.root / "platforms.json").write_text(json.dumps(self.platforms))
        self.base = "https://github.com/earendil-works/pi/releases/download/v1.2.3/"
        self.downloads = {}
        self.release = {"tag_name": "v1.2.3", "draft": False, "prerelease": False, "assets": []}
        sums = []
        for platform in self.platforms.values():
            name = platform["asset"]
            payload = name.encode()
            digest = hashlib.sha256(payload).hexdigest()
            self.downloads[self.base + name] = payload
            sums.append(f"{digest}  {name}")
            self.release["assets"].append({
                "name": name, "browser_download_url": self.base + name,
                "digest": f"sha256:{digest}",
            })
        self.release["assets"].append({"name": "SHA256SUMS", "browser_download_url": self.base + "SHA256SUMS"})
        self.downloads[self.base + "SHA256SUMS"] = "\n".join(sums).encode()
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if url.startswith("https://api.github.com/"):
            return json.dumps(self.release).encode()
        return self.downloads[url]

    def update(self):
        return updater.update(self.root, fetch=self.fetch)

    def test_verified_update_and_unchanged_check(self):
        self.assertTrue(self.update())
        sources = json.loads((self.root / "sources.json").read_text())
        self.assertEqual(sources["version"], "1.2.3")
        self.assertEqual(set(sources["hashes"]), set(self.platforms))
        original = (self.root / "sources.json").read_bytes()
        self.calls.clear()
        self.assertFalse(self.update())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.root / "sources.json").read_bytes(), original)

    def test_corrupt_archive_preserves_existing_pin(self):
        destination = self.root / "sources.json"
        destination.write_text(json.dumps({"version": "1.2.2", "hashes": {}}))
        original = destination.read_bytes()
        self.downloads[self.base + "pi-linux-x64.tar.gz"] = b"corrupted"
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            self.update()
        self.assertEqual(destination.read_bytes(), original)

    def test_missing_platform_does_not_publish_partial_update(self):
        self.release["assets"].pop(0)
        with self.assertRaisesRegex(ValueError, "Missing or unexpected"):
            self.update()
        self.assertFalse((self.root / "sources.json").exists())

    def test_github_digest_must_agree(self):
        self.release["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "GitHub asset digest mismatch"):
            self.update()

    def test_prereleases_are_rejected(self):
        self.release["prerelease"] = True
        with self.assertRaisesRegex(ValueError, "published stable"):
            self.update()

    def test_automatic_downgrade_is_rejected(self):
        (self.root / "sources.json").write_text(json.dumps({"version": "1.3.0", "hashes": {}}))
        with self.assertRaisesRegex(ValueError, "automatic downgrade"):
            self.update()

    def test_missing_hash_is_repaired_at_same_version(self):
        self.update()
        sources = json.loads((self.root / "sources.json").read_text())
        sources["hashes"].pop("x86_64-linux")
        (self.root / "sources.json").write_text(json.dumps(sources))
        self.assertTrue(self.update())
        self.assertEqual(set(json.loads((self.root / "sources.json").read_text())["hashes"]), set(self.platforms))

    def test_network_error_does_not_change_pin(self):
        destination = self.root / "sources.json"
        destination.write_text(json.dumps({"version": "1.2.2", "hashes": {}}))
        original = destination.read_bytes()

        def unavailable(url):
            raise OSError("Network unavailable")

        with self.assertRaisesRegex(OSError, "Network unavailable"):
            updater.update(self.root, fetch=unavailable)
        self.assertEqual(destination.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
