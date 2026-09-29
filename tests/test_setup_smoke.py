import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.setup_smoke import (SetupSmokeError, isolated_environment, offline_environment,
                                 snapshot_tree, verify_install, smoke, main)


class SetupSmokeTests(unittest.TestCase):
    def test_disposable_environment_hides_existing_adb_and_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            env = isolated_environment(Path(temp), {'Path': 'old-adb-path', 'TVCARE_ADB': 'old-adb',
                'ANDROID_HOME': 'old-sdk', 'USERPROFILE': 'old-profile', 'SystemRoot': r'C:\Windows'})
            self.assertNotIn('TVCARE_ADB', env)
            self.assertNotIn('ANDROID_HOME', env)
            self.assertEqual(env['PATH'], r'C:\Windows\System32')
            self.assertTrue(Path(env['LOCALAPPDATA']).is_dir())
            self.assertTrue(Path(env['USERPROFILE']).is_relative_to(Path(temp)))

    def test_offline_proxy_has_no_inherited_bypass(self):
        env = offline_environment({'https_proxy': 'old-proxy', 'No_Proxy': '*', 'KEEP': 'value'})
        self.assertEqual(env['HTTP_PROXY'], 'http://127.0.0.1:9')
        self.assertEqual(env['https_proxy'], 'http://127.0.0.1:9')
        self.assertEqual(env['NO_PROXY'], '')
        self.assertEqual(env['no_proxy'], '')
        self.assertEqual(env['KEEP'], 'value')
        self.assertNotIn('No_Proxy', env)

    def test_snapshot_detects_timestamp_only_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'tool'
            path.write_bytes(b'unchanged content')
            before = snapshot_tree(root)
            stamp = path.stat().st_mtime_ns + 2_000_000_000
            os.utime(path, ns=(stamp, stamp))
            after = snapshot_tree(root)
            self.assertEqual(before['tool']['sha256'], after['tool']['sha256'])
            self.assertNotEqual(before, after)

    def make_install(self, root):
        expected = {'version': '1.2.3', 'url': 'https://example.invalid/tools.zip', 'sha256': 'a' * 64}
        files = {}
        for name in ('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'NOTICE.txt', 'source.properties'):
            data = name.encode('ascii')
            (root / name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
        manifest = dict(expected, schema=1, files=files)
        (root / 'TVCARE-INSTALL.json').write_text(json.dumps(manifest), encoding='utf-8')
        return expected, manifest

    def test_install_verifies_pin_and_file_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected, manifest = self.make_install(root)
            self.assertEqual(verify_install(root, expected), 5)
            (root / 'adb.exe').write_bytes(b'tampered')
            with self.assertRaisesRegex(SetupSmokeError, 'installed_tool_hash_mismatch'):
                verify_install(root, expected)

    def test_install_rejects_manifest_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            expected, manifest = self.make_install(root)
            manifest['files']['../outside'] = 'a' * 64
            (root / 'TVCARE-INSTALL.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(SetupSmokeError, 'invalid_install_manifest_path'):
                verify_install(root, expected)

    @unittest.skipIf(os.name == 'nt', 'Only checks the non-Windows explicit NOT_RUN result')
    def test_non_windows_does_not_open_archive_or_install(self):
        with patch('scripts.setup_smoke.extract_archive', side_effect=AssertionError('must not execute')):
            self.assertEqual(smoke(Path('unused.zip'))['status'], 'NOT_RUN')

    def test_failure_evidence_never_echoes_raw_exception(self):
        output = io.StringIO()
        with patch('scripts.setup_smoke.smoke', side_effect=OSError('do-not-echo-private-value')):
            with patch('sys.stdout', output):
                self.assertEqual(main(['--archive', 'unused.zip']), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['reason'], 'unexpected_smoke_error')
        self.assertNotIn('do-not-echo-private-value', output.getvalue())


if __name__ == '__main__':
    unittest.main()
