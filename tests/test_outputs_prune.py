"""Destructive behavior is tested only in isolated temporary outputs trees."""
import hashlib
import json
import os
from pathlib import Path
import time

import pytest

from scripts import outputs_prune as prune


def age(path):
    old = time.time() - 3 * 86400
    for p in [*path.rglob('*'), path] if path.is_dir() else [path]:
        os.utime(p, (old, old), follow_symlinks=False)


@pytest.fixture
def batch(tmp_path):
    root = tmp_path / 'outputs'
    run = root / 'dev'
    frames = run / 'frames'
    frames.mkdir(parents=True)
    (frames / '1.jpg').write_bytes(b'frame-one')
    (frames / '2.jpg').write_bytes(b'frame-two')
    (run / 'result.json').write_text('{"state":"complete"}')
    age(root)
    manifest = tmp_path / 'manifest.json'
    data = {'schema': prune.SCHEMA, 'outputs_root': str(root),
            'delete': [{'path': 'dev/frames', 'rule_id': 'S1', 'reason': 'reviewed dev frames',
                        **prune.fingerprint(frames)}],
            'keep_files': [{'path': 'dev/result.json', 'bytes': (run / 'result.json').stat().st_size,
                            'sha256': prune.sha256(run / 'result.json')}]}
    manifest.write_text(json.dumps(data))
    return root, manifest, data


def rewrite(manifest, data):
    manifest.write_text(json.dumps(data))


def test_dry_run_is_read_only_including_no_receipt(batch):
    root, manifest, _ = batch
    before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob('*')}
    result = prune.prune(manifest, root=root)
    assert result['paths'] == 1 and result['bytes'] == 18
    assert not (root / 'prune-receipts').exists()
    assert before == {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in root.rglob('*')}


def test_execute_only_listed_files_preserves_logs_and_writes_receipt(batch):
    root, manifest, _ = batch
    result = prune.prune(manifest, root=root, execute=True)
    assert not (root / 'dev/frames').exists()
    assert (root / 'dev/result.json').is_file()
    receipt = json.loads(Path(result['receipt']).read_text())
    assert receipt['state'] == 'complete'
    assert receipt['manifest_sha256'] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert receipt['deleted'][0]['deleted_bytes'] == 18
    assert receipt['deleted'][0]['deleted_files'] == 2
    assert receipt['deleted'][0]['state'] == 'deleted'
    assert receipt['finished_unix'] >= receipt['started_unix']


@pytest.mark.parametrize('path', ['/tmp/outside', '../outside', 'dev/../frames', '.', '', 'dev//frames'])
def test_refuses_escaping_or_noncanonical_paths(batch, path):
    root, manifest, data = batch
    data['delete'][0]['path'] = path
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/1.jpg').exists()
    assert not (root / 'prune-receipts').exists()


@pytest.mark.parametrize('path', ['tensorboard/snap', 'agent-locks', 'prune-receipts',
                                   'retired-worktrees/old/outputs/tensorboard'])
def test_protected_infrastructure_cannot_be_deleted(batch, path):
    root, manifest, data = batch
    data['delete'][0]['path'] = path
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='protected infrastructure'):
        prune.prune(manifest, root=root, execute=True)


@pytest.mark.parametrize('directory', [False, True])
def test_refuses_recent_files_and_recent_empty_directories(batch, directory):
    root, manifest, _ = batch
    if directory:
        (root / 'dev/frames/new-empty').mkdir()
    else:
        os.utime(root / 'dev/frames/1.jpg', None)
    with pytest.raises(prune.Refusal, match='within 24 hours'):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/2.jpg').is_file()


@pytest.mark.parametrize('same_size', [False, True])
def test_refuses_changed_bytes_even_with_preserved_mtime(batch, same_size):
    root, manifest, _ = batch
    p = root / 'dev/frames/1.jpg'
    stamp = p.stat().st_mtime_ns
    p.write_bytes(b'other-one' if same_size else b'x')
    os.utime(p, ns=(stamp, stamp))
    with pytest.raises(prune.Refusal, match='changed'):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/2.jpg').exists()
    assert not (root / 'prune-receipts').exists()


def test_all_entries_preflight_before_any_deletion(batch):
    root, manifest, data = batch
    data['delete'].append({'path': 'missing', 'rule_id': 'D1', 'reason': 'test'})
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='missing'):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/1.jpg').exists()


@pytest.mark.parametrize('inside', [False, True])
def test_refuses_symlink_candidates_and_descendants(batch, inside):
    root, manifest, data = batch
    outside = root.parent / 'outside'
    outside.write_bytes(b'preserve')
    if inside:
        (root / 'dev/frames/link').symlink_to(outside)
        age(root / 'dev/frames')
    else:
        (root / 'link').symlink_to(root / 'dev/frames', target_is_directory=True)
        data['delete'][0]['path'] = 'link'
        rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='symlink'):
        prune.prune(manifest, root=root, execute=True)
    assert outside.read_bytes() == b'preserve'


def test_refuses_live_and_malformed_locks_but_dry_run_reports(batch):
    root, manifest, _ = batch
    lock = root / 'agent-locks/physics'
    lock.mkdir(parents=True)
    (lock / 'owner.json').write_text(json.dumps({'pid': os.getpid()}))
    assert 'active agent_lock' in prune.prune(manifest, root=root)['execution_blocker']
    with pytest.raises(prune.Refusal, match='active agent_lock'):
        prune.prune(manifest, root=root, execute=True)
    (lock / 'owner.json').write_text('{invalid')
    with pytest.raises(prune.Refusal, match='unknown lock state'):
        prune.prune(manifest, root=root, execute=True)
    assert not (root / 'prune-receipts').exists()


def test_refuses_overlaps_and_changed_kept_file(batch):
    root, manifest, data = batch
    data['delete'].append(dict(data['delete'][0]))
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='overlapping'):
        prune.prune(manifest, root=root)
    data['delete'].pop()
    rewrite(manifest, data)
    (root / 'dev/result.json').write_text('changed')
    with pytest.raises(prune.Refusal, match='kept file changed'):
        prune.prune(manifest, root=root, execute=True)


def test_keep_list_digest_and_overlap_are_enforced(batch):
    root, manifest, data = batch
    keep_list = manifest.parent / 'keep.json'
    keep_list.write_text(json.dumps({'files': data.pop('keep_files')}))
    data['keep_lists'] = [{'path': 'keep.json', 'sha256': prune.sha256(keep_list)}]
    rewrite(manifest, data)
    assert prune.prune(manifest, root=root)['paths'] == 1
    keep_list.write_text('{"files":[]}')
    with pytest.raises(prune.Refusal, match='keep-list hash changed'):
        prune.prune(manifest, root=root)
    del data['keep_lists']
    p = root / 'dev/frames/1.jpg'
    data['keep_files'] = [{'path': 'dev/frames/1.jpg', 'bytes': p.stat().st_size, 'sha256': prune.sha256(p)}]
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='overlaps kept'):
        prune.prune(manifest, root=root)


def test_partial_os_failure_leaves_honest_receipt(batch, monkeypatch):
    root, manifest, _ = batch
    unlink = os.unlink

    def fail_second(path, **kwargs):
        if str(path) == '2.jpg':
            raise OSError('injected disk error')
        return unlink(path, **kwargs)

    monkeypatch.setattr(prune.os, 'unlink', fail_second)
    with pytest.raises(OSError, match='injected disk error'):
        prune.prune(manifest, root=root, execute=True)
    receipt = json.loads(next((root / 'prune-receipts').glob('*.json')).read_text())
    assert receipt['state'] == 'partial_failure'
    assert receipt['deleted'][0]['deleted_files'] == 1
    assert receipt['deleted'][0]['last_deleted_path'] == 'dev/frames/1.jpg'
    assert (root / 'dev/frames/2.jpg').exists()
    assert (root / 'dev/result.json').exists()


def test_refuses_new_old_timestamp_file_after_preflight(batch, monkeypatch):
    root, manifest, _ = batch
    remove = prune._remove

    def inject(root, path, identities, record, save):
        (path / 'new.jpg').write_bytes(b'new')
        age(path)
        return remove(root, path, identities, record, save)

    monkeypatch.setattr(prune, '_remove', inject)
    with pytest.raises(prune.Refusal, match='changed after preflight'):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/new.jpg').exists()
    assert (root / 'dev/frames/1.jpg').exists()


def test_cli_defaults_to_dry_run_and_returns_failure(batch, monkeypatch, capsys):
    root, manifest, _ = batch
    real = prune.prune
    monkeypatch.setattr(prune, 'prune', lambda path, execute=False: real(path, execute=execute, root=root))
    assert prune.main([str(manifest)]) == 0
    assert json.loads(capsys.readouterr().out)['execute'] is False
    assert prune.main([str(manifest.parent / 'missing')]) == 1


def selection_batch(batch, names=None):
    root, manifest, data = batch
    selection = manifest.parent / 'selection.json'
    selection.write_text(json.dumps({'delete_names': ['1.jpg'] if names is None else names}))
    snapshot = {k: v for k, v in data['delete'][0].items() if k not in {'path', 'reason', 'rule_id'}}
    data['delete'][0] = {'path': 'dev/frames', 'kind': 'selection', 'rule_id': 'S2',
                         'reason': 'retain stage samples', 'snapshot': snapshot,
                         'bytes': 9, 'files': 1, 'directories': 0, 'allocated_bytes': 4096,
                         'selection_file': {'path': 'selection.json', 'sha256': prune.sha256(selection)}}
    p = root / 'dev/frames/2.jpg'
    data['keep_files'].append({'path': 'dev/frames/2.jpg', 'bytes': 9, 'sha256': prune.sha256(p)})
    rewrite(manifest, data)
    return root, manifest, data


def test_explicit_selection_keeps_directory_and_example_frame(batch):
    root, manifest, _ = selection_batch(batch)
    assert prune.prune(manifest, root=root)['bytes'] == 9
    result = prune.prune(manifest, root=root, execute=True)
    assert not (root / 'dev/frames/1.jpg').exists()
    assert (root / 'dev/frames/2.jpg').read_bytes() == b'frame-two'
    receipt = json.loads(Path(result['receipt']).read_text())
    assert receipt['deleted'][0]['deleted_files'] == 1
    assert receipt['deleted'][0]['deleted_directories'] == 0


@pytest.mark.parametrize('names', [['../result.json'], ['1.jpg', '1.jpg'], [], ['2.jpg']])
def test_selection_cannot_escape_repeat_or_delete_retained_sample(batch, names):
    root, manifest, _ = selection_batch(batch, names)
    with pytest.raises(prune.Refusal):
        prune.prune(manifest, root=root, execute=True)
    assert (root / 'dev/frames/1.jpg').exists()
    assert (root / 'dev/frames/2.jpg').exists()


def test_selection_file_is_bound_by_hash(batch):
    root, manifest, _ = selection_batch(batch)
    (manifest.parent / 'selection.json').write_text('{"delete_names":["2.jpg"]}')
    with pytest.raises(prune.Refusal, match='selection-list hash changed'):
        prune.prune(manifest, root=root, execute=True)


def test_dead_lock_does_not_get_removed_by_pruner(batch, monkeypatch):
    root, manifest, _ = batch
    lock = root / 'agent-locks/physics'
    lock.mkdir(parents=True)
    (lock / 'owner.json').write_text('{"pid":12345}')

    def dead(pid, signal):
        raise ProcessLookupError()

    monkeypatch.setattr(prune.os, 'kill', dead)
    prune.prune(manifest, root=root, execute=True)
    assert (lock / 'owner.json').is_file()
