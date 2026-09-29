"""Verified, user-local Windows prerequisite installation. Never contacts a TV.

Pin provenance: Google's repository2-1.xml, platform-tools stable 37.0.1,
Windows archive size 8044989 and SHA1 e03e78b1d80b396f1c3358e31251cb31740e1110.
SHA256 below was independently calculated from that HTTPS archive.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

from .adb import Adb, managed_adb_directory

PLATFORM_TOOLS_VERSION = "37.0.1"
PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools_r37.0.1-win.zip"
PLATFORM_TOOLS_SHA256 = "45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99"
PLATFORM_TOOLS_BYTES = 8044989
LICENSE_URL = "https://developer.android.com/studio/terms"
MANIFEST_NAME = "TVCARE-INSTALL.json"
REQUIRED_FILES = {"adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "NOTICE.txt", "source.properties"}
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_EXTRACT_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 256
DOWNLOAD_SECONDS = 120
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class SetupError(RuntimeError):
    """A recoverable setup problem suitable for display without a traceback."""


def probe_adb(path):
    """adb version does not enumerate devices or start the ADB server."""
    try:
        result = subprocess.run([str(path), "version"], shell=False, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError("ADB çalıştırılamadı. Dosyaların tamamını ZIP'ten çıkardığınızdan emin olun.") from exc
    output = result.stdout or ""
    if result.returncode or len(output) > 65536 or not re.search(r"^Android Debug Bridge version \d+\.\d+\.\d+", output, re.M):
        raise SetupError("ADB sürüm kontrolü başarısız. Kurulum yeniden denenebilir.")
    return output


class _GoogleRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname != "dl.google.com" or parsed.port not in (None, 443):
            raise SetupError("İndirme beklenmeyen bir adrese yönlendirildi; işlem durduruldu.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_archive(url, destination):
    """Stream a fixed HTTPS object with socket, elapsed-time and byte limits."""
    started = time.monotonic()
    opener = urllib.request.build_opener(_GoogleRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "TVCare prerequisite installer"})
    try:
        with opener.open(request, timeout=20) as response, Path(destination).open("xb") as output:
            if response.status != 200:
                raise SetupError("Google indirme sunucusu dosyayı gönderemedi. Daha sonra yeniden deneyin.")
            declared = response.headers.get("Content-Length")
            if declared and (not declared.isdecimal() or int(declared) > MAX_DOWNLOAD_BYTES):
                raise SetupError("İndirme boyutu güvenli sınırı aşıyor.")
            size = 0
            while True:
                if time.monotonic() - started > DOWNLOAD_SECONDS:
                    raise SetupError("İndirme zaman aşımına uğradı. İnternet bağlantısını kontrol edip yeniden deneyin.")
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise SetupError("İndirme boyutu güvenli sınırı aşıyor.")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except SetupError:
        raise
    except (OSError, urllib.error.URLError, http.client.HTTPException, ValueError) as exc:
        raise SetupError("Platform Tools indirilemedi. İnternet, güvenlik duvarı veya proxy ayarını kontrol edip yeniden deneyin.") from exc


def verify_archive(archive):
    path = Path(archive)
    if not path.is_file() or path.stat().st_size != PLATFORM_TOOLS_BYTES:
        raise SetupError("İndirilen dosyanın boyutu beklenen değerle uyuşmuyor; hiçbir program çalıştırılmadı.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != PLATFORM_TOOLS_SHA256:
        raise SetupError("SHA-256 doğrulaması başarısız; dosya kullanılmadı. Kurulumu yeniden deneyin.")


def _member_path(info):
    name = info.filename
    if (not name or "\x00" in info.orig_filename or any(char in name for char in '\\:<>"|?*') or name.startswith("/")
            or any(ord(char) < 32 for char in name)):
        raise SetupError("Arşivde güvenli olmayan bir dosya yolu var.")
    raw_parts = name.rstrip("/").split("/")
    if any(part in {"", ".", ".."} or part.endswith((".", " ")) or part.split(".")[0].upper() in WINDOWS_RESERVED for part in raw_parts):
        raise SetupError("Arşivde geçersiz Windows dosya yolu var.")
    path = PurePosixPath(*raw_parts)
    if path.parts[0] != "platform-tools":
        raise SetupError("Arşiv beklenen platform-tools klasörünün dışında dosya içeriyor.")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type not in (0, stat.S_IFREG, stat.S_IFDIR) or info.flag_bits & 1:
        raise SetupError("Arşivde bağlantı, özel veya şifreli dosya var; kurulum durduruldu.")
    if info.is_dir() and file_type == stat.S_IFREG or not info.is_dir() and file_type == stat.S_IFDIR:
        raise SetupError("Arşiv dosya türü tutarsız.")
    return path


def extract_archive(archive, staging):
    """Validate *all* members before extracting; never use ZipFile.extractall."""
    destination = Path(staging)
    try:
        with zipfile.ZipFile(archive) as source:
            infos = source.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS or sum(info.file_size for info in infos) > MAX_EXTRACT_BYTES:
                raise SetupError("Arşiv açılımı güvenli boyut sınırını aşıyor.")
            entries, seen = [], set()
            for info in infos:
                relative = _member_path(info)
                key = relative.as_posix().casefold()
                if key in seen:
                    raise SetupError("Arşivde tekrarlanan bir dosya yolu var.")
                seen.add(key)
                entries.append((info, relative))
            available = {path.as_posix() for info, path in entries if not info.is_dir()}
            if not {"platform-tools/" + name for name in REQUIRED_FILES}.issubset(available):
                raise SetupError("Arşiv ADB, gerekli DLL dosyaları veya lisans bilgisini içermiyor.")
            total = 0
            for info, relative in entries:
                target = destination.joinpath(*relative.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as stream, target.open("xb") as output:
                    while True:
                        chunk = stream.read(64 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > MAX_EXTRACT_BYTES:
                            raise SetupError("Arşiv açılımı güvenli boyut sınırını aşıyor.")
                        output.write(chunk)
            package = destination / "platform-tools"
            props = (package / "source.properties").read_text(encoding="utf-8")
            if not re.search(r"^Pkg\.Revision\s*=\s*" + re.escape(PLATFORM_TOOLS_VERSION) + r"\s*$", props, re.M):
                raise SetupError("Arşiv sürümü beklenen Platform Tools sürümüyle uyuşmuyor.")
            return package
    except SetupError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        raise SetupError("Platform Tools arşivi güvenli biçimde açılamadı; önceki kurulum korunuyor.") from exc


def _reject_managed_links(target):
    if target.exists() and not target.is_dir():
        raise SetupError("Kurulum klasörü yerine aynı adlı bir dosya var; dosya korunarak işlem durduruldu.")
    for path in (target, target.parent, target.parent.parent):
        if path.is_symlink():
            raise SetupError("Kurulum hedefi sembolik bağlantı olamaz.")
        if path.exists():
            attributes = getattr(path.stat(), "st_file_attributes", 0)
            if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise SetupError("Kurulum hedefi yönlendirilmiş bir Windows klasörü olamaz.")


@contextmanager
def _installation_lock(parent):
    with (parent / ".platform-tools-install.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SetupError("Başka bir önkoşul kurulumu çalışıyor. Bitince yeniden deneyin.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _publish(package, target):
    """Rename a fully verified directory; restore old files if publication fails."""
    backup = target.parent / (".platform-tools-backup-" + uuid.uuid4().hex)
    had_previous = target.exists()
    if had_previous:
        os.replace(target, backup)
    try:
        os.replace(package, target)
    except OSError:
        if had_previous:
            os.replace(backup, target)
        raise
    if had_previous:
        # A locked stale file is harmless; never turn a successful publish into
        # an apparent failure or destroy the newly installed working copy.
        shutil.rmtree(backup, ignore_errors=True)


def _is_bundled_adb(path):
    roots = [Path(__file__).resolve().parent.parent]
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    chosen = os.path.normcase(os.path.abspath(path))
    return any(chosen == os.path.normcase(os.path.abspath(root / "platform-tools" / "adb.exe")) for root in roots)


def install_requirements(accept_license=False, *, adb_binary=None, install_dir=None, existing_adb=None,
                         downloader=None, probe=None, input_fn=None, output=print, platform_name=None):
    """Return the usable ADB path; dependency hooks exist for isolated tests."""
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        raise SetupError("Otomatik önkoşul kurulumu Windows içindir. Bu sistemde Android Platform Tools kurulumunu kullanın.")
    probe = probe or probe_adb
    downloader = downloader or download_archive
    input_fn = input_fn or input
    adb = existing_adb if existing_adb is not None else Adb(adb_binary)
    if adb.path:
        try:
            probe(adb.path)
        except SetupError:
            if adb_binary or os.environ.get("TVCARE_ADB"):
                raise SetupError("Belirttiğiniz ADB yolu çalışmıyor. --adb veya TVCARE_ADB yolunu düzeltip yeniden deneyin.")
            if _is_bundled_adb(adb.path):
                raise SetupError("Uygulama yanındaki platform-tools klasöründeki ADB çalışmıyor. Bu klasörü kaldırın veya ZIP'in tamamını yeniden çıkarıp kurulumu tekrar çalıştırın.")
        else:
            output("ADB hazır. İnternet bağlantısı veya ek kurulum gerekmiyor.")
            return Path(adb.path)
    output("Google Android SDK Platform Tools " + PLATFORM_TOOLS_VERSION + " kurulacak (yaklaşık 8 MB).")
    output("Google Android SDK lisans koşulları: " + LICENSE_URL)
    if accept_license is not True:
        try:
            response = input_fn("Lisans koşullarını kabul edip indirmeyi başlatmak istiyor musunuz? [e/H]: ")
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupError("Kurulum iptal edildi. Lisans onayı verilmedi; hiçbir dosya indirilmedi.") from exc
        if response.strip().casefold() not in {"e", "evet", "y", "yes"}:
            raise SetupError("Kurulum iptal edildi. İstediğinizde yeniden çalıştırabilirsiniz.")
    target = Path(install_dir) if install_dir is not None else managed_adb_directory()
    try:
        _reject_managed_links(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with _installation_lock(target.parent):
            # Another process may have completed installation while the prompt
            # was open. Do not download or overwrite a now-working managed copy.
            if (target / "adb.exe").is_file():
                try:
                    probe(target / "adb.exe")
                except SetupError:
                    pass
                else:
                    output("ADB hazır. Mevcut kullanıcı kurulumu korunuyor.")
                    return target / "adb.exe"
            with tempfile.TemporaryDirectory(prefix=".platform-tools-stage-", dir=target.parent) as work:
                stage = Path(work)
                archive = stage / "download.zip"
                output("Google sunucusundan indiriliyor; ardından SHA-256 doğrulanacak…")
                downloader(PLATFORM_TOOLS_URL, archive)
                verify_archive(archive)
                package = extract_archive(archive, stage / "unpacked")
                files = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(package.rglob("*")) if p.is_file()}
                manifest = {"schema": 1, "version": PLATFORM_TOOLS_VERSION, "url": PLATFORM_TOOLS_URL,
                            "sha256": PLATFORM_TOOLS_SHA256, "files": files}
                (package / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                probe(package / "adb.exe")
                _reject_managed_links(target)
                _publish(package, target)
    except SetupError:
        raise
    except OSError as exc:
        raise SetupError("Kullanıcı klasörüne kurulum tamamlanamadı. Disk alanını ve dosya izinlerini kontrol edip yeniden deneyin.") from exc
    output("Önkoşullar hazır. TVCare'yi normal başlatma dosyasından açabilirsiniz.")
    return target / "adb.exe"


def run_setup(accept_license=False, *, adb_binary=None):
    print("TVCare önkoşul kurulumu")
    if getattr(sys, "frozen", False):
        print("Python ve TVCare'nin çalışma zamanı DLL dosyaları pakete dahildir; ayrıca kurmanız gerekmez.")
    else:
        print("Python çalışıyor. Hazır Windows paketi Python ve çalışma zamanı DLL dosyalarını içerir.")
    print("Bu adım TVCare arayüzünü açmaz ve TV'ye bağlanmaz.")
    try:
        install_requirements(accept_license, adb_binary=adb_binary)
        return 0
    except (SetupError, KeyboardInterrupt) as exc:
        print(str(exc) if str(exc) else "Kurulum iptal edildi. Yeniden deneyebilirsiniz.")
        return 1
