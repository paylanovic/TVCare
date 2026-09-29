#!/usr/bin/env python3
"""Build the current host's TVCare distribution without fetching any dependencies."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import zipfile
import unittest
import re

ROOT = Path(__file__).resolve().parents[1]


def version():
    text = (ROOT / 'tvbakim/__init__.py').read_text(encoding='utf-8')
    match = re.search(r"__version__\s*=\s*['\"]([0-9]+\.[0-9]+\.[0-9]+)['\"]", text)
    if not match:
        raise RuntimeError('A stable semantic version is required for releases.')
    return match.group(1)


def architecture():
    machine = platform.machine().lower()
    return {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)


def test_summary(result):
    skipped = [{'test': test.id(), 'reason': reason} for test, reason in result.skipped]
    status = 'PASS_WITH_SKIPS' if skipped else 'PASS'
    if not result.wasSuccessful() or result.testsRun == len(skipped):
        status = 'FAIL'
    return {'status': status, 'run': result.testsRun,
            'executed': result.testsRun - len(skipped), 'skipped': skipped,
            'failures': len(result.failures), 'errors': len(result.errors),
            'expected_failures': len(result.expectedFailures),
            'unexpected_successes': len(result.unexpectedSuccesses)}


def run_tests():
    sys.path.insert(0, str(ROOT))
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = test_summary(result)
    if summary['status'] == 'FAIL':
        raise RuntimeError('Tests failed; no release artifact was built.')
    return summary


def write_launchers(bundle):
    if os.name == 'nt':
        launchers = {
            'Start-TVCare.cmd': ('if /I "%~1"=="--demo" goto run\n'
                                '"%~dp0TVCare.exe" --setup\n'
                                'if errorlevel 1 goto failed\n'
                                ':run\n'
                                '"%~dp0TVCare.exe" %*\n'
                                'if errorlevel 1 goto failed\nexit /b 0\n'),
            'Install-Requirements.cmd': ('"%~dp0TVCare.exe" --setup %*\n'
                                         'if errorlevel 1 goto failed\n'
                                         'echo.\necho Ready. Open Start-TVCare.cmd to use TVCare.\n'
                                         'pause\nexit /b 0\n'),
            'Demo-TVCare.cmd': ('"%~dp0TVCare.exe" --demo %*\n'
                               'if errorlevel 1 goto failed\nexit /b 0\n'),
        }
        for name, body in launchers.items():
            (bundle / name).write_text('@echo off\nchcp 65001 >nul\n' + body +
                                      ':failed\necho.\necho TVCare could not complete this step.\n'
                                      'pause\nexit /b 1\n', encoding='utf-8', newline='\r\n')
    else:
        extension = '.command' if sys.platform == 'darwin' else '.sh'
        for name, arguments in [('TVCare', ''), ('Demo-TVCare', '--demo ')]:
            launcher = bundle / (name + extension)
            launcher.write_text('#!/bin/sh\ncd "$(dirname "$0")" || exit 1\n"./TVCare" ' + arguments + '"$@"\n'
                                'code=$?\nif [ "$code" -ne 0 ]; then echo "TVCare error: $code"; '
                                'printf "Press Enter to close..."; read answer; fi\nexit "$code"\n', encoding='utf-8')
            launcher.chmod(0o755)


def privacy_check(*arguments):
    subprocess.run([sys.executable, str(ROOT / 'scripts/privacy_check.py'), *map(str, arguments)],
                   cwd=ROOT, check=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform-tools', type=Path,
                        help='Optional explicit host platform-tools directory; upstream notices required.')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist', help='Output directory')
    parser.add_argument('--skip-tests', action='store_true', help='Build only; records tests as NOT_RUN')
    args = parser.parse_args(argv)
    if importlib.util.find_spec('PyInstaller') is None:
        parser.error('PyInstaller is missing. Install it in a build environment first (python -m pip install pyinstaller).')
    privacy_check('--source')
    release_version = version()
    apk = ROOT / 'resources/guard/kilit-koruyucu.apk'
    if not apk.is_file():
        parser.error('Guard APK missing. Build resources/guard/build.sh with your external signing key first.')
    env = os.environ.copy()
    env.pop('TVCARE_PLATFORM_TOOLS', None)
    if args.platform_tools:
        directory = args.platform_tools.expanduser().resolve()
        if not directory.is_dir():
            parser.error('--platform-tools must be an existing directory')
        env['TVCARE_PLATFORM_TOOLS'] = str(directory)
    tests = {'status': 'NOT_RUN', 'run': 0, 'executed': 0, 'skipped': []} if args.skip_tests else run_tests()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / 'build' / 'pyinstaller'
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--distpath', str(output), '--workpath', str(build_dir),
                    str(ROOT / 'packaging/tvcare.spec')], cwd=ROOT, check=True, env=env)
    bundle = output / 'TVCare'
    write_launchers(bundle)
    for name in ('README.md', 'README.en.md', 'LICENSE', 'SECURITY.md', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'):
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, bundle / name)
    license_source = ROOT / 'third_party' / 'licenses'
    license_manifest = json.loads((license_source / 'SOURCES.json').read_text(encoding='utf-8'))
    for notice in license_manifest['sources']:
        source = license_source / notice['file']
        if source.parent != license_source or hashlib.sha256(source.read_bytes()).hexdigest() != notice['sha256']:
            raise RuntimeError('An upstream runtime license notice is missing or has changed: ' + notice['file'])
    license_target = bundle / 'third_party' / 'licenses'
    license_target.mkdir(parents=True, exist_ok=True)
    for source in sorted(license_source.iterdir()):
        if source.is_file() and not source.is_symlink() and source.suffix in {'.txt', '.rst', '.md', '.json'}:
            shutil.copy2(source, license_target / source.name)
    docs = bundle / 'docs'
    docs.mkdir(exist_ok=True)
    for source in sorted((ROOT / 'docs').glob('*.md')):
        shutil.copy2(source, docs / source.name)
    screenshots = ROOT / 'docs' / 'screenshots'
    if screenshots.is_dir():
        (docs / 'screenshots').mkdir(exist_ok=True)
        for source in sorted(screenshots.glob('*.png')):
            if source.is_file() and not source.is_symlink():
                shutil.copy2(source, docs / 'screenshots' / source.name)
    forbidden = [p for p in bundle.rglob('*') if p.is_file() and
                 (p.suffix.lower() in {'.keystore', '.jks', '.pem', '.key'} or p.name == 'adbkey')]
    if forbidden:
        raise RuntimeError('Private key material found in output; distribution aborted.')
    metadata = {
        'product': 'TVCare', 'version': release_version, 'os': platform.system(),
        'architecture': architecture(), 'python': platform.python_version(),
        'tests': tests['status'], 'test_summary': tests,
        'live_device_tests': 'NOT_RUN', 'platform_tools_included': bool(args.platform_tools),
        'guard_apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
    }
    (bundle / 'BUILD.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    subprocess.run([sys.executable, str(ROOT / 'scripts/package_smoke.py'), '--bundle', str(bundle),
                    '--output', str(bundle / 'SMOKE.json')], cwd=ROOT, check=True, env=env)
    privacy_check('--bundle', bundle)
    manifest = []
    for path in sorted(bundle.rglob('*')):
        if path.is_file():
            manifest.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(bundle).as_posix()}')
    (bundle / 'SHA256SUMS').write_text('\n'.join(manifest) + '\n', encoding='utf-8')
    archive = output / f'TVCare-{release_version}-{platform.system().lower()}-{architecture()}.zip'
    # ZipInfo from filesystem retains Unix executable bits for the launch binary and ADB.
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as target:
        for path in sorted(bundle.rglob('*')):
            if path.is_symlink():
                info = zipfile.ZipInfo(path.relative_to(output).as_posix())
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                target.writestr(info, os.readlink(path))
            elif path.is_file():
                target.write(path, path.relative_to(output))
    privacy_check('--archive', archive)
    print(f'Built: {archive}\nSHA256: {hashlib.sha256(archive.read_bytes()).hexdigest()}')
    print('Live device validation: NOT_RUN. Build only applies to this host OS/architecture.')
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    raise SystemExit(main())
