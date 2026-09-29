"""Bounded ADB transport. All local invocations use argv and no shell."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys


class AdbError(RuntimeError):
    pass


def managed_adb_directory():
    """Per-user Windows tools; never alters the machine PATH or SDK folders."""
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "TVCare" / "tools" / "platform-tools"


def validate_endpoint(endpoint: str) -> str:
    """Accept explicit IPv4, bracketed IPv6 or localhost, always with a port."""
    if not isinstance(endpoint, str) or len(endpoint) > 100:
        raise AdbError("IP ve port gerekli (örnek: 192.0.2.10:5555).")
    match = re.fullmatch(r"(?:\[([^\]]+)\]|([^:\s]+)):(\d{1,5})", endpoint)
    if not match:
        raise AdbError("Geçersiz adres: IP:port veya [IPv6]:port kullanın.")
    host = match.group(1) or match.group(2)
    if host == "localhost" and match.group(1):
        raise AdbError("Köşeli parantez yalnızca IPv6 adreslerinde kullanılabilir.")
    if host != "localhost":
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError as exc:
            raise AdbError("Yalnızca IP adresi veya localhost desteklenir.") from exc
        if "%" in host or (parsed.version == 6) != bool(match.group(1)):
            raise AdbError("IPv6 adresini köşeli paranteze alın.")
    if not 1 <= int(match.group(3)) <= 65535:
        raise AdbError("Port 1–65535 aralığında olmalı.")
    return endpoint


def _serial(serial: str) -> str:
    if not isinstance(serial, str) or not re.fullmatch(r"[A-Za-z0-9_.:\[\]%-]{1,200}", serial) or serial.startswith("-"):
        raise AdbError("Geçersiz cihaz kimliği.")
    return serial


class Adb:
    def __init__(self, binary=None, runner=None):
        self._runner = runner or subprocess.run
        self.path = self._locate(binary)

    @staticmethod
    def _locate(binary):
        if binary:
            return shutil.which(str(binary)) or str(Path(binary).expanduser())
        if os.environ.get("TVCARE_ADB"):
            configured = os.environ["TVCARE_ADB"]
            return shutil.which(configured) or str(Path(configured).expanduser())
        executable = "adb.exe" if os.name == "nt" else "adb"
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(str(Path(sys.executable).resolve().parent / "platform-tools" / executable))
        if getattr(sys, "_MEIPASS", None):
            candidates.append(str(Path(sys._MEIPASS) / "platform-tools" / executable))
        candidates.append(str(Path(__file__).resolve().parent.parent / "platform-tools" / executable))
        if os.name == "nt":
            candidates.append(str(managed_adb_directory() / executable))
        candidates.append(shutil.which("adb"))
        for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            if os.environ.get(name):
                candidates.append(str(Path(os.environ[name]) / "platform-tools" / executable))
        candidates.extend([
            str(Path.home() / "Library/Android/sdk/platform-tools" / executable),
            str(Path.home() / "Android/Sdk/platform-tools" / executable),
            str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Android/Sdk/platform-tools" / executable),
        ])
        return next((p for p in candidates if p and Path(p).is_file()), None)

    def available(self):
        return bool(self.path and Path(self.path).is_file() and (os.name == "nt" or os.access(self.path, os.X_OK)))

    def _run(self, args, timeout=20, input_text=None):
        if not self.path:
            raise AdbError("ADB bulunamadı. Android Platform Tools kurun veya TVCARE_ADB yolunu belirtin.")
        try:
            result = self._runner([self.path, *args], shell=False, text=True,
                                  encoding="utf-8", errors="replace", capture_output=True,
                                  timeout=timeout, input=input_text)
        except subprocess.TimeoutExpired as exc:
            raise AdbError(f"ADB işlemi {timeout} saniyede yanıt vermedi.") from exc
        except OSError as exc:
            raise AdbError(f"ADB çalıştırılamadı: {exc}") from exc
        if len(result.stdout or "") > 8 * 1024 * 1024 or len(result.stderr or "") > 8 * 1024 * 1024:
            raise AdbError("ADB çıktısı 8 MB sınırını aştı; eksik veriyle işlem yapılmadı.")
        output = (result.stdout or "").replace("\r", "").strip()
        if result.returncode:
            detail = (result.stderr or output or "Bilinmeyen ADB hatası").strip()[:1500]
            raise AdbError(detail)
        return output

    def version(self):
        return self._run(["version"], timeout=10)

    def devices(self):
        result = []
        for line in self._run(["devices", "-l"]).splitlines():
            fields = line.split()
            if len(fields) < 2 or line.startswith(("List of devices", "*")):
                continue
            if fields[1] not in {"device", "offline", "unauthorized", "recovery", "sideload", "bootloader", "no"}:
                continue
            result.append({"serial": fields[0], "state": fields[1], "details": " ".join(fields[2:])})
        return result

    def discover(self):
        result = []
        for line in self._run(["mdns", "services"]).splitlines():
            fields = line.split()
            if len(fields) < 3 or not fields[1].startswith("_adb"):
                continue
            try:
                endpoint = validate_endpoint(fields[2])
            except AdbError:
                continue
            result.append({"name": fields[0], "endpoint": endpoint, "kind": fields[1]})
        return result

    def connect(self, endpoint):
        output = self._run(["connect", validate_endpoint(endpoint)], timeout=20)
        if not re.search(r"(?:already )?connected to ", output, re.I):
            raise AdbError(output or "ADB bağlantısı doğrulanamadı.")
        return output

    def pair(self, endpoint, code):
        endpoint = validate_endpoint(endpoint)
        if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
            raise AdbError("Eşleştirme kodu 6 rakam olmalı.")
        # Send via stdin: do not expose the pairing code in the process argv.
        output = self._run(["pair", endpoint], timeout=30, input_text=code + "\n")
        if "successfully paired" not in output.lower():
            raise AdbError(output or "Eşleştirme doğrulanamadı.")
        return output

    def shell(self, serial, args, timeout=20):
        if not isinstance(args, list) or not args or any(not isinstance(a, str) or "\x00" in a for a in args):
            raise AdbError("Kabuk komutu metin bağımsız değişkenleri listesi olmalı.")
        return self._run(["-s", _serial(serial), "shell", "-n", shlex.join(args)], timeout=timeout)

    def install(self, serial, apk):
        path = Path(apk).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".apk":
            raise AdbError("APK dosyası bulunamadı.")
        output = self._run(["-s", _serial(serial), "install", "-r", str(path)], timeout=120)
        if not re.search(r"^Success\s*$", output, re.M):
            raise AdbError(output or "APK kurulumu doğrulanamadı.")
        return output
