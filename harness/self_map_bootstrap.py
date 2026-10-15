"""Opt-in bounded command-prior bootstrap; the frozen PR496 core stays intact.

Metric floor intersections already supply scale. A small initial descriptor bank
must not be an absorbing state. Add new own observations at a bounded predicted
pose, without calling that prediction a visual measurement. Correspondences to
such a bank are correlated: retain propagated uncertainty rather than resetting
it to the conditional least-squares residual covariance.
"""
import numpy as np

from harness.natural_floor_slam import NaturalFloorSLAM, _motion_covariance

OPTION = 'command_prior_v1'


class PriorBootstrapSLAM(NaturalFloorSLAM):
    def __init__(self, robot_id, *, max_sigma_xy_m, max_sigma_yaw_rad):
        super().__init__(robot_id)
        self.max_sigma_xy_m = max_sigma_xy_m
        self.max_sigma_yaw_rad = max_sigma_yaw_rad
        self.prior_landmark_ids = set()

    def step(self, observation, *, command_delta, command_covariance):
        predicted_cov = _motion_covariance(self.pose, np.asarray(command_delta),
                                           self.covariance, np.asarray(command_covariance))
        event = super().step(observation, command_delta=command_delta,
                             command_covariance=command_covariance)
        if event['status'] in ('visual_update', 'visual_relocalized'):
            # Conservative retained envelope, NOT a calibrated posterior or an
            # independence claim for repeated observations of prior-seeded points.
            self.covariance = predicted_cov + self.covariance
            event['covariance'] = self.covariance.tolist()
            self.trajectory[-1]['covariance'] = self.covariance.tolist()
        bounded = (np.linalg.eigvalsh(self.covariance[:2, :2]).max() <= self.max_sigma_xy_m**2
                   and self.covariance[2, 2] <= self.max_sigma_yaw_rad**2)
        added = 0
        if event['status'] == 'command_only' and bounded:
            points, descriptors = observation.checked()
            previous = set(self.landmarks)
            added = self._add_landmarks(points, descriptors, self.pose, observation.frame_id, set())
            self.prior_landmark_ids.update(set(self.landmarks)-previous)
        event.update(prior_landmarks_added=added, landmark_count=len(self.landmarks),
                     uncertainty_model='retained_command_plus_fit_envelope',
                     prior_landmark_count=len(self.prior_landmark_ids))
        return event

    def snapshot(self, **kwargs):
        result = super().snapshot(**kwargs)
        result.update(bootstrap=OPTION, prior_landmark_ids=sorted(self.prior_landmark_ids),
                      uncertainty_model='retained_command_plus_fit_envelope')
        return result
