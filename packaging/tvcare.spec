# Build on each target OS/architecture. Only explicitly selected runtime resources.
from pathlib import Path
import os

root = Path(SPECPATH).parent
apk = root / 'resources' / 'guard' / 'kilit-koruyucu.apk'
if not apk.is_file():
    raise SystemExit('Build and verify the TVCare guard APK before packaging.')
datas = [
    (str(root / 'tvbakim' / 'static'), 'tvbakim/static'),
    (str(apk), 'resources/guard'),
    (str(root / 'resources' / 'guard' / 'kilit-koruyucu.sh'), 'resources/guard'),
]
# Binary handling preserves executable flags and finds relevant linked libraries.
binaries = []
platform_tools = os.environ.get('TVCARE_PLATFORM_TOOLS')
if platform_tools:
    directory = Path(platform_tools).resolve()
    executable = directory / ('adb.exe' if os.name == 'nt' else 'adb')
    if not executable.is_file():
        raise SystemExit('The provided platform-tools folder has no host ADB executable.')
    notices = [p for p in directory.iterdir() if p.is_file() and
               (p.name.upper().startswith(('NOTICE', 'LICENSE')) or p.name == 'source.properties')]
    if not any(p.name.upper().startswith(('NOTICE', 'LICENSE')) for p in notices):
        raise SystemExit('ADB distribution requires the upstream NOTICE/LICENSE files.')
    binaries.append((str(executable), 'platform-tools'))
    binaries.extend((str(p), 'platform-tools') for p in directory.glob('*.dll'))
    binaries.extend((str(p), 'platform-tools') for p in directory.glob('*.dylib'))
    binaries.extend((str(p), 'platform-tools') for p in directory.glob('*.so*'))
    datas.extend((str(p), 'platform-tools') for p in notices)

a = Analysis([str(root / 'tvbakim' / '__main__.py')], pathex=[str(root)],
             binaries=binaries, datas=datas, hiddenimports=[], hookspath=[],
             hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
# PyInstaller 6.22 rewrites Python co_filename to module-relative paths.
# package_smoke.py inspects all embedded code objects; privacy_check.py gates
# native binaries/resources too. Keep native stripping off for signed library integrity.
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='TVCare', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='TVCare')
