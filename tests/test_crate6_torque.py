"""Offline gravity audit, saved XML/PWM only; never constructs a simulator."""
import importlib.util
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crate6_torque',
    ROOT/'experiments/2026-10-14-crate-teacher/audit_crate6_torque.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def scene():
    return ET.parse(ROOT/'tests/fixtures/crate6-elbow.xml').getroot()


def test_xml_gravity_matches_independent_planar_moment_sum():
    pwm = {3: 500, 4: 1516, 5: 2358, 6: 1500}
    s = math.radians(90-(pwm[5]-1589)*.09)
    f = s-math.radians((pwm[4]-1553)*.09)
    p = f+math.radians((pwm[3]-1554)*.09)
    expected = 9.81*(.01333*math.cos(f)+.015371*math.cos(p)+.00012*math.sin(p))
    actual = audit.estimate(scene(), 'r2', pwm)
    assert actual['total_equal_share_nm'] == pytest.approx(expected, abs=1e-12)
    assert actual['total_equal_share_nm'] == pytest.approx(.16797763715529634, abs=1e-12)
    assert actual['limit_nm'] == .1765197


@pytest.mark.parametrize('bounds', [None, (.036, 1.)])
def test_entire_pad_window_has_no_ten_percent_margin_and_witness_is_real(bounds):
    xml = scene()
    report = audit.scan_pad_window(xml, z_bounds=bounds)
    assert report['shoulder_elbow_pairs_checked'] == 3389694
    assert not report['qualified']
    assert report['at_least_10pct_margin_pair_minima'] == 0
    best = report['best']
    assert .146 <= best['arm_axis_radius_m'] <= .158
    assert report['z_bounds_m'][0] <= best['z_m'] <= report['z_bounds_m'][1]
    assert best['total_equal_share_nm'] > report['threshold_nm']
    assert best['total_equal_share_nm'] < best['limit_nm']  # infeasible at 10%, not at zero margin
    pwm = best['issued_pwm']
    # Enumerate every wrist pulse for the winning shoulder/elbow pair, an
    # independent check that the monotonic pruning did not skip a better pose.
    from harness.visual_arm_v3 import tool_pose, MOUNT_X_M
    feasible = []
    for p3 in range(500, 2501):
        p = {**pwm, 3: p3}
        pose = tool_pose(p)
        radius = math.hypot(pose.x_m-MOUNT_X_M, pose.y_m)
        if (.146 <= radius <= .158 and report['z_bounds_m'][0] <= pose.z_m <= report['z_bounds_m'][1]
                and -90 <= pose.pitch_deg <= -39.865):
            feasible.append(audit.estimate(xml, 'r2', p)['total_equal_share_nm'])
    assert min(feasible) == pytest.approx(best['total_equal_share_nm'], abs=1e-12)


def test_scan_refuses_changed_inertial_model():
    xml = scene()
    next(b for b in xml.iter('body') if b.get('name') == 'r2__elbow_link').find('inertial').set('mass', '.08')
    with pytest.raises(AssertionError):
        audit.scan_pad_window(xml)
