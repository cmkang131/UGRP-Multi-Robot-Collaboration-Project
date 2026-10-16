"""Default-off release adapter for byte-pinned mapbuild observations.

This adapter never substitutes the old floor-line localizer. Static-map
acquisition and loaded-camera qualification belong to mapbuild6; until those
owner APIs are qualified, observations cannot authorize a release correction.
Inputs are own RGB, issued servo/relative motion, and an authored static map.
"""
from collections import Counter

OPTION = 'release_reloc_selfmap_v1'
METHODS = ('off', 'lk', 'rbpf')


class ReleaseSelfmap:
    def __init__(self, static, calibration, *, method='off'):
        if method not in METHODS:
            raise ValueError('UNKNOWN_RELEASE_SELFMAP_METHOD')
        self.method, self.static = method, static
        self.previous, self.last_servo, self.last_t = None, None, None
        self.rows, self.pose, self.rbpf = [], None, None
        if method != 'off':
            import numpy as np
            from harness.scene_colour_boundary import ColourBoundaryState, RELOC16_OPTION
            self.state = ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',
                                            calibration, option=RELOC16_OPTION)
            self.pose = np.zeros(3)

    def observe(self, now, rgb, servo, *, command_delta=None, command_covariance=None):
        if self.method == 'off':
            raise ValueError('EXPLICIT_RELEASE_SELFMAP_REQUIRED')
        import cv2
        import numpy as np
        from harness.servo_camera_fk import transform_from_commands
        from harness.e2e_rgb_vo import ground_pair, image_mask, compose, PARAMS
        from harness.mapbuild_rbpf import virtual_scan, MapbuildRBPF, OPTION as RBPF
        if self.last_t is not None and now <= self.last_t:
            raise ValueError('CAUSAL_OWN_FRAMES_REQUIRED')
        servo = {int(k): int(v) for k, v in servo.items()}
        camera, reason = transform_from_commands(servo, camera_pose='servo_fk_v1')
        row = dict(t=float(now), method=self.method, camera_qualified=camera is not None,
                   camera_reason=reason, floor_features=None, wall_hit_columns=0,
                   wall_segments=0, truth_inputs=0, held_world_reads=0)
        flow = dict(status='bootstrap')
        if camera is None:
            flow = dict(status='unknown_' + reason)
            row['column_reasons'] = {reason: 96}  # pinned mapbuild virtual scan width
        else:
            mask = image_mask(rgb, servo)
            pts = cv2.goodFeaturesToTrack(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY),
                maxCorners=PARAMS['max_corners'], qualityLevel=PARAMS['quality'],
                minDistance=PARAMS['min_distance_px'], mask=mask, blockSize=7)
            row['floor_features'] = 0 if pts is None else len(pts)
            scan = virtual_scan(rgb, servo, self.state)
            row.update(wall_hit_columns=sum(c['status'] == 'hit' for c in scan['columns']),
                       wall_segments=len(scan['segments']),
                       column_reasons=dict(Counter(c['reason'] for c in scan['columns'])),
                       wall_work=scan['work'])
            if self.previous is not None:
                if servo != self.last_servo:
                    flow = dict(status='unknown_servo_change')
                elif now-self.last_t > PARAMS['max_pair_gap_s']:
                    flow = dict(status='unknown_pair_gap')
                else:
                    flow = ground_pair(self.previous, rgb, servo)
            delta = flow.get('delta', command_delta)
            cov = flow.get('covariance', command_covariance)
            if self.method == 'rbpf' and delta is not None and cov is not None:
                if self.rbpf is None:
                    self.rbpf = MapbuildRBPF(servo, option=RBPF)
                # Match only a stable issued-camera interval, as mapbuild6.
                if self.last_servo is not None and servo != self.last_servo:
                    scan = {**scan, 'segments': [], 'features': []}
                row['rbpf_relative_pose'], row['rbpf_event'] = self.rbpf.step(
                    now, len(self.rows), delta, cov, scan)
        delta = flow.get('delta', command_delta)
        if delta is not None:
            self.pose = compose(self.pose, delta)
        row.update(lk=flow, lk_relative_pose=self.pose.tolist(),
                   map_pose=None, map_correction_accepted=False,
                   map_reason='owner_static_map_acquisition_api_pending',
                   motion_status='measured_LK' if flow['status'] == 'measured' else
                                 'command_prediction' if command_delta is not None else 'unknown')
        self.previous, self.last_servo, self.last_t = rgb, servo, float(now)
        self.rows.append(row)
        return row

    def decision(self):
        return dict(accepted=False, reason='owner_static_map_acquisition_api_pending',
                    map_pose=None, method=self.method, views=len(self.rows),
                    scope='component observations only; no map correction or gate admission')
