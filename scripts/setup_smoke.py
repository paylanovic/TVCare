#!/usr/bin/env python3
"""Windows-only frozen prerequisite setup smoke; never enumerates or connects to TVs.

The official pinned SDK download occurs only inside a disposable user profile.
Installed SDK files are never copied into the release archive or JSON evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.package_smoke import extract_archive, verify_manifest


class SetupSmokeError(RuntimeError):
    """Messages are fixed diagnostic codes, never raw child output or local paths."""


def isolated_environment(root, base=None):
    base = os.environ if base is None else base
    removed = {'PATH', 'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'TEMP', 'TMP',
               'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'ANDROID_USER_HOME', 'ANDROID_SDK_HOME',
               'TVCARE_ADB', 'ADB_VENDOR_KEYS', 'ADB_SERVER_SOCKET', 'ANDROID_ADB_SERVER_PORT',
               'SSL_CERT_FILE', 'SSL_CERT_DIR', 'REQUESTS_CA_BUNDLE'}
    env = {key: value for key, value in base.items() if key.upper() not in removed}
    paths = {'HOME': root / 'home', 'USERPROFILE': root / 'home',
             'LOCALAPPDATA': root / 'local-app-data', 'APPDATA': root / 'app-data',
             'TEMP': root / 'temp', 'TMP': root / 'temp'}
    for key, directory in paths.items():
        directory.mkdir(parents=True, exist_ok=True)
        env[key] = str(directory)
    system_root = next((v for k, v in base.items() if k.upper() == 'SYSTEMROOT'), r'C:\Windows')
    env['PATH'] = ntpath.join(system_root, 'System32')
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    return env


def offline_environment(env):
    blocked = {key: value for key, value in env.items()
               if key.upper() not in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'}}
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY'):
        blocked[key] = blocked[key.lower()] = 'http://127.0.0.1:9'
    blocked['NO_PROXY'] = blocked['no_proxy'] = ''
    return blocked


def snapshot_tree(directory):
    if not directory.is_dir():
        raise SetupSmokeError('managed_directory_missing')
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise SetupSmokeError('managed_install_contains_symlink')
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = {
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'size': path.stat().st_size, 'mtime_ns': path.stat().st_mtime_ns}
    return result


def verify_install(directory, expected):
    required = {'adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll', 'NOTICE.txt', 'source.properties'}
    if any(not (directory / name).is_file() for name in required):
        raise SetupSmokeError('required_platform_tools_file_missing')
    try:
        manifest = json.loads((directory / 'TVCARE-INSTALL.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise SetupSmokeError('install_manifest_missing_or_invalid') from None
    if manifest.get('schema') != 1 or any(manifest.get(key) != value for key, value in expected.items()):
        raise SetupSmokeError('install_manifest_does_not_match_pinned_download')
    recorded = manifest.get('files')
    if not isinstance(recorded, dict) or not required.issubset(recorded):
        raise SetupSmokeError('install_manifest_file_inventory_incomplete')
    for name, digest in recorded.items():
        path = directory / name
        if '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise SetupSmokeError('invalid_install_manifest_path')
        if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
            raise SetupSmokeError('invalid_install_manifest_path')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SetupSmokeError('installed_tool_hash_mismatch')
    return len(recorded)


def run_setup(executable, env):
    try:
        result = subprocess.run([str(executable), '--setup', '--accept-platform-tools-license'],
                                cwd=executable.parent, env=env, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=180)
    except subprocess.TimeoutExpired:
        raise SetupSmokeError('frozen_setup_timeout') from None
    if result.returncode != 0:
        if 'CERTIFICATE_VERIFY_FAILED' in result.stdout + result.stderr:
            raise SetupSmokeError('frozen_https_certificate_verification_failed')
        raise SetupSmokeError('frozen_setup_failed')



def check_command_launchers(bundle, env, refused_env):
    cmd = ntpath.join(next((v for k, v in env.items() if k.upper() == 'SYSTEMROOT'), r'C:\Windows'),
                      'System32', 'cmd.exe')

    def run(name, argument, environment, answer):
        if not (bundle / name).is_file():
            raise SetupSmokeError('consumer_command_launcher_missing')
        try:
            return subprocess.run([cmd, '/d', '/c', name, argument], cwd=bundle, env=environment,
                                  input=answer, capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', timeout=40)
        except subprocess.TimeoutExpired:
            raise SetupSmokeError('consumer_command_launcher_timeout') from None

    requirements = run('Install-Requirements.cmd', '--accept-platform-tools-license', env, '\n')
    if requirements.returncode:
        raise SetupSmokeError('requirements_command_reuse_failed')
    start = run('Start-TVCare.cmd', '--version', env, '\n')
    if start.returncode:
        raise SetupSmokeError('start_command_setup_chain_failed')
    if re.search(r'^TVCare [0-9]+\.[0-9]+\.[0-9]+', start.stdout, re.MULTILINE) is None:
        raise SetupSmokeError('start_command_did_not_reach_main_version')
    refused = run('Start-TVCare.cmd', '--help', offline_environment(refused_env), 'h\n\n')
    if refused.returncode == 0:
        raise SetupSmokeError('start_command_did_not_stop_after_license_refusal')
    if '--no-browser' in refused.stdout or re.search(r'^usage:', refused.stdout, re.MULTILINE):
        raise SetupSmokeError('start_command_reached_main_after_refusal')
    if (Path(refused_env['LOCALAPPDATA']) / 'TVCare/tools/platform-tools/adb.exe').exists():
        raise SetupSmokeError('license_refusal_installed_tools')


def check_html_without_enumeration(executable, env, directory):
    process = subprocess.Popen([str(executable), '--no-browser', '--data-dir', str(directory)],
                               cwd=executable.parent, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                               creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    output = queue.Queue()

    def reader():
        for line in process.stdout:
            output.put(line)
        output.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        deadline = time.monotonic() + 30
        origin = None
        while time.monotonic() < deadline:
            try:
                line = output.get(timeout=max(.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                raise SetupSmokeError('frozen_ui_exited_before_ready')
            match = re.search(r'(http://127\.0\.0\.1:\d+)/#token=[A-Za-z0-9_-]+', line)
            if match:
                origin = match.group(1)
                break
        if origin is None:
            raise SetupSmokeError('frozen_ui_startup_timeout')
        # Raw HTML only: no JS execution, /api/status, adb devices, or ADB daemon startup.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(origin + '/', timeout=10) as response:
            if response.status != 200 or b'TVCare' not in response.read():
                raise SetupSmokeError('frozen_ui_html_invalid')
    finally:
        if process.poll() is None:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise SetupSmokeError('frozen_ui_shutdown_timeout')
        process.stdout.close()
        if process.returncode != 0:
            raise SetupSmokeError('frozen_ui_exit_failed')


def smoke(archive):
    if os.name != 'nt':
        return {'status': 'NOT_RUN', 'reason': 'Windows prerequisite installer only',
                'live_device_tests': 'NOT_RUN', 'device_enumeration': 'NOT_RUN'}
    from tvbakim.setup_tools import (PLATFORM_TOOLS_VERSION, PLATFORM_TOOLS_URL,
                                    PLATFORM_TOOLS_SHA256, PLATFORM_TOOLS_BYTES)
    expected = {'version': PLATFORM_TOOLS_VERSION, 'url': PLATFORM_TOOLS_URL,
                'sha256': PLATFORM_TOOLS_SHA256}
    with tempfile.TemporaryDirectory(prefix='tvcare-setup-smoke-') as temp:
        root = Path(temp)
        bundle = extract_archive(archive.resolve(), root / 'extracted')
        manifest = verify_manifest(bundle)
        if manifest['status'] != 'PASS':
            raise SetupSmokeError('release_manifest_not_verified')
        # CI must test a consumer package, never a package prefilled with tools.
        if any(bundle.rglob('adb.exe')):
            raise SetupSmokeError('release_archive_unexpectedly_bundles_adb')
        executable = bundle / 'TVCare.exe'
        env = isolated_environment(root / 'profile')
        managed = Path(env['LOCALAPPDATA']) / 'TVCare/tools/platform-tools'
        if managed.exists():
            raise SetupSmokeError('setup_profile_not_empty')
        run_setup(executable, env)
        files = verify_install(managed, expected)
        version = subprocess.run([str(managed / 'adb.exe'), 'version'], env=env,
                                 capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        match = re.search(r'^Version\s+([0-9.]+)(?:-|\s|$)', version.stdout, re.MULTILINE)
        if version.returncode or match is None or match.group(1) != PLATFORM_TOOLS_VERSION:
            raise SetupSmokeError('installed_adb_version_not_verified')
        baseline = snapshot_tree(managed)
        run_setup(executable, env)
        if snapshot_tree(managed) != baseline:
            raise SetupSmokeError('repeat_setup_mutated_installation')
        run_setup(executable, offline_environment(env))
        if snapshot_tree(managed) != baseline:
            raise SetupSmokeError('offline_repeat_mutated_installation')
        check_command_launchers(bundle, env, isolated_environment(root / 'refused-profile'))
        if snapshot_tree(managed) != baseline:
            raise SetupSmokeError('command_launcher_mutated_installation')
        check_html_without_enumeration(executable, env, root / 'ui-data')
        if snapshot_tree(managed) != baseline:
            raise SetupSmokeError('ui_startup_mutated_installation')
        if verify_manifest(bundle)['status'] != 'PASS' or any(bundle.rglob('adb.exe')):
            raise SetupSmokeError('consumer_archive_contents_changed')
    return {'status': 'PASS', 'scope': 'frozen_windows_prerequisites',
            'live_device_tests': 'NOT_RUN', 'device_enumeration': 'NOT_RUN',
            'release_manifest': manifest, 'pinned_platform_tools': {
                'version': PLATFORM_TOOLS_VERSION, 'sha256': PLATFORM_TOOLS_SHA256,
                'archive_bytes': PLATFORM_TOOLS_BYTES, 'verified_installed_files': files},
            'frozen_https_download': 'PASS', 'adb_version_only': 'PASS',
            'managed_discovery_and_reuse': 'PASS', 'offline_reuse_with_blocked_proxy': 'PASS',
            'unchanged_file_hashes_sizes_and_mtimes': 'PASS', 'local_html_and_clean_shutdown': 'PASS',
            'requirements_cmd_reuse': 'PASS', 'start_cmd_setup_then_main': 'PASS',
            'start_cmd_stops_on_refused_license': 'PASS',
            'platform_tools_added_to_release': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        result = smoke(args.archive)
    except Exception as error:
        result = {'status': 'FAIL', 'scope': 'frozen_windows_prerequisites',
                  'reason': str(error) if isinstance(error, SetupSmokeError) else 'unexpected_smoke_error',
                  'error_type': type(error).__name__, 'live_device_tests': 'NOT_RUN',
                  'device_enumeration': 'NOT_RUN'}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    print(encoded)
    return 1 if result['status'] == 'FAIL' else 0


if __name__ == '__main__':
    raise SystemExit(main())
