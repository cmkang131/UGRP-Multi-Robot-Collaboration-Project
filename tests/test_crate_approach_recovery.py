"""Real saved visible slices, pulse safety and held-input capability boundary."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from scripts.run_crate_teacher import make_grasp_teacher, run_meta
from scripts.zone_teacher import FOLDED
from sim.crate_approach_recovery import OPTION, safe_pulse
from sim.crate_cartesian_lift import STATION_M, plan_lift
from sim.crate_lift_pose import ANTIPODAL_OPTION
from sim.grasp_act_visible_route import constraints
from harness.visual_arm_v3 import solve_grip_site_ik

CASES = json.loads((Path(__file__).parent/'fixtures/crate10-visible-approach.json').read_text())['cases']


def teacher(c, mode=OPTION):
    return make_grasp_teacher(c['rid'], c['end'], c['baseline_command']['pwm'],
        teacher_stability='align_relook_v1', teacher_search='search_reacquire_v1',
        approach_goal_set='approach_goal_set_v1', crate_lift_pose=ANTIPODAL_OPTION,
        crate_approach_recovery=mode)


@pytest.mark.parametrize('c', [c for c in CASES if c['seed'] != 77978], ids=lambda c: str(c['seed']))
def test_real_failed_approach_pulses_are_rejected_and_replacement_is_safe(c):
    t = teacher(c); w = c['world']; t.folded_ready = True; t.phase = c['phase']
    audit = new_input_audit(True, 'issued'); w = AuditedTeacherInput(w, audit)
    radius, discs, rects = constraints(w, t.rid, True, t.cargo_profile)
    pose = w['robots'][t.rid]['pose']
    assert not safe_pulse(c['baseline_command'], pose, discs, rects, radius)
    value = t._check_navigation_pulse(w, c['baseline_command'], w['t'])
    assert safe_pulse(value, pose, discs, rects, radius)
    assert value != c['baseline_command']
    assert audit['held_world_reads'] == audit['invisible_measurements'] == 0


def test_wall_blocked_stances_handoff_without_relaxing_antipodal_geometry():
    c = next(c for c in CASES if c['seed'] == 77978); t = teacher(c)
    t.folded_ready = True
    assert not t._plan_approach(c['world'], c['world']['t'])
    assert t.outcome == 'approach_blocked_handoff'
    assert t.crate_recovery_log[-1]['recovery'] == 'static_stances_blocked_handoff'
    assert all(x['reason'] == 'grasp_geometry' for x in t.goal_set_log[-1]['candidates'] if abs(x['offset_deg']) >= 30)


def test_off_preserves_command_and_parent_mode_is_not_overwritten_by_crate_timer():
    c = CASES[0]; t = teacher(c, 'off'); t.phase = c['phase']
    assert t.approach_progress == 'off'
    assert t._check_navigation_pulse(c['world'], c['baseline_command'], 0.) == c['baseline_command']
    assert teacher(c).approach_progress == 'approach_progress_v1'
    with pytest.raises(ValueError): teacher(c, 'typo')


def test_visibility_gap_is_not_counted_as_visible_stance_stall(monkeypatch):
    c = CASES[0]; t = teacher(c); w = deepcopy(c['world'])
    t.phase = 'approach'; t.crate_visible_progress = (0., w['t']-20.)
    t.crate_last_visible_t = w['t']-10.
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    monkeypatch.setattr(VisibleOnlyGraspTeacher, '_approach', lambda *a: (None, False))
    t._approach(w, w['t'])
    assert t.crate_visible_progress[1] == w['t'] and not t.approach_excluded


def test_hidden_and_held_inputs_are_not_read_and_lift_commands_are_unchanged():
    class Forbidden(dict):
        def __getitem__(self, k): raise AssertionError('held world input read: '+k)
    c = CASES[0]; t = teacher(c)
    t.sink.pwm = {1: 1500, **solve_grip_site_ik((STATION_M, 0, .024))}
    expected = plan_lift(t.sink.pwm)[0]
    t._set('complete', 1.); t.step(Forbidden(), 1.1, permit_lift=True)
    assert t.lift_prefix == expected and t.phase == 'lift'
    for i in range(1, 32): t.step(Forbidden(), 1.1+i*.1)
    assert t.lift_done
    t.phase = 'approach'
    assert t._check_navigation_pulse({'visibility': {t.rid: {'visible_probes': 0}}}, c['baseline_command'], 5.) == c['baseline_command']


def test_wheel_deadlines_and_intermediate_translation_cannot_cut_obstacle():
    c = deepcopy(CASES[0]['baseline_command'])
    c.update(wheels=[.35]*4, duration_s=[.1]*4)
    assert not safe_pulse(c, (0., 0., 0.), [(0.008, 0., .001)], [], .001)
    assert safe_pulse(c, (0., 0., 0.), [], [], .13)


def test_mode_is_recorded_in_execution_metadata():
    row = run_meta({'batch': 'test', 'cargo_scene_version': 'crate_mass_025_v1'}, 'sha', 500,
                   ANTIPODAL_OPTION, OPTION)
    assert row['crate_approach_recovery'] == OPTION
