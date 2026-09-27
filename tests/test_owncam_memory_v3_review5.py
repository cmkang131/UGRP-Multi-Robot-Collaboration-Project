"""Review 5: fix hysteresis, bounded initialization and a matched safety ablation.

Offline inputs only. Saved s151 frames replay through the actual detector/PF;
synthetic posteriors below test the state machine, not physical task success.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
import pytest

from harness.owncam_drive import CARRY_POSTURE, SEARCH_POSE, LOOK_P20
from tests.test_owncam_memory_v3 import controller, fix, params, report, static_map
from tests.test_owncam_memory_v3_review import leg_fixture

FIXTURE = Path(__file__).parent / 'fixtures/owncam_memory_v3_init'


@pytest.mark.parametrize('loaded', [False, True])
def test_p1_marginal_full_fix_must_not_reset_retry_budget(loaded):
    leg, loc, _ = leg_fixture(loaded, yaw=math.radians(2.9))
    fix(leg.memory, loc.t)
    # At 2.9 degrees the real loaded PF exceeds the 3 degree drive gate after
    # restoring carry. It must refix, not certify success and erase failures.
    assert leg._should_refix(True)
    assert leg.unverified_looks == 1


def test_p1_repeated_good_fixes_without_movement_have_separate_cap():
    leg, loc, est = leg_fixture(True, yaw=.005)
    leg.servo = dict(CARRY_POSTURE)
    for attempt in range(8):
        loc.t = 2. + attempt
        leg._start_look(loc.t, 'uncertain')
        if leg.outcome:
            break
        loc.t += .2
        fix(leg.memory, loc.t, (est['x'], est['y']))
        assert not leg._should_refix(True)
        assert leg.unverified_looks == 0
    assert leg.outcome == 'look_stagnation'
    assert attempt < 5


def saved_init_controller(cls=None):
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3
    record = json.loads((FIXTURE / 'manifest.json').read_text())
    ctl = (cls or M1OwnCamDeliveryMemV3)(static_map(), params(), seed=record['seed'],
        box_kind='cyan', slot_id='A1', slot_xy=(4.6, 0.), skill_factory=mock.Mock(),
        pose_estimate_cls=mock.Mock(), search_rows_y=(-.85, .75))
    data = (FIXTURE / record['image']).read_bytes()
    rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    commands = iter(record['commands'])
    cmd = next(commands, None)
    for row in record['frames']:
        while cmd is not None and cmd['t'] <= row['t']:
            ctl.on_command(cmd)
            cmd = next(commands, None)
        assert hashlib.sha256(data).hexdigest() == row['sha256']
        obs = {'frame_id': row['frame_id'], 'sim_time': row['t'], 'robot_id': 'r1',
               'camera': row['camera'], 'image': base64.b64encode(data).decode(),
               'sha256': row['sha256'], 'actuator_state': {'servo_pulses': row['commanded_servo']}}
        ctl.on_frame(row['t'], obs, rgb)
    while cmd is not None:
        ctl.on_command(cmd)
        cmd = next(commands, None)
    return ctl


def test_p2_saved_s151_rejected_initial_look_gets_stationary_recapture():
    ctl = saved_init_controller()
    rep = ctl.pose.report(1.8)
    assert rep.x_m == pytest.approx(-.868, abs=.002)
    assert rep.std_xy_m == pytest.approx(.168, abs=.002)
    decisions = [ctl.decide(t) for t in (1.8, 1.9, 2., 2.1)]
    assert ctl.outcome is None
    assert any(d['mode'] == 'capture' for d in decisions)
    assert all(c['kind'] == 'hold' for d in decisions for c in d.get('commands', []))


def test_p2_initial_recapture_times_out_with_no_observations():
    ctl = saved_init_controller()
    ctl.decide(1.8)
    result = ctl.decide(12.)
    assert result == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.sweep is None and ctl.leg is None


def test_comparison_off_blocks_same_current_sigma_as_on():
    from scripts.run_m1_owncam_memory_v3 import controller_class
    for condition in ('off', 'memory_v3'):
        ctl = controller(controller_class(condition))
        ctl.servo = dict(CARRY_POSTURE)
        ctl._start_leg((1., -.85), loaded=True)
        leg = ctl.leg
        est = dict(initialized=True, x=-.47, y=-.85, yaw=0., std_xy_m=.02,
                   std_yaw_rad=math.radians(3.1), cov=np.diag([.0002, .0002, math.radians(3.1)**2]),
                   since_tag_s=0.)
        leg.state, leg.state_since, leg.last_look_xy = 'drive', 1., (-.47, -.85)
        leg.loc.predict_to = lambda now: None
        leg.loc.estimate = lambda: est
        if hasattr(ctl, 'memory'):
            fix(ctl.memory, 2.)
        commands = leg.tick(2.)
        assert not any(c['kind'] == 'mecanum' for c in commands), condition


def test_comparison_off_rejects_same_unsafe_sweep_as_on():
    from scripts.run_m1_owncam_memory_v3 import controller_class
    from tests.test_owncam_memory_v3_review3 import door_map
    for condition in ('off', 'memory_v3'):
        ctl = controller(controller_class(condition))
        ctl.map, ctl.servo, ctl.phase = door_map(), dict(CARRY_POSTURE), 'skill'
        ctl.pose.report = lambda t: report(t, x=2., y=-.5, sigma=.001)
        ctl._start_sweep(2., 'look', LOOK_P20, [1500], CARRY_POSTURE, 'gate:test')
        assert ctl.outcome == 'LOOK_COLLISION_UNVERIFIED', condition
        assert ctl.sweep is None


def real_prediction_leg(*, memory_on=True):
    from harness.owncam_drive_mem_v3 import LegDriverMemV3
    from harness.owncam_landmark_tags import TagLandmarkProvider
    from harness.owncam_localizer import OwnCamLocalizer
    from harness.owncam_memory_v3 import OwnCamMemoryV3
    smap, p = static_map(), params()
    loc = OwnCamLocalizer(smap, p, seed=151)
    loc.initialized, loc.load.loaded = True, True
    loc.command({'t': 0., 'kind': 'initial_servo_command', 'pulses': CARRY_POSTURE})
    loc.load.loaded = True  # synthetic loaded posterior; no physics or true pose
    mem = OwnCamMemoryV3(smap, p, robot_id='r1', provider=TagLandmarkProvider(smap, p))
    leg = LegDriverMemV3(mem, loc, smap, p, loaded=True, goal_xy=(1., 0.), door_xy=(2., 0.),
                        initial_servo=CARRY_POSTURE, **({} if memory_on else {'memory_look_enabled': False}))
    leg.state, leg.state_since = 'drive', 0.
    leg.last_look_xy = (0., 0.)
    cloud = np.random.default_rng(5).normal(size=(loc.n, 3))
    cloud -= cloud.mean(axis=0)
    # Decorrelate and normalize so synthetic posterior sigmas are reproducible.
    cloud = cloud @ np.linalg.inv(np.linalg.cholesky(cloud.T @ cloud / loc.n)).T
    def posterior(yaw_deg):
        loc.px[:] = cloud * [.02 / math.sqrt(2), .02 / math.sqrt(2), math.radians(yaw_deg)]
        loc.logw[:] = 0.
        fix(mem, loc.t, (0., 0.))
    posterior(3.2)
    return leg, loc, posterior


def run_synthetic_look_loop(full_yaw, memory_on=True, *, arrival=False):
    leg, loc, posterior = real_prediction_leg(memory_on=memory_on)
    if arrival:
        leg.goal = [0., 0.]
        posterior(.5)
    moves = 0
    for step in range(1601):
        now = round(step * .1, 6)
        loc.predict_to(now)
        if (leg.state == 'look_pan' and now - leg.state_since >= .3
                and all(leg.servo.get(k) == v for k, v in leg.arm_target.items())):
            posterior(full_yaw if leg.look_mode == 'full' else 2.9)
        commands = leg.tick(now)
        for command in commands:
            row = {'t': now, **command}
            loc.command(row)
            leg.memory.guard.on_command(row, loc._motion_params())
            leg.on_command(row)
        moves += sum(c['kind'] == 'mecanum' for c in commands)
        if leg.outcome or moves:
            break
    return leg, loc, moves


def test_p1_real_tag_planner_pf_and_state_machine_terminate_marginal_loop():
    leg, loc, moves = run_synthetic_look_loop(2.9)
    print('marginal:', leg.look_counts, 'sim_s:', loc.t, 'moves:', moves, 'outcome:', leg.outcome)
    assert leg.outcome == 'pose_unverified'
    assert moves == 0 and loc.t < 60.
    assert leg.look_counts['short'] == 1 and leg.look_counts['full'] == 1


@pytest.mark.parametrize('memory_on', [False, True])
def test_p1_real_pf_accepted_fix_survives_carry_restore_and_moves(memory_on):
    leg, loc, moves = run_synthetic_look_loop(1.95, memory_on)
    print('recovered:', memory_on, leg.look_counts, 'sim_s:', loc.t, 'moves:', moves, 'outcome:', leg.outcome)
    assert leg.outcome is None and moves == 1
    assert leg._current_uncertainty_ok(leg.loc.estimate())
    assert leg.servo == CARRY_POSTURE


@pytest.mark.parametrize('memory_on', [False, True])
def test_p1_arrival_fix_also_leaves_prediction_margin(memory_on):
    leg, loc, moves = run_synthetic_look_loop(1.25, memory_on, arrival=True)
    assert leg.outcome == 'arrived' and moves == 0
    assert leg._current_uncertainty_ok(leg.loc.estimate(), arrival=True)


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_p2_converged_new_frame_exits_initial_recovery(condition):
    from scripts.run_m1_owncam_memory_v3 import controller_class
    ctl = saved_init_controller(controller_class(condition))
    ctl.decide(1.8)
    # Synthetic later own report isolates recovery control; NOT a saved s151 continuation.
    ctl.pose.report = lambda now: report(now, x=-.8, y=.55)
    ctl.last_frame_id += 1
    ctl.last_obs = {**ctl.last_obs, 'frame_id': ctl.last_frame_id, 'sim_time': 2.}
    result = ctl.decide(2.)
    assert ctl.phase != 'init' and ctl.outcome is None
    assert ctl.init_recovery is None
    assert result == ctl._hold()


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_p2_capture_budget_is_finite_even_with_fast_decisions(condition):
    from scripts.run_m1_owncam_memory_v3 import controller_class
    from harness.owncam_safety_v3 import INIT_MAX_CAPTURES
    ctl = saved_init_controller(controller_class(condition))
    ctl.decide(1.8)
    for i in range(INIT_MAX_CAPTURES + 1):
        now = 1.9 + i * .21
        result = ctl.decide(now)
        if result['mode'] == 'done':
            break
        assert result['mode'] == 'capture'
        # Same clock cannot spin in capture mode.
        assert ctl.decide(now) == ctl._hold()
    assert result == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}
    assert ctl.init_recovery['captures'] == INIT_MAX_CAPTURES


def test_stagnation_cannot_reset_on_look_or_pose_jump_without_issued_translation():
    from harness.owncam_safety_v3 import MAX_LOOKS_WITHOUT_PROGRESS
    leg, loc, est = leg_fixture(True, yaw=.005)
    leg.servo = dict(CARRY_POSTURE)
    for i in range(MAX_LOOKS_WITHOUT_PROGRESS):
        loc.t = 2. + i
        est['x'] += .11  # localization changes while stationary are not travel
        fix(leg.memory, loc.t, (est['x'], est['y']))
        leg._start_look(loc.t, 'refix')
        assert leg.outcome is None
    leg._start_look(loc.t, 'refix')
    assert leg.outcome == 'look_stagnation'


def test_stagnation_resets_on_issued_translation_and_estimated_goal_progress():
    leg, loc, est = leg_fixture(True, yaw=.005)
    leg.servo = dict(CARRY_POSTURE)
    fix(leg.memory, loc.t, (est['x'], est['y']))
    leg._start_look(loc.t, 'refix')
    leg.state = 'drive'
    leg.on_command({'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15})
    est['x'] += .11
    fix(leg.memory, loc.t, (est['x'], est['y']))
    leg._start_look(loc.t, 'refix')
    assert leg.outcome is None and leg.looks_without_progress == 1


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_comparison_retries_arrival_and_stagnation_use_identical_implementation(condition):
    from scripts.run_m1_owncam_memory_v3 import controller_class
    from harness.owncam_safety_v3 import LegSafetyV3, ControllerSafetyV3
    ctl = controller(controller_class(condition))
    ctl._start_leg((1., -.85), loaded=True)
    for name in ('_current_uncertainty_ok', '_should_refix', '_arm_step', '_arrive', '_look_stalled'):
        assert getattr(ctl.leg, name).__func__ is getattr(LegSafetyV3, name)
    for name in ('_start_sweep', '_arm_steps', '_init', 'decide'):
        assert getattr(ctl, name).__func__ is getattr(ControllerSafetyV3, name)
    assert ctl.memory_look_enabled is (condition == 'memory_v3')


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_runner_records_matched_contract_and_thread_caps(tmp_path, condition):
    from scripts import run_m1_owncam_memory_v3 as runner
    from scripts import run_m1_owncam as base_runner
    def fake_run(spec, out, student):
        out.mkdir()
        result = {'outcome': 'SIM_LIMIT', 'controller': {}}
        (out / 'result.json').write_text(json.dumps(result))
        (out / 'manifest.json').write_text('{}')
        return result, {}
    with mock.patch.dict('os.environ', {name: '1' for name in runner.THREAD_VARS}), \
         mock.patch.object(base_runner, 'run', side_effect=fake_run), \
         mock.patch.object(runner, 'free_gib', return_value=100.):
        _, _, record = runner.run_episode({'episode_id': 'unit'}, tmp_path / condition, {}, condition,
                                          prereg_sha256='unit-test')
    assert record['threads'] == {name: '1' for name in runner.THREAD_VARS}
    assert record['safety_contract'] == 'ugrp.owncam_safety.v3'
    assert record['comparison_role'] == 'matched_look_ablation'
    assert record['memory_look_enabled'] is (condition == 'memory_v3')
    assert 'harness/owncam_safety_v3.py' in record['memory_files_sha256']


def test_review5_is_in_ci():
    from scripts.run_ci_tests import TEST_PATTERNS
    assert 'tests/test_owncam_memory_v3_review5.py' in TEST_PATTERNS


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_only_on_uses_memory_to_choose_gate_and_search_reobservations(condition):
    from scripts.run_m1_owncam_memory_v3 import controller_class
    from harness.owncam_drive import WIDE_LOOK_PANS
    from types import SimpleNamespace
    ctl = controller(controller_class(condition))
    ctl.servo, ctl.phase = dict(SEARCH_POSE), 'search_leg'
    ctl.pose.report = lambda now: report(now, x=0., y=0., sigma=.001)
    obs = {'actuator_state': {'servo_pulses': {str(k): v for k, v in ctl.servo.items()}}}
    on = condition == 'memory_v3'
    with mock.patch.object(ctl.memory, 'plan_look', return_value={'pans': [1500]}) as plan:
        ctl._gate_look(2., 'gate:nav_unloaded:std_xy', obs, loaded=False)
        assert plan.call_count == int(on)
        assert ctl.sweep['mode'] == ('short' if on else 'full')
    ctl.sweep = None
    ctl.leg = SimpleNamespace(state='posture_back')
    with mock.patch.object(ctl, '_drive_leg', return_value=(None, 'arrived')), \
         mock.patch.object(ctl.memory, 'plan_search_pans', return_value={'pans': [1500], 'coverage': {}}) as plan:
        ctl._search_leg(2.)
        assert plan.call_count == int(on)
    assert ctl.sweep['queue'] == ([1500] if on else list(WIDE_LOOK_PANS))


@pytest.mark.parametrize('condition', ['off', 'memory_v3'])
def test_registered_old_prereg_cannot_silently_switch_off_semantics(tmp_path, condition):
    from scripts import run_m1_owncam_memory_v3 as runner
    path = tmp_path / 'old-prereg.json'
    path.write_text(json.dumps({'status': 'REGISTERED', 'student': {}, 'episodes': []}))
    with mock.patch.object(runner, 'run_episode') as run:
        with pytest.raises(SystemExit, match='shared safety contract'):
            runner.main(['--prereg', str(path), '--condition', condition, '--output', str(tmp_path / 'out')])
        run.assert_not_called()


def test_stagnation_time_limit_applies_even_without_another_look_request():
    from harness.owncam_safety_v3 import MAX_LOOK_STAGNATION_S
    leg, loc, _ = leg_fixture(True, yaw=.005)
    leg.servo = dict(CARRY_POSTURE)
    fix(leg.memory, loc.t)
    leg._start_look(loc.t, 'refix')
    start = loc.t
    assert leg.tick(start + MAX_LOOK_STAGNATION_S) == [{'kind': 'hold'}]
    assert leg.outcome == 'look_stagnation'


def test_initial_rejections_do_not_restart_deadline_or_consume_actual_sweep_budget():
    ctl = saved_init_controller()
    ctl.decide(1.8)
    deadline = ctl.init_recovery['deadline']
    for now in (2., 2.2, 2.4, 2.6):
        # New frame timestamps, same uncertain synthetic own estimate.
        ctl.last_frame_id += 1
        ctl.last_obs = {**ctl.last_obs, 'frame_id': ctl.last_frame_id, 'sim_time': now}
        result = ctl.decide(now)
        assert result == ctl._hold() and ctl.sweep is None and ctl.outcome is None
        assert ctl.init_looks == 0 and ctl.init_recovery['deadline'] == deadline
    assert ctl.decide(deadline) == {'mode': 'done', 'outcome': 'NOT_INITIALIZED'}


def test_prereg_matches_the_shared_safety_module_and_paired_conditions():
    from harness import owncam_safety_v3 as safety
    from scripts import run_m1_owncam_memory_v3 as runner
    draft = json.loads(Path('experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json').read_text())
    shared = draft['shared_safety']
    assert draft['status'] == 'DRAFT' and not draft['execution_authorized']
    assert draft['conditions'] == list(runner.MATCHED_CONDITIONS)
    assert draft['safety_contract'] == safety.SCHEMA
    assert shared['fix_accept_max']['std_yaw_deg'] == pytest.approx(math.degrees(safety.FIX_ACCEPT_YAW_RAD))
    assert shared['fix_accept_max']['arrival_std_yaw_deg'] == pytest.approx(math.degrees(safety.ARRIVAL_FIX_ACCEPT_YAW_RAD))
    assert shared['fix_accept_max']['loaded_std_xy_m'] == safety.FIX_ACCEPT_XY_M[True]
    assert shared['fix_accept_max']['unloaded_std_xy_m'] == safety.FIX_ACCEPT_XY_M[False]
    assert shared['max_unverified_looks'] == safety.MAX_UNVERIFIED_LOOKS
    assert shared['max_looks_without_progress'] == safety.MAX_LOOKS_WITHOUT_PROGRESS
    assert shared['max_look_stagnation_sim_s'] == safety.MAX_LOOK_STAGNATION_S
    assert shared['initialization']['stationary_recovery_sim_s'] == safety.INIT_RECOVERY_S
    assert shared['initialization']['max_capture_requests'] == safety.INIT_MAX_CAPTURES
    assert shared['initialization']['total_init_sim_s'] == safety.INIT_TIMEOUT_S
