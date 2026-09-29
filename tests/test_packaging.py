import io
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_release import architecture, test_summary, write_launchers
from scripts.package_smoke import checked_path, extract_archive, verify_manifest


class PackagingTests(unittest.TestCase):
    def test_zero_tests_and_all_skipped_are_not_pass(self):
        result = unittest.TestResult()
        self.assertEqual(test_summary(result)['status'], 'FAIL')
        case = unittest.FunctionTestCase(lambda: None)
        result.testsRun = 1
        result.skipped = [(case, 'platform exclusion')]
        self.assertEqual(test_summary(result)['status'], 'FAIL')

    def test_skips_are_explicit_with_executed_count(self):
        result = unittest.TestResult()
        result.testsRun = 3
        result.skipped = [(unittest.FunctionTestCase(lambda: None), 'POSIX-only fixture')]
        summary = test_summary(result)
        self.assertEqual(summary['status'], 'PASS_WITH_SKIPS')
        self.assertEqual(summary['executed'], 2)
        self.assertEqual(len(summary['skipped']), 1)

    def test_architecture_names_are_normalized(self):
        for host, expected in [('AMD64', 'x86_64'), ('aarch64', 'arm64'), ('arm64', 'arm64')]:
            with self.subTest(host=host), patch('platform.machine', return_value=host):
                self.assertEqual(architecture(), expected)

    def test_demo_launchers_are_present_and_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            write_launchers(bundle)
            demo = next(bundle.glob('Demo-TVCare.*'))
            self.assertIn('--demo', demo.read_text(encoding='utf-8'))
            if os.name != 'nt':
                self.assertTrue(os.access(demo, os.X_OK))

    def test_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as target:
                target.writestr('../outside', 'bad')
            with self.assertRaises(ValueError):
                extract_archive(archive, root / 'extract')
            self.assertFalse((root / 'outside').exists())

    def test_archive_rejects_external_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as target:
                item = zipfile.ZipInfo('TVCare/link')
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(item, '../../../outside')
            with self.assertRaises(ValueError):
                extract_archive(archive, root / 'extract')

    def test_manifest_detects_tampered_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'payload').write_bytes(b'modified')
            (root / 'SHA256SUMS').write_text('0' * 64 + '  payload\n', encoding='utf-8')
            with self.assertRaises(AssertionError):
                verify_manifest(root)


if __name__ == '__main__':
    unittest.main()
