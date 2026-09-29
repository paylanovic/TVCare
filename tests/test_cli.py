import contextlib
import io
import unittest
from unittest.mock import patch

from tvbakim.__main__ import main


class CliTests(unittest.TestCase):
    def test_license_acceptance_requires_explicit_setup_mode(self):
        with patch('sys.argv', ['TVCare', '--accept-platform-tools-license']), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)

    def test_demo_cannot_install_real_prerequisites(self):
        with patch('sys.argv', ['TVCare', '--demo', '--setup']), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main()
        self.assertEqual(error.exception.code, 2)

    def test_setup_failure_exits_before_opening_history_or_server(self):
        with patch('sys.argv', ['TVCare', '--setup']), \
                patch('tvbakim.setup_tools.run_setup', return_value=1) as setup, \
                patch('tvbakim.__main__.Store') as store, \
                patch('tvbakim.__main__.LocalServer') as server:
            self.assertEqual(main(), 1)
            setup.assert_called_once_with(False, adb_binary=None)
            store.assert_not_called()
            server.assert_not_called()


if __name__ == '__main__':
    unittest.main()
