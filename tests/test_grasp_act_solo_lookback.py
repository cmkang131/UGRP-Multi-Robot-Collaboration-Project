"""Command geometry and synthetic RGB only; no world, renderer or physics."""
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness.grasp_act_contract import command
from harness.visual_arm_v3 import forward_grip, solve_grip_site_ik, tool_pose
from harness.zone_own_perception import APPEARANCE
from sim.grasp_act_solo_lookback import (
    MODE, LookbackObserver, object_transform, plan_lookback, regions, transforms,
)

RUNS = json.loads(Path('tests/fixtures/solo_rgb_lift_v3/manifest.json').read_text())['runs']


def poses(run):
    return [{int(k): v for k, v in run['commands'][i]['pwm'].items()} for i in (0, -1)]


def colour(kind):
    lo, hi = APPEARANCE[kind]['hue'][0]
    return cv2.cvtColor(np.uint8([[[(lo+hi)//2, 220, 210]]]), cv2.COLOR_HSV2BGR)[0, 0]


def cmd(t, pwm, wheels=None):
    return command({'t': t, 'pwm': {str(k): v for k, v in pwm.items()},
                    'wheels': wheels or [0.]*4, 'duration_s': [.1]*4 if wheels else [0.]*4})


def save(tag, frame, t):
    return {'tag': tag, 't': t, 'shape': list(frame.shape)}


@pytest.mark.parametrize('run', RUNS, ids=lambda r: r['run'])
def test_recorded_pickups_frame_entire_floor_site_without_held_occlusion(run):
    low, high = poses(run)
    p = plan_lookback(run['kind'], low, high)
    assert .09 <= p['backoff_m'] <= .155
    assert p['pwm'][6] == high[6] and p['pwm'][1] == 1500
    x, y, _ = forward_grip(low)
    for dx in (-.005, 0., .005):
        _, _, v = regions(run['kind'], low, p['pwm'], site=(x+p['backoff_m']+dx, y, 0))
        assert v['qualified'] and v['held_occlusion_pixels'] == 0
        assert v['surface_in_frame_n'] == v['surface_N'] and v['site_pixels'] > 10000
    # Old unmoved post-lift frames cannot be substituted for a lookback frame.
    assert not regions(run['kind'], low, high)[2]['qualified']


@pytest.mark.parametrize('kind', ['cyan', 'can', 'tile'])
def test_alignment_window_and_both_pan_offsets_have_a_deterministic_plan(kind):
    for x in ([.1962, .2002, .2042] if kind != 'tile' else [.166, .172, .178]):
        for y in (-.003, .003):
            pitch = -66 if kind != 'tile' else -73+750*(x-.172)
            low = {1: 1500, **solve_grip_site_ik((x, y, .009 if kind == 'tile' else .024),
                preferred_pitch_deg=pitch, calibrated_grasp_only=False)}
            high = {1: 1500, **solve_grip_site_ik((x, y, .095),
                preferred_pitch_deg=tool_pose(low).pitch_deg, calibrated_grasp_only=False)}
            p = plan_lookback(kind, low, high)
            assert p['geometry']['qualified']
            assert p == plan_lookback(kind, low, high)
            # Static retained-cargo box clears the floor through the new arm
            # segment. No retention/friction/dynamic success claim.
            from sim.grasp_act_solo_teacher import cargo
            from itertools import product
            half = np.array(cargo(kind).dims_m)/2
            corners = np.array(list(product(*[[-h, h] for h in half])))
            for f in np.linspace(0, 1, 21):
                pwm = {s: round(high[s]+f*(p['pwm'][s]-high[s])) for s in high}
                obj = object_transform(kind, low, pwm)
                assert (corners @ obj[:3, :3].T+obj[:3, 3])[:, 2].min() > .012


def test_camera_chain_is_the_unchanged_mount_and_not_an_invented_camera_servo():
    from sim.masterpi_camera_review_v3 import POSITION_M, QUAT_WXYZ
    from harness.servo_camera_fk import fixed_transform, transform_from_commands
    from scripts.probe_solo_lift_inspect_pose import nominal_transforms
    for run in RUNS:
        low, high = poses(run)
        p = plan_lookback(run['kind'], low, high)['pwm']
        g, c = transforms(p)
        g0, c0 = nominal_transforms(p)
        np.testing.assert_allclose(g, g0, atol=1e-12)
        np.testing.assert_allclose(c, c0, atol=1e-12)
        mount = fixed_transform(dict(translation_m=POSITION_M, quaternion_wxyz=QUAT_WXYZ))
        mount[:3, :3] = mount[:3, :3] @ np.diag([1., -1., -1.])
        np.testing.assert_allclose(np.linalg.inv(g) @ c, mount, atol=1e-12)
        assert transform_from_commands(p, camera_pose='servo_fk_v1')[0] is None


def observer_case(kind):
    run = next(r for r in RUNS if r['kind'] == kind)
    low, high = poses(run)
    p = plan_lookback(kind, low, high)
    before_pose = {1: 2000, 3: 500, 4: 2500, 5: 1320, 6: low[6]}
    pre, _, _ = regions(kind, low, before_pose, held=False)
    before = np.full((480, 640, 3), 100, np.uint8)
    before[pre] = colour(kind)
    ob = LookbackObserver(kind)
    ob.start(before, cmd(0., before_pose), save)
    ob.issue(cmd(.1, low), 'close')
    ob.issue(cmd(.2, p['pwm']), 'lookback')
    # Exercise issued command integration, not a manually supplied world site.
    from sim.grasp_act_solo_teacher import primitives
    wheels, duration = primitives().duty([-.15, 0., 0.])
    step = {'wheels': wheels, 'duration_s': duration}
    now = .3
    while ob.site[0]-forward_grip(low)[0] < p['backoff_m']:
        ob.issue({**cmd(now, p['pwm']), **step}, 'lookback')
        now = round(now+.1, 8)
    ob.issue(cmd(now, p['pwm']), 'lookback_settle')
    return ob, cmd(now+.1, p['pwm']), before


@pytest.mark.parametrize('kind', ['cyan', 'red', 'green', 'yellow', 'can', 'tile'])
@pytest.mark.parametrize('scene,answer', [('empty', 'yes'), ('miss', 'no'), ('dark', 'unknown'),
                                       ('occluded', 'unknown'), ('same', 'unknown')])
def test_before_after_site_comparison(kind, scene, answer):
    # All four boxes share geometry; colours remain distinct.
    base_kind = kind if kind in ('can', 'tile') else 'cyan'
    ob, c, before = observer_case(base_kind)
    if kind != base_kind:
        ob.kind = kind
        pre, _, _ = regions(kind, ob.grasp, ob.before_command['pwm'], held=False)
        ob.before[pre] = colour(kind)
        before = ob.before.copy()
    frame = np.full_like(before, 100)
    roi, _, _ = regions(kind, ob.grasp, c['pwm'], site=ob.site)
    if scene == 'miss':
        frame[roi] = colour(kind)
    elif scene == 'dark':
        frame[:] = 0
    elif scene == 'occluded':
        frame[roi] = (25, 25, 25)
    elif scene == 'same':
        frame = before
    r = ob.observe(frame, c, complete=True, save=save)
    assert r['answer'] == answer, r
    assert r['evidence'] == MODE


def test_unknown_for_missing_baseline_motion_gap_changed_pose_or_unframed_site():
    for case in ('baseline', 'gap', 'changed', 'unframed'):
        ob, c, before = observer_case('cyan')
        if case == 'baseline':
            ob.before[:] = 100
        if case == 'gap':
            c['t'] += 3.
        if case == 'changed':
            c['pwm']['6'] += 10
        if case == 'unframed':
            ob.site = (*forward_grip(ob.grasp)[:2], 0.)
        r = ob.observe(np.full_like(before, 100), c, complete=True, save=save)
        assert r['answer'] == 'unknown', r


def test_hold_is_rechecked_after_yes_and_new_cargo_or_visual_loss_revokes_it():
    ob, c, before = observer_case('cyan')
    frame = np.full_like(before, 100)
    assert ob.observe(frame, c, complete=True, save=save)['answer'] == 'yes'
    roi, _, _ = regions('cyan', ob.grasp, c['pwm'], site=ob.site)
    frame[roi] = colour('cyan')
    c['t'] += .1
    assert ob.observe(frame, c, complete=True, save=save)['answer'] == 'no'
