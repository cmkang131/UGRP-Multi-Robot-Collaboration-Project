import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from sim.lazy_camera import FrameBatch, capture_robot_frames


def test_batch_keys_are_lazy_and_values_are_owned_once():
    calls = []
    batch = FrameBatch(('r1', 'r2'), lambda key, why: calls.append((key, why)) or object(), lambda: True)
    assert set(batch) == {'r1', 'r2'} and len(batch) == 2 and 'r1' in batch
    assert not calls
    first = batch['r2']
    assert batch['r2'] is first
    batch.retain()
    assert calls == [('r2', 'consumer'), ('r1', 'recording')]
    with pytest.raises(KeyError):
        batch['r3']


def test_historical_frame_never_renders_new_physics_state():
    now = [0]
    batch = FrameBatch(('r1',), lambda *_: pytest.fail('must not render'), lambda: now[0] == 0)
    now[0] = 1
    with pytest.raises(RuntimeError, match='physics boundary'):
        batch['r1']


class Host:
    def __init__(self, out):
        self.out, self.now, self.frame = out, 0., 0
        self.commands = {'r1': {1: 1500}, 'r2': {1: 1600}}
        self.rendered = []
        self.rows = {}
        self.closed = False
        b = io.BytesIO(); Image.new('RGB', (4, 3), 'red').save(b, format='JPEG')
        self.image = base64.b64encode(b.getvalue()).decode()
        self.ports = {r: SimpleNamespace(capture=lambda r=r: self.capture_one(r)) for r in self.commands}

    def capture_one(self, rid):
        self.rendered.append((rid, self.now))
        return dict(robot_id=rid, image=self.image, frame_id=self.frame+1, sim_time=self.now)

    def _append(self, name, row):
        self.rows.setdefault(name, []).append(json.loads(json.dumps(row)))

    def issue(self, rid, action):
        self.commands[rid][1] = action

    def advance_to(self, t):
        self.now = t

    def reset(self):
        self.now = 0

    def close(self):
        self.closed = True


@pytest.mark.parametrize('boundary', ['issue', 'advance_to', 'reset', 'close', 'capture'])
def test_recording_is_flushed_before_every_host_boundary(tmp_path, monkeypatch, boundary):
    monkeypatch.setenv('UGRP_CAMERA_RENDER', 'lazy-v1')
    host = Host(tmp_path)
    frames = capture_robot_frames(host, ('r1', 'r2'))
    assert not host.rendered
    frames['r2']
    if boundary == 'issue': host.issue('r1', 2000)
    elif boundary == 'advance_to': host.advance_to(1.)
    elif boundary == 'reset': host.reset()
    elif boundary == 'close': host.close()
    else: capture_robot_frames(host, ('r1', 'r2'))
    assert host.rendered[:2] == [('r2', 0.), ('r1', 0.)]
    assert host.rows['robots/r1/frames.jsonl'][0]['commanded_servo'] == {'1': 1500}
    host.close()
    assert host.closed
    assert json.loads((tmp_path/'camera-render.json').read_text())['mode'] == 'lazy-v1'


def test_default_is_legacy_eager_and_unknown_mode_fails(tmp_path, monkeypatch):
    monkeypatch.delenv('UGRP_CAMERA_RENDER', raising=False)
    host = Host(tmp_path)
    frames = capture_robot_frames(host, ('r1', 'r2'))
    assert isinstance(frames, dict) and host.rendered == [('r1', 0.), ('r2', 0.)]
    assert not {'issue','advance_to','reset','close'} & vars(host).keys()
    host.close()
    monkeypatch.setenv('UGRP_CAMERA_RENDER', 'typo')
    with pytest.raises(ValueError): capture_robot_frames(Host(tmp_path), ('r1',))


def test_oracle_guard_rejects_mac_before_any_physics(monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    monkeypatch.setattr(probe.platform, 'system', lambda: 'Darwin')
    with pytest.raises(RuntimeError, match='NO_MAC_PHYSICS'):
        probe.host_guard('a'*40)


def test_partial_write_failure_does_not_retake_or_overwrite_on_close(tmp_path, monkeypatch):
    monkeypatch.setenv('UGRP_CAMERA_RENDER', 'lazy-v1')
    host = Host(tmp_path)
    def fail(*_): raise OSError('ledger unavailable')
    host._append = fail
    frames = capture_robot_frames(host, ('r1', 'r2'))
    with pytest.raises(OSError): frames['r1']
    image = tmp_path/'robots/r1/rgb/00000.jpg'
    before = (image.stat().st_mtime_ns, image.read_bytes())
    with pytest.raises(OSError): host.close()
    assert host.closed and host.rendered == [('r1', 0.)]
    assert (image.stat().st_mtime_ns, image.read_bytes()) == before


def test_direct_bytes_do_not_normalize_control_ledger(tmp_path):
    from scripts.benchmark_lazy_camera import equal_bytes
    a, b = tmp_path/'a', tmp_path/'b'
    a.write_bytes(b'{"t":1.0}\n'); b.write_bytes(b'{"t":1.0}\n')
    assert equal_bytes(a,b)
    b.write_bytes(b'{"t":1.1}\n')
    assert not equal_bytes(a,b)


def driver_args(monkeypatch, output, kind='abba'):
    import sys
    from scripts import benchmark_lazy_camera as probe
    monkeypatch.setattr(probe, 'host_guard', lambda _: None)
    monkeypatch.setattr(sys, 'argv', ['probe','--kind',kind,'--output',str(output),
        '--expected-source-sha','a'*40,'--archive-manifest','unused',
        '--archive-manifest-sha256','b'*64])
    return probe


def test_direct_arm_requires_live_parent_lease(tmp_path, monkeypatch):
    from scripts import agent_lock
    probe = driver_args(monkeypatch, tmp_path/'new', 's3')
    monkeypatch.setattr(agent_lock, 'status', lambda _: None)
    monkeypatch.setattr(probe, 'run_one', lambda _: pytest.fail('physics must not start'))
    with pytest.raises(ValueError, match='LIVE_PARENT_LEASE'):
        probe.main()


def test_existing_output_never_acquires_lock_or_overwrites_receipt(tmp_path, monkeypatch):
    from scripts import agent_lock
    out = tmp_path/'old';out.mkdir();receipt=out/'lock.json';receipt.write_bytes(b'original')
    probe = driver_args(monkeypatch, out)
    monkeypatch.setattr(agent_lock, 'acquire', lambda *a, **k: pytest.fail('must not acquire'))
    with pytest.raises(ValueError, match='PRESERVE_EXISTING'):
        probe.main()
    assert receipt.read_bytes() == b'original'


def test_receipt_failure_still_releases_owned_lease(tmp_path, monkeypatch):
    from scripts import agent_lock
    probe = driver_args(monkeypatch, tmp_path/'new')
    held = dict(owner='codex',pid=123,branch='codex/sim-speed-ctrl2',acquired_unix=1.)
    released = []
    monkeypatch.setattr(agent_lock, 'acquire', lambda *a, **k: held)
    monkeypatch.setattr(agent_lock, 'status', lambda _: held)
    monkeypatch.setattr(agent_lock, 'release', lambda *a, **k: released.append(k))
    monkeypatch.setattr(probe, 'cohort', lambda _: 0)
    def fail(*_): raise OSError('ENOSPC')
    monkeypatch.setattr(probe, 'write', fail)
    with pytest.raises(OSError, match='ENOSPC'):
        probe.main()
    assert released == [dict(owner='codex')]


def test_commit_manifest_rejects_first_arm_source_mutation(tmp_path, monkeypatch):
    import hashlib
    from scripts import benchmark_lazy_camera as probe
    source = 'a'*40;root=tmp_path/source;(root/'sim').mkdir(parents=True)
    code=root/'sim/one.py';code.write_bytes(b'original\n')
    blob=hashlib.sha1(b'blob 9\0original\n').hexdigest()
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'archives':{source:{'sim/one.py':blob}}}))
    args=SimpleNamespace(archive_manifest=manifest,archive_manifest_sha256=probe.sha(manifest))
    monkeypatch.setattr(probe,'ROOT',root)
    probe.verify_archive(args,source)
    code.write_bytes(b'modified\n')
    with pytest.raises(ValueError,match='ARCHIVE_GIT_BLOB_CHANGED'):
        probe.verify_archive(args,source)


def test_admission_waits_for_peers_memory_and_decaying_load(tmp_path, monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    samples = iter([
        dict(peers=['research'], available_bytes=8*2**30, load=[1.,1.,1.]),
        dict(peers=[], available_bytes=5*2**30, load=[1.,1.,1.]),
        dict(peers=[], available_bytes=8*2**30, load=[2.1,1.,1.]),
        dict(peers=[], available_bytes=8*2**30, load=[2.,1.,1.]),
    ])
    slept = []
    monkeypatch.setattr(probe, 'host_sample', lambda: next(samples))
    monkeypatch.setattr(probe.time, 'sleep', slept.append)
    receipt = tmp_path/'admission.json'
    probe.wait_for_idle(receipt)
    assert slept == [10,10,10]
    data = json.loads(receipt.read_text())
    assert data['ready'] and len(data['samples']) == 4


def test_busy_admission_expires_without_physics_and_keeps_receipt(tmp_path, monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    times = iter([0.,3601.])
    monkeypatch.setattr(probe.time, 'monotonic', lambda: next(times))
    monkeypatch.setattr(probe, 'host_sample', lambda: dict(peers=['research'],available_bytes=8*2**30,load=[1.,1.,1.]))
    monkeypatch.setattr(probe.time, 'sleep', lambda _: pytest.fail('deadline already expired'))
    receipt = tmp_path/'refusal.json'
    with pytest.raises(TimeoutError, match='HOST_BUSY_NO_MEASUREMENT'):
        probe.wait_for_idle(receipt)
    assert json.loads(receipt.read_text())['ready'] is False
