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
    assert dev['admitted_calibration_sha256'] == [REAL_SHA]
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
    assert stored['run_status'] == 'FUNCTIONAL_DEV' and stored['tensorboard_cohort'] == 'v96-dev-pilot-functional'
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
        assert runtime.job_sim_limit_s == c.CASE_CAP_S == 300.
        assert c.execution_timing('p03')['executor_job_sim_limit_s'] == 300.
        actor = runtime.actors['r1']
        assert actor.job_sim_limit_s == 300.
        actor.now = 5.
        actor._start('test', 'pair', {})
        largest = max(r['lower_bound_s'] for m in MAPS for r in
                      __import__('harness.zone_pair_highpose_timing', fromlist=['bounds']).bounds(c.resolve(m)[0], 'carry'))
        assert largest > 120.
        assert not actor.expire_if_due(5.+largest) and not actor.expire_if_due(5.+300.)
        assert actor.expire_if_due(5.+300.1)
        assert runtime.record()['executor_job_sim_limit_s'] == 300.
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
