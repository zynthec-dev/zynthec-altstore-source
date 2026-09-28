import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


class BuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "source.json").exists():
            subprocess.run(["python3", "scripts/build.py"], cwd=ROOT, check=True)
        cls.source = json.loads((DIST / "source.json").read_text())
        cls.content = json.loads((ROOT / "catalog/content.json").read_text())

    def test_source_contains_only_catalogued_ipas(self):
        selected = {
            app["ipaFile"]
            for app in [*self.content.get("localApps", {}).values(), *self.content.get("uploadedApps", [])]
        }
        spec = importlib.util.spec_from_file_location("source_build", ROOT / "scripts/build.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        bundle_ids = {
            builder.plist_from_ipa(ipa)[0]["CFBundleIdentifier"]
            for ipa in ROOT.glob("*.ipa") if ipa.name in selected
        }
        excluded = set(self.content.get("excludedBundleIdentifiers", []))
        self.assertEqual({app["bundleIdentifier"] for app in self.source["apps"]}, bundle_ids - excluded)
        for app in self.source["apps"]:
            self.assertTrue(app["versions"][0]["downloadURL"].endswith(".ipa"))
            self.assertGreater(app["versions"][0]["size"], 0)

    @unittest.skipUnless((ROOT / "miPet-0.3-beta.ipa").exists(), "miPet release asset is not available")
    def test_mipet_metadata(self):
        app = next(app for app in self.source["apps"] if app["bundleIdentifier"] == "de.renewitt.mipet")
        self.assertEqual(app["versions"][0]["version"], "0.1.0")
        self.assertEqual(app["versions"][0]["marketingVersion"], "0.3-beta")

    def test_catalog_selected_ipa_and_release_tag_are_published(self):
        for app in self.source["apps"]:
            metadata = self.content.get("localApps", {}).get(app["bundleIdentifier"])
            if metadata is None:
                metadata = next((entry for entry in self.content.get("uploadedApps", []) if entry.get("bundleIdentifier") == app["bundleIdentifier"]), None)
            self.assertIsNotNone(metadata)
            url = urlparse(app["versions"][0]["downloadURL"])
            self.assertEqual(Path(unquote(url.path)).name, metadata["ipaFile"])
            self.assertIn(f"/releases/download/{metadata.get('releaseTag', 'apps')}/", url.path)

    def test_excluded_apps_are_not_published(self):
        identifiers = {app["bundleIdentifier"] for app in self.source["apps"]}
        self.assertFalse(identifiers.intersection(self.content.get("excludedBundleIdentifiers", [])))
        self.assertEqual(self.source["featuredApps"], [])

    def test_apps_use_supported_categories(self):
        supported = {"developer", "entertainment", "games", "lifestyle", "other", "photo-video", "social", "utilities"}
        self.assertTrue(all(app["category"] in supported for app in self.source["apps"]))

    def test_feed_has_no_private_origin_metadata(self):
        self.assertTrue(all("_origin" not in app for app in self.source["apps"]))

    def test_public_source_uses_canonical_domain_root(self):
        self.assertEqual(self.source["name"], "zynthec-source")
        self.assertEqual(self.source["identifier"], "com.zynthec.source")
        self.assertEqual(self.source["website"], "https://source.zynthec.com")
        self.assertEqual(self.source["sourceURL"], "https://source.zynthec.com")
        self.assertNotIn("source.json", self.source["sourceURL"])
        self.assertEqual(self.source["iconURL"], "https://source.zynthec.com/assets/source-icon.png")
        self.assertTrue(all(app["iconURL"].startswith("https://source.zynthec.com/") for app in self.source["apps"]))

    def test_configured_apps_have_valid_release_filenames(self):
        apps = [*self.content.get("localApps", {}).values(), *self.content.get("uploadedApps", [])]
        filenames = [app.get("ipaFile") for app in apps]
        self.assertTrue(all(isinstance(filename, str) and filename.strip().endswith(".ipa") for filename in filenames))
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_admin_is_built_without_storefront_or_installer_artifacts(self):
        self.assertTrue((DIST / "admin" / "index.html").exists())
        admin_html = (DIST / "admin" / "index.html").read_text()
        for unwanted in ('href="/admin/', 'src="/admin/', 'href="/assets/', 'src="/assets/',
                         "Erweiterte Verbindung", 'id="repo"', 'id="branch"'):
            self.assertNotIn(unwanted, admin_html)
        for unwanted in ("index.html", "app.js", "styles.css", "data/catalog.json", "data/loaders.json", "zloader.mobileconfig"):
            self.assertFalse((DIST / unwanted).exists())


if __name__ == "__main__":
    unittest.main()
