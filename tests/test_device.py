import unittest

from tvbakim.adb import AdbError
from tvbakim.catalog import TCL_PROFILE
from tvbakim.device import Device


PROPS = """[ro.product.manufacturer]: [TCL]
[ro.product.model]: [Smart TV]
[ro.product.device]: [BeyondTV4]
[ro.board.platform]: [rtd288o]
[ro.build.version.release]: [11]
[ro.build.version.sdk]: [30]
[ro.build.fingerprint]: [TCL/test/fingerprint]
[ro.serialno]: [real-unique-serial]
"""


class FakeAdb:
    def __init__(self, replies=None):
        self.replies = {("getprop",): PROPS, ("pm", "list", "features"): "feature:android.software.leanback", ("am", "get-current-user"): "0"}
        self.replies.update(replies or {})
    def shell(self, serial, args, timeout=20):
        reply = self.replies.get(tuple(args), "")
        if isinstance(reply, Exception):
            raise reply
        return reply


class DeviceTests(unittest.TestCase):
    def test_exact_profile_and_endpoint_independent_identity(self):
        a = Device(FakeAdb(), "1.2.3.4:5555").inspect()
        b = Device(FakeAdb(), "4.3.2.1:5555").inspect()
        self.assertEqual(a["identity"]["profile"], TCL_PROFILE)
        self.assertEqual(a["identity"]["serial_hash"], b["identity"]["serial_hash"])
        self.assertNotIn("real-unique-serial", str(a))
        self.assertTrue(a["capabilities"]["is_tv"])
        other = Device(FakeAdb({("getprop",): PROPS.replace("[11]", "[12]")}), "a").inspect()
        self.assertEqual(other["identity"]["profile"], "generic")

    def test_missing_identity_does_not_hash_network_endpoint(self):
        result = Device(FakeAdb({("getprop",): PROPS.replace("[real-unique-serial]", "[]")}), "1.2.3.4:5555").inspect()
        self.assertIsNone(result["identity"]["serial_hash"])
        self.assertFalse(result["capabilities"]["stable_identity"])
        result = Device(FakeAdb({("getprop",): PROPS.replace("[TCL/test/fingerprint]", "[]")}), "a").inspect()
        self.assertFalse(result["capabilities"]["stable_identity"])

    def test_setting_absent_and_literal_null_distinguished(self):
        device = Device(FakeAdb({("settings", "--user", "0", "list", "secure"): "x=null\ny=one=two\nempty="}), "a")
        self.assertEqual(device.read_setting("secure", "x"), {"present": True, "value": "null"})
        self.assertEqual(device.read_setting("secure", "missing"), {"present": False, "value": None})
        self.assertEqual(device.read_setting("secure", "y")["value"], "one=two")
        self.assertEqual(device.read_setting("secure", "empty")["value"], "")

    def test_exact_package_states_and_user_zero_only(self):
        for number, state in enumerate(["default", "enabled", "disabled", "disabled-user", "disabled-until-used"]):
            raw = f"  User 10: installed=true enabled=1\n  User 0: installed=true hidden=false enabled={number}\n"
            device = Device(FakeAdb({("dumpsys", "package", "com.tcl.browser"): raw}), "a")
            self.assertEqual(device.package_state("com.tcl.browser"), state)
        with self.assertRaises(AdbError):
            Device(FakeAdb(), "a").package_state("com.tcl.browser")

    def test_unknown_and_protected_and_phone_never_eligible(self):
        ids = ["com.tcl.browser", "com.google.android.katniss", "com.unknown.app"]
        replies = {("pm", "list", "packages", "--user", "0"): "\n".join("package:" + x for x in ids),
                   ("dumpsys", "package", "packages"): "\n".join(f"  Package [{x}] (abc):\n    User 0: installed=true enabled=0" for x in ids)}
        rows = Device(FakeAdb(replies), "a").packages()
        eligible = [row["id"] for row in rows if row["eligible"]]
        self.assertEqual(eligible, ["com.tcl.browser"])
        replies[("pm", "list", "features")] = "feature:android.hardware.telephony"
        self.assertFalse(any(row["eligible"] for row in Device(FakeAdb(replies), "a").packages()))

    def test_missing_health_data_is_not_zero_or_success(self):
        result = Device(FakeAdb({("cat", "/proc/meminfo"): AdbError("permission denied")}), "a").health()
        self.assertIsNone(result["memory"]["total_kb"])
        self.assertIsNone(result["events"]["counts"]["am_anr"])
        self.assertEqual(len(result["read_errors"]), 1)

    def test_health_parses_metrics_and_bounded_evidence(self):
        replies = {("cat", "/proc/uptime"): "120.5 55", ("cat", "/proc/meminfo"): "MemTotal: 2000 kB\nMemAvailable: 100 kB\nSwapTotal: 100 kB\nSwapFree: 40 kB",
                   ("df", "-k", "/data"): "Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/block/dm-1 1000 950 50 95% /data",
                   ("logcat", "-d", "-b", "events", "-t", "500"): "am_anr: sample\nam_kill: sample",
                   ("logcat", "-d", "-b", "main", "-b", "system", "-t", "500"): "\n".join(f"09-29 17:26:{x:02d}.000 TclPowerManagerService: wait CI cam work done,now doing for RTK" for x in range(30))}
        result = Device(FakeAdb(replies), "a").health()
        self.assertEqual(result["uptime_seconds"], 120.5)
        self.assertEqual(result["memory"]["swap_used_kb"], 60)
        self.assertEqual(result["storage"]["used_percent"], 95)
        self.assertEqual(len(result["cam_evidence_lines"]), 12)
        self.assertTrue(result["cam_wait_evidence"])

    def test_single_normal_cam_transition_not_persistent_fault(self):
        replies = {("logcat", "-d", "-b", "main", "-b", "system", "-t", "500"): "09-29 17:26:18.000 TclPowerManagerService: wait CI cam work done,now doing for RTK"}
        self.assertFalse(Device(FakeAdb(replies), "a").health()["cam_wait_evidence"])

    def test_separate_cam_cycles_and_gaps_not_persistent_fault(self):
        command = ("logcat", "-d", "-b", "main", "-b", "system", "-t", "500")
        marker = "TclPowerManagerService: wait CI cam work done,now doing for RTK"
        logs = "\n".join(f"09-29 17:26:{i * 3:02d}.000 {marker}" for i in range(8))
        self.assertFalse(Device(FakeAdb({command: logs}), "a").health()["cam_wait_evidence"])
        logs = "\n".join(f"09-29 17:26:{i:02d}.000 waitCICamSuspend start\n09-29 17:26:{i:02d}.100 {marker}" for i in range(8))
        self.assertFalse(Device(FakeAdb({command: logs}), "a").health()["cam_wait_evidence"])

    def test_secondary_or_unknown_user_blocks_owner_capability(self):
        for value in ["10", "", "Error: denied"]:
            with self.subTest(value=value):
                result = Device(FakeAdb({("am", "get-current-user"): value}), "a").inspect()
                self.assertFalse(result["capabilities"]["owner_user"])


if __name__ == "__main__":
    unittest.main()
