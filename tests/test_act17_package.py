import hashlib
import importlib.util
import io
import sys
from pathlib import Path
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import package_act17_model as m


class Pipe(io.RawIOBase):
    def __init__(self):self.payload=bytearray()
    def writable(self):return True
    def write(self,value):self.payload.extend(value);return len(value)


def test_registered_hash_pass_and_real_pipe_pass_are_byte_identical(tmp_path):
    files=[]
    for name,data in [('a.txt',b'a'*1024),('b.bin',bytes(range(256))*7)]:
        (tmp_path/name).write_bytes(data)
        files.append(dict(path=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    first=m.HashSink();m.stream_zip(tmp_path,files,first)
    actual=Pipe();m.stream_zip(tmp_path,files,actual)
    assert first.bytes==len(actual.payload)
    assert first.digest.hexdigest()==hashlib.sha256(actual.payload).hexdigest()
    with zipfile.ZipFile(io.BytesIO(actual.payload)) as archive:
        assert archive.testzip() is None
        for row in files:assert archive.read(row['path'])==(tmp_path/row['path']).read_bytes()


def test_source_mutation_rejects_stream(tmp_path):
    (tmp_path/'model.bin').write_bytes(b'changed')
    with pytest.raises(ValueError,match='staged file changed'):
        m.stream_zip(tmp_path,[dict(path='model.bin',bytes=3,sha256='0'*64)],m.HashSink())
