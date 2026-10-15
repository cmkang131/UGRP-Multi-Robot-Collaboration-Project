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
    def __init__(self, start, *, now=0., robot_id='r1', map_sha256='', amcl_option='off', drive_model_deadband_v1=False,
                 carry5_trim_yaw_calibration_v1=False, trim_calibration=None,
                 reloc9_rotation_calibration_v1=False, reloc10_rotation_calibration_v1=False, carry_pose_budget_recal_v1=False, reloc14_carry_budget_v1=False, reloc14_carry_tracking_v1=False, tracking_static=None, reloc15_rgb_heading_v1=False):
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
        from harness.drive_model import CommandDriveModel, validate_options
        validate_options(drive_model_deadband_v1)
        self.drive_model_enabled = drive_model_deadband_v1
        from harness.reloc9_rotation import validate, calibration
        validate(reloc9_rotation_calibration_v1)
        if reloc9_rotation_calibration_v1 and not drive_model_deadband_v1:
            raise ValueError('reloc9 rotation requires shared drive model')
        self.rotation_calibration = calibration() if reloc9_rotation_calibration_v1 else None
        if type(reloc10_rotation_calibration_v1) is not bool:
            raise ValueError('reloc10 rotation must be bool')
        if reloc10_rotation_calibration_v1 and (not drive_model_deadband_v1 or reloc9_rotation_calibration_v1):
            raise ValueError('reloc10 requires drive model and excludes reloc9 gain')
        from harness.reloc10_rotation import calibration as calibration10
        self.rotation10 = calibration10() if reloc10_rotation_calibration_v1 else None
        if type(carry_pose_budget_recal_v1) is not bool or (carry_pose_budget_recal_v1 and self.rotation10 is None):
            raise ValueError('carry pose recal requires reloc10 rotation')
        if type(reloc14_carry_budget_v1) is not bool or (reloc14_carry_budget_v1 and self.rotation10 is None):
            raise ValueError("reloc14 budget requires calibrated rotation")
        self.budget14 = reloc14_carry_budget_v1
        if self.budget14:
            import json
            from pathlib import Path
            self.drift_fit = json.loads((Path(__file__).resolve().parents[1]/"configs/calibration/reloc14_carry_budget_v1.json").read_text())
        self.budget_recal = carry_pose_budget_recal_v1
        if self.budget_recal:
            import json
            from pathlib import Path
            self.budget_fit = json.loads((Path(__file__).resolve().parents[1]/'configs/calibration/reloc13_carry_budget_v1.json').read_text())
        if type(carry5_trim_yaw_calibration_v1) is not bool:
            raise ValueError('carry5_trim_yaw_calibration_v1 must be bool')
        self.trim_calibration = None
        if carry5_trim_yaw_calibration_v1:
            from sim.solo_carry6 import validate_calibration
            if not drive_model_deadband_v1:
                raise ValueError('trim calibration requires its shared drive model')
            validate_calibration(trim_calibration)
            self.trim_calibration = dict(trim_calibration)
        self.partial_epoch = None
        self.drive_model = CommandDriveModel() if drive_model_deadband_v1 else None
        self.last_delta = None
        self.last_command_key = None
        self.start = dict(start)
        self.own = OwnPose(start['pose_m_rad'], start['sigma_xy_m'], start['sigma_yaw_rad'])
        self.robot_id, self.map_sha256, self.amcl_option = robot_id, map_sha256, amcl_option
        self.now = self.started = float(now)
        self.last_fix = None  # the task prior is not an RGB fix
        self.last_amcl_t = None
        self.own_frame = None
        self.fixes = 0
        self.distance_since_fix = self.turn_since_fix = 0.
        self.tracker = None
        if type(reloc14_carry_tracking_v1) is not bool:
            raise ValueError("carry tracking toggle must be bool")
        if reloc14_carry_tracking_v1:
            from sim.reloc14_carry_tracking import CarryTracker
            self.tracker = CarryTracker(tracking_static,start)
        if type(reloc15_rgb_heading_v1) is not bool:
            raise ValueError('heading toggle must be bool')
        self.heading = None
        if reloc15_rgb_heading_v1:
            from harness.reloc15_heading import Heading
            self.heading = Heading()
        self.last_dt = None

    @property
    def pose(self):
        return self.own.x.tolist()

    def issue(self, issued, dt):
        if not math.isfinite(dt) or not 0 < dt <= 1.+1e-8:
            raise ValueError('bounded command integration required')
        if abs(float(issued['t'])-self.now) > 1e-6:
            raise ValueError('command integration must follow the actual tick clock')
        dx, dy, da = command_delta(issued, dt, drive_model_deadband_v1=self.drive_model_enabled, model=self.drive_model)
        if self.rotation_calibration is not None:
            from harness.reloc9_rotation import corrected_delta
            dx, dy, da = corrected_delta(issued, (dx, dy, da), self.rotation_calibration)
        if self.rotation10 is not None:
            from harness.reloc10_rotation import corrected_delta as corrected10
            dx, dy, da = corrected10(issued, (dx, dy, da), self.rotation10)
        if self.trim_calibration is not None:
            from sim.solo_carry6 import calibrated_trim_delta
            dx, dy, da = calibrated_trim_delta(issued, (dx, dy, da), self.trim_calibration)
        if self.tracker is not None:
            self.tracker.issue(issued,(dx,dy,da))
        if self.heading is not None:
            self.heading.issue(issued,(dx,dy,da))
        self.last_delta = (dx, dy, da)
        self.last_command_key = self.command_key(issued, dt)
        self.own.propagate(dx, dy, da, k_trans=0., k_rot=0.)
        self.distance_since_fix += math.hypot(dx, dy)
        self.turn_since_fix += abs(da)
        self.last_dt = float(dt)
        self.now = float(issued['t'])+dt

    @staticmethod
    def command_key(issued, dt):
        return (float(issued['t']), tuple(issued['wheels']), tuple(issued['duration_s']), float(dt))

    def cached_delta(self, issued, dt):
        """One stateful integration per tick, shared by all carry consumers."""
        if dt == 0:
            return (0., 0., 0.)
        key = self.command_key(issued, dt)
        if (self.last_command_key is None or key[:3] != self.last_command_key[:3]
                or abs(key[3]-self.last_command_key[3]) > 1e-8):
            raise ValueError('carry command delta must be integrated once before consumption')
        return self.last_delta

    def propagate_point(self, point, issued, dt):
        dx, dy, yaw = self.cached_delta(issued, dt)
        x, y, z = point; x -= dx; y -= dy
        c, s = math.cos(yaw), math.sin(yaw)
        return [c*x+s*y, -s*x+c*y, z]

    def accepted_fix(self, now):
        self.partial_epoch = None
        self.last_fix = float(now)
        self.fixes += 1
        self.distance_since_fix = self.turn_since_fix = 0.

    def partial_fix(self):
        # The posterior already includes the command budget. Keep its null
        # variance; start adding NEW command uncertainty without a full fix.
        self.partial_epoch = (self.distance_since_fix, self.turn_since_fix)

    def observe_own(self, frame, now, *, camera):
        if camera != self.robot_id+'/robot_cam':
            raise ValueError('top RGB forbidden; own camera required (#366)')
        if getattr(frame, 'shape', None) != (480, 640, 3) or str(frame.dtype) != 'uint8':
            raise ValueError('native own RGB array required; top bundles forbidden')
        if not math.isfinite(now) or abs(now-self.now) > .15+1e-8:
            raise ValueError('own RGB timestamp does not match command estimate')
        self.own_frame = {'camera': camera, 't': now, 'sha256': hashlib.sha256(frame.tobytes()).hexdigest()}
        if self.tracker is not None:
            # Existing carry observe_own port receives OpenCV BGR from the JPEG
            # decoder. selfmap's detector accepts RGB: convert exactly once.
            fix=self.tracker.observe(frame[...,::-1].copy(),now)
            if fix is not None:
                self.own.x,self.own.P=fix
                self.accepted_fix(now)
        if self.heading is not None:
            self.heading.observe(frame[...,::-1].copy(),now,self.own)
        # A captured image alone is not a metric fix; only admitted PF updates reset the epoch.

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
                and max(sigma[:2]) <= MOTION_ERROR['max_xy_m'] and sigma[2] <= self.yaw_budget_limit())

    def yaw_budget_limit(self):
        # A correlated command envelope is not actual angular error. The 41deg
        # trigger is replay-fitted (578/578 >=20deg errors), not a 41deg task tolerance.
        if self.budget14:
            return MOTION_ERROR['max_yaw_rad']  # 20deg existing carry task criterion, not a fitted 41deg trigger.
        return math.radians(self.budget_fit['yaw_trigger_deg']) if self.budget_recal else MOTION_ERROR['max_yaw_rad']

    def sigmas(self):
        base = [math.sqrt(max(0., float(self.own.P[i, i]))) for i in range(3)]
        distance, turn = self.distance_since_fix, self.turn_since_fix
        if self.partial_epoch is not None:
            distance -= self.partial_epoch[0]; turn -= self.partial_epoch[1]
        if self.budget14:
            # reloc14 carry-budget-fit: NN nonnegative upper envelope over ALL
            # phases of 93266 (including re-search); 93315 held out. Coefficients
            # and raw hashes are in config. It is an error envelope, not sigma.
            features = [1.,distance,turn,self.now-(self.started if self.last_fix is None else self.last_fix)]
            def bound(name):
                return sum(x*c for x,c in zip(features,self.drift_fit['fits'][name]['coefficients']))
            xy=max(max(base[:2]),bound('xy_m'))
            return [xy,xy,max(base[2],math.radians(bound('yaw_deg')))]
        xy = MOTION_ERROR['translation_fraction']*distance
        fitted_rotation = self.rotation10 or self.rotation_calibration
        fraction = (max(.40, fitted_rotation['residual_rotation_fraction'])
                    if fitted_rotation is not None else MOTION_ERROR['rotation_fraction'])
        if self.budget_recal:
            fraction = self.budget_fit['rotation_fraction']
        yaw = (fraction*turn+
               MOTION_ERROR['yaw_rad_per_m']*distance)
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
                'motion_error': MOTION_ERROR,
                'carry_pose_budget_recal_v1': self.budget_recal,
                'reloc14_carry_budget_v1': self.budget14,
                **({'reloc15_heading':self.heading.last} if self.heading is not None else {}),
                **({'reloc14_tracking':self.tracker.last} if self.tracker is not None else {}),
                'budget_limits': {'yaw_rad': self.yaw_budget_limit(), 'xy_m': MOTION_ERROR['max_xy_m']}, 'last_dt_s': self.last_dt,
                'error_bound_semantics': 'covariance sigma plus correlated command bias; not calibrated sigma',
                'issued_distance_since_fix_m': self.distance_since_fix,
                'issued_turn_since_fix_rad': self.turn_since_fix,
                'uncertainty_calibrated': False, 'top_rgb_control_allowed': False,
                **({'reloc9_rotation_calibration_v1': True, 'rotation_calibration': {
                    k:self.rotation_calibration[k] for k in ('schema','yaw_scale','drive_model_sha256','method')},
                    'rotation_error_fraction': max(.40, self.rotation_calibration['residual_rotation_fraction'])}
                   if self.rotation_calibration is not None else {}),
                **({'reloc10_rotation_calibration_v1': True, 'rotation_calibration': self.rotation10,
                    'rotation_error_fraction': self.budget_fit['rotation_fraction'] if self.budget_recal else max(.40, self.rotation10['residual_rotation_fraction'])}
                   if self.rotation10 is not None else {}),
                **({'carry5_trim_yaw_calibration_v1': True, 'trim_calibration': self.trim_calibration}
                   if self.trim_calibration is not None else {}),
                **({'partial_budget_epoch': list(self.partial_epoch), 'partial_is_full_fix': False}
                   if self.partial_epoch is not None else {}),
                **({'drive_model_deadband_v1': True, 'drive_model': 'shared v7 relay and confirmed damping',
                    'budget_epoch_t': self.started if self.last_fix is None else self.last_fix}
                   if self.drive_model_enabled else {})}
