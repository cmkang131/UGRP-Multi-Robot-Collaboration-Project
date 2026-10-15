"""Solo set-down look-around on the shared Opus localizer (no simulator; detection stubbed)."""
import math
import numpy as np
import pytest
from harness import zone_pair_highpose_contract as contract
from sim.grasp_act_solo_lookaround import SoloLookaround
from sim.grasp_act_solo_teacher import SoloTeacher, primitives
from sim.lookaround_localization import LookaroundLocalizer


@pytest.fixture(scope='module')
def static():
    return contract.resolve('zone_wide_two_doors_final_v3')[0]


class Frames:
    """Counts how often the own frame is actually requested (only at captured views)."""
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return np.zeros((480, 640, 3), np.uint8)


def stub_observe(loc, log):
    def observe(now, raw_rgb, servo):
        assert raw_rgb.shape == (480, 640, 3) and set(servo) == {1, 3, 4, 5, 6}
        rec = {'status': 'measured', 'wall_points': 7, 'floor_lines': 1, 'doors': 0, 'seen_groups': ['g'],
               't': now}
        log.append((now, dict(servo)))
        return rec
    loc.observe = observe


def run_to_done(look, p, *, start_t=0., limit=400):
    pwm = dict(p.folded)
    frames, log = Frames(), []
    stub_observe(look.loc, log)
    look.start(start_t, pwm[6])
    done = False
    for i in range(limit):
        now = start_t+.1*(i+1)
        cmd, done = look.step(now, pwm, frames)
        pwm.update({int(k): v for k, v in cmd['pwm'].items()})
        look.issue(cmd, .1)
        if done:
            break
    return done, frames, log, i


def test_real_shared_plan_runs_to_completion_and_captures_every_planned_view(static):
    p = primitives()
    look = SoloLookaround(static, ops=p)
    look.arm([3.0, .10, -math.pi/2])
    done, frames, log, ticks = run_to_done(look, p)
    assert done
    views = look.loc.plan['views']
    assert views and len(log) == len(views) == frames.calls   # an own frame is requested only at a captured view
    assert look.measured_views == len(views)
    # Every captured view happens at the planned pan with the gripper open (camera FK qualification).
    assert [s[6] for _, s in log] == [v['pan_pulse'] for v in views]
    assert all(s[1] > 1600 for _, s in log)
    # Real motion, not a bookkeeping flag: the look script takes arm move + dwell time per view.
    assert ticks*.1 >= 1.0+.8*len(views)
    assert look.record()['predictions_are_observations'] is False


def test_body_rotation_plan_is_executed_as_valid_duty_pulses_and_rotated_back(static):
    p = primitives()
    look = SoloLookaround(static, ops=p)
    look.arm([.5, -1.0, 0.])                     # facing a wall: the plan turns the body 180 deg
    start = look.loc.own.x.copy()
    pwm, pulses, log = dict(p.folded), 0, []
    stub_observe(look.loc, log)
    look.start(0., pwm[6])
    assert look.loc.plan['rotated'] and {v['body_yaw_deg'] for v in look.loc.plan['views']} == {180.}
    done = False
    for i in range(1200):
        cmd, done = look.step(.1*(i+1), pwm, Frames())     # ops.command() validates every pulse (0.31-0.40, <= 150 ms)
        pwm.update({int(k): v for k, v in cmd['pwm'].items()})
        pulses += any(cmd['wheels'])
        look.issue(cmd, .1)
        if done:
            break
    assert done and len(log) == 3
    # 180 deg out and 180 deg back at the nominal 0.35 rad/s: about 2 x 9 s of 0.1 s pulses.
    assert 150 <= pulses <= 220
    assert abs(math.atan2(math.sin(look.loc.own.x[2]-start[2]), math.cos(look.loc.own.x[2]-start[2]))) < math.radians(8)


def test_issue_moves_the_pose_only_after_arming_and_by_issued_pulses(static):
    p = primitives()
    look = SoloLookaround(static, ops=p)
    pulse = p.command({'t': 0., 'wheels': [.35]*4, 'duration_s': [.1]*4, 'pwm': {str(s): v for s, v in p.folded.items() if s in (1, 3, 4, 5, 6)}})
    look.issue(pulse, .1)                       # not armed: nothing happens, nothing raises
    assert not look.armed
    with pytest.raises(ValueError, match='before the pose estimate'):
        look.start(0., 1500)
    look.arm([1., 1., 0.])
    with pytest.raises(ValueError, match='already armed'):
        look.arm([0., 0., 0.])
    look.issue(pulse, .1)
    assert look.loc.own.x[0] > 1.005 and look.loc.own.x[0] < 1.02      # 12.9 mm per 0.1 s pulse at 0.35
    half = p.command({'t': 0., 'wheels': [.35]*4, 'duration_s': [.05]*4, 'pwm': pulse['pwm']})
    before = look.loc.own.x[0]
    look.issue(half, .1)
    assert 0 < look.loc.own.x[0]-before < .0075                          # half-length pulses move half as far


def test_teacher_runs_the_set_down_look_after_backoff_with_the_real_adapter(static):
    p = primitives()
    p.gaze = lambda target, previous, **_: dict(previous)
    look = SoloLookaround(static, ops=p)
    t = SoloTeacher('cyan', 'west', p.folded, profile='solo_visible_only_v1', held_object_hidden_v1=True,
                    setdown_lookaround_v1=True, lookaround=look, ops=p)
    log = []
    target = {'xyz': [t.ops.station, 0., .024], 'yaw': 0.}
    frames = Frames()
    phases, done = [], False
    for i in range(900):
        now = i*.1
        if t.phase == 'lower' and not look.armed:
            look.arm([3.0, .10, -math.pi/2])        # the scene owner's estimate, outside the teacher
            stub_observe(look.loc, log)
        value, done = t.step(now, measurement=None if t.holding else target, rgb_holding='yes', own_rgb=frames)
        t.remember_applied(value)
        phases.append(t.phase)
        if done:
            break
    assert done and t.result == 'command_complete'
    assert 'backoff' in phases and 'lookaround' in phases
    assert phases.index('lookaround') > phases.index('backoff')
    assert look.measured_views >= 1 and frames.calls == look.measured_views
    assert t.diagnostic()['setdown_lookaround_v1'] is True


def test_unarmed_lookaround_cannot_finish_silently(static):
    p = primitives()
    p.gaze = lambda target, previous, **_: dict(previous)
    look = SoloLookaround(static, ops=p)
    t = SoloTeacher('cyan', 'west', p.folded, profile='solo_visible_only_v1', held_object_hidden_v1=True,
                    setdown_lookaround_v1=True, lookaround=look, ops=p)
    target = {'xyz': [t.ops.station, 0., .024], 'yaw': 0.}
    with pytest.raises(ValueError, match='before the pose estimate was armed'):
        for i in range(900):
            value, done = t.step(i*.1, measurement=None if t.holding else target, rgb_holding='yes')
            t.remember_applied(value)
            assert not done


def test_carry_relook_shares_only_command_belief_and_counts_real_updates(static):
    from sim.solo_carry_pose import CommandPose, task_start
    p = primitives()
    pose = CommandPose(task_start(static))
    look = SoloLookaround(static, ops=p, truth_free_v1=True, command_pose=pose)
    with pytest.raises(ValueError, match='no pose estimate'):
        look.arm([90., 80., 0.])
    look.arm()
    assert look.loc.own is pose.own
    pulse = p.command({'t': 0., 'wheels': [.35]*4, 'duration_s': [.1]*4,
                       'pwm': {str(s): v for s, v in p.folded.items() if s in (1, 3, 4, 5, 6)}})
    pose.issue(pulse, .1)
    at = pose.pose
    look.issue(pulse, .1)
    assert pose.pose == at  # no double propagation
    seen = []
    def observe(now, rgb, servo):
        seen.append(now)
        if len(seen) == 1:
            return {'status': 'measured', 'wall_points': 0, 'floor_lines': 0, 'doors': 0}
        pose.own.x[0] += .001  # detector substitute, no backend/evaluation
        return {'status': 'measured', 'grid': {'poses': 3}, 'fix_acceptance': {'accepted': True}, 'wall_points': 2,
                'floor_lines': 0, 'doors': 0, 'seen_groups': ['wall_west:e']}
    look.loc.observe = observe
    look.start(.1, 1500)
    pwm = dict(p.folded)
    for i in range(600):
        now = .2+i*.1
        cmd, done = look.step(now, pwm, Frames())
        pwm.update({int(k): v for k, v in cmd['pwm'].items()})
        if len(seen) == 1:
            assert pose.last_fix is None
        if done:
            break
    assert done and len(seen) >= 2 and pose.fixes == len(seen)-1
    assert pose.last_fix == seen[-1]
    assert look.record()['self_pose_source'] == 'task_start_issued_commands'
