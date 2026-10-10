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


def test_idle_after_deadline_does_not_admit_a_late_arm(tmp_path, monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    times = iter([0.,3595.,3605.])
    samples = iter([
        dict(peers=['research'],available_bytes=8*2**30,load=[1.,1.,1.]),
        dict(peers=[],available_bytes=8*2**30,load=[1.,1.,1.]),
    ])
    slept = []
    monkeypatch.setattr(probe.time, 'monotonic', lambda: next(times))
    monkeypatch.setattr(probe, 'host_sample', lambda: next(samples))
    monkeypatch.setattr(probe.time, 'sleep', slept.append)
    receipt = tmp_path/'late.json'
    with pytest.raises(TimeoutError, match='HOST_BUSY_NO_MEASUREMENT'):
        probe.wait_for_idle(receipt)
    assert slept == [5.]
    assert not json.loads(receipt.read_text())['ready']


def provider_record(probe, value):
    record = {'control': {'sim_time': 3.5, 'command': [0.,1.]}}
    for parts in probe.LATENCY_PATHS:
        node = record
        for part in parts[:-1]: node = node.setdefault(part,{})
        node[parts[-1]] = dict(n=7,p50=value,p90=value+1,max=value+2)
    return record


def test_projection_separates_only_registered_latency_and_key_order(tmp_path):
    from scripts import benchmark_lazy_camera as probe
    p = tmp_path/'student_record.json'
    a = provider_record(probe,1.)
    p.write_text(json.dumps(a));first,removed=probe.behavior_projection(p)
    p.write_text(json.dumps(provider_record(probe,99.),sort_keys=True))
    assert probe.behavior_projection(p)[0] == first and len(removed)==18
    changed=provider_record(probe,99.);changed['control']['sim_time']=3.6
    p.write_text(json.dumps(changed));assert probe.behavior_projection(p)[0] != first
    changed=provider_record(probe,99.)
    changed['solo']['provider']['provider']['inference_wall_ms']['n']=8
    p.write_text(json.dumps(changed));assert probe.behavior_projection(p)[0] != first
    changed=provider_record(probe,99.)
    changed['solo']['provider']['provider']['inference_wall_ms']['unknown']=1
    p.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='UNKNOWN_LATENCY'): probe.behavior_projection(p)


def test_concurrent_admission_allows_research_peers_and_rejects_limits(monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    row=dict(peers=['research'],available_bytes=6*2**30,load=[50.,20.,20.])
    monkeypatch.setattr(probe,'host_sample',lambda:row)
    assert probe.admit_concurrent()==row
    row['load'][0]=51.
    with pytest.raises(RuntimeError,match='LOAD_RETRY'):probe.admit_concurrent()
    row['load'][0]=1.;row['available_bytes']-=1
    with pytest.raises(RuntimeError,match='MEMORY_RETRY'):probe.admit_concurrent()


def test_batch_child_requires_exact_parent_source_run_and_barrier(tmp_path,monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    p=tmp_path/'batch.json';out=tmp_path/'s3-p1-eager'
    args=SimpleNamespace(parent_batch=p,expected_source_sha='a'*40,kind='s3',render_mode='eager',
        output=out,start_barrier=tmp_path/'start.json')
    p.write_text(json.dumps(dict(pid=123,source='a'*40,runs=[dict(kind='s3',mode='eager',output=str(out))])))
    monkeypatch.setattr(probe.os,'getppid',lambda:123)
    monkeypatch.setattr(probe.os,'kill',lambda pid,sig:None)
    probe.validate_parent_batch(args)
    args.render_mode='lazy-v1'
    with pytest.raises(ValueError,match='LIVE_REGISTERED'):probe.validate_parent_batch(args)
    args.render_mode='eager';args.start_barrier=tmp_path/'wrong'
    with pytest.raises(ValueError,match='START_BARRIER'):probe.validate_parent_batch(args)


def test_early_check_needs_motion_progress_and_normal_commands(tmp_path):
    from scripts import benchmark_lazy_camera as probe
    out=tmp_path/'run';robot=out/'robots/r3';robot.mkdir(parents=True)
    log=tmp_path/'log';log.write_text('healthy\n')
    (robot/'frames.jsonl').write_text(''.join(json.dumps(dict(sim_time=t))+'\n' for t in (3.,4.,5.)))
    (robot/'commands.jsonl').write_text(json.dumps(dict(kind='mecanum',forward=.1,turn=0.))+'\n'+ '{unfinished')
    (out/'own-controller.jsonl').write_text(json.dumps(dict(stage='explore',status='drive'))+'\n')
    probe.write(out/'evaluation-progress.json',dict(sim_time=12.,robots={'r3':dict(max_position_delta_m=.1)}))
    assert probe.early_state(out,'ego',log)['ok']
    probe.write(out/'evaluation-progress.json',dict(sim_time=12.,robots={'r3':dict(max_position_delta_m=0.)}))
    assert not probe.early_state(out,'ego',log)['ok']
    log.write_text('Traceback (most recent call last)')
    assert probe.early_state(out,'ego',log)['traceback']


def test_paired_driver_never_acquires_exclusive_lease(tmp_path,monkeypatch):
    from scripts import agent_lock
    probe=driver_args(monkeypatch,tmp_path/'new','paired')
    monkeypatch.setattr(agent_lock,'acquire',lambda *a,**k:pytest.fail('concurrent authorization'))
    monkeypatch.setattr(probe,'paired_cohort',lambda args:0)
    assert probe.main()==0


def test_early_append_observer_preserves_buffered_original_and_sees_commands(tmp_path):
    from scripts import benchmark_lazy_camera as probe
    host=Host(tmp_path);original=host._append
    probe.observe_append(host)
    # The real writer can buffer all bytes. The observer uses append call receipts.
    host._append('robots/r1/commands.jsonl',dict(kind='arm',pulse=1500))
    for t in (1.,2.,3.):host._append('robots/r1/frames.jsonl',dict(sim_time=t))
    assert host.rows['robots/r1/commands.jsonl']==[dict(kind='arm',pulse=1500)]
    record=json.loads((tmp_path/'command-progress.json').read_text())
    assert record['frames']==3 and record['commands']==1 and record['arm_commands']==1
    probe.write(tmp_path/'evaluation-progress.json',dict(sim_time=3.,robots={'r1':dict(max_position_delta_m=.1)}))
    log=tmp_path/'log';log.write_text('')
    assert probe.early_state(tmp_path,'s3',log)['ok']


def test_signal_during_popen_defers_until_child_is_registered(tmp_path,monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    children=[];signals={s:lambda *_:None for s in (probe.signal.SIGINT,probe.signal.SIGTERM,probe.signal.SIGHUP)}
    def interrupted(*_):
        assert len(children)==1
        raise InterruptedError('owned before unwind')
    signals[probe.signal.SIGTERM]=interrupted
    monkeypatch.setattr(probe.signal,'getsignal',lambda s:signals[s])
    monkeypatch.setattr(probe.signal,'signal',lambda s,h:signals.__setitem__(s,h))
    proc=SimpleNamespace(pid=123)
    def popen(*a,**kw):signals[probe.signal.SIGTERM](probe.signal.SIGTERM,None);return proc
    monkeypatch.setattr(probe.subprocess,'Popen',popen)
    with pytest.raises(InterruptedError,match='owned before unwind'):
        probe.spawn_registered(children,dict(output='one'),['unused'],tmp_path/'log')
    assert children[0][1] is proc


def test_cleanup_attempts_all_children_before_enospc_receipts(tmp_path,monkeypatch):
    from scripts import benchmark_lazy_camera as probe
    children=[(dict(output=str(tmp_path/f'run{i}')),SimpleNamespace(pid=i,returncode=0),None) for i in (1,2,3)]
    stopped=[];attempted=[]
    def stop(proc):
        stopped.append(proc.pid)
        if proc.pid==1:raise OSError('first stop failed')
    def receipt(path,row):
        assert stopped==[1,2,3]
        attempted.append(row['pid'])
        if row['pid']==1:raise OSError('ENOSPC')
    monkeypatch.setattr(probe,'stop_owned',stop)
    monkeypatch.setattr(probe,'write',receipt)
    with pytest.raises(RuntimeError,match='CHILD_CLEANUP'):probe.cleanup_children(children,tmp_path)
    assert stopped==[1,2,3] and attempted==[1,2,3]
