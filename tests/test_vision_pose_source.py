"""``vision_zero_tag_v1`` pose provider (issue #216): protocol/hash contract, the owned worker subprocess
(timeouts, crash, EOF, orphan), the provider's fail-closed path and the executor/host integration.

CI has no torch and no MuJoCo: the subprocess tests run ``tests/vision_loc_fake_worker.py`` (real
protocol, fixed observation) and the provider tests use ``InProcessWorker``. The real torch worker is
checked separately (``experiments/2026-09-27-vision-worker-closed-loop``).
"""
from __future__ import annotations

import copy
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import vision_loc_protocol as vp  # noqa: E402
from harness.vision_loc_client import (FrameRejected, InProcessWorker, VisionWorkerClient,  # noqa: E402
                                       WorkerFailure)
from harness.vision_pose_source import PRIOR_STD, VisionPoseSource  # noqa: E402

FAKE = ROOT / 'tests' / 'vision_loc_fake_worker.py'
VIS3_MAP = vp.load_json(vp.VIS3_DIR / 'maps' / 'zone_wide_door_walls_v3_notags.json')
CALIB = vp.load_json(ROOT / 'experiments' / '2026-09-26-zone-m1-owncam' / 'calibration_m1_dev.json')
DOCK = (-.85, -.85, 0.)
SEARCH_POSE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
NAN, INF = float('nan'), float('inf')
FRAME = np.full((480, 640, 3), 120, np.uint8)


def cfg(**over):
    c = vp.load_config()
    c.update(over)
    return c


def fake_client(mode='ok', timeout=5., startup=20., **kw):
    return VisionWorkerClient(cfg(frame_timeout_s=timeout, startup_timeout_s=startup),
                              argv=[sys.executable, str(FAKE), '--mode', mode], **kw)


def truth_obs(pf, pose):
    """Ideal observation (EDGE rows) of the static map at ``pose``: map ray cast, a test fixture only."""
    vl, _ = vp.load_vis3()
    vb, vt = vl.expected_rows(pf.geometry, np.asarray(pose, float)[None], pf.column_model_for(dict(pf.servo)))
    cols = pf.columns
    kinds, rows = [], []
    for v in (vb[0], vt[0]):
        ok = np.isfinite(v) & (v >= 0) & (v < 480)
        kinds.append(np.where(ok, vl.EDGE, vl.NONE).astype(int))
        rows.append(np.where(ok, v, np.nan))
    return vl.ColumnObs(np.asarray(cols), kinds[0], rows[0], rows[0].copy(), kinds[1], rows[1], rows[1].copy())


def provider(worker=None, *, prior=True, seed=3, truth=DOCK, fail_at=None):
    holder = {}
    w = worker or InProcessWorker(lambda seq, bgr: truth_obs(holder['p'].loc._pf, truth), fail_at=fail_at)
    p = VisionPoseSource(copy.deepcopy(VIS3_MAP), CALIB['params'], seed=seed, worker=w)
    holder['p'] = p
    p.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': dict(SEARCH_POSE)})
    if prior:
        p.init_prior(DOCK, PRIOR_STD, source='test: own dock')
    return p


def feed(p, t0, t1, frame=FRAME):
    reps, t = [], t0
    while t < t1 - 1e-9:
        reps.append(p.on_frame(round(t, 4), frame))
        t = round(t + .2, 4)
    return reps


# ---------------------------------------------------------------- pinned runtime / hashes
def test_pinned_vis3_files_match_the_registered_student():
    got = vp.check_frozen()
    reg = vp.prereg_student()
    assert got['vision_loc.py'] == reg['frozen_files_sha256']['vision_loc.py']
    assert got['selected_config_v3.json'] == reg['config']['sha256']
    assert vp.load_config()['model']['sha256'] == reg['model']['sha256']
    art = next(a for a in vp.load_json(ROOT / 'configs' / 'model_artifacts.json')['artifacts']
               if a['id'] == vp.load_config()['model']['artifact_id'])
    assert any(f['sha256'] == reg['model']['sha256'] for f in art['files'])


def test_a_changed_pinned_file_is_refused(tmp_path, monkeypatch):
    import shutil
    shutil.copytree(vp.VIS3_DIR, tmp_path / 'vis3', ignore=shutil.ignore_patterns('results', 'dev_configs*'))
    (tmp_path / '2026-09-26-markerless-probe').mkdir()
    shutil.copy(vp.VIS3_DIR.parent / '2026-09-26-markerless-probe' / 'markerless_probe.py',
                tmp_path / '2026-09-26-markerless-probe')
    monkeypatch.setattr(vp, 'VIS3_DIR', tmp_path / 'vis3')
    vp.check_frozen()
    with open(tmp_path / 'vis3' / 'vision_pf.py', 'a') as fh:
        fh.write('\n# edit\n')
    with pytest.raises(vp.ProtocolError, match='vision_pf.py'):
        vp.check_frozen()


@pytest.mark.parametrize('over', [{'device': 'mps'}, {'torch_threads': 2}, {'frame_timeout_s': 0},
                                  {'frame_timeout_s': NAN}, {'frame_timeout_s': None}, {'startup_timeout_s': True},
                                  {'sim_time_charge': {'charged': True}}, {'provider_id': 'tags_temporary'}])
def test_worker_config_boundaries(tmp_path, over):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({**vp.load_json(vp.CONFIG_FILE), **over}, allow_nan=True))
    with pytest.raises(vp.ProtocolError):
        vp.load_config(path)


# ---------------------------------------------------------------- protocol
def test_request_round_trip_and_closed_keys():
    line, digest = vp.encode_request(7, FRAME)
    seq, bgr, d = vp.decode_request(json.loads(line))
    assert (seq, d) == (7, digest) and np.array_equal(bgr, FRAME)
    req = json.loads(line)
    for bad in ({**req, 'top_rgb': 'x'}, {k: v for k, v in req.items() if k != 'seq'}, {**req, 'seq': -1},
                {**req, 'seq': True}, {**req, 'seq': None}, {**req, 'seq': 1.5}, {**req, 'bgr_sha256': '0' * 64},
                {**req, 'bgr_b64': ''}, {**req, 'schema': 'other'}, [], None, 0):
        with pytest.raises(vp.ProtocolError):
            vp.decode_request(bad)


@pytest.mark.parametrize('frame', [None, 0, [], np.zeros((0,), np.uint8), np.zeros((480, 640), np.uint8),
                                   np.zeros((480, 640, 3), np.float32), np.full((480, 640, 3), NAN),
                                   np.zeros((240, 320, 3), np.uint8)])
def test_bad_frames_are_refused_before_sending(frame):
    with pytest.raises(vp.ProtocolError):
        vp.encode_request(0, frame)


def _reply(**over):
    n = len(vp.columns())
    obs = {'b_kind': [1] * n, 'b_lo': [300.] * n, 'b_hi': [300.] * n, 't_kind': [0] * n, 't_lo': [None] * n,
           't_hi': [None] * n}
    for k, v in over.items():
        obs[k] = v
    r = vp.obs_reply(0, 'a' * 64, {k: [0] * n if k.endswith('kind') else [None] * n for k in vp.OBS_KEYS}, 1.)
    r['obs'] = obs
    r['obs_sha256'] = vp.sha256_bytes(json.dumps({k: obs[k] for k in vp.OBS_KEYS}, sort_keys=True,
                                                 separators=(',', ':'), allow_nan=True).encode())
    return r


def test_reply_validation():
    n = len(vp.columns())
    kind, obs, ms = vp.check_reply(_reply(), seq=0, bgr_sha256='a' * 64, n_columns=n)
    assert kind == 'obs' and int(obs.informative.sum()) == n and ms == 1.
    for bad in (dict(b_lo=[NAN] * n), dict(b_lo=[INF] * n), dict(b_lo=['1'] * n), dict(b_lo=[True] * n),
                dict(b_kind=[3] * n), dict(b_kind=[None] * n), dict(b_kind=[1] * (n - 1)), dict(b_kind=[]),
                dict(b_hi=[301.] * n), dict(t_lo=[1.] * n), dict(b_lo=[None] * n)):
        with pytest.raises(vp.ProtocolError):
            vp.check_reply(_reply(**bad), seq=0, bgr_sha256='a' * 64, n_columns=n)
    good = _reply()
    for bad in ({**good, 'seq': 1}, {**good, 'bgr_sha256': 'b' * 64}, {**good, 'obs_sha256': '0' * 64},
                {**good, 'infer_ms': -1}, {**good, 'infer_ms': NAN}, {**good, 'extra': 1}, None, [], {}):
        with pytest.raises(vp.ProtocolError):
            vp.check_reply(bad, seq=0, bgr_sha256='a' * 64, n_columns=n)
    rej = {'schema': vp.SCHEMA, 'seq': 0, 'bgr_sha256': 'a' * 64, 'rejected': 'x'}
    assert vp.check_reply(rej, seq=0, bgr_sha256='a' * 64, n_columns=n)[0] == 'rejected'
    with pytest.raises(vp.ProtocolError):
        vp.check_reply({**rej, 'rejected': ''}, seq=0, bgr_sha256='a' * 64, n_columns=n)


# ---------------------------------------------------------------- owned subprocess
def test_subprocess_round_trip_and_clean_eof_exit():
    c = fake_client()
    try:
        obs = c.observe(FRAME)
        assert int(obs.informative.sum()) == len(vp.columns()) and c.calls[0]['kind'] == 'obs'
        assert c.record()['failure'] is None
    finally:
        c.close()
    assert c.process.returncode == 0                       # stdin EOF ends the worker loop
    c.close()                                              # idempotent


@pytest.mark.parametrize('mode', ['die_after:1', 'garbage_after:1', 'error_after:1', 'wrong_seq'])
def test_worker_crash_or_bad_reply_fails_closed(mode):
    c = fake_client(mode)
    try:
        if mode != 'wrong_seq':
            c.observe(FRAME)
        with pytest.raises(WorkerFailure):
            c.observe(FRAME)
        assert c.failure and c.process.wait(timeout=5) is not None
        with pytest.raises(WorkerFailure):                  # never restarted
            c.observe(FRAME)
    finally:
        c.close()


def test_worker_timeout_kills_it_within_the_limit():
    c = fake_client('hang_after:0', timeout=1.)
    try:
        t0 = time.monotonic()
        with pytest.raises(WorkerFailure, match='timed out'):
            c.observe(FRAME)
        assert time.monotonic() - t0 < 4.
        assert c.process.wait(timeout=5) is not None
    finally:
        c.close()


@pytest.mark.parametrize('mode', ['no_ready', 'bad_ready'])
def test_worker_startup_failures_raise_and_leave_no_process(mode):
    with pytest.raises(WorkerFailure):
        fake_client(mode, startup=1.)


def test_rejected_frame_is_not_a_worker_failure():
    c = fake_client('reject')
    try:
        with pytest.raises(FrameRejected):
            c.observe(FRAME)
        assert c.failure is None
    finally:
        c.close()


def test_killed_parent_leaves_no_orphan_worker(tmp_path):
    pid_file = tmp_path / 'worker.pid'
    code = ('import sys,time; sys.path.insert(0, %r)\n'
            'from harness.vision_loc_client import VisionWorkerClient\n'
            'from harness import vision_loc_protocol as vp\n'
            'c = VisionWorkerClient(vp.load_config(), argv=[sys.executable, %r, "--pid-file", %r])\n'
            'print("up", flush=True); time.sleep(60)\n') % (str(ROOT), str(FAKE), str(pid_file))
    parent = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True)
    try:
        assert parent.stdout.readline().strip() == 'up'
        worker_pid = int(pid_file.read_text())
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                os.kill(worker_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.1)
        else:
            os.kill(worker_pid, signal.SIGKILL)
            pytest.fail('worker outlived its killed parent')
    finally:
        if parent.poll() is None:
            parent.kill()


# ---------------------------------------------------------------- provider
def test_provider_label_and_interface_match_the_executor_seam():
    from harness import m1_contract, m1_owncam_contract
    p = provider()
    assert p.source.startswith(vp.SOURCE_LABEL_PREFIX + ':')
    m1_owncam_contract.require_m1_source(p.source)
    m1_contract.require_m1_pose_source(p.source, 'test')
    for m in ('on_command', 'on_frame', 'report', 'set_motion_profile'):
        assert callable(getattr(p, m))
    assert callable(p.loc.estimate) and callable(p.loc.predict_to)


def test_provider_refuses_other_maps_params_and_seeds():
    w = InProcessWorker(lambda s, b: None)
    tagged = vp.load_json(ROOT / 'maps' / 'zones' / 'zone_wide_door_tags_v2.json')
    with pytest.raises(ValueError, match='registered'):
        VisionPoseSource(tagged, CALIB['params'], worker=w)
    changed = copy.deepcopy(VIS3_MAP)
    changed['obstacles'][0]['center_m'][0] += .01
    with pytest.raises(ValueError, match='registered'):
        VisionPoseSource(changed, CALIB['params'], worker=w)
    params = copy.deepcopy(CALIB['params'])
    params['particles'] = 10
    with pytest.raises(ValueError, match='M1 motion calibration'):
        VisionPoseSource(copy.deepcopy(VIS3_MAP), params, worker=w)
    for seed in (True, 1.5, None, '0'):
        with pytest.raises(TypeError):
            VisionPoseSource(copy.deepcopy(VIS3_MAP), CALIB['params'], seed=seed, worker=w)


@pytest.mark.parametrize('mean,std', [((NAN, 0., 0.), PRIOR_STD), ((INF, 0., 0.), PRIOR_STD), ((0., 0.), PRIOR_STD),
                                      (None, PRIOR_STD), ((0., 0., 0.), (0., .1, .1)), ((0., 0., 0.), (-.1, .1, .1)),
                                      ((True, 0., 0.), PRIOR_STD), ('abc', PRIOR_STD), ((0., 0., 0.), None)])
def test_prior_boundaries(mean, std):
    p = provider(prior=False)
    with pytest.raises(ValueError):
        p.init_prior(mean, std, source='x')


def test_prior_once_before_frames_and_needs_a_source():
    p = provider(prior=False)
    with pytest.raises(ValueError):
        p.init_prior(DOCK, PRIOR_STD, source='')
    p.on_frame(0., FRAME)
    with pytest.raises(RuntimeError):
        p.init_prior(DOCK, PRIOR_STD, source='late')
    q = provider()
    with pytest.raises(RuntimeError):
        q.init_prior(DOCK, PRIOR_STD, source='twice')


def test_without_a_prior_nothing_is_initialised_and_the_worker_is_not_called():
    p = provider(prior=False)
    reps = feed(p, 0., 2.)
    assert not any(r.initialized for r in reps) and p.worker.calls == []
    assert not p.loc.estimate()['initialized']


def test_converges_with_ideal_observations_and_is_deterministic():
    runs = []
    for _ in range(2):
        p = provider(seed=5)
        reps = feed(p, 0., 3.)
        runs.append([r.as_dict() for r in reps])
    assert runs[0] == runs[1]
    last = provider(seed=5)
    rep = feed(last, 0., 3.)[-1]
    assert rep.initialized and math.hypot(rep.x_m - DOCK[0], rep.y_m - DOCK[1]) < .05
    assert rep.std_xy_m < PRIOR_STD[0] and rep.since_tag_s is not None and rep.since_tag_s <= .2 + 1e-9
    assert last.counts['measured'] > 0 and last.loc.estimate()['since_tag_s'] == rep.since_tag_s
    assert last.record()['sim_time_charge']['charged'] is False


@pytest.mark.parametrize('frame', [None, np.zeros((0,), np.uint8), np.zeros((480, 640, 3), np.float64),
                                   np.full((480, 640, 3), NAN), np.zeros((480, 640), np.uint8), 'jpeg'])
def test_corrupted_frames_skip_only_their_measurement(frame):
    p = provider()
    feed(p, 0., 1.)
    before = p.counts['worker_calls']
    rep = p.on_frame(1.2, frame)
    assert rep.initialized and p.counts['rejected_frames'] == 1 and p.counts['worker_calls'] == before
    assert p.failure is None


@pytest.mark.parametrize('t', [NAN, INF, None, True, '1'])
def test_bad_frame_times_raise(t):
    with pytest.raises(ValueError):
        provider().on_frame(t, FRAME)


def test_worker_failure_fails_closed_for_the_rest_of_the_episode():
    p = provider(fail_at=5)
    reps = feed(p, 0., 1.6)
    k = next(i for i, r in enumerate(reps) if not r.initialized)
    assert k > 0 and all(r.initialized for r in reps[:k]) and not any(r.initialized for r in reps[k:])
    assert p.failure and p.failure['t'] == round(.2 * k, 4) and p.worker.closed
    assert [c['kind'] for c in p.worker.calls] == ['obs'] * 5
    calls = len(p.worker.calls)
    later = feed(p, 1.6, 3.)
    assert not any(r.initialized for r in later) and len(p.worker.calls) == calls
    est = p.loc.estimate()
    assert est['initialized'] is False and 'failure' in est and p.loc.initialized is False
    assert p.record()['failure']['reason'].endswith('injected worker failure')


def test_unsettled_frames_are_not_sent_to_the_worker():
    p = provider()
    feed(p, 0., 1.)
    n = p.counts['worker_calls']
    p.on_command({'t': 1.0, 'kind': 'look', 'pan_pulse': 1700})
    p.on_frame(1.1, FRAME)                                 # 0.1 s after an own pan command < settle 0.2 s
    assert p.counts['worker_calls'] == n
    p.on_frame(1.4, FRAME)
    assert p.counts['worker_calls'] == n + 1


# ---------------------------------------------------------------- executor + host integration
def _vision_executor(fail_at=None):
    from harness import zone_own_executor as zox
    from tests.test_zone_own_executor import ROWS_Y, SHEET
    ex = zox.ZoneOwnExecutor('r1', copy.deepcopy(VIS3_MAP), CALIB['params'], SHEET, skill_factory=lambda o, robot_id: None,
                             pose_estimate_cls=tuple, search_rows_y=ROWS_Y, judgments=False, seed=3)
    holder = {}
    # self-consistent fixture: the ideal observation at the filter's own mean (plumbing only, not a measurement)
    w = InProcessWorker(lambda seq, bgr: truth_obs(holder['p'].loc._pf, _mean(holder['p'].loc._pf)), fail_at=fail_at)
    p = VisionPoseSource(ex.map, ex.params, seed=3, worker=w)
    holder['p'] = p
    p.init_prior(DOCK, PRIOR_STD, source='test: own dock')
    ex._require_owncam(p.source, 'pose provider')         # as PR #229 StudyTeamHost does before ex.pose = provider
    ex.pose = p
    return ex, p


def _mean(pf):
    e = pf.estimate()
    return (e['x'], e['y'], e['yaw']) if e.get('initialized') else DOCK


def _motion(port, after=-1.):
    return [row for row in port.log if row[0] > after + 1e-9 and row[1] in ('mecanum', 'drive') and any(
        abs(float(row[2].get(k, 0.))) > 1e-9 for k in ('forward', 'left', 'turn'))]


def test_host_worker_crash_stops_base_motion_and_holds():
    """Worker dies while driving: no base motion after the next own tick, a hold at once, one terminal event."""
    from tests.test_zone_own_executor_host import FakeHost, team, terminal
    fail = {}
    ex, p = _vision_executor()

    def goto(host, kind, event, now):
        if kind == 'start':
            assert host.call('r1', 'goto', [.4, -.85])['accepted']
            for rid in ('r2', 'r3'):
                host.call(rid, 'hold', 60.)

    def kill(host):
        fail['t'] = float(host.world.data.time)
        p.worker.fail_at = p.worker.seq

    host = FakeHost(team(ex), goto, hooks=[(12., kill)])
    host.run(40.)
    port = host.robots['r1'].port
    assert _motion(port, -1.)[:1] and [r for r in _motion(port) if r[0] < fail['t']], 'fixture must drive first'
    assert p.failure is not None and fail['t'] <= p.failure['t'] <= fail['t'] + .25
    moving = _motion(port, p.failure['t'] + .1 + 1e-6)
    assert not moving, moving[:3]
    assert any(r[1] == 'hold' and p.failure['t'] - 1e-6 <= r[0] <= p.failure['t'] + .1 + 1e-6 for r in port.log)
    ends = terminal(host, 'r1')
    assert len(ends) == 1 and ends[0]['event'] == 'job_failed', ends
    assert any(e['event'] == 'pose_uncertain' and e['robot_id'] == 'r1' for e in host.event_log)


def test_new_tests_are_collected_by_ci():
    sys.path.insert(0, str(ROOT / 'scripts'))
    import fnmatch
    import run_ci_tests
    assert any(fnmatch.fnmatch('tests/test_vision_pose_source.py', pat) for pat in run_ci_tests.TEST_PATTERNS)
