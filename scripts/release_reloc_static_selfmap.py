"""Opt-in release selfmap -> byte-pinned mapbuild7 static CSM API.

Own-map zero is an arbitrary gauge, never a world/spawn pose. Sparse settled
look views may supply command prediction; they do not demonstrate carry LK.
All numerical gates belong to the immutable owner modules, not this adapter.
"""
from collections import Counter

OPTION = 'mapbuild_static_csm_v1'


class StaticReleaseSelfmap:
    def __init__(self, static, calibration, *, method='off', registration='off'):
        if method not in ('off', 'lk', 'rbpf') or registration not in ('off', OPTION):
            raise ValueError('UNKNOWN_RELEASE_SELFMAP_OPTION')
        if method == 'rbpf':
            raise ValueError('RBPF_STATIC_RELEASE_NOT_QUALIFIED')
        self.enabled = method != 'off' and registration == OPTION
        self.method = method
        self.previous = self.servo = self.last_t = None
        self.rows, self.segments, self.origins = [], [], []
        if self.enabled:
            import numpy as np
            from harness.mapbuild_camera import adapters
            from harness.servo_camera_fk import CARRY_OPTION
            from harness.mapbuild_static_registration import StaticRegistration
            from harness.scene_colour_boundary import ColourBoundaryState, RELOC16_OPTION
            self.pair, self.scan = adapters(CARRY_OPTION)
            self.state = ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',
                                            calibration, option=RELOC16_OPTION)
            self.reg = StaticRegistration(static, option=registration)
            self.pose = np.zeros(3)
            self.rbpf = None

    def observe(self, now, rgb, servo, *, command_delta, settled):
        if not self.enabled:
            raise ValueError('EXPLICIT_RELEASE_STATIC_SELFMAP_REQUIRED')
        if self.last_t is not None and now <= self.last_t:
            raise ValueError('CAUSAL_OWN_FRAMES_REQUIRED')
        import numpy as np
        from harness.e2e_rgb_vo import compose, PARAMS
        from harness.self_odom_grid import transform
        servo = {int(k): int(v) for k, v in servo.items()}
        delta = np.asarray(command_delta, float)
        if delta.shape != (3,) or not np.isfinite(delta).all():
            raise ValueError('FINITE_OWN_COMMAND_DELTA_REQUIRED')
        reason = ('bootstrap' if self.previous is None else
                  'unknown_servo_change' if servo != self.servo else
                  'unknown_pair_gap' if now-self.last_t > PARAMS['max_pair_gap_s'] else
                  'unknown_camera_unsettled' if not settled else None)
        flow = dict(status=reason) if reason else self.pair(self.previous, rgb, servo)
        measured = flow['status'] == 'measured'
        self.pose = compose(self.pose, flow['delta'] if measured else delta)
        view = self.scan(rgb, servo, self.state)
        # A settled sparse capture is a scan, not a synthetic adjacent LK pair.
        # Settlement comes from the recorded own-issued servo/wait script.
        admitted = bool(settled)
        if admitted:
            self.segments.extend(transform(s, self.pose).tolist() for s in view['segments'])
            self.origins.extend(transform([view['camera']], self.pose)[0].tolist()
                                for _ in view['segments'])
        row = dict(t=float(now), lk=flow, own_pose=self.pose.tolist(),
                   motion_status='measured_LK' if measured else 'command_prediction',
                   scan_admitted=admitted, wall_segments=len(view['segments']),
                   wall_hit_columns=sum(c['status'] == 'hit' for c in view['columns']),
                   column_reasons=dict(Counter(c['reason'] for c in view['columns'])),
                   truth_inputs=0, held_world_reads=0)
        self.previous, self.servo, self.last_t = rgb, servo, float(now)
        self.rows.append(row)
        return row

    def register(self):
        if not self.enabled:
            raise ValueError('EXPLICIT_RELEASE_STATIC_SELFMAP_REQUIRED')
        # No identity/spawn/previous-legacy-localizer fallback on rejection.
        result = self.reg.register(self.segments, camera_origins=self.origins)
        from harness.e2e_rgb_vo import compose
        anchor = result['static_from_own']
        return dict(registration=result, own_pose=self.pose.tolist(),
                    map_pose=None if anchor is None else compose(anchor, self.pose).tolist(),
                    accepted=anchor is not None, views=len(self.rows),
                    method=self.method, truth_inputs=0,
                    scope='offline component candidate; physical release/carry not qualified')
