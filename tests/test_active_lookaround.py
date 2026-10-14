import math
import numpy as np
import pytest
from sim.active_lookaround import OwnPose, plan_views, predicted_bearing, gain, information, wrap

LANDMARKS = [{'id': 'cone_ne', 'type': 'cone', 'xy': (3., 2.)}, {'id': 'cone_nw', 'type': 'cone', 'xy': (-1., 2.)},
             {'id': 'door_s', 'type': 'door', 'xy': (1., -2.)}, {'id': 'corner_e', 'type': 'corner', 'xy': (4., 0.)}]


def fov(pose, yaw_deg, pan_deg, lm, half=math.radians(40), rmax=5.):
    b = wrap(predicted_bearing(pose, lm['xy'])-math.radians(yaw_deg+pan_deg))
    return abs(b) < half and math.dist(pose[:2], lm['xy']) < rmax


def test_plan_is_canonical_and_informative():
    pose = (0., 0., 0.); P = np.diag([.05**2, .05**2, math.radians(3)**2])
    plan = plan_views(pose, P, LANDMARKS, fov)
    pans = [v['pan_deg'] for v in plan['views']]
    assert 1 <= len(pans) <= 3 and pans == sorted(pans)
    assert plan['expected_gain_nats'] > 1 and len(plan['expected_landmarks']) >= 3
    assert plan_views(pose, P, LANDMARKS, fov) == plan              # deterministic


def test_plan_rotates_body_only_when_pans_see_nothing():
    lms = [{'id': 'behind', 'type': 'corner', 'xy': (-3., .2)}, {'id': 'behind2', 'type': 'cone', 'xy': (-3., -1.5)}]
    P = np.diag([.05**2, .05**2, math.radians(3)**2])
    plan = plan_views((0., 0., 0.), P, lms, fov)
    yaws = {v['body_yaw_deg'] for v in plan['views']}
    assert plan['rotated'] and plan['views'] and len(yaws) == 1 and abs(yaws.pop()) == 90.   # smallest rotation that sees them
    assert not plan_views((0., 0., 0.), P, LANDMARKS, fov)['rotated']


def test_ekf_bearings_reduce_pose_error_and_gate_outliers():
    truth = np.array([.08, -.06, math.radians(4)])
    est = OwnPose((0., 0., 0.), sigma_xy=.1, sigma_yaw=math.radians(5))
    before = math.hypot(*(est.x[:2]-truth[:2]))
    for lm in LANDMARKS:
        est.update_bearing(lm['xy'], predicted_bearing(truth, lm['xy']), label=lm['id'])
    for lm in LANDMARKS:
        est.update_bearing(lm['xy'], predicted_bearing(truth, lm['xy']), label=lm['id'])
    after = math.hypot(*(est.x[:2]-truth[:2]))
    assert after < before/3 and abs(wrap(est.x[2]-truth[2])) < math.radians(1)
    assert not est.update_bearing((3., 2.), predicted_bearing(truth, (3., 2.))+.6, label='outlier')


def test_propagate_grows_uncertainty():
    est = OwnPose((0., 0., 0.)); p0 = np.trace(est.P)
    est.propagate(.2, 0., 0.); assert est.x[0] == pytest.approx(.2) and np.trace(est.P) > p0
    assert gain(est.P, information(est.x, [(2., 1.), (2., -1.)])) > 0
