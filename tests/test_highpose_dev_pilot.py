"""v96 DEV_PILOT admission (coordinator 2026-10-03): exact sha256 only,
FUNCTIONAL_DEV only, never promotable; MEASURED_SIM path unchanged.

The synthetic DEV file mirrors the real calibration_dev_pilot.json layout
(status DEV_PILOT, dev_rule DEV_PILOT_C0_ZERO_v1, confirmatory false, c0 = 0,
10 unloaded params.motion fields null + listed in missing, DEV provenance
siblings). Trust is installed ONLY by monkeypatching dev_pilot_admission.
"""
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from tests.test_zone_final_pair_v3 import MAPS
from tests.highpose_fixtures import d5_output, trust_fixture, write
from harness import zone_pair_highpose_contract as c
from harness import zone_pair_highpose_starts as starts
from scripts import run_pair_highpose as run

UNLOADED = ['gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'noise_rel', 'noise_abs',
            'scale_std', 'scale_walk', 'use_scale', 'rest_noise']
REAL = Path('/Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/result/calibration_dev_pilot.json')
REAL_SHA = '398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5'
C_SHA = 'aba4ac586b2554844ad5b4b17efe968a4247278664ffb433f83f6785ca1769c4'
V102_SHA = 'ce447ada62295d24c7f7a5929ce878e70fa297651e16ca192536f4a403cd8c5f'
V102_PATH = (Path(__file__).resolve().parents[1]/'experiments'/'2026-10-05-loaded-gain-calibration-v102'/'products'
             /'loaded_v102'/'calibration_dev_pilot_loaded_v102.json')
V104_SHA = 'a04371f614bd7f6f7583ef4f4121abce1c337fd5652899dbfe0fe6df1703f926'
V104_PATH = (Path(__file__).resolve().parents[1]/'experiments'/'2026-10-05-loaded-rest-calibration-v104'/'products'
             /'calibration_dev_pilot_loaded_v102_rest_v104.json')
V101 = Path(__file__).resolve().parents[1]/'experiments'/'2026-10-05-unloaded-gain-calibration-v101'/'products'
C_PATH = V101/'C'/'calibration_dev_pilot_unloaded_v101.json'
BASE_COPY = Path(__file__).resolve().parents[1]/'experiments'/'2026-10-03-v92-dev-pilot'/'calibration_dev_pilot.json'


def dev_file(tmp_path, *, mutate=None):
    _, cal = d5_output(tmp_path)
    write(tmp_path/'input_manifest_dev.json', {'schema': 'ugrp.v92_dev_pilot_inputs.v1',
        'execution_source_sha': cal['source_sha'], 'working_tree_dirty': False,
        'script_sha256': 'c'*64, 'files': []})
    cal = copy.deepcopy(cal)
    cal.update(status='DEV_PILOT', dev_rule='DEV_PILOT_C0_ZERO_v1', confirmatory=False,
               assembler_sha256=None, measurement_manifest_sha256=None,
               dev_manifest_sha256=c.base.sha(tmp_path/'input_manifest_dev.json'),
               measured_parent={'path': 'outputs/x/calibration.json', 'sha256': 'd'*64, 'status': 'PARTIAL'})
    cal['params']['motion_loaded']['deadband']['c0'] = [0., 0., 0.]
    cal['params']['motion'] = {k: None for k in UNLOADED}
    cal['missing'] = [{'field': 'params.motion.'+k, 'reason': 'no approved unloaded profile'} for k in UNLOADED]
    if mutate:
        mutate(cal)
    path = tmp_path/'calibration_dev_pilot.json'
    write(path, cal)
    return path, cal


def admit(monkeypatch, *shas):
    dev = copy.deepcopy(c.registry()['dev_pilot'])
    dev['admitted_calibration_sha256'] = list(shas)
    monkeypatch.setattr(c, 'dev_pilot_admission', lambda: dev)
    return dev


def test_registry_keeps_measured_list_empty_and_admits_one_exact_dev_sha():
    adm, _ = c.d5_admission()
    assert adm['completed_measurements'] == [] and c.registry()['runnable'] is False
    dev = c.registry()['dev_pilot']
    assert dev['admitted_calibration_sha256'] == [REAL_SHA, C_SHA, V102_SHA, V104_SHA]
    assert dev['promotable'] is False and dev['run_status'] == 'FUNCTIONAL_DEV'
    assert dev['tensorboard_cohort'] != 'FUNCTIONAL_DEV_REPLAY' and dev['cohort_role'] != 'FUNCTIONAL_DEV_REPLAY'


def test_dev_file_accepted_only_by_exact_admitted_sha(tmp_path, monkeypatch):
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    with pytest.raises(ValueError, match='not admitted'):
        c.dev_pilot_calibration(path, sha, MAPS[0])
    admit(monkeypatch, sha)
    cal = c.dev_pilot_calibration(path, sha, MAPS[0])
    assert cal['params']['motion_loaded']['deadband']['c0'] == [0., 0., 0.]
    assert cal['missing'] == [] and cal['dev_pilot_fill']['label'] == 'DEV'
    fill = c.dev_pilot_admission()['unloaded_motion_fill']
    assert cal['params']['motion'] == fill['values'] and cal['params']['motion']['tau_stop_s'] == cal['params']['motion']['tau_s']
    assert not {'use_scale', 'rest_noise', 'tau_axis_s'} & set(cal['params']['motion'])   # code defaults, never None
    assert c.admitted_calibration(path, sha, MAPS[0]) == cal
    path.write_text(path.read_text().replace('DEV_PILOT_C0_ZERO_v1', 'DEV_PILOT_C0_ZERO_v1 '))
    with pytest.raises(ValueError):
        c.dev_pilot_calibration(path, sha, MAPS[0])


@pytest.mark.parametrize('fault', ['c0', 'u1', 'status', 'rule', 'confirmatory', 'extra_missing',
                                   'filled_motion', 'manifest', 'parent', 'dirty'])
def test_dev_rule_and_provenance_faults_rejected(tmp_path, monkeypatch, fault):
    def mutate(cal):
        if fault == 'c0': cal['params']['motion_loaded']['deadband']['c0'] = [.01, 0., 0.]
        elif fault == 'u1': cal['params']['motion_loaded']['deadband']['u1'] = [0., .02, .02]
        elif fault == 'status': cal['status'] = 'MEASURED_SIM'
        elif fault == 'rule': cal['dev_rule'] = 'DEV_PILOT_C0_ZERO_v2'
        elif fault == 'confirmatory': cal['confirmatory'] = True
        elif fault == 'extra_missing': cal['missing'].append({'field': 'pair_model.slope_to_yaw_ratio'})
        elif fault == 'filled_motion': cal['params']['motion']['tau_s'] = .3
        elif fault == 'manifest': cal['dev_manifest_sha256'] = 'e'*64
        elif fault == 'parent': cal['measured_parent']['status'] = 'MEASURED_SIM'
    path, _ = dev_file(tmp_path, mutate=mutate)
    if fault == 'dirty':
        m = json.loads((tmp_path/'input_manifest_dev.json').read_text()); m['working_tree_dirty'] = True
        write(tmp_path/'input_manifest_dev.json', m)
    admit(monkeypatch, c.base.sha(path))
    with pytest.raises(ValueError):
        c.dev_pilot_calibration(path, c.base.sha(path), MAPS[0])


def test_neither_path_accepts_the_other_file(tmp_path, monkeypatch):
    dev_dir, measured_dir = tmp_path/'dev', tmp_path/'measured'
    dev_dir.mkdir(); measured_dir.mkdir()
    dev_path, dev_cal = dev_file(dev_dir)
    m_path, m_cal = d5_output(measured_dir)
    # Even with the DEV sha wrongly placed on the MEASURED_SIM trust root.
    trusted = trust_fixture(monkeypatch, m_path, m_cal)
    trusted['completed_measurements'][0]['calibration_sha256'] = c.base.sha(dev_path)
    with pytest.raises(ValueError):
        c.measured_calibration(dev_path, c.base.sha(dev_path), MAPS[0])
    # Even with the MEASURED file's sha wrongly admitted as DEV.
    admit(monkeypatch, c.base.sha(m_path))
    with pytest.raises(ValueError, match='status/rule'):
        c.dev_pilot_calibration(m_path, c.base.sha(m_path), MAPS[0])


def test_dev_run_is_functional_dev_and_can_never_be_promoted(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_v3 import FakePhysics, FakeRuntime
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'], 'p03', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    assert bundle['run_status'] == 'FUNCTIONAL_DEV' and bundle['promotable'] is False
    assert bundle['dev_pilot_unloaded_motion_fill']['source_sha256'] == c.base.sha(c.ROOT/'harness/owncam_localizer.py')
    result = run.run_case(bundle, tmp_path/'run', seed=911, backend_factory=FakePhysics,
                          runtime_factory=FakeRuntime, calibration=path, calibration_sha=sha)
    for record in (result, result['checkpoint']):
        assert {k: record[k] for k in c.DEV_PILOT_LABELS} == c.DEV_PILOT_LABELS
    stored = json.loads((tmp_path/'run'/'result.json').read_text())
    assert stored['run_status'] == 'FUNCTIONAL_DEV' and stored['tensorboard_cohort'] == 'v98-dev-pilot-functional'
    # Promotion: every confirmatory entry refuses; relabelling also fails.
    for record in (result, stored, result['checkpoint'], {'cases': [stored]}):
        with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
            c.require_promotable(record)
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        starts.qualify_run(stored, {'id': 'confirm-01'}, {}, [])
    relabelled = {**stored, 'admission_mode': 'MEASURED_SIM', 'promotable': True}
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        starts.qualify_run(relabelled, {'id': 'confirm-01'}, {}, [])
    measured_bundle = {**bundle, **{k: None for k in c.DEV_PILOT_LABELS}}
    measured_bundle.pop('admission_mode')
    with pytest.raises(ValueError):
        run.run_case(measured_bundle, tmp_path/'run2', seed=911, backend_factory=FakePhysics,
                     runtime_factory=FakeRuntime, calibration=path, calibration_sha=sha)
    assert not (tmp_path/'run2').exists()


def test_cli_dev_pilot_needs_explicit_flag(tmp_path, monkeypatch, capsys):
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    argv = ['--check', 'p03', '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'none'),
            '--calibration', str(path), '--calibration-sha256', sha]
    assert run.main(argv) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['runnable'] is False and plan['admission_mode'] == 'MEASURED_SIM'
    assert run.main(argv+['--admission', 'dev-pilot']) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan['runnable'] is True and plan['blocked_on'] == [] and plan['denominator'] == 3
    assert plan['run_status'] == 'FUNCTIONAL_DEV' and plan['promotable'] is False


def test_runtime_job_limit_matches_case_cap_under_dev_pilot(tmp_path, monkeypatch):
    from harness.zone_pair_highpose_runtime import Runtime
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    runtime = Runtime(c.resolve(MAPS[0])[0], path, sha, seed=911)
    try:
        assert runtime.job_sim_limit_s == c.CASE_CAP_S == 900.
        assert c.execution_timing('p03')['executor_job_sim_limit_s'] == 900.
        actor = runtime.actors['r1']
        assert actor.job_sim_limit_s == 900.
        actor.now = 5.
        actor._start('test', 'pair', {})
        largest = max(r['lower_bound_s'] for m in MAPS for r in
                      __import__('harness.zone_pair_highpose_timing', fromlist=['bounds']).bounds(c.resolve(m)[0], 'carry'))
        assert largest > 120.
        assert not actor.expire_if_due(5.+largest) and not actor.expire_if_due(5.+900.)
        assert actor.expire_if_due(5.+900.1)
        assert runtime.record()['executor_job_sim_limit_s'] == 900.
    finally:
        runtime.close()


def test_runtime_adopts_and_records_the_registered_v98_frame_gate(tmp_path, monkeypatch):
    from harness import zone_pair_highpose_frame_gate as fg
    from harness.zone_pair_highpose_runtime import OwnExecutor, Runtime
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    gates = c.own_image_gates()
    runtime = Runtime(c.resolve(MAPS[0])[0], path, sha, seed=911)
    try:
        assert all(type(actor) is OwnExecutor for actor in runtime.actors.values())
        rec = runtime.record()['own_image_gates']
        assert rec['sha256'] == gates['sha256'] == c.registry()['own_image_gates']['sha256']
        assert rec['values'] == gates['values']
        assert rec['frame_gate'] == fg.record() and rec['frame_gate']['profile'] == c.FRAME_GATE_PROFILE
        assert (rec['frame_gate']['frame_contrast_spread_min'], rec['frame_gate']['frame_value_std_min']) == (1., .22)
        for provider in runtime.providers.values():
            assert provider.provider.runtime_contract['own_image_gates']['sha256'] == gates['sha256']
            assert provider.provider.worker.gates == gates['values']
    finally:
        runtime.close()


def test_staged_runtime_adopts_the_same_v98_frame_gate(tmp_path, monkeypatch):
    from harness import zone_pair_highpose_staging as st
    from harness.zone_final_pair_skill import task
    from harness.zone_pair_highpose_runtime import OwnExecutor
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    static = c.resolve(MAPS[0])[0]
    stations = st.spawn_poses(static, task(static)['beam_pose'], 'high_hold_staged')
    staging = {'stage': 'high_hold_staged', 'stations_xyyaw': stations,
               'priors': {rid: st.stated_prior(station) for rid, station in stations.items()}}
    runtime = st.StagedRuntime(static, path, sha, seed=911, stage='high_hold_staged', staging=staging)
    try:
        assert all(type(actor) is OwnExecutor for actor in runtime.actors.values())
        assert runtime.record()['own_image_gates']['sha256'] == c.own_image_gates()['sha256']
        assert runtime.record()['look_recovery']['id'] == 'v98_dock_look_relook_v1'
        assert runtime.team.rendezvous_timeout_s == 30.
    finally:
        runtime.close()


@pytest.mark.skipif(not REAL.exists(), reason='local DEV_PILOT artifact (PR #369) not present')
def test_real_dev_pilot_file_validates_on_every_map():
    assert c.base.sha(REAL) == REAL_SHA
    for map_id in c.registry()['maps']:
        cal = c.admitted_calibration(REAL, REAL_SHA, map_id)
        assert cal['dev_pilot_fill']['label'] == 'DEV'
        assert cal['params']['motion_loaded']['deadband']['c0'] == [0., 0., 0.]
    with pytest.raises(ValueError):
        c.measured_calibration(REAL, REAL_SHA, MAPS[0])


def _probe():
    spec = importlib.util.spec_from_file_location(
        'probe_headless', c.ROOT/'experiments/2026-10-03-pair-carry-highpose/probe_headless.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_headless_nominal_replay_with_c0_zero_carry_leg(tmp_path, monkeypatch):
    """Nominal reviewer schedule through headless MuJoCo + a carry leg at HIGH.

    The real c0 consumers run in lockstep under the DEV fixture: the carry
    command inverse (motor_command), its admissibility check, and the HIGH
    provider's PF prediction with the c0 = 0 deadband. Grip decisions are
    log-only and covered on recorded frames in test_highpose_transit.py; this
    replay has no renderer, so align/grasp from own RGB and the full
    Runtime/Team wiring are NOT exercised here. Eval positions only score.
    """
    from harness.vision_pose_source_highpose import HighPoseSource
    from harness.zone_final_pair_skill import motor_command
    from harness.zone_pair_executor import carry_role_sign
    from harness import zone_final_pair_contract as previous
    from sim.camera_robot_port import validate_raw_action
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    cal = c.student_calibration(c.dev_pilot_calibration(path, sha, MAPS[0]))
    loaded = cal['params']['motion_loaded']
    assert loaded['deadband']['c0'] == [0., 0., 0.]
    # Whole carry speed range: with c0 = 0 the inverse is sqrt(|v| u1) below u1.
    for speed in np.linspace(.005, .06, 12):
        for sign in (-1., 1.):
            u = motor_command(loaded, np.array([sign*speed, 0., 0.]))
            assert np.all(np.isfinite(u))
            validate_raw_action({'kind': 'mecanum', 'forward': float(u[0]), 'left': float(u[1]),
                                 'turn': float(u[2]), 'duration_s': .15}, allow_reverse=True, allow_mecanum=True)
    probe = _probe()
    events = probe.commands()
    carry = {}
    for rid in c.ROBOTS:
        u = motor_command(loaded, np.array([carry_role_sign(rid)*.06, 0., 0.]))
        carry[rid] = {'kind': 'mecanum', 'forward': float(u[0]), 'left': float(u[1]), 'turn': float(u[2]),
                      'duration_s': .15}
        for k in range(int(4./.1)):           # 28-32 s, inside the HIGH hold (27.2-34 s)
            events.append({'t': round(28.+k*.1, 8), 'robot_id': rid, 'action': dict(carry[rid])})
    events.sort(key=lambda e: e['t'])
    provider = HighPoseSource(c.resolve(MAPS[0])[0], path, sha)
    bundle = previous.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
    backend = probe.Headless(bundle, tmp_path/'raw', seed=911)
    try:
        backend.reset(5.)
        start = backend.now
        backend.set_deadline(start+52.)
        provider.init_prior((0., 0., 0.), (.1, .1, .1), source='synthetic replay prior')
        provider.on_command({'kind': 'initial_servo_command', 't': 0., 'pulses': {1: 2000, **probe.pose.grasp_postures()[1][-1]}})
        data = backend.world.data
        xy = {}
        j = 0
        for i in range(1041):
            t = round(i*.05, 8)
            if t in (27.5, 33.5):
                xy[t] = {r: data.body(r+'__robot').xpos[:2].copy() for r in c.ROBOTS}
            if t == 31.:                      # mid carry leg: loaded, c0 = 0 deadband path active
                provider.loc.predict_to(31.)
                mid = (provider.loc.load.loaded, provider.loc.estimate())
            while j < len(events) and events[j]['t'] <= t+1e-8:
                e = events[j]
                backend.issue(e['robot_id'], e['action'])
                if e['robot_id'] == 'r1' and e['t'] > 0:
                    provider.on_command({**e['action'], 't': e['t']})
                j += 1
            if i == 1040:
                break
            backend.advance_to(start+(i+1)*.05)
        loaded_mid, est_mid = mid
        assert loaded_mid and np.all(np.isfinite([est_mid['x'], est_mid['y'], est_mid['yaw']]))
        provider.loc.predict_to(52.)
        est = provider.loc.estimate()                 # gripper opened at 49 s -> unloaded again
        assert not provider.loc.load.loaded and np.all(np.isfinite([est['x'], est['y'], est['yaw']]))
        assert provider.failure is None
        moved = {r: float(np.linalg.norm(xy[33.5][r]-xy[27.5][r])) for r in c.ROBOTS}
        assert all(v > .05 for v in moved.values()), moved           # eval-side scoring only
    finally:
        backend.close()
        provider.close()


class _Ep:
    def __init__(self):
        self.events, self.controller = [], type('C', (), {'failure': None, 'state': 'align'})()


class _ProbeRuntime:
    """FakeRuntime with live endpoints: the stage-terminal event (or a failure) at t_event."""
    def __init__(self, *a, t_event=7., failure=None, **kw):
        from tests.test_zone_final_pair_v3 import FakeRuntime
        self.inner, self.t_event, self.failure = FakeRuntime(), t_event, failure
        self.eps = {'r1': _Ep(), 'r2': _Ep()}
        self.team = type('T', (), {'sessions': [{'endpoints': self.eps}]})()
        # The opening look_around job has already ended (as in the real runtime).
        self.actors = {r: type('A', (), {'jobs_done': [{'kind': 'look_around', 'outcome': 'LOOKED_POSE_UNCERTAIN'}]})()
                       for r in self.eps}
    def __getattr__(self, name):
        return getattr(self.inner, name)
    def step(self, now):
        if now >= self.t_event and not self.eps['r1'].events:
            for ep in self.eps.values():
                if self.failure:
                    ep.controller.failure = self.failure
                else:
                    ep.events.append({'event': 'high_carry_pose', 't': now})
        return self.inner.step(now)


@pytest.mark.parametrize('failure', [None, 'GRIP_NOT_SEEN'])
def test_stage_probe_stops_at_stage_end_with_its_own_status(tmp_path, monkeypatch, failure):
    from tests.test_zone_final_pair_v3 import FakePhysics
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'], 'p03', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    result = run.student_run_case(bundle, tmp_path/'probe', seed=911, backend_factory=FakePhysics,
        runtime_factory=lambda *a, **k: _ProbeRuntime(*a, failure=failure, **k),
        calibration=path, calibration_sha=sha, probe='raise_high')
    assert result['status'] == ('STAGE_PROBE_FAILED' if failure else 'STAGE_PROBE_REACHED')
    assert result['protocol_complete'] is False and 'checkpoint' not in result
    assert 6. <= result['check_sim_s'] < 7. and result['commands_issued']['r1'] > 0
    assert result['stage_probe']['stage'] == 'raise_high' and result['stage_probe']['case_result'] is False
    assert result['controller_outcome']['r1']['failure'] == failure
    assert {k: result[k] for k in c.DEV_PILOT_LABELS} == c.DEV_PILOT_LABELS
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable(result)
    measured = {**c.bundle(case['map_id'], 'p03'), 'case': case, 'source_sha': 'a'*40}
    with pytest.raises(ValueError):
        run.student_run_case(measured, tmp_path/'probe2', seed=911, backend_factory=FakePhysics,
                             calibration=path, calibration_sha=sha, probe='raise_high')
    assert not (tmp_path/'probe2').exists()


def test_direct_student_run_case_refuses_dev_file_in_measured_bundle(tmp_path, monkeypatch):
    """Re-review #2: a public direct call cannot make an unlabelled DEV-calibrated run."""
    from tests.test_zone_final_pair_v3 import FakePhysics, FakeRuntime
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    measured = {**c.bundle(case['map_id'], 'p03'), 'case': case, 'source_sha': 'a'*40}
    runnable = {**measured, 'runnable': True, 'blocked_on': []}   # even a forged runnable flag
    for bundle in (measured, runnable):
        with pytest.raises(ValueError):
            run.student_run_case(bundle, tmp_path/'direct', seed=911, backend_factory=FakePhysics,
                                 runtime_factory=FakeRuntime, calibration=path, calibration_sha=sha)
        assert not (tmp_path/'direct').exists()


def test_require_promotable_refuses_any_record_carrying_a_dev_sha(tmp_path, monkeypatch):
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    stripped = {'status': 'COLLECTED_UNQUALIFIED', 'calibration_sha256': sha}
    nested = {'status': 'COLLECTED_UNQUALIFIED', 'pair': [{'robots': {'r1': {'provider': {'sha256': sha}}}}]}
    relabelled = {**stripped, 'admission_mode': 'MEASURED_SIM', 'promotable': True}
    for record in (stripped, nested, relabelled, {'cases': [stripped]}):
        with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
            c.require_promotable(record)
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        starts.qualify_run(stripped, {'id': 'confirm-01'}, {}, [])
    clean = {'status': 'COLLECTED_UNQUALIFIED', 'calibration_sha256': 'e'*64}
    assert c.require_promotable(clean) is clean


@pytest.mark.parametrize('probe', [None, 'high_hold'])
def test_cli_execute_dev_pilot_one_case_on_a_sim_slot_is_not_host_error(tmp_path, monkeypatch, probe):
    """main --execute under DEV_PILOT: the source-unchanged check uses the DEV bundle."""
    import subprocess
    from tests.test_zone_final_pair_v3 import FakePhysics, FakeRuntime
    import sim.final_pair_v3 as backend_module
    import scripts.agent_sim_slots as slots
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    primary = tmp_path/'primary'
    (primary/'outputs').mkdir(parents=True)
    real_check_output = subprocess.check_output
    def check_output(cmd, *a, **k):
        if cmd[:2] == ['git', 'rev-parse']:
            return str(primary/'.git')+'\n'
        if cmd[:2] == ['git', 'branch']:
            return 'codex/pair-carry-highpose\n'
        return real_check_output(cmd, *a, **k)
    slot_calls = []
    monkeypatch.setattr(run.subprocess, 'check_output', check_output)
    monkeypatch.setattr(run, 'check_source', lambda sha_: None)
    monkeypatch.setattr(slots, 'require_sim_slot', lambda root, **k: slot_calls.append(k))
    monkeypatch.setattr(slots, 'sim_snapshot', lambda root: {'loadavg': [1., 1., 1.]})
    monkeypatch.setattr(backend_module, 'PhysicsBackend', FakePhysics)
    import sim.final_pair_highpose_clock as clock_module   # v98 main() builds the host clock v2 backend
    monkeypatch.setattr(clock_module, 'PhysicsBackend', FakePhysics)
    real_case, real_student = run.run_case, run.student_run_case
    monkeypatch.setattr(run, 'run_case', lambda b, o, **k: real_case(b, o, runtime_factory=FakeRuntime, **k))
    monkeypatch.setattr(run, 'student_run_case', lambda b, o, **k: real_student(
        b, o, **{'runtime_factory': lambda *a, **kw: _ProbeRuntime(*a, **kw), **k}))
    out = primary/'outputs'/'v96-dev'
    argv = ['--check', 'p03', '--map-id', c.cases('p03')[0]['map_id'], '--case-id', 'after_door',
            '--expected-source-sha', 'a'*40, '--output', str(out), '--execute', '--lock-owner', 'claude',
            '--sim-slot', 'sim-claude-test', '--calibration', str(path), '--calibration-sha256', sha,
            '--admission', 'dev-pilot'] + (['--stage-probe', probe] if probe else [])
    assert run.main(argv) == 0
    top = json.loads((out/'result.json').read_text())
    assert top['source_unchanged'] is True and top['unattempted'] == []
    assert top['status'] == ('STAGE_PROBE_COLLECTED' if probe else 'COLLECTED_UNQUALIFIED')
    assert top['denominator'] == 1 and top['registered_denominator'] == 3 and top['case_selection'] == 'after_door'
    assert top['lock_mode'] == 'sim_slot' and slot_calls == [{'slot': 'sim-claude-test', 'owner': 'claude',
                                                               'branch': 'codex/pair-carry-highpose'}]
    assert top['run_status'] == 'FUNCTIONAL_DEV' and top['promotable'] is False
    assert [r['case']['id'] for r in top['cases']] == ['after_door']
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable(top)
    with pytest.raises(ValueError, match='exactly one'):
        run.main(argv[:5]+['nope']+argv[6:])


def test_staged_geometry_preroll_and_prior_are_static_and_recorded():
    from harness import zone_pair_highpose_staging as st
    from harness import zone_pair_highpose as pose
    from sim.zone_model_conventions import station_offset
    static, _, _ = c.resolve(c.cases('p03')[0]['map_id'])
    stations = st.stations(static, [1.0, .05, 0.])
    off = station_offset(static, 'long_beam', 'end_neg')
    assert stations['r1'] == [1.0+off[0], .05+off[1], off[2]] and abs(stations['r2'][2]) > 3.
    high = [r for r in st.preroll_actions('high_held') if r['phase'] == 'stage_high']
    assert {(r['robot_id'], r['action'].get('servo_id', 6)) for r in high} == {(r, s) for r in ('r1', 'r2') for s in (3, 4, 5, 6)}
    assert all(r['action'].get('pulse', r['action'].get('pan_pulse')) == pose.HIGH[r['action'].get('servo_id', 6)] for r in high)
    open_rows = st.preroll_actions('floor_open')
    assert not any(r['action'].get('servo_id') == 1 and r['action']['pulse'] == st.CLOSED for r in open_rows)
    prior = st.stated_prior(stations['r1'])
    assert prior['is_fix'] is False and prior['std_per_axis'] == [.15, .15, .174533]
    assert prior['mean_xyyaw'] == stations['r1']


@pytest.mark.parametrize('probe', ['raise_high_align', 'align_to_carry', 'high_hold_staged', 'carry_leg_staged'])
def test_staged_probe_preroll_runs_before_controller_clock_and_is_recorded(tmp_path, monkeypatch, probe):
    from tests.test_zone_final_pair_v3 import FakePhysics
    from harness import zone_pair_highpose_staging as st
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'], 'p03', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    backends = []
    def factory(*a, **k):
        backends.append(FakePhysics(*a, **k))
        return backends[-1]
    result = run.student_run_case(bundle, tmp_path/probe, seed=911, backend_factory=factory,
        runtime_factory=lambda *a, **k: _ProbeRuntime(*a, t_event=1e9, **k),
        calibration=path, calibration_sha=sha, probe=probe)
    spec = st.PROBE_SPECS[probe]
    pre = [a for t, rid, a in backends[0].actions if t <= 1.+st.PREROLLS[spec['preroll']]['end_s']]
    assert len(pre) >= len(st.preroll_actions(spec['preroll']))
    rec = json.loads((tmp_path/probe/'stage_probe_staging.json').read_text())
    assert rec['preroll'] == spec['preroll'] and rec['end_sim_s'] == pytest.approx(1.+st.PREROLLS[spec['preroll']]['end_s'])
    assert rec['priors']['r1']['is_fix'] is False and result['staging']['stage'] == probe
    closed = rec['close_issued_at_s']
    assert (closed is None) == (spec['preroll'] == 'none')
    assert result['status'] == 'STAGE_PROBE_NOT_REACHED' and result['stage_probe']['staged'] is True
    assert result['check_sim_s'] == pytest.approx(spec['cap_s'])
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable(result)


def _staged_runtime(tmp_path, monkeypatch, stage):
    from harness import zone_pair_highpose_staging as st
    from harness.zone_final_pair_skill import task
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    static = c.resolve(MAPS[0])[0]
    spawn = st.spawn_poses(static, task(static)['beam_pose'], stage)
    staging = {'stage': stage, 'stations_xyyaw': spawn,
               'priors': {rid: st.stated_prior(pose_) for rid, pose_ in spawn.items()}}
    return st, st.StagedRuntime(static, path, sha, seed=911, stage=stage, staging=staging), staging


def test_floor_entries_are_dropped_and_recorded():
    from harness import zone_pair_highpose_staging as st
    assert set(st.DROPPED) == {'raise_high_staged', 'raise_high_closed'}
    assert not set(st.DROPPED) & set(st.PROBE_SPECS) and not set(st.DROPPED) & set(run.STAGE_PROBES)
    assert all('admission' in why for why in st.DROPPED.values())
    assert set(st.PROBE_SPECS) == {'raise_high_align', 'align_to_carry', 'high_hold_staged', 'carry_leg_staged'}
    assert set(st.PARKED) == {'high_hold_staged', 'carry_leg_staged'} and set(st.PARKED) <= set(st.PROBE_SPECS)


def test_align_to_carry_continues_from_the_align_entry_until_both_robots_are_done():
    from harness import zone_pair_highpose_staging as st
    a, b = st.PROBE_SPECS['raise_high_align'], st.PROBE_SPECS['align_to_carry']
    same = ('preroll', 'spawn', 'opening_look_around', 'entry')
    assert {k: a[k] for k in same} == {k: b[k] for k in same}
    assert (b['cap_s'], b['terminal_event'], b['terminal_state'], b['barrier']) == (900., 'state', 'done', None)
    assert b['cap_s'] == c.CASE_CAP_S
    assert run.STAGE_PROBES['align_to_carry']['staged'] is True
    ev = lambda *states: type('E', (), {'events': [{'event': 'state', 'state': x} for x in states],
                                        'controller': type('C', (), {'failure': None})()})()
    def progress(r1, r2):
        rt = type('R', (), {'team': type('T', (), {'sessions': [{'endpoints': {'r1': r1, 'r2': r2}}]})(), 'actors': {}})()
        return run.stage_progress(rt, 'align_to_carry')
    assert not progress(ev('wait_carry', 'carry', 'lower'), ev('released'))['done']   # other states do not end it
    got = progress(ev('carry', 'done'), ev('released', 'done'))
    assert got['done'] and got['stop'] and got['reached'] == {'r1': True, 'r2': True}


def test_dock_approach_probe_ends_when_both_robots_entered_wait_approach():
    spec = run.STAGE_PROBES['dock_approach']
    assert (spec['terminal_event'], spec['terminal_state'], spec['barrier']) == ('state', 'wait_approach', None)
    assert 200. <= spec['cap_s'] <= c.CASE_CAP_S and not spec.get('staged')      # real dock start, real PF prior
    ev = lambda *states: type('E', (), {'events': [{'event': 'state', 'state': x} for x in states],
                                        'controller': type('C', (), {'failure': None})()})()
    def progress(r1, r2):
        rt = type('R', (), {'team': type('T', (), {'sessions': [{'endpoints': {'r1': r1, 'r2': r2}}]})(), 'actors': {}})()
        return run.stage_progress(rt, 'dock_approach')
    assert not progress(ev('approach', 'wait_approach'), ev('approach'))['done']     # r2 still approaching
    got = progress(ev('approach', 'wait_approach', 'align'), ev('reapproach', 'wait_approach'))
    assert got['done'] and got['stop'] and got['reached'] == {'r1': True, 'r2': True}


def test_align_entry_spawns_at_the_plan_prestation_and_keeps_the_opening_look_around(tmp_path, monkeypatch):
    import math
    from scripts import run_m2_pair as m2
    st, runtime, staging = _staged_runtime(tmp_path, monkeypatch, 'raise_high_align')
    try:
        static = c.resolve(MAPS[0])[0]
        from harness.zone_final_pair_skill import task
        station = st.stations(static, task(static)['beam_pose'])
        for rid, (x, y, yaw) in staging['stations_xyyaw'].items():
            sx, sy, syaw = station[rid]
            back = m2.study.PRESTATION_BACK_M
            assert (x, y, yaw) == pytest.approx((sx-back*math.cos(syaw), sy-back*math.sin(syaw), syaw))
        assert runtime.started is False and staging['skipped_opening_look_around'] is False
    finally:
        runtime.close()
    st, runtime, staging = _staged_runtime(tmp_path/'high', monkeypatch, 'high_hold_staged')
    try:
        assert runtime.started is True and staging['skipped_opening_look_around'] is True
    finally:
        runtime.close()


def test_staged_high_history_sets_loaded_by_the_own_command_rule(tmp_path, monkeypatch):
    from harness import zone_pair_highpose as pose
    st, runtime, staging = _staged_runtime(tmp_path, monkeypatch, 'high_hold_staged')
    try:
        final = {k: v for k, v in pose.HIGH.items()}
        final[1] = st.CLOSED
        rows = st.own_history('high_held', final)
        assert rows[0]['kind'] == 'initial_servo_command' and rows[0]['pulses'][1] == st.OPEN
        assert [r for r in rows if r.get('servo_id') == 1] == [{'kind': 'arm', 'servo_id': 1, 'pulse': st.CLOSED}]
        assert st.own_history('none', final) == [{'kind': 'initial_servo_command', 'pulses': final}]
        runtime.initial_commands(33., {rid: dict(final) for rid in ('r1', 'r2')})
        for rid in ('r1', 'r2'):
            assert staging['own_history']['robots'][rid] == {'rows': len(rows), 'loaded_by_rule': True}
            runtime.providers[rid].report(33.2)          # past the fixed 0.16 s delay: queued commands applied
            provider = runtime.providers[rid].provider
            assert provider.loc.load.loaded is True
            assert provider.servo == {k: v for k, v in final.items()}
    finally:
        runtime.close()
    # The single-row hand-off (the 7623c4dc staging) leaves the localizer unloaded at HIGH.
    from harness.zone_pair_highpose_runtime import Runtime
    path, _ = dev_file(tmp_path/'plain')
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    plain = Runtime(c.resolve(MAPS[0])[0], path, sha, seed=911)
    try:
        plain.initial_commands(33., {rid: dict(final) for rid in ('r1', 'r2')})
        plain.providers['r1'].report(33.2)
        assert plain.providers['r1'].provider.loc.load.loaded is False
    finally:
        plain.close()


def test_align_entry_records_what_the_real_arrival_records():
    from types import SimpleNamespace
    from harness import zone_pair_highpose_staging as st
    logs, states = [], []
    est = {'x': .2, 'y': .05, 'yaw': .01, 'std_xy_m': .006}
    ctl = SimpleNamespace(rid='r1', claims={}, arm=SimpleNamespace(commanded={3: 1, 4: 2}),
                          driver=SimpleNamespace(outcome=None, loc=SimpleNamespace(estimate=lambda: est)),
                          log=lambda *a, **k: logs.append((a, k)), set=lambda state, now, **k: states.append((state, k)))
    execution = SimpleNamespace(own=SimpleNamespace(last_report=None, servo={3: 740, 4: 2320, 5: 1320}))
    st.enter(ctl, execution, 'raise_high_align', {}, 9.)
    assert ctl.driver.outcome == 'arrived' and states == [('wait_approach', {'stage_probe_entry': True})]
    assert ctl.claims['at_prestation']['estimate'] == [.2, .05, .01] and ctl.claims['at_prestation']['std_xy_m'] == .006
    assert ctl.arm.commanded == {3: 740, 4: 2320}
    assert not hasattr(ctl, 'grasp_pose') and not hasattr(ctl, 'pregrasp_done')


def test_staged_ground_truth_inputs_are_labelled_test_setup_only():
    """Reviewer 2026-10-04: the staged prior mean (true spawn pose) and the HIGH entries' grip/lift claims are
    test-setup ground truth, labelled in the code, the controller log and the staging record."""
    import inspect
    from harness import zone_pair_highpose_staging as st
    from scripts import run_pair_highpose as runner
    assert st.TEST_SETUP_GT['test_setup_ground_truth'] is True and 'never E2E' in st.TEST_SETUP_GT['scope']
    prior = st.stated_prior([1., 2., 0.])
    assert prior['test_setup_ground_truth'] is True and prior['mean_is'] == 'true staged spawn pose'
    enter = inspect.getsource(st.enter)
    assert enter.count('**TEST_SETUP_GT') == 4            # gripped, lifted, both stage_probe_entry logs
    assert 'ground_truth_inputs' in inspect.getsource(runner) and '**staging.TEST_SETUP_GT' in inspect.getsource(runner)


# ---- measured unloaded calibration C (zone-final-environment-gaincal-v101, coordinator decision 2026-10-05)
def test_measured_unloaded_calibration_c_is_admitted_by_its_exact_sha_and_fills_every_missing_field():
    dev = c.registry()['dev_pilot']
    source = dev['admitted_source'][C_SHA]
    assert (Path(__file__).resolve().parents[1]/source['path']) == C_PATH and c.base.sha(C_PATH) == C_SHA
    assert source['heldout_status'].startswith('VALIDATED_DEV') and 'not MEASURED_SIM' in source['heldout_status']
    cal = c.admitted_calibration(str(C_PATH), C_SHA, MAPS[0])
    assert cal['missing'] == [] and 'dev_pilot_fill' not in cal and cal['status'] == c.DEV_PILOT
    motion = cal['params']['motion']
    assert all(motion.get(k) is not None for k in UNLOADED)
    assert dev['unloaded_motion_fill']['values'] != {k: motion[k] for k in dev['unloaded_motion_fill']['values']}   # not the DEV code defaults
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable({'calibration_sha256': C_SHA})


def test_measured_unloaded_calibration_c_differs_from_its_parent_only_in_the_registered_fields():
    cal, base = json.loads(C_PATH.read_text()), json.loads(BASE_COPY.read_text())
    assert c.base.sha(BASE_COPY) == REAL_SHA and cal['parent_calibration']['sha256'] == REAL_SHA
    changed = {k for k in set(cal) | set(base) if cal.get(k) != base.get(k)}
    assert changed == {'params', 'missing', 'field_provenance', 'source_sha', 'dev_manifest_sha256',
                       'unloaded_gain_calibration', 'parent_calibration'}
    assert {k for k in cal['params'] if cal['params'][k] != base['params'][k]} == {'motion'}
    assert cal['params']['motion_loaded'] == base['params']['motion_loaded']            # loaded model untouched
    motion = cal['params']['motion']
    assert set(UNLOADED) <= set(motion) and all(motion[k] is not None for k in UNLOADED)
    prov = cal['field_provenance']
    assert all(prov['params.motion.' + k] in ('measured_unloaded_gain_calibration_v101', 'registered_r4_r5_measured_noise')
               for k in UNLOADED)
    assert prov['params.motion.noise_rel'] == prov['params.motion.noise_abs'] == 'registered_r4_r5_measured_noise'


def test_measured_unloaded_calibration_c_pins_its_fit_and_heldout_records():
    cal = json.loads(C_PATH.read_text())['unloaded_gain_calibration']
    assert c.base.sha(V101/'fit'/'fit.json') == cal['fit_sha256'] and c.base.sha(V101/'heldout'/'heldout.json') == cal['heldout_sha256']
    held = json.loads((V101/'heldout'/'heldout.json').read_text())
    assert held['status'] == cal['heldout_status'] == 'VALIDATED_DEV' and held['fit_sha256'] == cal['fit_sha256']
    assert cal['bundle_id'] == 'zone-final-environment-gaincal-v101' and cal['variant'] == 'C'
    assert 'NOT MEASURED_SIM' in cal['qualification']


def test_extra_dev_seeds_only_for_dev_pilot_stage_probes():
    """2026-10-05 coordinator: seeds 912/913 for DEV stage probes only (more failure types), labelled, never evidence."""
    from harness import zone_pair_highpose_starts as starts
    conf = {r['seed'] for r in starts.registration()['confirmation_starts']}
    assert not set(run.STAGE_PROBE_DEV_EXTRA_SEEDS) & (conf | {starts.DEV_SEED})
    base = ['--check', 'carry', '--map-id', 'zone_wide_door_geometry_v3', '--expected-source-sha', 'a'*40,
            '--output', '/nonexistent', '--case-id', 'zone_wide_door_geometry_v3']
    probe = run.parser().parse_args(base + ['--seed', '912', '--admission', 'dev-pilot', '--stage-probe', 'align_to_carry'])
    assert run.extra_dev_seed(probe)
    for argv in (base + ['--seed', '912', '--admission', 'dev-pilot'],                      # full case: 911 only
                 base + ['--seed', '912', '--stage-probe', 'align_to_carry'],               # measured-sim admission
                 base + ['--seed', '914', '--admission', 'dev-pilot', '--stage-probe', 'align_to_carry'],
                 base + ['--seed', str(min(conf)), '--admission', 'dev-pilot', '--stage-probe', 'align_to_carry']):
        args = run.parser().parse_args(argv)
        assert not run.extra_dev_seed(args)
        with pytest.raises(ValueError, match='SEED_911'):
            run.plan(args)


@pytest.mark.parametrize('seed', [912, 913, 9301001, 914])
def test_direct_student_run_case_refuses_non_dev_seed_full_case_before_backend(tmp_path, monkeypatch, seed):
    """review delta4 P1-1: the common entry point applies the seed rule too (no output folder, no backend)."""
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('carry')[0]
    bundle = {**c.bundle(case['map_id'], 'carry', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    made = []
    out = tmp_path/f'direct-{seed}'
    with pytest.raises(ValueError, match='SEED_911'):
        run.student_run_case(bundle, out, seed=seed, backend_factory=lambda *a, **k: made.append(1),
                             calibration=path, calibration_sha=sha, probe=None)
    assert not made and not out.exists()
    if seed in run.STAGE_PROBE_DEV_EXTRA_SEEDS:     # an extra seed with a stage probe outside DEV_PILOT: refused too
        measured = {**bundle, 'admission_mode': c.MEASURED_SIM}
        with pytest.raises(ValueError, match='SEED_911'):
            run.student_run_case(measured, out, seed=seed, backend_factory=lambda *a, **k: made.append(1),
                                 calibration=path, calibration_sha=sha, probe='align_to_carry')
        assert not made and not out.exists()


def test_direct_student_run_case_extra_seed_stage_probe_is_labelled(tmp_path, monkeypatch):
    from tests.test_zone_final_pair_v3 import FakePhysics
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    case = c.cases('p03')[0]
    bundle = {**c.bundle(case['map_id'], 'p03', c.DEV_PILOT), 'case': case, 'source_sha': 'a'*40}
    result = run.student_run_case(bundle, tmp_path/'s912', seed=912, backend_factory=FakePhysics,
        runtime_factory=lambda *a, **k: _ProbeRuntime(*a, t_event=1e9, **k),
        calibration=path, calibration_sha=sha, probe='align_to_carry')
    assert result['seed'] == 912 and result['extra_dev_seed'] == {'seeds': [912, 913], 'evidence': False, 'pooled': False}
    assert result['status'] == 'STAGE_PROBE_NOT_REACHED'
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable(result)
    dev = run.student_run_case(bundle, tmp_path/'s911', seed=911, backend_factory=FakePhysics,
        runtime_factory=lambda *a, **k: _ProbeRuntime(*a, t_event=1e9, **k),
        calibration=path, calibration_sha=sha, probe='align_to_carry')
    assert dev['seed'] == 911 and dev['extra_dev_seed'] is None


# ---- measured loaded calibration v102 (zone-final-pair-loaded-gaincal-v102, coordinator task 2026-10-05)
def test_measured_loaded_calibration_v102_is_admitted_by_its_exact_sha():
    dev = c.registry()['dev_pilot']
    source = dev['admitted_source'][V102_SHA]
    assert (Path(__file__).resolve().parents[1]/source['path']) == V102_PATH and c.base.sha(V102_PATH) == V102_SHA
    assert source['heldout_status'].startswith('VALIDATED_DEV') and 'not MEASURED_SIM' in source['heldout_status']
    assert source['parent']['sha256'] == C_SHA
    cal = c.admitted_calibration(str(V102_PATH), V102_SHA, MAPS[0])
    assert cal['missing'] == [] and cal['status'] == c.DEV_PILOT and cal['dev_rule'] == c.DEV_PILOT_RULE
    db = cal['params']['motion_loaded']['deadband']
    assert db['c0'] == [0., 0., 0.] and len(db['u0']) == 3 and db['u0'][2] == 0. and db['u0'][0] > 0 and db['u0'][1] > 0
    assert db['u1'][0] == db['u1'][1] == 1e-6                     # ramp numerically off on the two affine axes
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable({'calibration_sha256': V102_SHA})


def test_measured_loaded_calibration_v102_differs_from_its_parent_only_in_the_registered_fields():
    cal, base = json.loads(V102_PATH.read_text()), json.loads(C_PATH.read_text())
    assert c.base.sha(C_PATH) == C_SHA and cal['parent_calibration']['sha256'] == C_SHA
    changed = {k for k in set(cal) | set(base) if cal.get(k) != base.get(k)}
    assert changed == {'params', 'field_provenance', 'source_sha', 'dev_manifest_sha256',
                       'loaded_gain_calibration', 'parent_calibration'}
    assert {k for k in cal['params'] if cal['params'][k] != base['params'][k]} == {'motion_loaded'}
    new, old = cal['params']['motion_loaded'], base['params']['motion_loaded']
    assert {k for k in set(new) | set(old) if new.get(k) != old.get(k)} == {'gain', 'tau_s', 'tau_axis_s', 'tau_stop_s', 'deadband'}
    assert new['gain'][2] == old['gain'][2] and new['tau_axis_s'][2] == old['tau_axis_s'][2]       # turn axis untouched
    assert new['deadband']['u1'][2] == old['deadband']['u1'][2]
    assert all(new['gain'][i][j] == old['gain'][i][j] for i in range(3) for j in range(3) if i != j or i == 2)
    assert cal['params']['motion'] == base['params']['motion'] and cal['camera_models'] == base['camera_models']
    assert cal['loaded_gain_calibration']['heldout_status'] == 'VALIDATED_DEV' and cal['confirmatory'] is False


# ---- loaded rest_noise by the unchanged v101 rule (zone-final-pair-loaded-restcal-v104, #363 (가), 2026-10-05)
def test_loaded_rest_v104_calibration_is_admitted_by_its_exact_sha():
    source = c.registry()['dev_pilot']['admitted_source'][V104_SHA]
    assert (Path(__file__).resolve().parents[1]/source['path']) == V104_PATH and c.base.sha(V104_PATH) == V104_SHA
    assert source['parent']['sha256'] == V102_SHA and 'not MEASURED_SIM' in source['heldout_status']
    cal = c.admitted_calibration(str(V104_PATH), V104_SHA, MAPS[0])
    assert cal['missing'] == [] and cal['status'] == c.DEV_PILOT and cal['params']['motion_loaded']['rest_noise'] is False
    with pytest.raises(ValueError, match=c.NOT_PROMOTABLE):
        c.require_promotable({'calibration_sha256': V104_SHA})


def test_loaded_rest_v104_differs_from_v102_only_in_rest_noise_and_its_record():
    cal, base = json.loads(V104_PATH.read_text()), json.loads(V102_PATH.read_text())
    changed = {k for k in set(cal) | set(base) if cal.get(k) != base.get(k)}
    assert changed == {'params', 'field_provenance', 'parent_calibration', 'loaded_rest_calibration', 'source_sha',
                       'dev_manifest_sha256'}
    assert cal['source_sha'] == '835c8fcdb7c05cd69cf18f6a9c9bfc942b1ae63e'           # the v104 collection source
    assert {k for k in cal['params'] if cal['params'][k] != base['params'][k]} == {'motion_loaded'}
    new, old = cal['params']['motion_loaded'], base['params']['motion_loaded']
    assert {k for k in set(new) | set(old) if new.get(k) != old.get(k)} == {'rest_noise'}
    assert (old['rest_noise'], new['rest_noise']) == (True, False)
    assert new['noise_abs'] == old['noise_abs'] and new['noise_rel'] == old['noise_rel']   # unmeasured, unchanged
    prov = {k for k in set(cal['field_provenance']) | set(base['field_provenance'])
            if cal['field_provenance'].get(k) != base['field_provenance'].get(k)}
    assert prov == {'params.motion_loaded.rest_noise'}
    rec = cal['loaded_rest_calibration']
    assert rec['rest_noise'] is False and all(rec['result'][r]['rms_m'] < 1e-3 for r in ('r1', 'r2'))
    assert cal['parent_calibration'] == {'path': str(V102_PATH.relative_to(Path(__file__).resolve().parents[1])),
                                         'sha256': V102_SHA}
