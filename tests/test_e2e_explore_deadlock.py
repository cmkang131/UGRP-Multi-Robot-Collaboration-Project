"""Idle action lifecycle, admission, native planner and real receive wiring; no physics."""
import json
from pathlib import Path
import numpy as np
import pytest
from scripts.replay_e2e_idle import FIXTURE, restored, replay
from harness.e2e_explore_deadlock import install, PARAMS


def fixture():
    return json.loads(FIXTURE.read_text())[0]


def idle_commands(g, start=0., end=30.):
    for t in np.arange(start, end, .2):
        g.command(dict(t=float(t), kind='hold'))


def test_all_saved_terminal_states_keep_off_hold_and_resume_bounded_scan():
    result = replay(json.loads(FIXTURE.read_text()))
    assert result['n'] == result['N'] == 22
    for row in result['records']:
        off, on = row['outcomes']['off'], row['outcomes']['replan_v1']
        assert not any(off['action'].get(k,0) for k in ('forward','left','turn')) and off['finished']
        assert on['action']['turn'] > 0 and on['phase'] == 'sensor_sweep'
        assert on['elapsed_s'] == PARAMS['idle_s']


def test_expiry_reselects_real_native_path_and_preserves_obstacles_and_pose():
    g, n, c, pose = restored(fixture(), 'replan_v1')
    target = pose[:2]+[1., 0.]
    n.blacklist = [target.copy()]; n.visited = [target.copy()]
    n.core.frontiers = lambda *a: np.array([[*target, 0., 0., 1., 15., -1.]])
    costs = c.costs.copy(); raw = c.raw.copy(); before = pose.copy()
    idle_commands(g)
    action, trace = g.receive(robot_id=g.robot_id, t=30.)
    assert n.locked and not n.finished and n.phase is None
    assert n.path and np.linalg.norm(np.array(n.path[-1])-target) < 1e-8
    assert action['kind'] == 'mecanum'
    assert g.explore_deadlock.cycles == 1 and not n.blacklist and not n.visited
    np.testing.assert_array_equal(c.costs, costs)
    np.testing.assert_array_equal(c.raw, raw)
    np.testing.assert_array_equal(pose, before)


@pytest.mark.parametrize('guard', ['rotation', 'ownership_gap', 'done', 'approach', 'failed', 'view', 'recovery', 'r3'])
def test_no_recovery_for_motion_handoff_or_protected_state(guard):
    g, n, c, pose = restored(fixture(), 'replan_v1')
    idle_commands(g)
    if guard == 'rotation':g.command(dict(t=29.8, kind='mecanum', turn=.5))
    elif guard == 'ownership_gap':g.explore_deadlock.last_issued=25.
    elif guard == 'done':g.done=True
    elif guard == 'approach':g.stage='approach'
    elif guard == 'failed':n.failed=True
    elif guard == 'view':n.view_active=True
    elif guard == 'recovery':n.phase='wait'
    elif guard == 'r3':g.robot_id='r3'
    g.explore_deadlock.before_receive(30.)
    assert g.explore_deadlock.cycles == 0 and n.finished


def test_bounded_scan_cannot_get_stuck_or_retry_every_frame():
    g, n, c, pose = restored(fixture(), 'replan_v1')
    idle_commands(g)
    action, _ = g.receive(robot_id=g.robot_id, t=30.)
    assert action['turn'] > 0
    # No odometry rotation: native sweep still has its 30 SIM-second deadline.
    action, _ = g.receive(robot_id=g.robot_id, t=60.2)
    assert n.phase is None and not any(action.get(k,0) for k in ('forward','left','turn'))
    for t in np.arange(60.4, 62., .2):
        action, _ = g.receive(robot_id=g.robot_id, t=t)
        g.command(action)
    assert g.explore_deadlock.cycles == 1


def test_off_identity_and_invalid_options():
    obj=object(); assert install(obj) is obj
    with pytest.raises(ValueError, match='UNKNOWN_EXPLORE_DEADLOCK'):install(obj, 'typo')


def test_v208_bundle_v207_off_identity_relay_and_real_robot_wiring():
    from scripts.run_e2e_ownmap_live import bundle
    from scripts.s4_proxy_relay import accepted_call_id
    from harness.e2e_live_mapping import Robot
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.s4_event_policy import Options
    kw=dict(enabled=True,stall_odometry='rgb_vo_us_v1',ultrasonic_front='on_v1',
        exploration_progress='frontier_progress_v1',boundary_views='candidate_views_v1',b_marker_detect='contrast_v1',
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1')
    old=bundle('sha',61001,'study_gemma4_31b_v1',**kw)
    assert old == bundle('sha',61001,'study_gemma4_31b_v1',**kw,explore_deadlock='off')
    new=bundle('sha',61001,'study_gemma4_31b_v1',**kw,explore_deadlock='replan_v1')
    assert new['execution_bundle_id']=='e2e-explore-deadlock-v208'
    assert 'harness/e2e_explore_deadlock.py' in new['source_sha256']
    assert 'configs/simulation_workflows.d/e2e_explore_deadlock_v208.json' in new['source_sha256']
    for k in ('schema','execution_bundle_id','workflow_version','source_sha256','explore_deadlock'):
        old.pop(k,None);new.pop(k,None)
    assert new['e2e_options'].pop('explore_deadlock') == 'replan_v1'
    assert old == new
    with pytest.raises(ValueError,match='V207_REQUIRED'):
        bundle('sha',61001,'study_gemma4_31b_v1',explore_deadlock='replan_v1')
    for arm in ('a','b'):
        for seed in (61001,61002,61003):assert accepted_call_id(f'e2e-idle-{arm}-s{seed}:call-0001-r1:1')
    assert not accepted_call_id('e2e-idle-a-s61004:call-0001-r1:1')
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot=Robot('r1',61001,cov,Options(),exploration_progress='frontier_progress_v1',
        boundary_views='candidate_views_v1',explore_deadlock='replan_v1',
        stall_options=StallOptions(stall_odometry='rgb_vo_us_v1'),
        vo_floor_mask='homography_v1',vo_rotation_policy='no_ransac_v1')
    import base64,cv2,hashlib
    rgb=np.zeros((480,640,3),np.uint8);_,jpeg=cv2.imencode('.jpg',rgb);data=jpeg.tobytes()
    for i,t in enumerate((0.,30.)):
        if i:
            n=robot.goal.explorer.navigator;n.finished=True;n.phase=None;n.sweep_pending=None;n.locked=False
            idle_commands(robot.goal)
        trace=robot.receive(dict(frame_id=i,sim_time=t,sha256=hashlib.sha256(data).hexdigest(),
            image=base64.b64encode(data).decode()),rgb)
    assert trace['explore_deadlock']['cycles']==1
    assert trace['explore_deadlock']['search']['frontier_count'] >= 0
    assert any(robot.nav_command.get(k,0) for k in ('turn','forward','left'))
    assert n.locked or n.phase == 'sensor_sweep'
