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
    write(raw/'result.json', dict(status=status, source_sha='a'*40, seed=65101,
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
    args = ['--seed', '65101', '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'out')]
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
        record.admission(record.load_spec(), 65101, 'a'*40, tmp_path/'queue.json', tmp_path/'out')
    q.update(execution_enabled=True, physical_execution_authorized=True, rendering_authorized=True,
        recording_spec_sha256=sha256(record.SPEC), machine_type=record.load_spec()['machine_type'],
        coordinator_approval=dict(approved=True, source_sha='a'*40, credit_stop_verified=True,
            seeds_unused_verified=True, storage_budget_verified=True, machine_verified=True))
    write(tmp_path/'queue.json', q)
    monkeypatch.setattr(record.shutil, 'disk_usage', lambda p: SimpleNamespace(free=10**12))
    record.admission(record.load_spec(), 65101, 'a'*40, tmp_path/'queue.json', tmp_path/'out')
    assert not (tmp_path/'out').exists()  # Admission itself never starts a run.
    q['source_sha'] = 'b'*40
    write(tmp_path/'queue.json', q)
    with pytest.raises(ValueError, match='COORDINATOR_APPROVAL'):
        record.admission(record.load_spec(), 65101, 'a'*40, tmp_path/'queue.json', tmp_path/'out')


def test_real_actor_dependencies_load_without_world_or_renderer():
    from harness.active_camera import SEARCH
    from harness.e2e_record_scalars import normalize
    from scripts.run_e2e_ownmap_live import ownmap_record
    robots = record.make_robots(record.load_spec(), 65101)
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
            trace = robot.receive(obs, np.full((480, 640, 3), 110, np.uint8))
            row = normalize(ownmap_record(robot, obs, trace, i*.1))
            assert 'fused_delta' in row['stall_odometry']
            json.dumps(row, allow_nan=False)
            if i % 2 == 0: robot.commanded(robot.nav_command, i*.1)


@pytest.mark.parametrize('speed_failure', [False, True])
def test_native_writer_retains_every_tick_and_only_own_fields(tmp_path, monkeypatch, speed_failure):
    from scripts import run_e2e_ownmap_live
    image = jpeg_bytes()
    spec = tiny_spec()
    if speed_failure:
        spec.update(sim_cap_s=60., frames_per_robot=601)
    issued, observed, evaluations = [], [], []
    class Backend:
        now = 1.3
        frame = 0
        def __init__(self):
            self.out = tmp_path
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
                               clock=lambda: 4*(b.now-1.3))
        assert len(evaluations) == 301 and len(list(tmp_path.glob('robots/*/rgb/*.jpg'))) == 602
        assert json.loads((tmp_path/'first30.json').read_text())['passed'] is False
        return
    result = record.record_loop(b, {r: Robot() for r in spec['robots']}, spec, tmp_path, clock=lambda: 0.)
    assert result['frames_per_robot'] == 5 and len(evaluations) == 5
    assert observed == pytest.approx([t for t in [0., .1, .2, .3, .4] for _ in range(2)])
    assert len(list(tmp_path.glob('robots/*/rgb/*.jpg'))) == 10
    # Native writer stores even byte-identical stationary frames.
    assert all(p.read_bytes() == image for p in tmp_path.glob('robots/*/rgb/*.jpg'))
    assert [t for t, r, a in issued if a['kind'] == 'hold'] == pytest.approx([1.3, 1.3, 1.5, 1.5])


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


@pytest.mark.parametrize('damage', ['missing_jpeg', 'clock', 'frame_count', 'host', 'failed', 'bytes'])
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
        r.update({'host': 'azure3'} if damage == 'host' else {'status': 'HOST_ERROR'})
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
