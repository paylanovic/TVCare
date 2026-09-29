#!/usr/bin/env python3
"""Verify a host package and run only synthetic or explicitly missing-ADB sessions."""
from __future__ import annotations

import argparse
import hashlib
import json
import marshal
import os
from pathlib import Path, PurePosixPath
import queue
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
import types
import urllib.request
import zipfile


def checked_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name:
        raise ValueError('Unsafe package path')
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Package path escapes extraction directory')
    return path


def extract_archive(archive, directory):
    """Preserve executable bits and safe in-bundle Unix symlinks."""
    links = []
    with zipfile.ZipFile(archive) as source:
        if sum(item.file_size for item in source.infolist()) > 1024 ** 3:
            raise ValueError('Package exceeds smoke-test size limit')
        if source.testzip() is not None:
            raise ValueError('Package CRC verification failed')
        for item in source.infolist():
            target = checked_path(directory, item.filename)
            mode = item.external_attr >> 16
            if stat.S_ISLNK(mode):
                destination = source.read(item).decode('utf-8')
                if Path(destination).is_absolute() or not (target.parent / destination).resolve().is_relative_to(directory.resolve()):
                    raise ValueError('Package symlink escapes extraction directory')
                links.append((target, destination))
                continue
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(item))
            if os.name != 'nt':
                target.chmod(stat.S_IMODE(mode) or 0o644)
    for target, destination in links:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(destination)
    return directory / 'TVCare'


def verify_manifest(bundle):
    path = bundle / 'SHA256SUMS'
    if not path.is_file():
        return {'status': 'NOT_RUN', 'reason': 'Manifest not generated yet'}
    count = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        target = checked_path(bundle, name)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise AssertionError('Package hash mismatch: ' + name)
        count += 1
    return {'status': 'PASS', 'files': count}


def verify_code_filenames(executable, bundle):
    """Inspect actual marshaled code, including compressed PYZ and nested code objects."""
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    count = 0

    def inspect(code):
        nonlocal count
        if not isinstance(code, types.CodeType):
            return
        filename = code.co_filename
        if filename.startswith(('/', '\\')) or re.match(r'^[A-Za-z]:', filename):
            raise AssertionError('Absolute compiled Python filename found')
        count += 1
        for constant in code.co_consts:
            inspect(constant)

    for name, entry in archive.toc.items():
        if entry[-1] in ('s', 'm', 'M'):
            inspect(marshal.loads(archive.extract(name)))
        elif entry[-1] == 'z':
            embedded = archive.open_embedded_archive(name)
            for module in embedded.toc:
                inspect(embedded.extract(module))
    for path in bundle.rglob('base_library.zip'):
        with zipfile.ZipFile(path) as source:
            for name in source.namelist():
                if name.endswith('.pyc'):
                    inspect(marshal.loads(source.read(name)[16:]))
    if count == 0:
        raise AssertionError('No compiled Python code inspected')
    return {'status': 'PASS', 'code_objects': count}


def launch_session(executable, directory, demo):
    args = [str(executable), '--no-browser', '--data-dir', str(directory)]
    if demo:
        args.append('--demo')
    else:
        # Explicit nonexistent path: discovery cannot use the runner's real ADB.
        args += ['--adb', str(directory / 'definitely-missing-adb')]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {}
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', errors='replace', env=env, **options)
    output = queue.Queue()

    def reader():
        for line in process.stdout:
            output.put(line)
        output.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        deadline = time.monotonic() + 30
        origin = token = None
        while time.monotonic() < deadline:
            line = output.get(timeout=max(.1, deadline - time.monotonic()))
            if line is None:
                raise AssertionError('Frozen app exited before serving its UI')
            match = re.search(r'(http://127\.0\.0\.1:\d+)/#token=([A-Za-z0-9_-]+)', line)
            if match:
                origin, token = match.groups()
                break
        if origin is None:
            raise AssertionError('Frozen app did not start within 30 seconds')

        def request(path, body=None):
            headers = {'Authorization': 'Bearer ' + token, 'Origin': origin}
            data = None
            if body is not None:
                data = json.dumps(body).encode('utf-8')
                headers['Content-Type'] = 'application/json'
            req = urllib.request.Request(origin + path, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.load(response)

        def job(path, body):
            record = request(path, body)['job']
            deadline = time.monotonic() + 15
            while record['status'] not in ('succeeded', 'failed'):
                if time.monotonic() > deadline:
                    raise AssertionError('Synthetic operation timed out')
                time.sleep(.03)
                record = request('/api/jobs/' + record['id'])
            if record['status'] != 'succeeded':
                raise AssertionError('Synthetic operation failed: ' + record.get('error', 'unknown'))
            return record['result']

        with urllib.request.urlopen(origin, timeout=10) as response:
            assert b'TVCare' in response.read()
        current = request('/api/status')
        if demo:
            assert current['demo'] is True and current['devices']
            serial = current['devices'][0]['serial']
            inspection = job('/api/inspect', {'serial': serial})
            assert inspection['health']['synthetic'] is True
            before = inspection['settings']['window_animation_scale']
            plan = job('/api/plan', {'serial': serial, 'actions': [
                {'type': 'setting', 'namespace': 'global', 'key': 'window_animation_scale', 'value': '0.5'}]})
            transaction = job('/api/apply', {'plan_id': plan['id'], 'confirmed': True})
            assert transaction['status'] == 'succeeded'
            changed = job('/api/inspect', {'serial': serial})
            assert changed['settings']['window_animation_scale']['value'] == '0.5'
            rollback = job('/api/rollback-plan', {'serial': serial, 'transaction_id': transaction['id']})
            restored = job('/api/apply', {'plan_id': rollback['id'], 'confirmed': True})
            assert restored['status'] == 'succeeded'
            after = job('/api/inspect', {'serial': serial})
            assert after['settings']['window_animation_scale'] == before
            report = request('/api/report')
            assert report['evidence'] == 'synthetic_demo'
        else:
            assert current['adb']['available'] is False and not current['devices']
        return {'status': 'PASS', 'mode': 'synthetic_demo' if demo else 'explicit_missing_adb',
                'checks': ['startup', 'html', 'status', 'inspect', 'apply', 'rollback', 'report'] if demo
                else ['startup', 'html', 'missing_adb_status']}
    finally:
        if process.poll() is None:
            process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise AssertionError('Frozen app failed to shut down gracefully')
        process.stdout.close()
        if process.returncode != 0:
            raise AssertionError('Frozen app exited with code ' + str(process.returncode))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bundle', type=Path)
    group.add_argument('--archive', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='tvcare-package-smoke-') as temporary:
        temporary = Path(temporary)
        bundle = extract_archive(args.archive.resolve(), temporary / 'extracted') if args.archive else args.bundle.resolve()
        executable = bundle / ('TVCare.exe' if os.name == 'nt' else 'TVCare')
        version = subprocess.check_output([str(executable), '--version'], timeout=15, text=True, encoding='utf-8').strip()
        assert version.startswith('TVCare ')
        manifest = verify_manifest(bundle)
        if args.archive and manifest['status'] != 'PASS':
            raise AssertionError('Release archive has no hash manifest')
        result = {'status': 'PASS', 'version': version, 'live_device_tests': 'NOT_RUN',
                  'manifest': manifest,
                  'compiled_path_privacy': verify_code_filenames(executable, bundle),
                  'demo': launch_session(executable, temporary / 'demo-data', True),
                  'missing_adb': launch_session(executable, temporary / 'missing-adb-data', False)}
    encoded = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding='utf-8')
    print(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
