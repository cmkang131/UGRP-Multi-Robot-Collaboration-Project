"""Carry2 input boundary: authored task start, own commands and own RGB only.

The start is a declared diagnostic condition, not a pose read from setup.
Uncertainty is a development model, not a physical localization certificate.
AMCL is an optional report port; no other worktree/provider is imported here.
"""
from __future__ import annotations

import hashlib
import math

from harness.grasp_act_visible_world import command_delta
from sim.active_lookaround import OwnPose

START_PROFILE = 'solo_carry_task_start_v2'
AMCL_SOURCE = 'own_rgb_static_map_amcl_v1'
START_KEYS = {'profile', 'source', 'pose_m_rad', 'sigma_xy_m', 'sigma_yaw_rad',
              'instruction', 'is_observation'}
MOTION_ERROR = {'translation_fraction': .25, 'rotation_fraction': .25,
                'yaw_rad_per_m': .10, 'max_xy_m': .5, 'max_yaw_rad': math.radians(20.),
                'basis': 'uncalibrated conservative accumulated slip budget; carry4.md',
                'profile': 'correlated_command_error_v1'}


def task_start(static):
    """Fixed task instruction: west of the pickup bay, facing map east.

    Reuses the authored-start-prior principle of owncam_bootstrap_v6b, not
    its dock-row assignment or any scene spawn. E2E own_start alone is not a
    world-map anchor; this explicitly declared start condition supplies one.
    """
    region = static['regions']['pickup']
    x, y = region['center_m']
    hx, _ = region['half_extents_m']
    return {'profile': START_PROFILE, 'source': 'fixed_task_description.static_pickup_west',
            'pose_m_rad': [x-hx-.25, y, 0.], 'sigma_xy_m': .05,
            'sigma_yaw_rad': math.radians(3.),
            'instruction': 'Start 0.25 m west of the static pickup region, at its midline, facing east.',
            'is_observation': False}


class CommandPose:
    def __init__(self, start, *, now=0., robot_id='r1', map_sha256='', amcl_option='off'):
        if amcl_option not in ('off', 'report_v1'):
            raise ValueError('unknown carry AMCL report option')
        if (set(start) != START_KEYS
                or start['profile'] != START_PROFILE
                or start['source'] != 'fixed_task_description.static_pickup_west'):
            raise ValueError('authored task start required; spawn/truth inputs forbidden')
        values = [*start['pose_m_rad'], start['sigma_xy_m'], start['sigma_yaw_rad'], now]
        if (len(start['pose_m_rad']) != 3 or not all(map(math.isfinite, values))
                or min(start['sigma_xy_m'], start['sigma_yaw_rad']) <= 0):
            raise ValueError('finite task prior required')
        self.start = dict(start)
        self.own = OwnPose(start['pose_m_rad'], start['sigma_xy_m'], start['sigma_yaw_rad'])
        self.robot_id, self.map_sha256, self.amcl_option = robot_id, map_sha256, amcl_option
        self.now = self.started = float(now)
        self.last_fix = None  # the task prior is not an RGB fix
        self.last_amcl_t = None
        self.own_frame = None
        self.fixes = 0
        self.distance_since_fix = self.turn_since_fix = 0.
        self.last_dt = None

    @property
    def pose(self):
        return self.own.x.tolist()

    def issue(self, issued, dt):
        if not math.isfinite(dt) or not 0 < dt <= 1.+1e-8:
            raise ValueError('bounded command integration required')
        if abs(float(issued['t'])-self.now) > 1e-6:
            raise ValueError('command integration must follow the actual tick clock')
        dx, dy, da = command_delta(issued, dt)
        self.own.propagate(dx, dy, da, k_trans=0., k_rot=0.)
        self.distance_since_fix += math.hypot(dx, dy)
        self.turn_since_fix += abs(da)
        self.last_dt = float(dt)
        self.now = float(issued['t'])+dt

    def accepted_fix(self, now):
        self.last_fix = float(now)
        self.fixes += 1
        self.distance_since_fix = self.turn_since_fix = 0.

    def observe_own(self, frame, now, *, camera):
        if camera != self.robot_id+'/robot_cam':
            raise ValueError('top RGB forbidden; own camera required (#366)')
        if getattr(frame, 'shape', None) != (480, 640, 3) or str(frame.dtype) != 'uint8':
            raise ValueError('native own RGB array required; top bundles forbidden')
        if not math.isfinite(now) or abs(now-self.now) > .15+1e-8:
            raise ValueError('own RGB timestamp does not match command estimate')
        self.own_frame = {'camera': camera, 't': now, 'sha256': hashlib.sha256(frame.tobytes()).hexdigest()}
        # Seeing an image or matching floor colour is not a metric pose fix.

    def accept_amcl(self, report, now):
        if self.amcl_option == 'off':
            raise ValueError('carry AMCL report port is off')
        required = {'source', 'robot_id', 'map_sha256', 'pose', 'sigma_xy_m',
                    'sigma_yaw_rad', 't', 'age_s'}
        if set(report) != required or report['source'] != AMCL_SOURCE:
            raise ValueError('own RGB AMCL report only; top/truth inputs forbidden')
        if report['robot_id'] != self.robot_id or report['map_sha256'] != self.map_sha256:
            raise ValueError('AMCL robot/map mismatch')
        pose = report['pose']; sx = report['sigma_xy_m']; sa = report['sigma_yaw_rad']
        at, age = report['t'], report['age_s']
        if (len(pose) != 3 or not all(math.isfinite(x) for x in [*pose, sx, sa, at, age, now])
                or abs(now-self.now) > 1e-6 or not 0 <= age <= .25
                or abs(now-at-age) > 1e-6 or not 0 < sx <= .15 or not 0 < sa <= math.radians(10.)
                or (self.last_amcl_t is not None and at <= self.last_amcl_t)):
            raise ValueError('fresh finite low-uncertainty AMCL report required')
        # Reports must describe the current estimate; stale-epoch poses would
        # need command replay. Do not silently drop intervening motion.
        if age > 1e-6:
            raise ValueError('AMCL report must be extrapolated to current command epoch')
        updated = OwnPose(pose, sx, sa)
        self.own.x, self.own.P = updated.x, updated.P  # preserve shared re-look belief
        self.last_amcl_t = at
        self.accepted_fix(at)

    def ready(self, now):
        sigma = self.sigmas()
        return (math.isfinite(now) and -.001 <= now-self.now <= .2+1e-8
                and all(math.isfinite(v) for v in self.pose+sigma)
                and max(sigma[:2]) <= MOTION_ERROR['max_xy_m'] and sigma[2] <= MOTION_ERROR['max_yaw_rad'])

    def sigmas(self):
        base = [math.sqrt(max(0., float(self.own.P[i, i]))) for i in range(3)]
        xy = MOTION_ERROR['translation_fraction']*self.distance_since_fix
        yaw = (MOTION_ERROR['rotation_fraction']*self.turn_since_fix+
               MOTION_ERROR['yaw_rad_per_m']*self.distance_since_fix)
        # Correlated bias grows with total issued motion, not sqrt(tick count).
        # This budget is deliberately NOT described as a calibrated covariance.
        return [base[0]+xy, base[1]+xy, base[2]+yaw]

    def record(self):
        return {'pose_estimate': self.pose, 'source': 'task_start_then_issued_commands_own_rgb_relook',
                'task_start': self.start, 'sigma_m_m_rad': self.sigmas(),
                'estimate_t': self.now, 'last_rgb_fix_t': self.last_fix,
                'rgb_fix_age_s': None if self.last_fix is None else self.now-self.last_fix,
                'command_only_age_s': self.now-(self.started if self.last_fix is None else self.last_fix),
                'rgb_fixes': self.fixes, 'own_frame': self.own_frame,
                'amcl_option': self.amcl_option, 'localization_verified': False,
                'motion_error': MOTION_ERROR, 'last_dt_s': self.last_dt,
                'error_bound_semantics': 'covariance sigma plus correlated command bias; not calibrated sigma',
                'issued_distance_since_fix_m': self.distance_since_fix,
                'issued_turn_since_fix_rad': self.turn_since_fix,
                'uncertainty_calibrated': False, 'top_rgb_control_allowed': False}
