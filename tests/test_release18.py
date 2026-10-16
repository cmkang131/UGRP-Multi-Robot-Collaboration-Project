"""Command-history/real pixel regressions; no physics, render or network."""
import pytest

from sim import release14, release17, release18 as new
from sim.lookaround_localization import Camera
from tests.test_release_regrasp import stripe, teachers
from tests.test_grasp_act_release_run import fake_backend  # noqa: F401


def setup(*, reuse=new.REUSE, changed=False, busy=False, stage=True, holding=False, age=3.):
    t = teachers()['r1']
    t.odometry_profile = 'yaw_cal_v1'
    history = new.CommandHistory()
    issued, scheduled = [], []
    a = new.LineAlign(t, 3., camera=Camera(), undistort=lambda f: f,
                      wheel_command=lambda *v: issued.append(v), clearance=lambda *v: True,
                      fov_step=release17.FOV_STEP, settle_reuse=reuse, command_history=history,
                      after_approach=stage, idle=lambda: not busy)
    t.pwm.update(a.expected)
    t.holding = holding
    history.observe(t.pwm, 3.-age)
    if changed:
        history.observe({**t.pwm, 6:t.pwm[6]+1}, 2.9)
    history.observe(t.pwm, 3.)
    return a, t, history, issued, scheduled


def test_reuse_requires_fresh_rgb_and_full_visual_stability():
    a, t, h, issued, scheduled = setup()
    for now in (3., 3.1, 3.2, 3.3):
        h.observe(t.pwm, now)
        status = a.tick(now, lambda *v: stripe(), lambda *v: scheduled.append(v))
        assert (status == 'ready') == (now == 3.3)
    assert not scheduled and not issued
    assert sum(e['event'] == 'image' for e in a.records) == 4
    assert a.records[0]['omitted_wait_s'] == 2.6


@pytest.mark.parametrize('opts', [dict(reuse='off'), dict(changed=True), dict(busy=True),
                                dict(stage=False), dict(holding=True), dict(age=2.5)])
def test_changed_unsettled_busy_or_other_stage_keeps_original_wait(opts):
    a, t, h, issued, scheduled = setup(**opts)
    a.tick(3., lambda *v: pytest.fail('early image'), lambda *v: scheduled.append(v))
    assert scheduled and a.until == 5.6
    assert a.records[0]['event'] == 'open_then_hover'


def test_open_wait_reuse_retains_full_hover_wait_and_fresh_images():
    a,t,h,issued,scheduled=setup(stage=False)
    a.before_approach=True
    # The gripper has stayed open, while the camera/arm just changed.
    t.pwm[3]+=1
    h.observe(t.pwm,3.)
    a.tick(3.,lambda *v:pytest.fail('hover not settled'),lambda *v:scheduled.append(v))
    assert a.until == 4.4 and a.records[0]['event']=='reuse_settled_open'
    assert scheduled[0][1] == [(0.,a.hover)]
    t.pwm.update(a.hover)
    assert a.tick(4.3,lambda *v:pytest.fail('hover not settled'),lambda *v:None)=='pending'
    assert a.tick(4.4,lambda *v:stripe(),lambda *v:None)=='pending'
    assert a.records[-1]['event']=='mode_enter'


def test_recently_opened_gripper_keeps_original_open_wait():
    a,t,h,issued,scheduled=setup(stage=False)
    a.before_approach=True
    h.observe({**t.pwm,1:1300},3.)
    h.observe(t.pwm,3.)
    a.tick(3.,lambda *v:pytest.fail('recent open'),lambda *v:scheduled.append(v))
    assert a.until==5.6 and a.records[0]['event']=='open_then_hover'


def test_stale_unknown_history_and_clock_reversal_fail_closed():
    a, t, h, issued, scheduled = setup()
    assert h.age(t.pwm, 3.1) is None
    assert new.CommandHistory().age(t.pwm, 3.) is None
    with pytest.raises(ValueError):
        h.observe(t.pwm, 2.9)
    a.command_history = None
    a.tick(3., lambda *v: pytest.fail('early image'), lambda *v: scheduled.append(v))
    assert a.until == 5.6


def test_new_commands_after_reuse_still_abort_alignment():
    a, t, h, issued, scheduled = setup()
    a.tick(3., lambda *v: stripe(), lambda *v: scheduled.append(v))
    t.pwm[6] += 1
    assert a.tick(3.1, lambda *v: pytest.fail('changed command image'), lambda *v: None) == 'failed'
    assert a.failure.endswith('open_hover_command_changed')


def test_missing_rgb_cannot_become_ready_from_command_age():
    a, t, h, issued, scheduled = setup()
    for now in (3., 3.2, 3.4, 3.6, 3.8, 4.):
        h.observe(t.pwm, now)
        a.tick(now, lambda *v: None, lambda *v: scheduled.append(v))
    assert a.state == 'failed' and a.failure.endswith('shaft_unobserved_1s')


def test_validation_and_runner_defaults():
    import inspect
    from scripts.run_grasp_act_release import run
    plan = {'end_color_scene':'grasp_act_teal_blue_v1'}
    opts = {**release14.SAFE, 'command_motion':'yaw_cal_v1', 'release_fov_step':release17.FOV_STEP}
    for reuse in new.REUSE_MODES:
        new.validate(new.PROFILE, False, {**opts,'release_settle_reuse':reuse}, plan)
    for profile in release17.PROFILES:
        with pytest.raises(ValueError, match='requires release18'):
            new.validate(profile, False, {**opts,'release_settle_reuse':new.REUSE}, plan)
    with pytest.raises(ValueError):
        new.validate(new.PROFILE, True, opts, plan)
    assert inspect.signature(run).parameters['release_settle_reuse'].default == 'off'


def test_runner_scheduler_uses_history_with_actual_pixels(tmp_path, fake_backend, monkeypatch):
    from tests import test_release15 as existing
    from scripts import run_grasp_act_release as runner
    original_run = runner.run
    results = []
    def run(*args, **kwargs):
        kwargs.update(release_profile=new.PROFILE, command_motion='yaw_cal_v1',
                      release_fov_step=release17.FOV_STEP, release_settle_reuse=new.REUSE)
        result = original_run(*args, **kwargs)
        results.append(result)
        return result
    monkeypatch.setattr(runner, 'run', run)
    existing.test_runner_real_map_near_wall_and_actual_pixel_barrier(tmp_path, fake_backend, monkeypatch)
    checks = results[0]['line_rechecks']
    assert sum(e['event']=='reuse_settled_open_hover' for c in checks for e in c['events']) == 2
    assert sum(e['event']=='reuse_settled_open' for c in checks for e in c['events']) == 2
    assert results[0]['release_settle_reuse'] == new.REUSE


def test_goal_region_accepts_inside_without_extra_centering():
    from sim import release_global_observation as old
    reports={rid:dict(kind='localized_margin',margin_m=m,lateral_clearance_m=.1,expected_slack_m=.8)
             for rid,m in zip(('r1','r2'),(.22,.55))}
    assert new.pair_choice(reports,('r1','r2'),0.)==old.pair_choice(reports,('r1','r2'),0.)
    assert new.pair_choice(reports,('r1','r2'),0.,goal_region=new.GOAL_REGION)['action']=='lower'
    for problem in ({'margin_m':.039},{'lateral_clearance_m':.039},{'kind':'none'},
                    {'margin_m':1.2},{'reason':'release_axis_unaligned'}):
        changed={**reports,'r1':{**reports['r1'],**problem}}
        a=new.pair_choice(changed,('r1','r2'),0.,goal_region=new.GOAL_REGION,axis_recovery=True)
        assert a['action']!='lower'


def test_goal_toggle_and_queue_are_disabled_by_default():
    import inspect
    from scripts.run_grasp_act_release import run
    from scripts.prepare_release18_queue import build,verify
    assert inspect.signature(run).parameters['release_goal_region'].default=='off'
    with pytest.raises(ValueError):
        new.validate(release17.PROFILE,False,{'release_goal_region':new.GOAL_REGION},{})
    queue=build('0'*40)
    verify(queue)
    queue['runs'][0]['enabled']=True
    with pytest.raises(AssertionError):
        verify(queue)
