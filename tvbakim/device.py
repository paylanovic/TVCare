"""Read-only Android TV inspection with explicit missing-evidence handling."""
from __future__ import annotations

import hashlib
import re

from .adb import AdbError
from .catalog import TCL_PROFILE, metadata

PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\Z")
STATES = {"0": "default", "1": "enabled", "2": "disabled", "3": "disabled-user", "4": "disabled-until-used"}


def validate_package(package):
    if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
        raise AdbError("Geçersiz paket adı.")
    return package


class Device:
    def __init__(self, adb, serial):
        self.adb = adb
        self.serial = serial
        self._inspection = None

    def _shell(self, args, timeout=20):
        return self.adb.shell(self.serial, args, timeout=timeout)

    def inspect(self):
        raw = self._shell(["getprop"])
        props = dict(re.findall(r"^\[([^\]]+)\]: \[(.*)\]$", raw, re.M))
        if not props:
            raise AdbError("Cihaz özellikleri okunamadı; kimlik doğrulanamıyor.")
        fields = {"manufacturer": "ro.product.manufacturer", "model": "ro.product.model", "device": "ro.product.device",
                  "platform": "ro.board.platform", "android": "ro.build.version.release", "sdk": "ro.build.version.sdk", "fingerprint": "ro.build.fingerprint"}
        identity = {name: props.get(prop, "") for name, prop in fields.items()}
        serial = props.get("ro.serialno", "").strip()
        if serial.lower() in {"", "unknown", "null", "none", "0123456789abcdef"}:
            serial = props.get("ro.boot.serialno", "").strip()
        stable = (serial.lower() not in {"", "unknown", "null", "none", "0123456789abcdef"}
                  and bool(identity["fingerprint"].strip()))
        identity["serial_hash"] = hashlib.sha256((serial + "\n" + identity["fingerprint"]).encode()).hexdigest() if stable else None
        exact_tcl = (identity["manufacturer"].lower() == "tcl" and identity["device"].lower() == "beyondtv4"
                     and identity["platform"].lower() == "rtd288o" and identity["android"] == "11" and identity["sdk"] == "30")
        identity["profile"] = TCL_PROFILE if exact_tcl else "generic"
        errors = []
        try:
            features = self._shell(["pm", "list", "features"])
            is_tv = any(line.strip() in {"feature:android.software.leanback", "feature:android.hardware.type.television"} for line in features.splitlines())
        except AdbError as exc:
            is_tv = False
            errors.append(str(exc))
        try:
            user_raw = self._shell(["am", "get-current-user"]).strip()
            current_user = int(user_raw) if re.fullmatch(r"\d+", user_raw) else None
        except AdbError as exc:
            current_user = None
            errors.append(str(exc))
        self._inspection = {"identity": identity, "capabilities": {"stable_identity": stable, "is_tv": is_tv,
                            "current_user": current_user, "owner_user": current_user == 0}, "read_errors": errors}
        return self._inspection

    def read_setting(self, namespace, key):
        if namespace not in {"global", "secure", "system"} or not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", key):
            raise AdbError("Geçersiz ayar adı veya alanı.")
        # settings get cannot distinguish absent keys from a literal value of "null".
        raw = self._shell(["settings", "--user", "0", "list", namespace])
        if re.search(r"(?i)(permission denial|securityexception|error:|exception occurred)", raw):
            raise AdbError("Ayar listesi okunamadı.")
        for line in raw.splitlines():
            name, separator, value = line.partition("=")
            if separator and name == key:
                return {"present": True, "value": value}
        return {"present": False, "value": None}

    @staticmethod
    def _state_from_dump(raw):
        match = re.search(r"^\s*User 0:([^\n]*)", raw, re.M)
        if not match or not re.search(r"\binstalled=true\b", match.group(1)):
            raise AdbError("Paketin kullanıcı 0 durumu doğrulanamadı.")
        state = re.search(r"\benabled=([0-4])\b", match.group(1))
        if not state:
            raise AdbError("Paketin etkinlik durumu okunamadı.")
        return STATES[state.group(1)]

    def package_state(self, package):
        return self._state_from_dump(self._shell(["dumpsys", "package", validate_package(package)], timeout=30))

    def packages(self):
        inspection = self._inspection or self.inspect()
        raw = self._shell(["pm", "list", "packages", "--user", "0"])
        installed = sorted(set(re.findall(r"^package:([A-Za-z][A-Za-z0-9_.]+)$", raw, re.M)))
        if not installed:
            raise AdbError("Kurulu paket listesi okunamadı.")
        disabled = set(re.findall(r"^package:(\S+)$", self._shell(["pm", "list", "packages", "-d", "--user", "0"]), re.M))
        # One bounded dumpsys call avoids hundreds of per-package remote round trips.
        dump_errors = []
        try:
            dump = self._shell(["dumpsys", "package", "packages"], timeout=45)
        except AdbError as exc:
            dump = ""
            dump_errors.append(str(exc))
        blocks = re.split(r"^\s*Package \[([^\]]+)\].*$", dump, flags=re.M)
        states = {}
        for index in range(1, len(blocks) - 1, 2):
            try:
                states[blocks[index]] = self._state_from_dump(blocks[index + 1])
            except AdbError:
                pass
        result = []
        for package in installed:
            info = metadata(package, inspection["identity"]["profile"])
            state = states.get(package, "unknown")
            if not inspection["capabilities"]["is_tv"]:
                info.update(eligible=False, reason="Android TV özelliği doğrulanamadı.")
            elif not inspection["capabilities"]["stable_identity"]:
                info.update(eligible=False, reason="Kalıcı cihaz kimliği okunamadı.")
            elif not inspection["capabilities"].get("owner_user"):
                info.update(eligible=False, reason="TV'nin ana kullanıcı profiline (kullanıcı 0) geçin.")
            elif state == "unknown":
                info.update(eligible=False, reason="Paketin geri alınabilir etkinlik durumu okunamadı.")
            result.append({"id": package, "enabled": package not in disabled, "state": state, **info})
        return result

    def health(self):
        errors = []
        def read(args, timeout=20):
            try:
                return self._shell(args, timeout)
            except AdbError as exc:
                errors.append({"source": " ".join(args), "error": str(exc)[:300]})
                return ""
        uptime = read(["cat", "/proc/uptime"])
        try:
            uptime_seconds = float(uptime.split()[0])
        except (ValueError, IndexError):
            uptime_seconds = None
        mem = dict((key, int(value)) for key, value in re.findall(r"^(\w+):\s+(\d+)\s+kB", read(["cat", "/proc/meminfo"]), re.M))
        memory = {"total_kb": mem.get("MemTotal"), "available_kb": mem.get("MemAvailable"), "free_kb": mem.get("MemFree"), "swap_total_kb": mem.get("SwapTotal"), "swap_free_kb": mem.get("SwapFree")}
        memory["swap_used_kb"] = max(0, mem["SwapTotal"] - mem["SwapFree"]) if "SwapTotal" in mem and "SwapFree" in mem else None
        storage = {"total_kb": None, "used_kb": None, "available_kb": None, "used_percent": None}
        for line in read(["df", "-k", "/data"]).splitlines():
            match = re.search(r"\s(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%\s+/data\s*$", line)
            if match:
                storage = dict(zip(storage, map(int, match.groups())))
        event_raw = read(["logcat", "-d", "-b", "events", "-t", "500"], timeout=25)
        event_counts = {tag: len(re.findall(r"\b" + tag + r"\b", event_raw)) if event_raw else None for tag in ("am_anr", "am_crash", "am_kill", "am_proc_start", "killinfo")}
        system_logs = read(["logcat", "-d", "-b", "main", "-b", "system", "-t", "500"], timeout=25)
        candidate_lines = [line[:350] for line in system_logs.splitlines() if re.search(r"waitCiCamForRtk|wait.*CI.*CAM|wait.*cam_suspend|CICam_State", line, re.I)]
        evidence = candidate_lines[-12:]
        wait_times = []
        wait_groups = []
        for line in candidate_lines:
            if "waitCICamSuspend start" in line:
                if wait_times:
                    wait_groups.append(wait_times)
                wait_times = []
            if "wait CI cam work done,now doing for RTK" not in line:
                continue
            match = re.search(r"\b(\d{2}):(\d{2}):(\d{2}\.\d+)\b", line)
            if match:
                hours, minutes, seconds = map(float, match.groups())
                stamp = hours * 3600 + minutes * 60 + seconds
                if wait_times and (stamp - wait_times[-1]) % 86400 > 2:
                    wait_groups.append(wait_times)
                    wait_times = []
                wait_times.append(stamp)
        # A normal transition emits CAM messages too. Require observed waiting
        # over at least 5 seconds, not merely a matching keyword.
        if wait_times:
            wait_groups.append(wait_times)
        durations = [(group[-1] - group[0]) % 86400 for group in wait_groups if len(group) >= 6]
        wait_duration = max(durations) if durations else None
        persistent_wait = wait_duration is not None and 5 <= wait_duration < 3600
        suspend = read(["getprop", "rtk.hal.cam_suspend"])
        cam_state = read(["getprop", "rtk.hal.CICam_State"])
        warnings = []
        if memory["total_kb"] and memory["available_kb"] is not None and memory["available_kb"] / memory["total_kb"] < .1:
            warnings.append({"code": "low_memory", "message": "Ölçüm anında kullanılabilir bellek %10'un altında.", "evidence": {"available_kb": memory["available_kb"], "total_kb": memory["total_kb"]}})
        if storage["used_percent"] is not None and storage["used_percent"] >= 90:
            warnings.append({"code": "low_storage", "message": "Veri alanının en az %90'ı dolu.", "evidence": storage})
        if event_counts["am_anr"]:
            warnings.append({"code": "anr", "message": "Son 500 olay kaydında yanıt vermeme olayı görüldü.", "evidence": {"count": event_counts["am_anr"]}})
        if evidence:
            warnings.append({"code": "cam_wait", "message": "CAM beklemesine ilişkin kayıt bulundu; tek başına kalıcı kilit kanıtı değildir.", "evidence": evidence})
        return {"uptime_seconds": uptime_seconds, "memory": memory, "storage": storage,
                "events": {"scope": "last_500_entries", "counts": event_counts}, "warnings": warnings,
                "cam_suspend": suspend or None, "ci_cam_state": cam_state or None,
                "cam_wait_evidence": persistent_wait, "cam_wait_duration_seconds": wait_duration,
                "cam_evidence_lines": evidence, "read_errors": errors}
