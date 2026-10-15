"""Offline fixtures only: never construct a MuJoCo world or render a scene."""
import base64
import copy
import hashlib
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from scripts import record_map_amcl as record
from scripts import compare_map_amcl_recording as compare
from scripts import replay_map_amcl as replay
from harness.e2e_result_writer import write
from scripts.extract_e2e_pose_features import sha256

SERVO = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def jpeg_bytes():
    # Synthetic bitmap fixture, not simulation rendering or reconstructed data.
    out = io.BytesIO()
    Image.fromarray(np.full((480, 640, 3), 110, np.uint8)).save(out, format='JPEG')
    return out.getvalue()


def tiny_spec():
    return dict(record.load_spec(), seeds=[65101], expected_intervals=2,
                sim_cap_s=.4, frames_per_robot=5)


def fixture_run(root, *, status='RECORDED'):
    spec = tiny_spec()
    raw = root/record.run_name(65101)/'raw'
    raw.mkdir(parents=True)
    image = jpeg_bytes()
    image_sha = hashlib.sha256(image).hexdigest()
    for rid in spec['robots']:
        folder = raw/f'robots/{rid}'
        (folder/'rgb').mkdir(parents=True)
        frames, own, truth = [], [], []
        for i in range(5):
            rel = f'robots/{rid}/rgb/{i:05d}.jpg'
            (raw/rel).write_bytes(image)
            frames.append(dict(frame_id=i, sim_time=1.3+i*.1, sha256=image_sha,
                path=rel, commanded_servo=SERVO))
            own.append(dict(frame_id=i, t=i*.1, sha256=image_sha,
                stall_odometry=dict(command_substeps=int(i>0),
                    command_delta=[.01, 0., 0.], fused_delta=[.01, 0., 0.])))
            truth.append(dict(t=1.3+i*.1, robot_xyz_m=[.01*i, 0., 0.], robot_yaw_rad=0.))
        for name, rows in [('frames', frames), ('ownmap', own), ('commands', [dict(t=1.3, kind='hold')])]:
            (folder/f'{name}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        target = raw/f'eval_only/{rid}'
        target.mkdir(parents=True)
        (target/'trajectory.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in truth))
    write(raw/'inputs/static_map.json', dict(bounds_m=[-1., 2., -1., 2.],
        obstacles=[dict(kind='wall', center_m=[.5, -.9], half_extents_m=[1.5, .05])], regions={}))
    audit = dict(status='MEASURED_CONTROLLER_BOUNDARY', top_camera_inputs=0, truth_reads=0,
                 held_world_reads=0, rejected_inputs=0, own_rgb_inputs=10, controller_calls=10)
    write(raw/'input-audit.json', audit)
    write(raw/'result.json', dict(status=status, source_sha='a'*40, seed=65101, input_audit=audit,
        finalization_complete=True, finalization_errors=[], host='gcp1', machine_type=spec['machine_type'],
        project=spec['project'], spec_sha256='spec', frames_per_robot=5, origin_s=1.3,
        top_camera_input=False, candidate_in_control=False))
    write(raw/'bundle.json', {})
    write(raw/'scene.json', {})
    (raw/'scene.xml').write_text('<synthetic-fixture/>')
    seal(raw)
    return spec, raw


def seal(raw):
    write(raw/'artifacts.sha256.json', {str(p.relative_to(raw)): sha256(p)
        for p in raw.rglob('*') if p.is_file() and p.name != 'artifacts.sha256.json'})


def test_spec_is_finite_off_and_reuses_current_configuration():
    spec = record.load_spec()
    assert len(spec['seeds'])*2 == spec['expected_intervals'] == 80
    assert len(set(spec['seeds'])) == 40
    assert not spec['execution_enabled'] and not spec['automatic_promotion']
    b = record.bundle(spec, 65101, 'a'*40)
    assert b['map_id'] == 'zone_wide_door_e2e_b80_v1'
    assert b['s3_camera_binding'] == 'v3_persistent_v1'
    assert b['options']['drive_profile'] == 'masterpi_drive_friction_v7'
    assert not b.get('sensors') and not b.get('speed4')


def test_default_off_and_mac_execution_rejected_before_physics(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(record, 'record', lambda *args: pytest.fail('physics entry reached'))
    args = ['--seed', '65102', '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')]
    assert record.main(args) == 0
    assert 'EXECUTION_OFF' in capsys.readouterr().out
    assert not (tmp_path/'out').exists()
    monkeypatch.setattr(record.platform, 'system', lambda: 'Darwin')
    with pytest.raises(ValueError, match='NO_MAC'):
        record.main(args+['--execute', '--approval', str(tmp_path/'absent')])


def test_linux_requires_real_source_bound_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(record.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(record.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setenv('UGRP_EXECUTION_HOST', 'gcp1')
    monkeypatch.setenv('MUJOCO_GL', 'osmesa')
    monkeypatch.setattr(record.subprocess, 'check_output',
                        lambda args, **kw: 'a'*40 if 'rev-parse' in args else '')
    q = dict(project='ugrp-act-train-1014', host='gcp1', source_sha='a'*40,
             coordinator_approval=dict(approved=False, source_sha=None))
    write(tmp_path/'queue.json', q)
    with pytest.raises(ValueError, match='COORDINATOR_APPROVAL'):
        record.admission(record.load_spec(), 65102, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65102))
    q.update(raw_root=str(tmp_path), limits=dict(max_parallel_jobs=3), execution_enabled=True, physical_execution_authorized=True, rendering_authorized=True,
        recording_spec_sha256=sha256(record.SPEC), machine_type=record.load_spec()['machine_type'],
        coordinator_approval=dict(approved=True, source_sha='a'*40, credit_stop_verified=True,
            seeds_unused_verified=True, storage_budget_verified=True, machine_verified=True))
    write(tmp_path/'queue.json', q)
    monkeypatch.setattr(record.shutil, 'disk_usage', lambda p: SimpleNamespace(free=10**12))
    record.admission(record.load_spec(), 65102, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65102))
    assert not (tmp_path/'out').exists()  # Admission itself never starts a run.
    q['amcl4'] = dict(offline_speed_and_accuracy_verified=False,
                     remaining_recordings_authorized=False)
    write(tmp_path/'queue.json', q)
    with pytest.raises(ValueError, match='AMCL4_OFFLINE'):
        record.admission(record.load_spec(), 65102, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65102))
    q['amcl4']['offline_speed_and_accuracy_verified'] = True
    write(tmp_path/'queue.json', q)
    record.admission(record.load_spec(), 65102, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65102))
    first_raw = tmp_path/record.run_name(65102)/'raw'
    write(first_raw/'result.json', dict(source_sha='a'*40, status='RECORDED',
        first30=dict(wall_per_sim=4.), finalization_complete=True, finalization_errors=[], frames_per_robot=601))
    write(first_raw/'artifacts.sha256.json', {})
    with pytest.raises(ValueError, match='AMCL4_FIRST_RECORDING_ACCURACY'):
        record.admission(record.load_spec(), 65103, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65103))
    q['amcl4'].update(remaining_recordings_authorized=True,
        first_recording_accuracy_review=dict(passed=True, seed=65102, source_sha='a'*40,
            result_sha256=sha256(first_raw/'result.json'), artifacts_sha256=sha256(first_raw/'artifacts.sha256.json')))
    write(tmp_path/'queue.json', q)
    record.admission(record.load_spec(), 65103, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65103))
    q['amcl4']['first_recording_accuracy_review']['result_sha256'] = 'stale'
    write(tmp_path/'queue.json', q)
    with pytest.raises(ValueError, match='AMCL4_FIRST_RECORDING_ACCURACY'):
        record.admission(record.load_spec(), 65103, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65103))
    q['source_sha'] = 'b'*40
    write(tmp_path/'queue.json', q)
    with pytest.raises(ValueError, match='COORDINATOR_APPROVAL'):
        record.admission(record.load_spec(), 65102, 'a'*40, tmp_path/'queue.json', tmp_path/record.run_name(65102))


def test_real_actor_dependencies_load_without_world_or_renderer():
    from harness.active_camera import SEARCH
    from harness.e2e_record_scalars import normalize
    from scripts.run_e2e_ownmap_live import ownmap_record
    robots = record.make_robots(record.load_spec(), 65101)
    audit = record.InputAudit()
    assert set(robots) == {'r1', 'r2'}
    for robot in robots.values():
        assert robot.goal.e2e_vo.range_stall is None
        assert robot.goal.e2e_vo.fallback
        for sid, pwm in SEARCH.items():
            robot.commanded(dict(kind='look', pan_pulse=pwm) if sid == 6 else
                            dict(kind='arm', servo_id=sid, pulse=pwm), 0.)
        data = jpeg_bytes()
        for i in range(5):
            obs = dict(frame_id=i, sim_time=i*.1, image=base64.b64encode(data).decode(),
                       sha256=hashlib.sha256(data).hexdigest())
            trace = audit.receive(robot, obs, np.full((480, 640, 3), 110, np.uint8), i*.1)
            row = normalize(ownmap_record(robot, obs, trace, i*.1))
            assert 'fused_delta' in row['stall_odometry']
            json.dumps(row, allow_nan=False)
            if i % 2 == 0: robot.commanded(robot.nav_command, i*.1)
    assert audit.snapshot()['controller_calls'] == 10


def test_instance_stage_timers_preserve_native_port_output_and_render_count(tmp_path):
    from tests.test_camera_robot_port import _WorldSpy
    from sim.camera_robot_port import CameraRobotPort
    world = _WorldSpy()
    rendered = []
    world.render_rgb = lambda **kw: rendered.append(kw)
    def jpeg(**kw):
        world.render_rgb(**kw)
        return world.jpeg
    world.render_jpeg = jpeg
    world._physics_step_for = lambda robot: None
    backend = SimpleNamespace(world=world, ports={'r1': CameraRobotPort(world, 'r1')},
        advance_to=lambda t: world._physics_step_for(None), _append=lambda *a: None,
        flush=lambda: None, eval_sample=lambda: None, issue=lambda *a: None)
    metrics = record.Metrics()
    metrics.install(backend)
    obs = backend.ports['r1'].capture()
    backend.advance_to(.1)
    assert len(rendered) == 1 and base64.b64decode(obs['image']) == world.jpeg
    for key in ('render_rgb_and_sync_r1', 'jpeg_encode_r1', 'image_hash', 'camera_capture_r1',
                'physics_step', 'physics_advance'):
        assert metrics.timers[key]['calls'] == 1


@pytest.mark.parametrize('speed_failure', [False, True])
def test_native_writer_retains_every_tick_and_only_own_fields(tmp_path, monkeypatch, speed_failure):
    from scripts import run_e2e_ownmap_live
    image = jpeg_bytes()
    spec = tiny_spec()
    metrics, audit = record.Metrics(), record.InputAudit()
    if speed_failure:
        spec.update(sim_cap_s=60., frames_per_robot=601)
    issued, observed, evaluations = [], [], []
    class Backend:
        now = 1.3
        frame = 0
        def __init__(self):
            self.out = tmp_path
            self.recording_metrics = metrics
            self.commands = {rid: dict(SERVO) for rid in spec['robots']}
            self.ports = {rid: SimpleNamespace(capture=lambda rid=rid: dict(frame_id=self.frame-1,
                sim_time=self.now, sha256=hashlib.sha256(image).hexdigest(),
                image=base64.b64encode(image).decode(), forbidden_top='POISON')) for rid in spec['robots']}
        def set_deadline(self, value): self.deadline = value
        def issue(self, rid, action): issued.append((self.now, rid, action))
        def advance_to(self, value): self.now = value
        def eval_sample(self): evaluations.append(self.now)
        def flush(self): pass
        def _append(self, name, value):
            p = self.out/name
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('a') as f: f.write(json.dumps(value)+'\n')
    class Robot:
        robot_id = 'fixture'
        nav_command = dict(kind='hold')
        translation_commands = 0
        def commanded(self, action, now): pass
        def receive(self, obs, rgb):
            assert set(obs) == {'frame_id', 'sim_time', 'sha256', 'image'}
            observed.append(obs['sim_time'])
            return {}
    monkeypatch.setattr(run_e2e_ownmap_live, 'ownmap_record', lambda robot, obs, trace, now:
                        dict(t=now, frame_id=obs['frame_id'], sha256=obs['sha256']))
    monkeypatch.setattr(record.shutil, 'disk_usage', lambda p: SimpleNamespace(free=10**12))
    b = Backend()
    if speed_failure:
        with pytest.raises(TimeoutError, match='SPEED_GATE_FAILED'):
            record.record_loop(b, {r: Robot() for r in spec['robots']}, spec, tmp_path,
                               clock=lambda: 7*(b.now-1.3), metrics=metrics, audit=audit)
        assert len(evaluations) == 301 and len(list(tmp_path.glob('robots/*/rgb/*.jpg'))) == 602
        assert json.loads((tmp_path/'first30.json').read_text())['passed'] is False
        assert audit.snapshot()['controller_calls'] == 602
        assert audit.snapshot()['truth_reads'] == audit.snapshot()['top_camera_inputs'] == 0
        return
    result = record.record_loop(b, {r: Robot() for r in spec['robots']}, spec, tmp_path,
                                clock=lambda: 0., metrics=metrics, audit=audit)
    assert result['frames_per_robot'] == 5 and len(evaluations) == 5
    assert observed == pytest.approx([t for t in [0., .1, .2, .3, .4] for _ in range(2)])
    assert len(list(tmp_path.glob('robots/*/rgb/*.jpg'))) == 10
    # Native writer stores even byte-identical stationary frames.
    assert all(p.read_bytes() == image for p in tmp_path.glob('robots/*/rgb/*.jpg'))
    assert [t for t, r, a in issued if a['kind'] == 'hold'] == pytest.approx([1.3, 1.3, 1.5, 1.5])
    assert metrics.timers['jpeg_save']['calls'] == metrics.timers['jpeg_decode']['calls'] == 10
    assert audit.snapshot()['controller_calls'] == audit.snapshot()['own_rgb_inputs'] == 10


def test_saved_jpeg_to_five_candidates_and_evaluation_last(tmp_path, monkeypatch):
    spec, raw = fixture_run(tmp_path/'runs')
    cohort = compare.cohort_for(tmp_path/'runs', spec, 'a'*40, 'spec')
    assert all(i['unavailable_reason'] is None for i in cohort['intervals'])
    write(tmp_path/'cohort.json', cohort)
    count = 0
    original_replay, original_read = replay.replay, replay.read
    def estimate(*a, **kw):
        nonlocal count
        count += 1
        return original_replay(*a, **kw)
    def read(path, *a):
        if 'eval_only' in str(path): assert count % 5 == 0 and count > 0
        return original_read(path, *a)
    monkeypatch.setattr(replay, 'replay', estimate)
    monkeypatch.setattr(replay, 'read', read)
    summary = replay.main(['--raw-root', str(tmp_path/'runs'), '--cohort', str(tmp_path/'cohort.json'),
        '--feature-root', str(tmp_path/'features'), '--extract-saved-rgb', '--map-amcl', 'amcl_v1',
        '--output', str(tmp_path/'comparison')])
    assert summary['comparison_complete'] and count == 10
    assert len(summary['paired_aggregates']) == 5
    assert all(v['evaluated_N'] == 2 for v in summary['paired_aggregates'].values())
    assert summary['paired_aggregates']['off+fused_delta']['passed_pose_n'] == 2
    traces = [json.loads(p.read_text().splitlines()[0]) for p in (tmp_path/'comparison').glob('*.jsonl')]
    assert len({t['sha256'] for t in traces}) == 1


@pytest.mark.parametrize('damage', ['missing_jpeg', 'clock', 'frame_count', 'host', 'failed', 'bytes', 'audit_missing', 'audit_nonzero'])
def test_failed_or_incomplete_recording_keeps_all_denominators(tmp_path, damage):
    spec, raw = fixture_run(tmp_path/'runs')
    if damage == 'missing_jpeg': (raw/'robots/r1/rgb/00002.jpg').unlink()
    elif damage == 'bytes': (raw/'robots/r1/rgb/00002.jpg').write_bytes(b'corrupt')
    elif damage in ('clock', 'frame_count'):
        p = raw/'robots/r1/frames.jsonl'
        rows = [json.loads(line) for line in p.read_text().splitlines()]
        if damage == 'clock': rows[2]['sim_time'] += .02
        else: rows.pop()
        p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        seal(raw)
    else:
        p = raw/'result.json'
        r = json.loads(p.read_text())
        if damage == 'audit_missing': r.pop('input_audit')
        elif damage == 'audit_nonzero': r['input_audit']['truth_reads'] = 1
        else: r.update({'host': 'azure3'} if damage == 'host' else {'status': 'HOST_ERROR'})
        write(p, r)
        seal(raw)
    cohort = compare.cohort_for(tmp_path/'runs', spec, 'a'*40, 'spec')
    assert len(cohort['intervals']) == cohort['expected_N'] == 2
    assert all(i['unavailable_reason'] for i in cohort['intervals'])


def test_stationary_segment_path_ratio_does_not_break_summary():
    row = dict(status='complete', metrics=dict(passed_pose=True, passed_pr480=False,
        xy_median_m=0., yaw_median_deg=0., path_ratio=None), jumps=dict(acceptable_n=4, N=4))
    assert replay.aggregate([row], 2)['median']['path_ratio'] is None


def test_compressed_original_text_is_verified_without_discarding_interval(tmp_path):
    spec, raw = fixture_run(tmp_path/'runs')
    for p in list(raw.rglob('*.json'))+list(raw.rglob('*.jsonl')):
        subprocess.run(['zstd', '-q', '-o', str(p)+'.zst', str(p)], check=True)
        p.unlink()  # Only this test's disposable fixture after zstd succeeds.
    cohort = compare.cohort_for(tmp_path/'runs', spec, 'a'*40, 'spec')
    assert all(i['unavailable_reason'] is None for i in cohort['intervals'])
    from scripts.extract_e2e_pose_features import extract
    assert extract(raw, raw/'inputs/static_map.json', tmp_path/'features')['frames'] == {'r1': 5, 'r2': 5}


def test_absent_runs_and_candidate_failure_preserve_paired_N(tmp_path, monkeypatch):
    spec, raw = fixture_run(tmp_path/'runs')
    spec['seeds'].append(65102)
    cohort = compare.cohort_for(tmp_path/'runs', spec, 'a'*40, 'spec')
    assert cohort['expected_N'] == 4
    assert all(i['unavailable_reason'] for i in cohort['intervals'][2:])
    write(tmp_path/'cohort.json', cohort)
    original = replay.replay
    def fail_one(rows, option, *args, **kw):
        if option == 'amcl_landmarks_v1': raise ValueError('synthetic candidate failure')
        return original(rows, option, *args, **kw)
    monkeypatch.setattr(replay, 'replay', fail_one)
    summary = replay.main(['--raw-root', str(tmp_path/'runs'), '--cohort', str(tmp_path/'cohort.json'),
        '--feature-root', str(tmp_path/'features'), '--extract-saved-rgb', '--map-amcl', 'amcl_v1',
        '--output', str(tmp_path/'replay')])
    assert not summary['comparison_complete'] and len(summary['rows']) == 20
    assert summary['aggregates']['off+fused_delta']['evaluated_N'] == 2
    assert all(r['evaluated_N'] == 0 and r['expected_N'] == 4 for r in summary['paired_aggregates'].values())


def test_workflow_catalog_registers_both_paths():
    from sim.workflow_manager import catalog
    catalog_data, _ = catalog(record.ROOT)
    entries = {w['id']: w for w in catalog_data['workflows']}
    assert entries['map-amcl-record']['runner'] == 'scripts.record_map_amcl'
    assert entries['map-amcl-compare-recording']['side_effect'] == 'offline_analysis'


def test_corrupt_compressed_result_is_a_recorded_failure(tmp_path):
    spec, raw = fixture_run(tmp_path/'runs')
    (raw/'result.json').unlink()
    (raw/'result.json.zst').write_bytes(b'not zstd')
    cohort = compare.cohort_for(tmp_path/'runs', spec, 'a'*40, 'spec')
    assert cohort['expected_N'] == 2
    assert all('CORRUPT_COMPRESSED_SOURCE' in i['unavailable_reason'] for i in cohort['intervals'])


@pytest.mark.parametrize('values,warning,blocked', [
    ([3.5], False, False), ([3.51], True, False), ([6.], True, False),
    ([6.01], True, True), ([2., 4., 15.], True, False),
    ([None, 2.], False, True), ([], False, True), ([float('nan')], False, True)])
def test_speed_policy_uses_complete_wave_median(values, warning, blocked):
    result = record.speed_summary([None if v is None else dict(wall_per_sim=v) for v in values])
    assert result['warning'] is warning and result['blocked'] is blocked


def test_queue_slot_limit_and_release_on_error(tmp_path):
    from harness.map_recording_audit import Metrics
    metrics = Metrics()
    with record.recording_slot(tmp_path, 2, metrics) as first:
        with pytest.raises(RuntimeError):
            with record.recording_slot(tmp_path, 2, metrics) as second:
                assert (first, second) == (0, 1)
                with pytest.raises(BlockingIOError, match='LIMIT_REACHED'):
                    with record.recording_slot(tmp_path, 2, metrics): pytest.fail('over limit')
                raise RuntimeError('interrupted run')
        with record.recording_slot(tmp_path, 2, metrics) as freed:
            assert freed == 1
    assert metrics.timers['flock_acquire']['calls'] == 4


def test_timers_separate_nested_cost_and_keep_exceptions():
    from harness.map_recording_audit import Metrics
    clock = iter([0., 1., 3., 5.])
    metrics = Metrics(clock=lambda: next(clock))
    with pytest.raises(ValueError):
        with metrics.measure('capture'):
            with metrics.measure('render'):
                raise ValueError('failed')
    assert metrics.timers['capture'] == dict(calls=1, inclusive_s=5., exclusive_s=3.)
    assert metrics.timers['render'] == dict(calls=1, inclusive_s=2., exclusive_s=2.)


def test_audit_measures_calls_and_denies_truth_top_and_held_reads():
    from harness.map_recording_audit import InputAudit
    audit = InputAudit()
    obs = dict(frame_id=1, sim_time=1., sha256='a'*64, image='jpeg',
               camera='robot_cam', robot_id='r1', actuator_state='NEVER_FORWARDED')
    saved = []
    actor = SimpleNamespace(robot_id='r1', receive=lambda own, rgb: saved.append(copy.deepcopy(own)))
    audit.receive(actor, obs, None, 0.)
    assert set(saved[0]) == audit.allowed and saved[0]['sim_time'] == 0.
    assert audit.snapshot()['controller_calls'] == audit.snapshot()['own_rgb_inputs'] == 1
    assert audit.snapshot()['truth_reads'] == audit.snapshot()['held_world_reads'] == 0
    with pytest.raises(ValueError, match='FORBIDDEN'):
        saved[0].get('truth')
    assert audit.snapshot()['truth_reads'] == 1
    audit.receive(actor, obs, None, .1, held=True)
    with pytest.raises(ValueError, match='FORBIDDEN'):
        saved[-1]['held_world_position']
    assert audit.snapshot()['held_world_reads'] == 1
    with pytest.raises(ValueError, match='FORBIDDEN'):
        audit.receive(actor, dict(obs, camera='cctv_top'), None, .2)
    assert audit.snapshot()['top_camera_inputs'] == 1
    assert audit.snapshot()['controller_calls'] == 2


def test_speed_checker_keeps_failed_and_missing_runs(tmp_path):
    from scripts.check_map_amcl_speed import check_wave
    for n, ratio in enumerate((2., 4., 15.)):
        raw = tmp_path/str(n)/'raw'
        write(raw/'result.json', dict(source_sha='a'*40, status='RECORDED', finalization_complete=True))
        write(raw/'first30.json', dict(wall_per_sim=ratio, frames_per_robot=301, observation_period_s=.1))
    runs = [tmp_path/str(n) for n in range(3)]
    assert check_wave(runs, 'a'*40)['median_wall_per_sim'] == 4.
    assert not check_wave(runs, 'a'*40)['blocked']
    assert check_wave(runs+[tmp_path/'missing'], 'a'*40)['blocked']
    write(runs[0]/'raw/result.json', dict(source_sha='a'*40, status='HOST_ERROR', finalization_complete=True))
    assert check_wave(runs, 'a'*40)['blocked']


@pytest.mark.parametrize('interior', [False, True])
def test_rectangle_batches_keep_all_candidate_costs_bit_exact(interior):
    from harness.e2e_b_partial import rect_sd
    from harness.map_recording_speed import grid_cost
    rng = np.random.default_rng(41)
    points = rng.normal(size=(300, 2))
    centers = rng.normal(size=(1681, 2))
    for yaw in (0., .131, 1.8):
        sd = rect_sd(points[None], centers[:, None], yaw, (.4, .7))
        residual = np.maximum(sd, 0) if interior else np.abs(sd)
        baseline = (np.minimum(residual, .06)**2).mean(axis=1)
        candidate = grid_cost(points, centers, yaw, (.4, .7), .06, interior=interior)
        assert np.array_equal(baseline, candidate)
