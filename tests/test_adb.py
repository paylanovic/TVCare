import subprocess
import tempfile
import unittest
from pathlib import Path

from tvbakim.adb import Adb, AdbError, validate_endpoint


class AdbTests(unittest.TestCase):
    def runner(self, stdout="", returncode=0, stderr=""):
        self.calls = []
        def run(argv, **kwargs):
            self.calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, returncode, stdout, stderr)
        return run

    def test_endpoints_reject_injection_and_dns(self):
        for endpoint in ["192.0.2.2:5555", "[::1]:5555", "localhost:37000"]:
            self.assertEqual(validate_endpoint(endpoint), endpoint)
        for endpoint in ["example.com:5555", "1.2.3.4:0", "1.2.3.4:65536", "1.2.3.4:5555;id", "-s:any", "::1:5555", "[localhost]:5555", "1.2.3.4", " 1.2.3.4:5555"]:
            with self.subTest(endpoint=endpoint), self.assertRaises(AdbError):
                validate_endpoint(endpoint)

    def test_shell_is_argv_and_remote_arguments_are_quoted(self):
        adb = Adb("adb", self.runner("ok"))
        self.assertEqual(adb.shell("192.0.2.2:5555", ["settings", "put", "secure", "x", "a;$(id) b"]), "ok")
        argv, kw = self.calls[0]
        self.assertEqual(argv[1:5], ["-s", "192.0.2.2:5555", "shell", "-n"])
        self.assertEqual(argv[-1], "settings put secure x 'a;$(id) b'")
        self.assertFalse(kw["shell"])
        self.assertEqual(kw["timeout"], 20)
        with self.assertRaises(AdbError):
            adb.shell("-d", ["getprop"])

    def test_timeout_and_nonzero_are_errors(self):
        adb = Adb("adb", self.runner(returncode=1, stderr="unauthorized"))
        with self.assertRaisesRegex(AdbError, "unauthorized"):
            adb.version()
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("adb", 10)
        with self.assertRaisesRegex(AdbError, "yanıt vermedi"):
            Adb("adb", timeout).version()

    def test_exit_zero_connection_failure_is_error(self):
        with self.assertRaises(AdbError):
            Adb("adb", self.runner("failed to connect to 1.2.3.4:5555")).connect("1.2.3.4:5555")

    def test_oversized_output_is_error_not_partial_parse(self):
        with self.assertRaisesRegex(AdbError, "8 MB"):
            Adb("adb", self.runner("x" * (8 * 1024 * 1024 + 1))).version()

    def test_pairing_secret_not_in_argv(self):
        adb = Adb("adb", self.runner("Successfully paired to 1.2.3.4:37000"))
        adb.pair("1.2.3.4:37000", "123456")
        self.assertNotIn("123456", self.calls[0][0])
        self.assertEqual(self.calls[0][1]["input"], "123456\n")
        with self.assertRaises(AdbError):
            adb.pair("1.2.3.4:37000", "12345;id")

    def test_devices_and_discovery(self):
        rows = Adb("adb", self.runner("List of devices attached\naaa device product:x model:TV\nbbb unauthorized\nccc offline\n")).devices()
        self.assertEqual([row["state"] for row in rows], ["device", "unauthorized", "offline"])
        rows = Adb("adb", self.runner("List of discovered mdns services\nTV _adb-tls-connect._tcp. 192.0.2.2:33333\nBad _adb-tls-connect._tcp. example.com:5555")).discover()
        self.assertEqual(len(rows), 1)

    def test_install_requires_success_marker(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "app.apk"
            path.write_bytes(b"test fixture")
            with self.assertRaises(AdbError):
                Adb("adb", self.runner("Failure [INSTALL_FAILED]")).install("device1", path)


if __name__ == "__main__":
    unittest.main()
