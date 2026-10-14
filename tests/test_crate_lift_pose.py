"""Command-only selector/barrier integration; no simulator construction."""
import pytest

from harness.visual_arm_v3 import MOUNT_X_M
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.crate_lift_pose import OPTION, THRESHOLD_NM, elbow_torque, select_lift_prefix
from sim.grasp_act_teacher import IssuedArm, grasp_poses
from scripts.zone_teacher import ArmSequence


def poses(radius=.146):
    hover, descent = grasp_poses((MOUNT_X_M+radius, 0., .024))
    return {1: 1500, **descent[-1]}, hover


def test_selected_motion_is_exact_prefix_and_every_loaded_sample_has_margin():
    closed, legacy = poses()
    best, report = select_lift_prefix(closed, legacy)
    original = ArmSequence(IssuedArm(closed), closed)
    original.queue(legacy, 0., duration=1.2, settle=.5)
    assert report['status'] == 'selected' and best['rise_m'] >= .012
    assert best['events'] == original.events[:len(best['events'])]
    current = dict(closed)
    times = sorted({t for t, _, _ in best['events']})
    for t in times:
        for at, sid, pwm in best['events']:
            if at == t:
                current[sid] = pwm
        assert abs(elbow_torque(current)['total_equal_share_nm']) <= THRESHOLD_NM


def test_absent_candidate_does_not_post_ready_or_queue_lift_and_never_reads_truth():
    closed, legacy = poses(.158)
    t = CrateGraspTeacher('r1', 'teal', closed, bounds=(-20, 20, -20, 20), crate_lift_pose=OPTION)
    t.lift_pose = legacy
    t._set('complete', 1.)
    assert t.phase == 'closed' and t.outcome == 'crate_lift_pose_no_candidate'
    assert t.diagnostic()['lift_pose_selection']['status'] == 'none'
    assert not t.lift_ready()
    class Forbidden(dict):
        def __getitem__(self, key):
            raise AssertionError('forbidden world input')
    t.step(Forbidden(), 1.1, permit_pick=True, permit_lift=True)
    assert not t.arm.events and not t.lift_done


def test_success_queues_only_owned_selected_samples_after_barrier():
    closed, legacy = poses()
    t = CrateGraspTeacher('r1', 'teal', closed, bounds=(-20, 20, -20, 20), crate_lift_pose=OPTION)
    t.lift_pose = legacy
    t._set('complete', 1.)
    assert t.lift_ready()
    t.step({}, 1.1, permit_pick=True, permit_lift=False)
    assert not t.arm.events
    t.step({}, 1.2, permit_pick=True, permit_lift=True)
    assert t.phase == 'lift'
    assert t.arm.events == [(1.2+at, sid, p) for at, sid, p in t.lift_prefix['events']]
    assert t.arm.commanded == t.lift_prefix['issued_pwm']


def test_off_preserves_original_full_lift():
    closed, legacy = poses()
    t = CrateGraspTeacher('r1', 'teal', closed, bounds=(-20, 20, -20, 20))
    t.lift_pose = legacy
    t._set('complete', 1.)
    t._queue_lift(1.2)
    expected = ArmSequence(IssuedArm(closed), closed)
    expected.queue(legacy, 1.2, duration=1.2, settle=.5)
    assert t.arm.events == expected.events and t.lift_selection is None


def test_runner_identity_and_invalid_load_guard(tmp_path):
    from scripts.run_crate_teacher import make_grasp_teacher, run, run_meta
    closed, _ = poses()
    assert make_grasp_teacher('r1', 'teal', closed, crate_lift_pose=OPTION).crate_lift_pose == OPTION
    plan = {'batch': 'offline', 'cargo_scene_version': 'crate_mass_025_v1', 'lug_color_scene': 'crate_lug_colors_v1'}
    meta = run_meta(plan, 'source', 500, OPTION)
    assert meta['cargo_scene_version'] == 'crate_mass_025_v1' and meta['crate_lift_pose'] == OPTION
    for scene, reach in [('crate_mass_030_v1', 'pad_window_v2'), ('crate_mass_025_v1', 'calibrated_mid_v1')]:
        with pytest.raises(ValueError, match='requires crate_mass_025_v1 and pad_window_v2'):
            run({}, tmp_path/'never-created', crate_scene=scene, reach_mode=reach, crate_lift_pose=OPTION)
    assert not (tmp_path/'never-created').exists()
