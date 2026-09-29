"""Run the actual Android shell loop with simulated properties and monotonic time.
No ADB invocation, real shutdown command, or wall clock waits occur.
"""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "resources/guard/kilit-koruyucu.sh"


@unittest.skipIf(os.name == "nt", "Android shell harness requires POSIX sh")
class GuardScriptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        (self.proc / "uptime").write_text("0.00 0.00\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, TVCARE_GUARD_DIR=str(self.root), TVCARE_PROC_DIR=str(self.proc),
                        TVCARE_GUARD_SCRIPT=str(SCRIPT), TVCARE_SCENARIO="fault", TVCARE_END="16",
                        PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", ""))
        self.command("flock", f'exec "{sys.executable}" -c "import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)"')
        self.command("sleep", '''read n rest < "$TVCARE_PROC_DIR/uptime"
n=${n%%.*}; n=$((n + $1)); echo "$n.00 0.00" > "$TVCARE_PROC_DIR/uptime"
[ "$n" -lt "$TVCARE_END" ] || touch "$TVCARE_GUARD_DIR/kilit-koruyucu.disabled"
exit 0''')
        self.command("getprop", '''read n rest < "$TVCARE_PROC_DIR/uptime"; n=${n%%.*}
case "$1" in
rtk.hal.cam_suspend)
  if [ "$TVCARE_SCENARIO" = transient ] && [ "$n" -ge 4 ]; then echo end
  elif [ "$TVCARE_SCENARIO" = reset ] && [ "$n" -ge 3 ] && [ "$n" -lt 6 ]; then echo end
  else echo start; fi;;
sys.tcl.powerstatus) if [ "$TVCARE_SCENARIO" = awake ]; then echo on; else echo suspend; fi;;
rtk.hal.CICam_State) if [ "$TVCARE_SCENARIO" = cam_ready ]; then echo true; else echo false; fi;;
esac''')
        self.command("timeout", 'shift; "$@"')
        for name in ("reboot", "svc"):
            self.command(name, f'echo "{name} $(cat "$TVCARE_PROC_DIR/uptime") $*" >> "$TVCARE_GUARD_DIR/events"')

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_guard(self, *args, **env):
        return subprocess.run(["sh", str(SCRIPT), *args], env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=30, check=True)

    def events(self):
        path = self.root / "events"
        return path.read_text().splitlines() if path.exists() else []

    def test_fault_requires_five_elapsed_seconds_and_cooldown(self):
        self.run_guard(TVCARE_END="80")
        requests = [line for line in self.events() if line.startswith("reboot")]
        self.assertEqual(len(requests), 2)
        self.assertIn("5.00", requests[0])
        self.assertGreaterEqual(float(requests[1].split()[1]), 67)
        self.assertFalse((self.root / "kilit-koruyucu.pid").exists())

    def test_fractional_uptime_never_rounds_threshold_down(self):
        (self.proc / "uptime").write_text("0.80 0.00\n")
        self.command("sleep", '\n'.join([
            'read n rest < "$TVCARE_PROC_DIR/uptime"',
            'n=${n%%.*}; n=$((n + $1)); echo "$n.20 0.00" > "$TVCARE_PROC_DIR/uptime"',
            '[ "$n" -lt "$TVCARE_END" ] || touch "$TVCARE_GUARD_DIR/kilit-koruyucu.disabled"',
            'exit 0']))
        self.run_guard()
        self.assertIn("6.20", self.events()[0])

    def test_transient_fault_never_shuts_down(self):
        self.run_guard(TVCARE_SCENARIO="transient")
        self.assertEqual(self.events(), [])

    def test_awake_tv_never_shuts_down(self):
        self.run_guard(TVCARE_SCENARIO="awake")
        self.assertEqual(self.events(), [])

    def test_ready_cam_never_shuts_down(self):
        self.run_guard(TVCARE_SCENARIO="cam_ready")
        self.assertEqual(self.events(), [])

    def test_fault_timer_resets_when_condition_clears(self):
        self.run_guard(TVCARE_SCENARIO="reset")
        self.assertIn("11.00", self.events()[0])

    def test_disabled_prevents_start_and_enable_is_explicit(self):
        self.assertEqual(self.run_guard("--stop").stdout.strip(), "DISABLED")
        self.run_guard()
        self.assertEqual(self.events(), [])
        self.assertEqual(self.run_guard("--status").stdout.strip(), "DISABLED")
        self.run_guard("--enable")
        self.assertEqual(self.run_guard("--status").stdout.strip(), "STOPPED")

    def test_reused_pid_is_not_running_and_stale_lock_recovers(self):
        lock = self.root / "kilit-koruyucu.lock"
        lock.mkdir()
        (lock / "pid").write_text("123")
        (self.root / "kilit-koruyucu.pid").write_text("123")
        process = self.proc / "123"
        process.mkdir()
        (process / "cmdline").write_bytes(b"unrelated\0process\0")
        self.assertEqual(self.run_guard("--status").stdout.strip(), "STOPPED")
        self.run_guard()
        self.assertTrue(self.events())

    def test_existing_verified_guard_prevents_duplicate(self):
        lock = self.root / "kilit-koruyucu.lock"
        lock.mkdir()
        (lock / "pid").write_text("123")
        (self.root / "kilit-koruyucu.pid").write_text("123")
        process = self.proc / "123"
        process.mkdir()
        (process / "cmdline").write_bytes(b"sh\0" + str(SCRIPT).encode() + b"\0")
        self.assertEqual(self.run_guard("--status").stdout.strip(), "RUNNING:123")
        self.run_guard()
        self.assertEqual(self.events(), [])

    def test_disabled_live_process_is_stopping_not_stopped(self):
        lock = self.root / "kilit-koruyucu.lock"
        lock.mkdir()
        (lock / "pid").write_text("123")
        (self.root / "kilit-koruyucu.pid").write_text("123")
        process = self.proc / "123"
        process.mkdir()
        (process / "cmdline").write_bytes(b"sh\0" + str(SCRIPT).encode() + b"\0")
        self.run_guard("--stop")
        self.assertEqual(self.run_guard("--status").stdout.strip(), "STOPPING:123")

    def test_running_legacy_guard_is_not_mistaken_for_new_guard(self):
        (self.root / "kilit-koruyucu.pid").write_text("123")
        process = self.proc / "123"
        process.mkdir()
        (process / "cmdline").write_bytes(b"sh\0" + str(SCRIPT).encode() + b"\0")
        self.assertEqual(self.run_guard("--status").stdout.strip(), "LEGACY")
        self.run_guard()
        self.assertEqual(self.events(), [])

    def test_log_is_rotated_at_bounded_size(self):
        (self.root / "kilit-koruyucu.log").write_text("x" * 66000)
        self.run_guard()
        self.assertTrue((self.root / "kilit-koruyucu.log.1").exists())
        self.assertLess((self.root / "kilit-koruyucu.log").stat().st_size, 65536)

    def test_stop_before_threshold_prevents_request(self):
        self.run_guard(TVCARE_END="4")
        self.assertEqual(self.events(), [])


if __name__ == "__main__":
    unittest.main()
