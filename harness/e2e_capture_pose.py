"""Local visual-servo capture after staging, with optional coarse pan tracking.

Docking approaches its staging pose before invoking a local visual controller.
Pan tracking uses the current own-RGB grip and existing calibrated arm model;
it never changes camera placement, motor primitives or grasp tolerances.
"""
from types import MethodType
import copy

OPTIONS = ('pose08_v1', 'pose08_track_v1', 'pose12_track_v1')
VERSIONS = dict(zip(OPTIONS, (272, 273, 274)))
RADII = dict(zip(OPTIONS, (.08, .08, .12)))
PARAMS = dict(pan_change_min_us=24, fresh_grasp_required=True,
              final_tolerances_unchanged=True, stationary_camera_update=True)


def parameters(option):
    return dict(PARAMS, capture_station_radius_m=RADII[option],
                coarse_pan_tracking=option != 'pose08_v1')


def radius(tr, original):
    option = getattr(tr, 'capture_pose', 'off')
    if option == 'off':
        return original
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_CAPTURE_POSE')
    return min(original, RADII[option])


def admit(tr, distance):
    if getattr(tr, 'capture_pose', 'off') == 'off':
        return True
    return distance <= radius(tr, float('inf'))


def install(tr, option):
    if option == 'off':
        return
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_CAPTURE_POSE')
    tr.capture_pose = option
    if option == 'pose08_v1':
        return
    from harness.zone_s3_coarse_fine import PARAMS as SERVO_PARAMS
    for servo in tr.align.values():
        original = servo.observe
        def tracked(self, now, obs, commanded, grip, heading, _original=original):
            if self.gate.ready(now, obs) and obs['frame_id'] != self.last_frame:
                plan = self.planner(grip, heading, self.rid)
                if not plan['ready'] and abs(plan['pan']-commanded[6]) >= PARAMS['pan_change_min_us']:
                    self.last_frame = obs['frame_id']
                    self.streak = 0
                    self.gate.until = now+SERVO_PARAMS['pan_move_s']+SERVO_PARAMS['settle_s']
                    self.gate.frame_id = obs['frame_id']
                    state = tr.approach.setdefault(self.rid, {})
                    state['gaze_settle_until'] = max(state.get('gaze_settle_until', -1.), self.gate.until)
                    self.audit.append(dict(t=now, frame_id=obs['frame_id'], sha256=obs.get('sha256'),
                        grip=list(grip), heading=heading, plan=copy.deepcopy(plan),
                        phase='coarse_track_pan', source='fresh_own_rgb_grip_geometry',
                        aligned_receipt=False))
                    return 'pan', plan['pan']
            return _original(now, obs, commanded, grip, heading)
        servo.observe = MethodType(tracked, servo)


def compose(bundle, option):
    if option == 'off':
        return ()
    if option not in OPTIONS or bundle['execution_bundle_id'] != 'e2e18-v271':
        raise ValueError('CAPTURE_POSE_REQUIRES_V271')
    version = VERSIONS[option]
    bundle['e2e_options']['capture_pose'] = option
    bundle['capture_pose_parameters'] = parameters(option)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
