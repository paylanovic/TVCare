#!/usr/bin/env python3
"""Fail closed on private material in publishable source or a release bundle.

This is a release gate, not a claim that regexes prove absence of all secrets.
Private per-project search markers can be provided via TVCARE_PRIVATE_MARKERS
(JSON array in the environment); they are never printed or written to output.
"""
from __future__ import annotations
import argparse
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','build','dist','__pycache__','.venv','node_modules','platform-tools','.pytest_cache'}
FORBIDDEN_PARTS={'yedek','local-data','TVCare-Demo'}
PRIVATE_SUFFIXES={'.keystore','.jks','.pk8','.x509','.key','.pem','.p12','.pfx'}
PATTERNS={
 'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 'github_token': re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,255}|github_pat_[A-Za-z0-9_]{40,255}'),
 'aws_access_key': re.compile(rb'AKIA[A-Z0-9]{16}'),
 'personal_home_path': re.compile(rb'/(?:Users|home)/(?!runner(?:/|\b)|build(?:/|\b))[^/\s"\x00]{2,80}/'),
 'windows_home_path': re.compile(rb'[A-Za-z]:[\\/]+Users[\\/]+(?!runneradmin|runner|Public|Default)[A-Za-z0-9_. -]+[\\/]'),
 'private_network_address': re.compile(rb'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b'),
}


def scan_bytes(name,data,markers,findings,depth=0):
    parts=Path(name).parts
    if any(part in FORBIDDEN_PARTS for part in parts) or Path(name).suffix.lower() in PRIVATE_SUFFIXES or Path(name).name in {'adbkey','adbkey.pub','.env','.DS_Store'}:
        findings.append({'file':name,'category':'forbidden_file'})
    for category,pattern in PATTERNS.items():
        if pattern.search(data): findings.append({'file':name,'category':category})
    if any(marker and marker.lower() in data.lower() for marker in markers):
        findings.append({'file':name,'category':'private_marker'})
    if depth<3 and zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(m.file_size for m in archive.infolist())>512*1024*1024:
                findings.append({'file':name,'category':'archive_too_large'}); return
            for member in archive.infolist():
                if not member.is_dir(): scan_bytes(name+'!/'+member.filename,archive.read(member),markers,findings,depth+1)


def source_files(root):
    if (root/'.git').exists():
        command=subprocess.run(['git','ls-files','-z'],cwd=root,check=True,capture_output=True)
        return [root/part.decode('utf-8') for part in command.stdout.split(b'\0') if part]
    return [p for p in root.rglob('*') if p.is_file() and not any(part in SKIP for part in p.relative_to(root).parts)
            and p.name!='.DS_Store' and p.suffix not in {'.pyc','.idsig'}]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source',action='store_true')
    group.add_argument('--bundle',type=Path)
    group.add_argument('--archive',type=Path)
    args=parser.parse_args()
    markers=[x.encode() for x in json.loads(os.environ.get('TVCARE_PRIVATE_MARKERS','[]'))]
    findings=[]
    if args.source:
        root=ROOT; files=source_files(root)
    elif args.bundle:
        root=args.bundle.resolve(); files=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
    else:
        root=args.archive.resolve().parent; files=[args.archive.resolve()]
    if not files: parser.error('No publishable files found; refusing an empty scan.')
    for p in files:
        if p.is_symlink():
            # Source symlinks could publish files outside the reviewed tree.
            findings.append({'file':p.relative_to(root).as_posix(),'category':'source_symlink'}); continue
        scan_bytes(p.relative_to(root).as_posix(),p.read_bytes(),markers,findings)
    print(json.dumps({'status':'FAIL' if findings else 'PASS','files':len(files),'findings':findings},ensure_ascii=False,indent=2))
    return 1 if findings else 0

if __name__=='__main__': raise SystemExit(main())
