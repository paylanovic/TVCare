"""Durable write-ahead records. Never replace a device's earlier baseline."""
from __future__ import annotations
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def data_directory(demo=False):
    if sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support'
    else:
        root = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    return root / ('TVCare-Demo' if demo else 'TVCare')


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()
        self._instance = None

    def acquire(self):
        f = (self.path / '.instance.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if f.tell() == 0:
                    f.write(b'0'); f.flush()
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            raise RuntimeError('TVCare bu veri klasöründe zaten çalışıyor.')
        self._instance = f

    def close(self):
        if self._instance:
            self._instance.close()
            self._instance = None

    def _file(self, record_id):
        if not isinstance(record_id, str) or not re.fullmatch(r'[a-f0-9]{32}', record_id):
            raise ValueError('Geçersiz kayıt kimliği.')
        return self.path / (record_id + '.json')

    def save(self, record):
        with self._lock:
            target = self._file(record['id'])
            temp = self.path / ('.' + uuid.uuid4().hex + '.tmp')
            try:
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
                    f.flush(); os.fsync(f.fileno())
                os.replace(temp, target)
                if os.name != 'nt':
                    directory = os.open(self.path, os.O_RDONLY)
                    try: os.fsync(directory)
                    finally: os.close(directory)
            finally:
                temp.unlink(missing_ok=True)

    def get(self, record_id):
        with self._lock:
            return json.loads(self._file(record_id).read_text(encoding='utf-8'))

    def history(self):
        with self._lock:
            records = []
            for p in self.path.glob('*.json'):
                try:
                    record = self.get(p.stem)
                    if not isinstance(record,dict) or record.get('id')!=p.stem or not isinstance(record.get('actions'),list):
                        raise ValueError('Bozuk işlem kaydı')
                    records.append(record)
                except (ValueError, OSError):
                    records.append({'id':p.stem, 'status':'unreadable', 'created_at':'',
                                    'error':'Kayıt okunamadı; bu dosyayı silmeyin.'})
            return sorted(records, key=lambda r:r.get('created_at',''), reverse=True)

    def recover(self):
        for record in self.history():
            if record.get('status') == 'running':
                record['status'] = 'interrupted'
                record['error'] = 'Önceki oturum işlem sırasında kapandı. Cihaza bağlanıp geri alma planını inceleyin.'
                self.save(record)
