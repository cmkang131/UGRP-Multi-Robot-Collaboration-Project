"""Explicit, unqualified mapbuild10 long-route diagnostic adapter.

Uses the unchanged MC20 AMCL profile; no simulator/teacher/evaluator inputs.
The coordinator approved one diagnostic round, not production qualification.
"""
import numpy as np
from harness.mapbuild_amcl import StaticAMCL, OPTION
from harness.e2e_rgb_vo import compose, between, fuse
from harness.self_odom_grid import transform


class DiagnosticCorrection:
    def __init__(self, static, calibration, requirements, prior, *, enabled=False, seed=2026101700):
        if not enabled:
            raise ValueError('EXPLICIT_LONG_DIAGNOSTIC_REQUIRED')
        self.amcl = StaticAMCL(static, calibration, requirements, option=OPTION,
            profile='nav2_defaults_v1', seed=seed,
            initial_prior_option='start_zone_prior_v1', initial_prior=prior)
        self.static_from_own = None
        self.frames = []
        self.ledger = []
        self.pose = np.zeros(3)

    @property
    def navigation_ready(self):
        return bool(self.amcl.current and self.amcl.current['converged'])

    def step(self, t, frame_id, command_delta, command_covariance, flow, scan, *, servo):
        if flow.get('status') == 'measured':
            mode = 'replace' if not np.any(command_covariance) else 'fused'
            delta, Q, nis, how = fuse(command_delta, command_covariance,
                flow['delta'], flow['covariance'], mode=mode)
        else:
            delta, Q, nis, how = np.asarray(command_delta), np.asarray(command_covariance), None, 'command_kept'
        event = dict(self.amcl.step(t, frame_id, delta, scan, servo=servo))
        absolute = self.absolute_pose()
        self.pose = self.amcl.odom.copy() if self.static_from_own is None else between(self.static_from_own, absolute)
        # Immutable own-map observations. They NEVER enter the static field.
        inserted = bool(self.amcl.local_map and self.amcl.local_map[-1]['frame_id'] == frame_id)
        if inserted:
            self.frames.append(dict(t=t, frame_id=frame_id, pose=self.pose.tolist(),
                world_segments=transform(np.asarray(scan['segments']).reshape(-1, 2), self.pose).reshape(-1, 2, 2).tolist(),
                source='own_rgb', gauge='diagnostic_registered_own' if self.static_from_own is not None else 'own_odom',
                used_for_localization=False))
        event.update(motion_delta=np.asarray(delta).tolist(), motion_covariance=np.asarray(Q).tolist(),
            fusion=how, nis=nis, accepted=False, inserted=inserted,
            diagnostic_navigation_pose_used=self.static_from_own is not None,
            production_qualified=False, absolute_proposal=absolute.tolist() if absolute is not None else None)
        self.ledger.append(event)
        return self.pose.tolist(), event

    def absolute_pose(self):
        if self.amcl.current is None:
            return None
        return compose(self.amcl.current['candidate_pose'], between(self.amcl.sensor_odom, self.amcl.odom))

    def initialize_static(self):
        if not self.navigation_ready:
            return dict(status='rejected', reason='amcl_distribution_unresolved',
                category='static_amcl', blocked_object='own_observed_wall', minimum_gap_m=None,
                gap_status='not_measured', static_from_own=None, production_qualified=False)
        # One fixed gauge; later AMCL estimates change the own-frame pose.
        if self.static_from_own is None:
            from harness.selfmap_map_correction import inverse
            self.static_from_own = compose(self.absolute_pose(), inverse(self.amcl.odom))
        self.pose = between(self.static_from_own, self.absolute_pose())
        return dict(status='accepted', reason='coordinator_approved_diagnostic_only',
            category='static_amcl', blocked_object='own_observed_wall', minimum_gap_m=None,
            gap_status='not_measured', static_from_own=self.static_from_own.tolist(),
            production_qualified=False, runtime_qualified=False)
