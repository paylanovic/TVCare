import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

from tvbakim import setup_tools as setup
from tvbakim.adb import Adb, managed_adb_directory


def fixture_archive(extra=(), omitted=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("platform-tools/", "")
        for name in sorted(setup.REQUIRED_FILES - set(omitted)):
            content = ("Pkg.Revision=" + setup.PLATFORM_TOOLS_VERSION + "\n").encode() if name == "source.properties" else b"synthetic fixture - not executable"
            archive.writestr("platform-tools/" + name, content)
        for name, content in extra:
            archive.writestr(name, content)
    return stream.getvalue()


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "tools" / "platform-tools"
        self.payload = fixture_archive()
        self.downloads = []
        self.probes = []
        self.messages = []
        self.env = patch.dict(os.environ, {"TVCARE_ADB": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        for name, value in [("PLATFORM_TOOLS_SHA256", hashlib.sha256(self.payload).hexdigest()), ("PLATFORM_TOOLS_BYTES", len(self.payload))]:
            patcher = patch.object(setup, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def download(self, url, destination):
        self.downloads.append(url)
        Path(destination).write_bytes(self.payload)

    def probe(self, path):
        self.probes.append(Path(path))
        if not Path(path).is_file():
            raise setup.SetupError("synthetic missing executable")
        return "Android Debug Bridge version 1.0.41\nVersion " + setup.PLATFORM_TOOLS_VERSION

    def install(self, **options):
        kwargs = dict(accept_license=True, existing_adb=SimpleNamespace(path=None), install_dir=self.target,
                      downloader=self.download, probe=self.probe, output=self.messages.append, platform_name="win32")
        kwargs.update(options)
        return setup.install_requirements(**kwargs)

    def test_success_download_verified_before_probe_and_repeat_offline(self):
        result = self.install()
        self.assertEqual(result, self.target / "adb.exe")
        self.assertEqual(self.downloads, [setup.PLATFORM_TOOLS_URL])
        self.assertEqual(len(self.probes), 1)
        manifest = json.loads((self.target / setup.MANIFEST_NAME).read_text())
        self.assertEqual(manifest["sha256"], hashlib.sha256(self.payload).hexdigest())
        self.assertTrue(setup.REQUIRED_FILES.issubset(manifest["files"]))
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.target.iterdir()}
        self.downloads.clear()
        def offline(*args): raise AssertionError("network must not be called")
        self.install(existing_adb=SimpleNamespace(path=result), downloader=offline)
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.target.iterdir()})
        self.assertTrue(any("Önkoşullar hazır" in message for message in self.messages))
        self.assertTrue(any("ADB hazır" in message for message in self.messages))

    def test_existing_external_adb_no_prompt_network_or_managed_directory(self):
        external = self.root / "external-adb.exe"
        external.write_bytes(b"existing")
        def forbidden(*args): raise AssertionError("not expected")
        result = self.install(accept_license=False, existing_adb=SimpleNamespace(path=external), downloader=forbidden, input_fn=forbidden)
        self.assertEqual(result, external)
        self.assertEqual(external.read_bytes(), b"existing")
        self.assertFalse(self.target.parent.exists())

    def test_cancel_and_eof_download_nothing(self):
        for answer in [lambda prompt: "", lambda prompt: "hayır", lambda prompt: (_ for _ in ()).throw(EOFError())]:
            with self.subTest(answer=answer), self.assertRaises(setup.SetupError):
                self.install(accept_license=False, input_fn=answer)
        self.assertEqual(self.downloads, [])
        self.assertFalse(self.target.parent.exists())

    def test_explicit_invalid_adb_does_not_install_behind_override(self):
        with self.assertRaisesRegex(setup.SetupError, "Belirttiğiniz"):
            self.install(adb_binary="missing", existing_adb=SimpleNamespace(path="missing"))
        with patch.dict(os.environ, {"TVCARE_ADB": "missing"}):
            with self.assertRaisesRegex(setup.SetupError, "Belirttiğiniz"):
                self.install(existing_adb=SimpleNamespace(path="missing"))
        self.assertEqual(self.downloads, [])

    def test_broken_bundled_adb_not_hidden_by_successful_managed_install(self):
        bundled = self.root / "app" / "platform-tools" / "adb.exe"
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"broken")
        def broken(path): raise setup.SetupError("synthetic bad bundled executable")
        with patch.object(setup.sys, "_MEIPASS", str(bundled.parent.parent), create=True):
            with self.assertRaisesRegex(setup.SetupError, "Uygulama yanındaki"):
                self.install(existing_adb=SimpleNamespace(path=bundled), probe=broken)
        self.assertEqual(self.downloads, [])
        self.assertFalse(self.target.exists())

    def test_permission_error_is_friendly_and_preserves_destination(self):
        with patch.object(setup, "_reject_managed_links", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(setup.SetupError, "dosya izinlerini"):
                self.install()

    def test_tampered_hash_never_executes_or_publishes(self):
        with patch.object(setup, "PLATFORM_TOOLS_SHA256", "0" * 64):
            with self.assertRaisesRegex(setup.SetupError, "SHA-256"):
                self.install()
        self.assertEqual(self.probes, [])
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob(".platform-tools-stage-*")), [])

    def test_incomplete_download_never_executes(self):
        def incomplete(url, destination): Path(destination).write_bytes(self.payload[:10])
        with self.assertRaisesRegex(setup.SetupError, "boyutu"):
            self.install(downloader=incomplete)
        self.assertEqual(self.probes, [])

    def test_download_and_probe_failure_preserve_previous_files(self):
        self.target.mkdir(parents=True)
        (self.target / "keep.txt").write_bytes(b"previous installation")
        for failure in ("download", "probe"):
            def download(url, destination):
                if failure == "download": raise OSError("offline")
                self.download(url, destination)
            def probe(path): raise setup.SetupError("bad dll")
            with self.subTest(failure=failure), self.assertRaises(setup.SetupError):
                self.install(downloader=download, probe=probe)
            self.assertEqual((self.target / "keep.txt").read_bytes(), b"previous installation")
            self.assertEqual(len(list(self.target.iterdir())), 1)

    def test_publish_rename_failure_restores_existing_directory(self):
        self.target.mkdir(parents=True)
        (self.target / "keep.txt").write_bytes(b"keep")
        real_replace = os.replace
        def fail_publish(source, destination):
            if Path(source).name == "platform-tools" and "unpacked" in str(source):
                raise PermissionError("synthetic locked destination")
            return real_replace(source, destination)
        with patch.object(setup.os, "replace", side_effect=fail_publish):
            with self.assertRaises(setup.SetupError): self.install()
        self.assertEqual((self.target / "keep.txt").read_bytes(), b"keep")

    def test_target_link_and_non_directory_rejected(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"unrelated file")
        with self.assertRaises(setup.SetupError): self.install()
        self.assertEqual(self.target.read_bytes(), b"unrelated file")
        self.target.unlink()
        external = self.root / "external"
        external.mkdir()
        try:
            self.target.symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("Host cannot create the filesystem symlink fixture")
        with self.assertRaises(setup.SetupError): self.install()
        self.assertEqual(list(external.iterdir()), [])

    def test_unsupported_os_and_no_tv_calls(self):
        with self.assertRaisesRegex(setup.SetupError, "Windows"):
            self.install(platform_name="linux")
        result = subprocess.CompletedProcess([], 0, "Android Debug Bridge version 1.0.41", "")
        with patch.object(setup.subprocess, "run", return_value=result) as runner:
            setup.probe_adb("adb.exe")
        self.assertEqual(runner.call_args.args[0], ["adb.exe", "version"])
        self.assertIs(runner.call_args.kwargs["shell"], False)
        self.assertEqual(runner.call_args.kwargs["timeout"], 10)


class ArchiveSafetyTests(unittest.TestCase):
    def extract(self, payload):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "file.zip"
            archive.write_bytes(payload)
            return setup.extract_archive(archive, Path(root) / "stage")

    def test_traversal_absolute_ads_backslash_devices_and_duplicates_rejected(self):
        names = ["../outside", "/absolute", "C:/absolute", "platform-tools/../escape", "platform-tools/x:stream",
                 "platform-tools\\escape", "platform-tools/CON.txt", "platform-tools/dir./x", "platform-tools/foo ",
                 "other/file", "platform-tools/ADB.EXE", "platform-tools//x", "platform-tools/*"]
        for name in names:
            with self.subTest(name=name), self.assertRaises(setup.SetupError):
                self.extract(fixture_archive([(name, b"malicious")]))

    def test_symlink_member_rejected(self):
        member = zipfile.ZipInfo("platform-tools/link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(setup.SetupError):
            self.extract(fixture_archive([(member, b"../../outside")]))

    def test_missing_required_dll_and_wrong_properties_rejected(self):
        with self.assertRaisesRegex(setup.SetupError, "DLL"):
            self.extract(fixture_archive(omitted=["AdbWinApi.dll"]))
        with self.assertRaisesRegex(setup.SetupError, "sürümü"):
            self.extract(fixture_archive(extra=[("platform-tools/source.properties", b"Pkg.Revision=0")], omitted=["source.properties"]))

    def test_extraction_limits_checked_before_writes(self):
        with patch.object(setup, "MAX_EXTRACT_BYTES", 1), self.assertRaises(setup.SetupError):
            self.extract(fixture_archive())
        with patch.object(setup, "MAX_ARCHIVE_MEMBERS", 1), self.assertRaises(setup.SetupError):
            self.extract(fixture_archive())


class DownloadAndDiscoveryTests(unittest.TestCase):
    def test_offline_download_has_clear_retryable_error(self):
        opener = SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("offline")))
        with patch.object(setup.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(setup.SetupError, "yeniden"):
                setup.download_archive(setup.PLATFORM_TOOLS_URL, "not-created.zip")

    def test_incomplete_http_body_has_clear_retryable_error(self):
        opener = SimpleNamespace(open=lambda *a, **k: (_ for _ in ()).throw(http.client.IncompleteRead(b"short")))
        with patch.object(setup.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(setup.SetupError, "yeniden"):
                setup.download_archive(setup.PLATFORM_TOOLS_URL, "not-created.zip")

    def test_redirect_to_non_google_or_http_rejected(self):
        handler = setup._GoogleRedirect()
        for url in ["http://dl.google.com/file.zip", "https://evil.example/file.zip", "https://dl.google.com:444/file.zip"]:
            with self.subTest(url=url), self.assertRaises(setup.SetupError):
                handler.redirect_request(None, None, 302, "redirect", {}, url)

    def test_environment_override_remains_explicit(self):
        with patch.dict(os.environ, {"TVCARE_ADB": "missing-explicit-adb"}), patch("tvbakim.adb.shutil.which", return_value=None):
            self.assertEqual(Adb._locate(None), "missing-explicit-adb")
            self.assertEqual(Adb._locate("other-explicit-adb"), "other-explicit-adb")

    def test_managed_directory_is_per_user(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"LOCALAPPDATA": root}):
            self.assertEqual(managed_adb_directory(), Path(root) / "TVCare/tools/platform-tools")

    def test_run_setup_failure_nonzero_and_no_exception(self):
        with patch.object(setup, "install_requirements", side_effect=setup.SetupError("synthetic failure")), patch("builtins.print") as output:
            self.assertEqual(setup.run_setup(), 1)
            self.assertTrue(any(call.args == ("synthetic failure",) for call in output.call_args_list))


if __name__ == "__main__":
    unittest.main()
