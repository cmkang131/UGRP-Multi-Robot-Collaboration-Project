"""Lossless record streams; frame files and original archives are untouched.

Gzip is an explicit storage representation, not a different JSON serializer.
Logical byte hashes/sizes and stored byte hashes/sizes are recorded separately.
"""
from __future__ import annotations
import gzip
import hashlib
from pathlib import Path


class RecordStream:
    def __init__(self, path, *, storage='off'):
        if storage not in ('off', 'gzip-v1'):
            raise ValueError('off or gzip-v1 storage required')
        self.logical_path = Path(path)
        self.storage = storage
        self.path = self.logical_path if storage == 'off' else self.logical_path.with_name(self.logical_path.name+'.gz')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.logical_path.exists() or self.logical_path.with_name(self.logical_path.name+'.gz').exists():
            raise FileExistsError(self.logical_path)
        self.raw = self.path.open('xb', buffering=65536)
        self.stream = (self.raw if storage == 'off' else
                       gzip.GzipFile(filename='', fileobj=self.raw, mode='wb', compresslevel=1, mtime=0))
        self.size = 0
        self.digest = hashlib.sha256()
        self.closed = False

    def write(self, text):
        self.write_bytes(text.encode('utf-8'))
        return len(text)

    def write_bytes(self, data):
        if self.closed:
            raise ValueError('write to closed record')
        self.stream.write(data)
        self.digest.update(data)
        self.size += len(data)
        return len(data)

    def tell(self):
        return self.size

    def close(self):
        if not self.closed:
            try:
                if self.stream is not self.raw:
                    self.stream.close()
            finally:
                self.raw.close()
                self.closed = True

    def receipt(self):
        if not self.closed:
            raise ValueError('close record before receipt')
        h = hashlib.sha256()
        with self.path.open('rb') as source:
            for chunk in iter(lambda: source.read(1 << 20), b''):
                h.update(chunk)
        return dict(logical_name=self.logical_path.name, stored_name=self.path.name,
                    storage=self.storage, logical_bytes=self.size, logical_sha256=self.digest.hexdigest(),
                    stored_bytes=self.path.stat().st_size, stored_sha256=h.hexdigest())


def logical_open(path):
    """Read a named logical record; reject an ambiguous representation."""
    path = Path(path)
    compressed = path.with_name(path.name+'.gz')
    if path.exists() and compressed.exists():
        raise ValueError('ambiguous plain and compressed record')
    return path.open('rb') if path.exists() else gzip.open(compressed, 'rb')


def logical_equal(left, right):
    with logical_open(left) as a, logical_open(right) as b:
        while True:
            x, y = a.read(1 << 20), b.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True
