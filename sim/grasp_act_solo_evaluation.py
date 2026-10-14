"""Evaluation-only physics score. Never imported by SoloTeacher.

Whole-object clearance (not centre height) follows the pair v3 grasp gate;
the 12 mm rule is identical for a 12 mm tile and a 50 mm can. All dimensions
are catalogue collision dimensions, not rendered bounding spheres.
"""
from __future__ import annotations
import math

CRITERIA = {'min_clearance_m': .012, 'max_tilt_deg': 10., 'lift_hold_s': 3.,
            'finger_min_n': .5, 'release_settle_s': 2., 'release_speed_m_s': .01,
            'release_max_tilt_deg': 3., 'release_clearance_m': .005,
            'placement_offset_m': .05, 'weld': 'off'}


def bottom_z(shape, center, rotation, size):
    """Analytic lowest collision point, also valid for a tilted cylinder."""
    if shape == 'box':
        extent = sum(abs(rotation[2][i])*size[i] for i in range(3))
    elif shape == 'cylinder':
        nz = max(-1., min(1., rotation[2][2]))
        extent = size[0]*math.sqrt(max(0., 1.-nz*nz))+size[1]*abs(nz)
    else:
        raise ValueError('box/cylinder collision geometry required')
    return center[2]-extent


class Score:
    def __init__(self):
        self.last_t = None
        self.lift_s = self.release_s = 0.
        self.max_lift_s = self.max_release_s = 0.
        self.previous_lift = self.previous_release = False
        self.lift_ok = False

    def add(self, now, *, min_z, support_z, tilt_deg, finger_forces, speed,
            open_issued, placement_offset, weld_active):
        if weld_active:
            raise ValueError('WELD_ACTIVE')
        dt = 0. if self.last_t is None else now-self.last_t
        if not 0 <= dt <= .15+1e-8:
            raise ValueError('consecutive evaluation samples required')
        c = CRITERIA
        lift = min_z-support_z >= c['min_clearance_m'] and tilt_deg <= c['max_tilt_deg'] and min(finger_forces) >= c['finger_min_n']
        release = (self.lift_ok and open_issued and abs(min_z-support_z) <= c['release_clearance_m']
                   and tilt_deg <= c['release_max_tilt_deg'] and speed <= c['release_speed_m_s']
                   and placement_offset <= c['placement_offset_m'] and max(finger_forces) < c['finger_min_n'])
        self.lift_s = self.lift_s+dt if lift and self.previous_lift else 0.
        self.release_s = self.release_s+dt if release and self.previous_release else 0.
        self.max_lift_s = max(self.max_lift_s, self.lift_s)
        self.max_release_s = max(self.max_release_s, self.release_s)
        self.lift_ok |= self.max_lift_s >= c['lift_hold_s']-1e-8
        self.previous_lift, self.previous_release, self.last_t = lift, release, now

    def record(self, command_complete):
        release_ok = self.max_release_s >= CRITERIA['release_settle_s']-1e-8
        return {'lift_success': self.lift_ok, 'release_success': release_ok,
                'physical_success': bool(command_complete and self.lift_ok and release_ok),
                'max_stable_lift_s': self.max_lift_s, 'max_stable_release_s': self.max_release_s,
                'criteria': CRITERIA}
