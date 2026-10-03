"""V92 registration/schedule/runner regressions; no physics, RGB or network."""
import copy
import errno
import gzip
import hashlib
import json
import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_final_pair_contract as c
from harness import zone_final_pair_loaded as v92
from harness import zone_final_pair_loaded_schedule as s
from scripts import run_final_pair_loaded as run
from scripts import agent_lock, agent_sim_slots
from tests.test_zone_final_pair_v3 import FakePhysics, offline_only


def bundle():
    return {**v92.bundle(v92.MAP_ID, v92.CHECK), 'case': v92.cases(v92.CHECK, v92.MAP_ID)[0]}


def args(out):
    return ['--check', v92.CHECK, '--map-id', v92.MAP_ID, '--expected-source-sha', 'a'*40,
            '--output', str(out), '--seed', '911']


def test_schedule_archive_and_preserved_sources():
    record = v92.schedule_registration()
    raw = gzip.decompress((c.ROOT/v92.SCHEDULE).read_bytes())
    assert raw == s.schedule_bytes()
    assert len(raw) == record['bytes']
    assert hashlib.sha256(raw).hexdigest() == record['sha256']
    assert json.loads(raw) == s.schedule()
    frozen = json.loads((c.ROOT/'experiments/2026-10-03-v92-loaded-schedule/preservation.json').read_text())
    for path, digest in frozen['unchanged_sha256'].items():
        assert c.base.sha(c.ROOT/path) == digest, path


def test_controller_pose_not_replaced_by_visible_candidate_or_floor_loaded_claim():
    from harness.zone_final_pair_vision import grasp_postures
    from harness.visual_arm_v3 import tool_pose
    hover, path = grasp_postures()
    assert s.POSES['controller_hover'] == hover
    assert s.POSES['floor_grasp'] == path[-1]
    assert abs(tool_pose(s.POSES['edge_view_150']).z_m-.15) < .0002
    assert s.POSES['edge_view_150'] != hover
    plan = s.design()
    assert set(plan['unsupported_controller_requirements']) == {
        'floor_grasp_loaded', 'controller_hover_edge', 'edge_view_150', 'transition_extrinsics'}
    assert all(seg['pose'] == 'controller_hover' for seg in plan['segments'] if seg['mode'] != 'relative_yaw')
    assert all(seg['pose'] == 'edge_view_150' for seg in plan['segments'] if seg['mode'] == 'relative_yaw')


def test_every_original_288_command_cell_has_full_horizons_and_orbit_not_opposed():
    plan = s.design()
    primary = [seg for seg in plan['segments'] if seg['mode'] != 'relative_yaw']
    cells = 0
    for rid in ('r1', 'r2'):
        for axis in s.AXES:
            for sign in (1, -1):
                for magnitude in s.FROZEN_LEVELS:
                    found = [seg for seg in primary if seg['axis'] == axis and seg['phase'] == 'step'
                             and np.isclose(s.action_vector(seg, rid)[axis], sign*magnitude)]
                    assert len(found) == 1
                    for horizon in (.2, .5, 1., 2., 3., 3.2):
                        assert round((found[0]['duration_s']-horizon)/.05)+1 >= 100
                        cells += 1
    assert cells == 288  # command support only, not post-contact sample survival
    inputs = np.array([list(s.action_vector(seg, 'r1').values()) for seg in primary])
    assert np.linalg.matrix_rank(inputs) == 3
    for seg in primary:
        a, b = s.action_vector(seg, 'r1'), s.action_vector(seg, 'r2')
        if seg['mode'] == 'common_orbit':
            assert a == b
            assert a['left'] == pytest.approx(-s.ORBIT_RADIUS_M*a['turn'])
            assert a['forward'] == 0
        else:
            assert all(a[k] == -b[k] for k in s.AXES)
    for axis in ('forward', 'left'):
        low = [seg for seg in primary if seg['axis'] == axis and seg['analysis_role'] == 'low_command_diagnostic'
               and seg['phase'] == 'step']
        assert sorted(seg['value'] for seg in low) == [-.004, -.002, -.001, .001, .002, .004]


def test_motion_split_long_steps_coasts_prbs_and_visible_relative_yaw_separate():
    plan = s.design()
    for mode, axis in [('world_translation', 'forward'), ('world_translation', 'left'),
                       ('common_orbit', 'turn'), ('relative_yaw', 'turn')]:
        segments = [seg for seg in plan['segments'] if (seg['mode'], seg['axis']) == (mode, axis)]
        prbs = [seg for seg in segments if seg['phase'] == 'prbs']
        assert len(prbs) == 31
        assert [seg['value'] for seg in prbs] == [.015*x for x in s.prbs31()]
        assert all(seg['duration_s'] == .5 and seg['analysis_role'] == 'validate_prbs' for seg in prbs)
        for i, seg in enumerate(segments):
            if seg['phase'] == 'step':
                assert seg['duration_s'] == 10.
                assert segments[i+1]['phase'] == 'coast' and segments[i+1]['duration_s'] == 1.
        assert segments[-1]['phase'] == 'coast' and segments[-1]['duration_s'] == 2.5
    for seg in plan['segments']:
        if seg['mode'] == 'relative_yaw':
            a, b = s.action_vector(seg, 'r1'), s.action_vector(seg, 'r2')
            assert a['left'] == b['left'] == 0
            assert a['turn'] == -b['turn']


def test_fixed_schedule_valid_leases_grip_pan_and_prospective_settled_windows():
    from sim.camera_robot_port import validate_raw_action
    events = s.schedule()
    assert events == sorted(events, key=lambda e: e['t'])
    for event in events:
        validate_raw_action(event['action'], allow_mecanum=True, allow_reverse=True)
        assert 0 <= event['t'] < s.CAP_S
        assert abs(event['t']/.05-round(event['t']/.05)) < 1e-7
    for rid in ('r1', 'r2'):
        own = [e for e in events if e['robot_id'] == rid]
        grip = [(e['t'], e['action']['pulse']) for e in own if e['action'].get('servo_id') == 1]
        assert grip == [(0., 2000), (2., 1500), (714., 2000)]
        pans = [e['action']['pan_pulse'] for e in own if e['action']['kind'] == 'look']
        assert all(abs(a-b) <= 20 for a, b in zip(pans, pans[1:]))
        for window in s.design()['camera_windows']:
            before = [e for e in own if e['t'] < window['start_s'] and e['action']['kind'] in ('arm', 'look')]
            assert window['start_s']-max(e['t'] for e in before) >= 8.
            assert (window['end_s']-window['start_s'])/.2 >= 5
            assert not any(window['start_s'] <= e['t'] < window['end_s'] for e in own)
        drives = [e for e in own if e['action']['kind'] == 'mecanum']
        assert all(e['action']['duration_s'] == .05 for e in drives)
        assert all(a['t']+.05 <= b['t']+1e-8 for a, b in zip(drives, drives[1:]))


def test_registration_workflow_source_closure_and_new_cap():
    from sim import workflow_manager as wm
    from scripts.run_ci_tests import TEST_PATTERNS, collect_test_files
    b = bundle()
    assert b['execution_bundle_id'] == 'zone-final-pair-v92'
    assert b['workflow_version'] == '3.4.0'
    assert b['case']['sim_cap_s'] == 720.
    assert b['caps']['total_including_reset_s'] == 725.
    assert b['clearance_preflight']['admitted']
    assert b['timing']['eval_pose_period_s'] == .05
    assert b['timing']['rgb_capture_period_s'] == .2
    for path in (v92.SCHEDULE, v92.REGISTRY, v92.WORKFLOW, 'sim/final_pair_fast_guard.py',
                 'sim/masterpi_camera_profile.py', 'scripts/agent_sim_slots.py', 'sim/masterpi_dynamics_v2.py'):
        assert b['source_sha256'][path] == c.base.sha(c.ROOT/path)
    row, _ = wm._row(c.ROOT, v92.WORKFLOW_ID)
    assert row['version'] == '3.4.0'
    plan = wm.plan(c.ROOT, v92.WORKFLOW_ID, args(c.ROOT/'outputs/unused')+['--sim-slot', 'sim-v92-test'])
    assert plan['command'][1:3] == ['-m', 'scripts.run_final_pair_loaded']
    assert not plan['execution_started']
    assert collect_test_files(c.ROOT, TEST_PATTERNS).count('tests/test_zone_final_pair_loaded.py') == 1


@pytest.mark.parametrize('mutation', ['id', 'unloaded', 'map', 'weld', 'contact', 'render', 'seed',
                                     'role', 'teacher', 'training', 'timing', 'interlock', 'measurement', 'cap', 'schedule'])
def test_mutation_refused_before_backend_and_output(tmp_path, mutation):
    b = bundle()
    edits = {'id': ('execution_bundle_id', 'zone-final-pair-v88'), 'unloaded': ('check', 'calibration-unloaded'),
             'map': ('map_id', 'zone_wide_corridor_final_v3'), 'weld': ('weld', 'on'),
             'contact': ('contact_profile', 'default'), 'render': ('render_profile', 'default'), 'seed': ('seed', 912),
             'role': ('collection_role', 'HELD_OUT_VALIDATION'), 'teacher': ('teacher_only', False),
             'training': ('training_eligible', False)}
    if mutation in edits:
        k, v = edits[mutation]
        b[k] = v
    if mutation == 'timing': b['timing']['eval_pose_period_s'] = .2
    if mutation == 'interlock': b['runtime_interlock']['required'] = False
    if mutation == 'measurement': b['measurement']['clearance']['minimum_m'] = .1
    if mutation == 'cap': b['caps']['per_case_s'] = 370.
    if mutation == 'schedule': b['schedule']['sha256'] = '0'*64
    with pytest.raises(ValueError):
        run.run_case(b, tmp_path/'case', seed=911, backend_factory=lambda *a, **kw: pytest.fail('backend reached'))
    from sim.final_pair_loaded import PhysicsBackend
    with pytest.raises(ValueError):
        PhysicsBackend(b, tmp_path/'case', seed=911)
    assert not (tmp_path/'case').exists()


@pytest.mark.parametrize('failure', [None, 'interlock', 'ENOSPC'])
def test_runner_exact_samples_schedule_and_retained_failure(tmp_path, failure):
    made = []
    class Fake(FakePhysics):
        def advance_to(self, t):
            if failure == 'ENOSPC': raise OSError(errno.ENOSPC, 'test disk full')
            if failure == 'interlock': raise ValueError('CLEARANCE_ABORT: test')
            return super().advance_to(t)
    def factory(*a, **kw):
        made.append(Fake(*a, **kw))
        return made[-1]
    b = bundle()
    result = run.run_case(b, tmp_path/'case', seed=911, backend_factory=factory)
    assert (tmp_path/'case/inputs/schedule.json').read_bytes() == s.schedule_bytes()
    assert result['physical_success'] is None and result['research_result'] is False
    assert {k: result[k] for k in v92.ROLE} == v92.ROLE
    if failure:
        assert result['status'] == 'HOST_ERROR'
        assert result['collection_data_status'] == 'PARTIAL_INVALID_HOST_ERROR'
        assert result['partial_data_retained'] is True
        assert result['failure']['class'] == ('ENOSPC' if failure == 'ENOSPC' else 'HOST_ERROR')
    else:
        assert result['status'] == 'COLLECTED_UNQUALIFIED'
        assert len(made[0].samples) == 14401 and len(made[0].frames) == 3601
        assert len(made[0].actions) == len(s.schedule())
        assert result['check_sim_s'] == 720.
    assert made[0].closed
    hashes = json.loads((tmp_path/'case/artifacts.sha256.json').read_text())
    assert hashes['result.json'] == c.base.sha(tmp_path/'case/result.json')


def test_owned_sim_slot_main_records_host_and_rejects_wrong_slot(tmp_path, monkeypatch):
    original = run.subprocess.check_output
    def git(argv, **kw):
        if '--git-common-dir' in argv: return str(tmp_path/'.git')+'\n'
        if '--show-current' in argv: return 'codex/v92-test\n'
        return original(argv, **kw)
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run, 'check_source', lambda _: None)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda _: SimpleNamespace(free=20*1024**3))
    monkeypatch.setattr(agent_lock, 'DEFAULT_ROOT', tmp_path/'locks')
    monkeypatch.setitem(sys.modules, 'sim.final_pair_loaded', SimpleNamespace(PhysicsBackend=FakePhysics))
    agent_sim_slots.acquire_sim_slot(tmp_path/'locks', slot='sim-owned', owner='codex',
        branch='codex/v92-test', purpose='fake', pid=os.getpid(), expected_minutes=1)
    agent_sim_slots.acquire_sim_slot(tmp_path/'locks', slot='sim-other', owner='codex',
        branch='codex/other', purpose='fake', pid=os.getpid(), expected_minutes=1)
    out = tmp_path/'outputs/run'
    for flags in ([], ['--sim-slot', 'sim-other']):
        with pytest.raises(ValueError, match='live owned'):
            run.main(args(out)+['--execute', '--lock-owner', 'codex']+flags)
    assert not out.exists()
    assert run.main(args(out)+['--execute', '--lock-owner', 'codex', '--sim-slot', 'sim-owned']) == 0
    result = json.loads((out/'result.json').read_text())
    assert result['lock_mode'] == 'sim_slot' and result['sim_slot'] == 'sim-owned'
    assert result['source_unchanged'] is True and result['status'] == 'COLLECTED_UNQUALIFIED'
    for key in ('host_start', 'host_end'):
        assert len(result[key]['loadavg']) == 3
        assert [x['name'] for x in result[key]['concurrent_holders']] == ['sim-other', 'sim-owned']
