import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
from unittest.mock import Mock

import pytest

from scripts import azure_archive_native as native
from scripts import azure_shutdown as shutdown


def tar_bytes(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, data, kind in entries:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            if kind == tarfile.SYMTYPE:
                item.linkname = '/tmp/escape'
            archive.addfile(item, io.BytesIO(data) if item.isfile() else None)
    stream.seek(0)
    return stream


@pytest.mark.parametrize('name,kind', [('../escape', tarfile.REGTYPE),
                                    ('/escape', tarfile.REGTYPE), ('raw', tarfile.SYMTYPE),
                                    ('extra', tarfile.REGTYPE)])
def test_extract_rejects_paths_links_and_extra_files(tmp_path, name, kind):
    hashes = {'raw': {'bytes': 1, 'sha256': '0' * 64}}
    with pytest.raises(ValueError):
        native.extract(tar_bytes([(name, b'x', kind)]), tmp_path, hashes)
    assert not (tmp_path / 'raw').exists()


def test_extract_rejects_duplicate_and_truncated_inventory(tmp_path):
    hashes = {'raw': {'bytes': 1, 'sha256': '0' * 64}}
    with pytest.raises(ValueError):
        native.extract(tar_bytes([('raw', b'x', tarfile.REGTYPE)] * 2), tmp_path, hashes)
    with pytest.raises(RuntimeError, match='incomplete'):
        native.extract(tar_bytes([]), tmp_path, hashes)


def test_native_receiver_publishes_full_hashes_and_preserves_legacy_partial(tmp_path, monkeypatch):
    import shutil
    if not shutil.which('zstd'):
        pytest.skip('zstd required for receiver integration')
    source = tmp_path / 'source'; source.mkdir()
    (source / 'raw').write_bytes(b'original evidence')
    hashes = native.inventory(source)
    root = tmp_path / 'arm'; root.mkdir()
    partial = root / '.incoming-one'; partial.mkdir(); (partial / 'old').write_text('keep')
    stream = tar_bytes([('raw', b'original evidence', tarfile.REGTYPE)])
    packed = subprocess.check_output(['zstd', '-q'], input=stream.read())
    header = dict(schema=native.SCHEMA, run='one', inventory=hashes)
    module = Path(native.__file__)
    process = subprocess.Popen([os.sys.executable, str(module), 'receive', '--archive-root', str(root)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={**os.environ, 'SSH_ORIGINAL_COMMAND': native.COMMAND})
    process.stdin.write((json.dumps(header) + '\n').encode()); process.stdin.flush()
    ready = json.loads(process.stdout.readline()); assert ready['ready']
    process.stdin.write(packed); process.stdin.close()
    proof = json.loads(process.stdout.readline())
    assert process.wait(timeout=10) == 0, process.stderr.read()
    assert proof['verified'] and proof['hash_matches'] == len(hashes)
    assert native.inventory(root / 'native-one') == hashes
    assert (source / 'raw').read_bytes() == b'original evidence'
    assert (partial / 'old').read_text() == 'keep'
    # Existing verified archive is reusable; a different manifest cannot overwrite it.
    messages = []
    monkeypatch.setattr(native, 'emit', messages.append)
    assert native.receive_locked(root, header, hashes)['reused']
    hashes['raw']['sha256'] = '0' * 64
    with pytest.raises(RuntimeError, match='no overwrite'):
        native.receive_locked(root, header, hashes)
    assert (root / 'native-one/raw').read_bytes() == b'original evidence'


def test_arm_reserve_refuses_before_creating_incoming(tmp_path, monkeypatch):
    monkeypatch.setattr(native.shutil, 'disk_usage', lambda _: Mock(free=native.RESERVE))
    with pytest.raises(RuntimeError, match='25 GiB'):
        native.receive_locked(tmp_path, {'run': 'one'}, {'raw': {'bytes': 1, 'sha256': '0' * 64}})
    assert list(tmp_path.iterdir()) == []


def test_sender_source_mutation_prevents_marker_and_preserves_source(tmp_path, monkeypatch):
    root = tmp_path; run = root / 'runs/one'; run.mkdir(parents=True)
    (run / 'EXIT').write_text('0'); (run / 'raw').write_text('original')
    monkeypatch.setattr(shutdown, 'run_processes', lambda _: set())
    def changed(*args):
        (run / 'raw').write_text('changed')
        return {'verified': True}
    monkeypatch.setattr(native, 'transport', changed)
    with pytest.raises(RuntimeError, match='source changed before marker'):
        native.archive(root, run)
    assert not (root / 'lifecycle/archives/one.json').exists()
    assert run.is_dir() and not run.is_symlink()


def test_sender_marker_is_accepted_by_recovery_and_skips_repeat_transfer(tmp_path, monkeypatch):
    root = tmp_path; run = root / 'runs/one'; run.mkdir(parents=True)
    (run / 'EXIT').write_text('0'); (run / 'raw').write_text('original')
    (root / 'arm/native-one').mkdir(parents=True)
    monkeypatch.setattr(shutdown, 'run_processes', lambda _: set())
    transport = Mock(return_value={'verified': True, 'files': 2, 'hash_matches': 2})
    monkeypatch.setattr(native, 'transport', transport)
    result = native.archive(root, run)
    assert result['preserved_local'] and shutdown.archived(root, run)
    assert native.archive(root, run) == result
    assert transport.call_count == 1
    assert run.is_dir() and not run.is_symlink()


def test_archive_toggle_defaults_off_and_on_calls_native(tmp_path, monkeypatch):
    run = tmp_path / 'runs/one'; run.mkdir(parents=True); (run / 'EXIT').write_text('0')
    (tmp_path / 'arm').mkdir()
    monkeypatch.setattr(shutdown.os.path, 'ismount', lambda _: True)
    monkeypatch.setattr(shutdown, 'run_processes', lambda _: set())
    monkeypatch.setattr(shutdown.shutil, 'disk_usage', lambda _: Mock(free=100 * 2**30))
    helper = Mock(return_value={'verified': True})
    monkeypatch.setattr(native, 'archive', helper)
    monkeypatch.delenv('UGRP_ARCHIVE_NATIVE', raising=False)
    monkeypatch.setattr(shutdown.subprocess, 'run', Mock(side_effect=RuntimeError('legacy rsync')))
    with pytest.raises(RuntimeError, match='legacy rsync'):
        shutdown._archive_one(tmp_path, run)
    helper.assert_not_called()
    monkeypatch.setenv('UGRP_ARCHIVE_NATIVE', 'on_v1')
    assert shutdown._archive_one(tmp_path, run) == {'verified': True}
    helper.assert_called_once_with(tmp_path, run)


def test_receiver_refuses_unapproved_ssh_command(tmp_path, monkeypatch):
    monkeypatch.setenv('SSH_ORIGINAL_COMMAND', 'cat /etc/passwd')
    with pytest.raises(ValueError, match='protocol command'):
        native.receive(tmp_path)
