"""Offline checks for the carry look-around probe (no physics)."""
import json
from pathlib import Path
from scripts.probe_carry_lookaround import delta, verdict, region_points, LIMITS, YAW_EFFORT

ROLES = {'r1': 'teal', 'r2': 'blue'}


def sample(grip1=(0., 0., 0.), force=(2., 2.), shift=0., pitch=0.):
    row = {'beam_pitch_deg': pitch, 'beam_roll_deg': 0., 'beam_yaw_deg': 10., 'beam_min_z': .02}
    row['r1'] = {'finger_n': list(force), 'grip_in_beam_m': list(grip1), 'base_xy': [0., 0.], 'base_yaw_deg': 0.}
    row['r2'] = {'finger_n': [2., 2.], 'grip_in_beam_m': [0., 0., 0.], 'base_xy': [shift, 0.], 'base_yaw_deg': 0.}
    return row


def test_quiet_hold_passes():
    base = sample()
    s = sample(); s['delta'] = delta(s, base, ROLES)
    worst, reasons = verdict([s], ROLES, 'r1')
    assert reasons == [] and worst['r1']['slip_axis_mm'] == 0.


def test_each_failure_reason_is_reported():
    base = sample()
    s = sample(grip1=(.006, .004, 0.), force=(.3, 2.), shift=.02, pitch=6.)
    s['delta'] = delta(s, base, ROLES)
    _, reasons = verdict([s], ROLES, 'r1')
    assert {'tilt', 'r1:grip_force', 'r1:slip_axis', 'r1:slip_perp', 'r2:partner_dragged'} <= set(reasons)


def test_actor_own_motion_is_not_partner_drag():
    base = sample(); s = sample(); s['r1']['base_xy'] = [.05, 0.]
    s['delta'] = delta(s, base, ROLES)
    assert verdict([s], ROLES, 'r1')[1] == []


def test_region_points_inside_region_and_wheel_band():
    pts = region_points({'center_m': [4.6, .4], 'half_extents_m': [.3, .7]})
    assert len(pts) == 9 and all(4.3 < x < 4.9 and -.3 < y < 1.1 for x, y, _ in pts)
    assert .31 <= YAW_EFFORT + 1/12 <= .40 and LIMITS['finger_min_n'] == .5


def test_workflow_registered():
    rows = json.loads(Path('configs/simulation_workflows.json').read_text())['workflows']
    row = next(r for r in rows if r['id'] == 'grasp-act-lookaround-probe')
    assert row['runner'] == 'scripts.probe_carry_lookaround' and Path(row['entry']).is_file()
