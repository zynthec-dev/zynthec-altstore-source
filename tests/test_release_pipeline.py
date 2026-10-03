import hashlib
import importlib.util
import io
import json
import plistlib
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_pipeline", ROOT / "scripts/release_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline)


def test_ipa(bundle_id="de.renewitt.mipet"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("Payload/Test.app/Info.plist", plistlib.dumps({"CFBundleIdentifier": bundle_id}))
    return stream.getvalue()


class ReleasePipelineTests(unittest.TestCase):
    def test_only_selected_release_assets_are_downloaded(self):
        content = json.loads((ROOT / "catalog/content.json").read_text())
        self.assertEqual(pipeline.selected_assets(content, "apps"), [("apps", "miPet-0.3-beta.ipa")])

    def test_tag_is_unique_and_valid(self):
        first = pipeline.new_release_tag("miPet", "0.4 beta")
        second = pipeline.new_release_tag("miPet", "0.4 beta")
        self.assertRegex(first, pipeline.RELEASE_TAG)
        self.assertNotEqual(first, second)

    def test_public_download_selects_exact_asset_and_preserves_release_date(self):
        data = test_ipa()
        asset = {"name": "miPet-0.4.ipa", "size": len(data),
                 "browser_download_url": "https://github.com/example/download/miPet-0.4.ipa",
                 "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                 "updated_at": "2026-09-28T12:00:00Z"}
        release = {"assets": [{"name": "unselected.ipa"}, asset]}
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, "ROOT", Path(folder)), patch.object(
            pipeline.urllib.request, "urlopen", side_effect=[io.BytesIO(json.dumps(release).encode()), io.BytesIO(data)]
        ) as fetch:
            pipeline.download_selected({"localApps": {"de.renewitt.mipet": {"ipaFile": asset["name"]}}}, "owner/repo", "apps")
            path = Path(folder) / asset["name"]
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(path.stat().st_mtime, 1790596800)
            self.assertEqual(fetch.call_args_list[1].args[0].full_url, asset["browser_download_url"])
            self.assertNotIn("Authorization", fetch.call_args_list[0].args[0].headers)

    def test_public_download_rejects_corrupt_release_asset(self):
        data = test_ipa()
        release = {"assets": [{"name": "miPet.ipa", "size": len(data),
                   "browser_download_url": "https://github.com/example/download/miPet.ipa",
                   "digest": "sha256:" + "0" * 64}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline, "ROOT", Path(folder)), patch.object(
            pipeline.urllib.request, "urlopen", side_effect=[io.BytesIO(json.dumps(release).encode()), io.BytesIO(data)]
        ):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                pipeline.download_selected({"localApps": {"de.renewitt.mipet": {"ipaFile": "miPet.ipa"}}}, "owner/repo", "apps")

    def test_staged_upload_creates_release_and_preserves_change_notes(self):
        data = test_ipa()
        sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        tag = "app-mipet-v0-4-20260928T205613Z-a1b2c3d4"
        app = {
            "ipaFile": "miPet-0.4.ipa", "releaseTag": tag, "name": "miPet",
            "marketingVersion": "0.4", "versionDescription": "Neue Animationen",
            "pendingUpload": {"sha": sha, "tag": tag, "size": len(data)},
        }
        content = {"localApps": {"de.renewitt.mipet": app}, "uploadedApps": [], "excludedBundleIdentifiers": []}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "content.json"
            with patch.object(pipeline, "CONTENT", output), patch.object(pipeline, "fetch_blob", return_value=data), patch.object(
                pipeline.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0)]
            ) as run:
                self.assertTrue(pipeline.publish_pending(content, "zynthec-dev/zynthec-altstore-source", "apps", "test-token"))
            self.assertNotIn("pendingUpload", json.loads(output.read_text())["localApps"]["de.renewitt.mipet"])
            self.assertIn("Neue Animationen", run.call_args_list[1].args[0])
            self.assertIn(tag, run.call_args_list[2].args[0])

    def test_wrong_bundle_id_is_rejected_before_release_creation(self):
        data = test_ipa("com.example.wrong")
        sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        tag = "app-mipet-v0-4-20260928T205613Z-a1b2c3d4"
        content = {"localApps": {"de.renewitt.mipet": {
            "ipaFile": "miPet-0.4.ipa", "releaseTag": tag, "name": "miPet",
            "marketingVersion": "0.4", "versionDescription": "Neue Animationen",
            "pendingUpload": {"sha": sha, "tag": tag, "size": len(data)},
        }}, "uploadedApps": []}
        with patch.object(pipeline, "fetch_blob", return_value=data), patch.object(pipeline.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "bundle ID"):
                pipeline.publish_pending(content, "zynthec-dev/zynthec-altstore-source", "apps", "test-token")
            run.assert_not_called()

    def test_direct_url_workflow_creates_versioned_release(self):
        content = {"localApps": {"de.renewitt.mipet": {"ipaFile": "miPet-0.3-beta.ipa", "name": "miPet"}}, "uploadedApps": []}
        with tempfile.TemporaryDirectory() as folder:
            ipa = Path(folder) / "miPet-0.4.ipa"
            ipa.write_bytes(test_ipa())
            output = Path(folder) / "content.json"
            with patch.object(pipeline, "CONTENT", output), patch.object(pipeline.subprocess, "run") as run:
                tag = pipeline.publish_url_file(content, "zynthec-dev/zynthec-altstore-source", ipa, "miPet", "0.4", "Neue Animationen")
            self.assertRegex(tag, pipeline.RELEASE_TAG)
            self.assertIn("Neue Animationen", run.call_args_list[0].args[0])
            published = json.loads(output.read_text())["localApps"]["de.renewitt.mipet"]
            self.assertEqual(published["releaseTag"], tag)
            self.assertEqual(published["versionDescription"], "Neue Animationen")


if __name__ == "__main__":
    unittest.main()
