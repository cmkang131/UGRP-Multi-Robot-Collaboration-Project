"""Own RGB/executor contracts only: never construct a simulation or renderer."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import self_map_executor as ex
from harness import self_map_integration as sm
from scripts import run_self_map_diagnostic as run
from test_self_map_integration import fixture_mapper, receive


def test_default_off_no_construction_or_io(monkeypatch, tmp_path):
    legacy = object()
    monkeypatch.setattr(ex, 'SelfMapExecutor', lambda **kw: pytest.fail('constructed off'))
    assert ex.make_executor(legacy) is legacy
    assert run.main(['--output', str(tmp_path/'absent'), '--expected-source-sha', 'a'*40,
                     '--seed', '93510']) == 0
    assert not (tmp_path/'absent').exists()
    monkeypatch.setattr(run.platform, 'system', lambda: 'Darwin')
    with pytest.raises(RuntimeError, match='NO_MAC'):
        run.main(['--output', str(tmp_path/'absent'), '--expected-source-sha', 'a'*40,
                  '--seed', '93510', '--execute', '--self-map-executor', ex.OPTION])


def test_rebuild_refits_each_historical_pose_and_does_not_shift_anchor(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, pose_rebuild='refit_history_v1')
    receive(mapper, 1)
    state['pose'] = np.array([.04, 0., 0.])
    receive(mapper, 2)
    # Corrupt a stored pose to demonstrate descriptor refit rather than reuse.
    mapper.history[1]['pose'] = np.array([.2, .1, .1])
    mapper.zones.tracks.append({'confirmed_t': 1.})
    state['pose'] = np.array([.3, 0., 0.])
    result = receive(mapper, 3)
    assert result['map_updated'] and not mapper.rebuild_required
    assert mapper.rebuilds[-1]['committed'] and mapper.rebuilds[-1]['refitted'] == 2
    np.testing.assert_allclose(mapper.history[0]['pose'], [0, 0, 0])
    np.testing.assert_allclose(mapper.history[1]['pose'], [.04, 0, 0], atol=1e-9)
    expected = sm.PoseGrid('r1', .1)
    for r in mapper.history:
        expected.insert(frame_id=r['observation'].frame_id, pose=r['pose'], **r['rays'])
    assert mapper.grid.navigation.odds == expected.navigation.odds
    assert not mapper.zones.tracks and not result['complete']


def test_unresolved_rebuild_is_atomic_and_blocks_completion(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, pose_rebuild='refit_history_v1')
    receive(mapper, 1)
    receive(mapper, 2)
    original_fit = mapper.slam._fit
    monkeypatch.setattr(mapper.slam, '_fit', lambda p, d, prior, frame:
        (None, [], {}) if frame == 2 else original_fit(p, d, prior, frame))
    before = copy.deepcopy(mapper.grid.navigation.odds)
    state['pose'] = np.array([.3, 0, 0])
    result = receive(mapper, 3)
    assert mapper.grid.navigation.odds == before
    assert mapper.rebuilds[-1]['unresolved'] == [2]
    assert not result['map_updated'] and not result['complete']


def test_current_footprint_never_becomes_rgb_evidence_or_erases_obstacle(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, navigation_support='current_footprint_v1')
    mapper.grid.navigation.odds[(0, 0)] = 1.
    before = mapper.snapshot()
    planning = mapper.planning_grid()
    assert planning.support and planning.state((0, 0)) == 1
    assert mapper.snapshot() == before
    assert not mapper.grid.navigation.floor_frames


class Sweep:
    def __init__(self):
        self.events, self.phase = [], None
    def request_sweep(self, t, reason):
        self.events.append(dict(t=t, reason=reason))
    def start_sweep(self, pose, t):
        self.phase = 'sensor_sweep'
    def command(self, costmap, pose, plan, t):
        self.phase = None
        self.events.append(dict(t=t, reason='sensor_sweep_completed'))
        return dict(t=t, kind='mecanum', forward=0., left=0., turn=0., duration_s=.1)


def step(c, frame, t):
    command, trace = c.receive(robot_id=c.robot_id, t=t, frame_id=frame,
        rgb=np.zeros((480, 640, 3), np.uint8))
    if command:
        c.command(command)
    return command, trace


def test_pan_spin_frontier_actual_pulse_arrival_and_reobserve(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=100)
    for i in range(1, 11):
        command, trace = step(c, i, float(i))
        if i <= 9:
            assert command['kind'] == 'look' and command['pan_pulse'] == ex.PANS[i-1]
    assert c.stage == 'spin'
    step(c, 11, 11.)
    assert c.stage == 'select'
    monkeypatch.setattr(ex, 'frontier_candidates', lambda *a, **k: [
        dict(target_m=[.35, .05], heading_rad=0., path_m=[[0, 0], [.35, .05]])])
    # Real A*, pursuit, calibrated pulse and observed-footprint collision check.
    command, trace = step(c, 12, 12.)
    assert command['kind'] == 'mecanum' and command['forward'] > 0
    assert c.stage == 'drive' and trace['executed_path_m']
    # A visual estimate reaches the selected goal, triggering a new sweep.
    for i in range(1, 6):
        state['pose'] = np.array([.07*i, .01*i, 0])
        step(c, 12+i, 12.+.2*i)
    assert c.stage == 'pan'
    assert any(e['reason'] == 'frontier_arrival' for e in c.events)


def test_no_frontier_and_unavailable_pose_never_declare_completion(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch)
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=5)
    c.stage = 'select'
    monkeypatch.setattr(ex, 'frontier_candidates', lambda *a, **k: [])
    _, trace = step(c, 1, 1.)
    assert c.stage == 'pan' and not c.done and not trace['complete']
    state['blank'] = True
    command, trace = step(c, 2, 5.)
    assert c.done and c.stop_reason == 'sim_time_cap' and command['kind'] == 'hold'
    assert not trace['complete']


def test_terminal_completion_emits_hold_and_never_more_motion(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    row = receive(mapper, 1)
    monkeypatch.setattr(mapper, 'receive', lambda **kw: dict(row, complete=True))
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep())
    command, _ = step(c, 2, 2.)
    assert command['kind'] == 'hold' and c.stop_reason == 'self_map_complete'
    monkeypatch.setattr(mapper, 'receive', lambda **kw: pytest.fail('terminal reads'))
    assert step(c, 3, 3.)[0]['kind'] == 'hold'


class RecordingPlant:
    """In-memory clock + existing JPEG fixture data, no simulated dynamics."""
    instances = []
    fail_at = None
    camera = 'robot_cam'
    def __init__(self, b, out, seed):
        self.b, self.out, self.now, self.frame = b, out, 1.3, 0
        self.commands = {'r3': b['initial_servo'].copy()}
        self.issued, self.closed = [], False
        self.instances.append(self)
    def reset(self, cap):
        return self.now
    def set_deadline(self, t):
        self.deadline = t
    def issue(self, robot, action):
        self.issued.append((self.now, action))
    def capture(self):
        if self.fail_at == self.frame:
            raise OSError('fixture capture failure')
        data = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))[1].tobytes()
        path = self.out/f'robots/r3/rgb/{self.frame:05d}.jpg'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        obs = dict(robot_id='r3', camera=self.camera, frame_id=self.frame+1,
                   sim_time=self.now, sha256=hashlib.sha256(data).hexdigest())
        with (self.out/'robots/r3/frames.jsonl').open('a') as f:
            f.write(json.dumps(obs)+'\n')
        self.frame += 1
        return {'r3': (obs, None)}
    def eval_sample(self):
        return None
    def advance_to(self, t):
        assert t <= self.deadline
        self.now = t
    def close(self):
        self.closed = True


def controller_factory(**kw):
    return ex.make_executor(**kw, sweep=Sweep())


def test_runner_all_10hz_frames_terminal_stop_and_error_preservation(tmp_path, monkeypatch):
    out = tmp_path/'raw'
    result = run.acquire(out, run.bundle('a'*40, 93510, 1.), RecordingPlant,
                         controller_factory=controller_factory)
    assert result['status'] == 'RECORDED' and result['stop_reason'] == 'sim_time_cap'
    assert result['frames'] == 11 and result['rgb_ledger_verified']
    plant = RecordingPlant.instances[-1]
    assert plant.closed and plant.issued[-1][1] == {'kind': 'hold'}
    assert len(list(out.glob('robots/r3/rgb/*.jpg'))) == 11
    trace = [json.loads(l) for l in (out/'trace.jsonl').read_text().splitlines()]
    assert trace[-1]['t'] == 2.3 and not trace[-1]['complete']
    monkeypatch.setattr(RecordingPlant, 'fail_at', 3)
    failed = run.acquire(tmp_path/'failed', run.bundle('a'*40, 93511, 1.), RecordingPlant,
                         controller_factory=controller_factory)
    assert failed['status'] == 'HOST_ERROR' and failed['frames'] == 3
    assert RecordingPlant.instances[-1].closed
    assert (tmp_path/'failed/result.json').exists() and (tmp_path/'failed/map.json').exists()


def test_top_camera_never_reaches_control(tmp_path, monkeypatch):
    monkeypatch.setattr(RecordingPlant, 'camera', 'top')
    r = run.acquire(tmp_path/'bad-camera', run.bundle('a'*40, 93512, 1.), RecordingPlant,
                    controller_factory=controller_factory)
    assert r['status'] == 'HOST_ERROR' and r['frames'] == 0
    assert r['failure']['message'] == 'OWN_ROBOT_CAMERA_REQUIRED'


def test_registered_workflow_and_storage_budget():
    from sim.workflow_manager import plan
    root = Path(__file__).parents[1]
    record = plan(root, 'self-map-diagnostic', ['--output', '/tmp/selfmap-contract-only',
        '--expected-source-sha', 'a'*40, '--seed', '93510'])
    assert 'scripts.run_self_map_diagnostic' in record['command']
    budget = run.storage_estimate(180)
    assert budget['frames'] == 1801 and budget['per_run_bytes'] <= 384*1024**2


def test_existing_sweep_progress_is_odom_only_but_collision_pose_is_map_frame():
    from harness.active_frontier_cycle import CycleNavigator
    # Exercise the existing sweep methods without constructing a native planner.
    sweep = CycleNavigator.__new__(CycleNavigator)
    sweep.locked = False
    sweep.events = []
    sweep.sweep_pending = 'initial'
    sweep.reset_action = lambda: None
    sweep.start_sweep([0., 0., .2], 0.)
    seen = []
    costmap = SimpleNamespace(pose_clear=lambda p: seen.append(list(p)) or True)
    frame = ex.SweepFrame(costmap, 1.)
    command = sweep.command(frame, np.array([0., 0., .3]), {}, .2)
    assert sweep.sweep_rotation == pytest.approx(.1)
    assert seen[0][2] == pytest.approx(1.3)
    assert command['turn'] > 0
    sweep.command(frame, np.array([0., 0., .4]), {}, 30.)
    assert sweep.phase is None and sweep.events[-1]['reason'] == 'sensor_sweep_incomplete'


def test_completion_during_pulse_waits_for_calibrated_interval(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    row = receive(mapper, 1)
    c = ex.SelfMapExecutor('r1', mapper=mapper, sweep=Sweep())
    c.next_control = 2.2
    monkeypatch.setattr(mapper, 'receive', lambda **kw: dict(row, complete=True))
    assert c.receive(robot_id='r1', t=2.1, frame_id=2, rgb=None)[0] is None
    assert not c.done
    assert c.receive(robot_id='r1', t=2.2, frame_id=3, rgb=None)[0]['kind'] == 'hold'
    assert c.done


def test_large_generated_text_roundtrip_and_manifest(tmp_path):
    p = tmp_path/'trace.jsonl'
    content = b'{"t": 1, "frame_id": 1}\n'*4000
    p.write_bytes(content)
    run.compress_text(tmp_path)
    assert not p.exists()
    restored, _ = run.read(p)
    assert restored.encode() == content
    manifest = json.loads((tmp_path/'compression-manifest.json').read_text())
    assert manifest[0]['sha256'] == hashlib.sha256(content).hexdigest()
