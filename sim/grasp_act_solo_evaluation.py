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


class ZoneScore:
    """Evaluation-only full collision footprint and whole carry retention.

    A drop/regrasp cannot erase a failure. All samples from confirmed carry
    through the start of lowering must retain lift clearance and both fingers.
    """
    def __init__(self, region, *, active_recovery=False):
        self.active_recovery = active_recovery
        self.intermediate_setdowns = 0
        self.last_phase = None
        self.region = region
        self.lift = Score()
        self.last_t = None
        self.start_t = self.end_t = self.carry_start = self.carry_end = None
        self.carry_samples = self.drop_samples = 0
        self.no_drop = True
        self.release_s = self.max_release_s = 0.
        self.previous_release = False
        self.last_inside = False

    def add(self, now, *, phase, footprint_xy, finger_contacts=False, **row):
        # Preserve the old lift criterion; pickup-offset release is ignored.
        self.lift.add(now, **row)
        if self.active_recovery and phase == 'carry_recover_lower' and self.last_phase != phase:
            self.intermediate_setdowns += 1
        self.last_phase = phase
        dt = 0. if self.last_t is None else now-self.last_t
        self.start_t = now if self.start_t is None else self.start_t
        self.end_t = now
        from sim.solo_carry_to_zone import TRAVEL_PHASES
        carrying = phase in (*TRAVEL_PHASES, 'zone_place_view', 'zone_place_advance')
        if carrying:
            self.carry_start = now if self.carry_start is None else self.carry_start
            self.carry_end = now
            self.carry_samples += 1
            retained = bool(row['min_z']-row['support_z'] >= CRITERIA['min_clearance_m'] and
                            min(row['finger_forces']) >= CRITERIA['finger_min_n'])
            self.no_drop &= retained
            self.drop_samples += not retained
        cx, cy = self.region['center_m']; hx, hy = self.region['half_extents_m']
        self.last_inside = bool(footprint_xy) and all(
            abs(x-cx) <= hx and abs(y-cy) <= hy for x, y in footprint_xy)
        release = (phase in ('open', 'retract', 'backoff', 'lookaround', 'complete') and
            self.lift.lift_ok and self.carry_samples > 0 and self.last_inside and row['open_issued'] and not finger_contacts and
            abs(row['min_z']-row['support_z']) <= CRITERIA['release_clearance_m'] and
            row['tilt_deg'] <= CRITERIA['release_max_tilt_deg'] and
            row['speed'] <= CRITERIA['release_speed_m_s'] and
            max(row['finger_forces']) < CRITERIA['finger_min_n'])
        self.release_s = self.release_s+dt if release and self.previous_release else 0.
        self.max_release_s = max(self.max_release_s, self.release_s)
        self.previous_release, self.last_t = release, now

    def record(self, command_complete):
        release = self.release_s >= CRITERIA['release_settle_s']-1e-8
        retained = self.carry_samples > 0 and self.no_drop
        return {'lift_success': self.lift.lift_ok, 'zone_placement_success': release,
            'release_success': release, 'no_drop_during_carry': retained,
            'physical_success': bool(command_complete and self.lift.lift_ok and release and retained),
            **({'intermediate_controlled_setdowns': self.intermediate_setdowns,
                'retention_scope': 'travel legs only; deliberate recovery setdowns separately counted',
                'uninterrupted_carry': self.intermediate_setdowns == 0} if self.active_recovery else {}),
            'carry_samples': self.carry_samples, 'drop_samples': self.drop_samples,
            'max_stable_lift_s': self.lift.max_lift_s, 'max_stable_release_s': self.max_release_s,
            'final_footprint_inside_zone': self.last_inside,
            'carry_sim_s': None if self.carry_start is None else self.carry_end-self.carry_start,
            'task_sim_s': None if self.start_t is None else self.end_t-self.start_t,
            'criteria': {**{k: v for k, v in CRITERIA.items() if k != 'placement_offset_m'},
                         'placement': 'every collision-box corner inside destination zone',
                         'retention': 'every 10 Hz carry sample: clearance >=12 mm and both fingers >=0.5 N',
                         'detached': 'no cargo/finger contact and open command',
                         'scope': 'evaluation only; sub-100 ms drops not resolved'}}
