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


def stream_batch(batch):
    from scripts import outputs_prune_stream as s
    root, manifest, _ = batch
    # Make three independently journaled batches; retain endpoints and record.
    frames = root / 'dev/frames'
    for i in range(3, 13):
        (frames / f'{i:02d}.jpg').write_bytes(f'frame-{i}'.encode())
    age(root)
    delete = ['03.jpg', '04.jpg', '05.jpg', '06.jpg', '07.jpg', '08.jpg', '09.jpg', '10.jpg']
    keep = ['1.jpg', '11.jpg', '12.jpg', '2.jpg']
    def row(folder, names):
        names = sorted(names)
        with s.directory_fd(root, folder) as fd:
            recs = [s.file_record(fd, n) for n in names]
        return {'folder': folder, 'names_zlib_base64': s.pack_names(names), 'files': len(names),
                'bytes': sum(r['bytes'] for r in recs),
                'allocated_bytes': sum(r['allocated_bytes'] for r in recs),
                'content_sha256': s.digest_records(recs), 'rule_id': 'D1',
                'reason': '1 Hz thinning; retain first/last and model request'}
    dels = [row('dev/frames', delete[i:i+3]) for i in range(0, len(delete), 3)]
    keeps = [row('dev', ['result.json']), row('dev/frames', keep)]
    data = {'schema': s.SCHEMA, 'outputs_root': str(root),
            'delete_totals': {k: sum(r[k] for r in dels) for k in ['files', 'bytes', 'allocated_bytes']}}
    for action, entries in [('delete', dels), ('keep', keeps)]:
        p = manifest.parent / (action + '.jsonl')
        p.write_bytes(b''.join(s.canonical(r) for r in entries))
        data[action + '_lists'] = [{'path': p.name, 'sha256': prune.sha256(p), 'batches': len(entries)}]
    rewrite(manifest, data)
    return root, manifest, data, delete, keep


def test_stream_thinning_dry_run_and_receipt(batch):
    from scripts import outputs_prune_stream as s
    root, manifest, _, deletes, keeps = stream_batch(batch)
    before = prune.fingerprint(root, enforce_age=False)
    result = prune.prune(manifest, root=root, progress_every=0)
    assert result['files'] == len(deletes)
    assert result['kept_files_verified'] == len(keeps) + 1
    assert prune.fingerprint(root, enforce_age=False) == before
    result = prune.prune(manifest, root=root, execute=True, progress_every=0)
    assert sorted(p.name for p in (root / 'dev/frames').iterdir()) == keeps
    receipt = json.loads(Path(result['receipt']).read_text())
    expected = hashlib.sha256(''.join('dev/frames/' + p + '\n' for p in deletes).encode()).hexdigest()
    assert receipt['removed_paths_sha256'] == expected
    assert receipt['folders']['dev/frames']['removed_files'] == len(deletes)
    assert receipt['folders']['dev/frames']['kept_files_after'] == len(keeps)
    assert receipt['folders']['dev/frames']['recovered_absent'] == 0
    assert receipt['state'] == 'complete'
    assert receipt['kept_files_verified_after'] == len(keeps) + 1


def test_stream_resume_partial_batch_and_completed_batch(batch, monkeypatch):
    root, manifest, _, deletes, keeps = stream_batch(batch)
    unlink = os.unlink
    def stop(name, **kwargs):
        if str(name) == '07.jpg':
            raise KeyboardInterrupt('power-cut simulation')
        unlink(name, **kwargs)
    monkeypatch.setattr(prune.os, 'unlink', stop)
    with pytest.raises(KeyboardInterrupt):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    receipt = next((root / 'prune-receipts').glob('*.json'))
    receipt = next(p for p in (root / 'prune-receipts').glob('*.json') if '.pending.' not in p.name)
    partial = json.loads(receipt.read_text())
    assert partial['state'] == 'interrupted'
    assert partial['completed_batches'] == 1
    assert partial['folders']['dev/frames']['removed_files'] == 4
    assert partial['pending_absent_uncommitted'] == 1
    monkeypatch.setattr(prune.os, 'unlink', unlink)
    result = prune.prune(manifest, root=root, execute=True, resume=receipt, progress_every=0)
    after = json.loads(receipt.read_text())
    assert after['state'] == 'complete'
    assert after['folders']['dev/frames']['removed_files'] == 8
    assert after['folders']['dev/frames']['recovered_absent'] == 1
    assert sorted(p.name for p in (root / 'dev/frames').iterdir()) == keeps
    assert after['removed_paths_sha256'] == hashlib.sha256(''.join('dev/frames/'+p+'\n' for p in deletes).encode()).hexdigest()
    # Repeating a complete receipt is idempotent.
    again = prune.prune(manifest, root=root, execute=True, resume=receipt, progress_every=0)
    assert again['removed_paths_sha256'] == result['removed_paths_sha256']


def test_stream_resume_refuses_missing_outside_durable_pending(batch, monkeypatch):
    root, manifest, _, _, _ = stream_batch(batch)
    (root / 'dev/frames/03.jpg').unlink()
    with pytest.raises(FileNotFoundError):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    assert (root / 'dev/frames/04.jpg').exists()


@pytest.mark.parametrize('target', ['keep', 'delete'])
def test_stream_content_hash_and_keep_overlap(batch, target):
    from scripts import outputs_prune_stream as s
    root, manifest, data, _, _ = stream_batch(batch)
    p = root / 'dev/frames' / ('11.jpg' if target == 'keep' else '07.jpg')
    stamp = p.stat().st_mtime_ns
    p.write_bytes(b'changed')
    os.utime(p, ns=(stamp, stamp))
    with pytest.raises(prune.Refusal, match='content changed'):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    assert (root / 'dev/frames/03.jpg').exists()


def test_stream_sidecar_overlap_and_path_validation(batch):
    from scripts import outputs_prune_stream as s
    root, manifest, data, _, _ = stream_batch(batch)
    data['keep_lists'] = data['delete_lists']
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='overlaps kept'):
        prune.prune(manifest, root=root, progress_every=0)
    for name in ['../outside', '/outside', 'a/b', 'a\\b']:
        row = {'files': 1, 'names_zlib_base64': s.pack_names([name])}
        with pytest.raises(prune.Refusal):
            s.unpack_names(row)
    with pytest.raises(prune.Refusal, match='batch size'):
        s.unpack_names({'files': 513, 'names_zlib_base64': s.pack_names([f'{n:04d}' for n in range(513)])})


def test_stream_torn_journal_after_unlink_recovers(batch, monkeypatch):
    from scripts import outputs_prune_stream as s
    root, manifest, _, _, _ = stream_batch(batch)
    original = s._unlink_pending
    def cut(*args):
        original(*args)
        raise SystemExit('crash before journal commit')
    monkeypatch.setattr(s, '_unlink_pending', cut)
    with pytest.raises(SystemExit):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    receipt = next(p for p in (root / 'prune-receipts').glob('*.json') if '.pending.' not in p.name)
    with receipt.with_suffix('.done.jsonl').open('ab') as stream:
        stream.write(b'{"batch_index":0')
    monkeypatch.setattr(s, '_unlink_pending', original)
    prune.prune(manifest, root=root, execute=True, resume=receipt, progress_every=0)
    result = json.loads(receipt.read_text())
    assert result['state'] == 'complete'
    assert result['folders']['dev/frames']['recovered_absent'] == 3


def test_stream_resume_refuses_reappeared_file_and_changed_manifest(batch, monkeypatch):
    root, manifest, data, _, _ = stream_batch(batch)
    result = prune.prune(manifest, root=root, execute=True, progress_every=0)
    receipt = Path(result['receipt'])
    data['note'] = 'a different approval batch'
    rewrite(manifest, data)
    with pytest.raises(prune.Refusal, match='manifest or root mismatch'):
        prune.prune(manifest, root=root, execute=True, resume=receipt, progress_every=0)
    del data['note'];rewrite(manifest, data)
    (root / 'dev/frames/03.jpg').write_bytes(b'new data')
    with pytest.raises(prune.Refusal, match='reappeared'):
        prune.prune(manifest, root=root, execute=True, resume=receipt, progress_every=0)


def test_stream_symlink_and_recent_and_active_lock(batch):
    root, manifest, _, _, _ = stream_batch(batch)
    lock = root / 'agent-locks/physics';lock.mkdir(parents=True)
    (lock/'owner.json').write_text(json.dumps({'pid': os.getpid()}))
    assert 'active agent_lock' in prune.prune(manifest, root=root, progress_every=0)['execution_blocker']
    with pytest.raises(prune.Refusal, match='active agent_lock'):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    (lock/'owner.json').unlink();lock.rmdir()
    original_stamp = (root / 'dev/frames/03.jpg').stat().st_mtime_ns
    os.utime(root / 'dev/frames/03.jpg', None)
    with pytest.raises(prune.Refusal, match='24 hours'):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    os.utime(root / 'dev/frames/03.jpg', ns=(original_stamp, original_stamp))
    p=root/'dev/frames/03.jpg';p.unlink();p.symlink_to(root/'dev/result.json')
    with pytest.raises(prune.Refusal, match='symlink'):
        prune.prune(manifest, root=root, execute=True, progress_every=0)


def test_d1_samples_use_sim_time_and_endpoints_per_camera():
    from scripts.outputs_retention_rules import select_samples
    for camera in ['r1', 'r2', 'top']:
        frames = [(f'{camera}/{i}.jpg', f'{i}.jpg', i * .2) for i in range(19)]
        kept, rule, cadence = select_samples(frames)
        assert kept == {f'{camera}/{i}.jpg' for i in [0, 5, 10, 15, 18]}
        assert cadence == pytest.approx(.2)
        assert 'SIM second' in rule
    frames = [(f'{i}.jpg', f'{i}.jpg', i) for i in range(21)]
    assert len(select_samples(frames)[0]) == 21  # already 1 Hz: no extra thinning


@pytest.mark.parametrize('n', [1, 2, 9, 19, 20, 21, 99, 100, 101, 10000])
def test_d1_unknown_timing_numeric_order_and_ten_percent(n):
    from scripts.outputs_retention_rules import select_samples
    frames = [(f'{i}.jpg', f'{i}.jpg', None) for i in reversed(range(n))]
    kept, rule, cadence = select_samples(frames)
    assert '0.jpg' in kept and f'{n-1}.jpg' in kept
    assert len(kept) <= max(2, n // 10)
    assert cadence is None and 'unknown SIM timing' in rule


def test_d1_missing_or_invalid_time_uses_explicit_fallback():
    from scripts.outputs_retention_rules import select_samples
    frames = [(str(i), str(i), i * .2 if i != 2 else float('nan')) for i in range(30)]
    assert 'unknown SIM timing' in select_samples(frames)[1]


def test_stream_does_not_collect_new_unlisted_files(batch):
    root, manifest, _, _, keeps = stream_batch(batch)
    (root/'dev/frames/new.jpg').write_bytes(b'new active capture')
    result = prune.prune(manifest, root=root, execute=True, progress_every=0)
    receipt = json.loads(Path(result['receipt']).read_text())
    assert (root/'dev/frames/new.jpg').read_bytes() == b'new active capture'
    assert receipt['folders']['dev/frames']['kept_files_after'] == len(keeps) + 1


def test_stream_refuses_directory_symlink_swap_after_preflight(batch, monkeypatch):
    from scripts import outputs_prune_stream as s
    root, manifest, _, _, _ = stream_batch(batch)
    original = s._unlink_pending
    def swap(*args):
        (root/'dev/frames').rename(root/'dev/oldframes')
        (root/'dev/frames').symlink_to(root/'dev/oldframes', target_is_directory=True)
        return original(*args)
    monkeypatch.setattr(s, '_unlink_pending', swap)
    with pytest.raises((OSError, prune.Refusal)):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    assert (root/'dev/oldframes/03.jpg').exists()


def test_stream_concurrent_pruner_is_refused(batch, monkeypatch):
    from scripts import outputs_prune_stream as s
    root, manifest, _, _, _ = stream_batch(batch)
    def busy(*args):
        raise BlockingIOError('owned')
    monkeypatch.setattr(s.fcntl, 'flock', busy)
    with pytest.raises(prune.Refusal, match='another pruning process'):
        prune.prune(manifest, root=root, execute=True, progress_every=0)
    assert (root/'dev/frames/03.jpg').exists()


@pytest.mark.parametrize('boundary,expected', [(-1, {0}), (.2, {0, 1}), (.3, {1, 2}), (9, {2})])
def test_d1_keeps_frames_on_both_sides_of_recorded_leg_boundary(boundary, expected):
    from scripts.outputs_retention_rules import bracket_indices
    assert bracket_indices([0., .2, .4], boundary) == expected
