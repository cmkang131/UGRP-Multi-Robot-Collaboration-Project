"""Opt-in AMCL4 ablations. No profile is admitted for online control.

Motion thresholds and KLD were already in map_amcl. The principal new saving is
checking that gate BEFORE RGB feature extraction. All frames remain recorded;
command deltas still enter every step. No gain/bias correction is applied.
"""
from dataclasses import replace
import numpy as np

PROFILES = ('off', 'amcl4_motion_v1', 'amcl4_resample2_v1',
            'amcl4_kld250_v1', 'amcl4_features30_v1', 'amcl4_balanced_v1')


def parameters_for(profile):
    from harness.map_amcl import Parameters
    if profile not in PROFILES:
        raise ValueError('UNKNOWN_AMCL4_PROFILE')
    changes = {}
    if profile in ('amcl4_resample2_v1', 'amcl4_balanced_v1'):
        changes['resample_interval'] = 2
    if profile in ('amcl4_kld250_v1', 'amcl4_balanced_v1'):
        changes['min_particles'] = 250
    if profile in ('amcl4_features30_v1', 'amcl4_balanced_v1'):
        changes.update(max_beams=30, max_landmarks=4)
    return replace(Parameters(), **changes)


class RGBPipeline:
    """Saved/own RGB only. Construction and stepping never touch a renderer.

    `off` reproduces eager extraction, even on frames the filter later rejects.
    Other profiles defer extraction until motion/new view AND camera settling.
    Empty observations never consume an epoch. There is no stale feature reuse.
    """
    def __init__(self, static_map, *, profile='off', option='amcl_landmarks_v1', seed=64001):
        from harness.map_amcl import create
        from harness.map_recording_audit import Metrics
        from harness.own_map_amcl_vendor.landmarks import MapFeatures
        from harness.self_map_landmark_sensor import Sensor
        self.metrics = Metrics()
        self.pf = create(static_map, option=option, profile=profile, seed=seed, metrics=self.metrics)
        if self.pf is None:
            raise ValueError('RGB_PIPELINE_REQUIRES_AMCL')
        self.profile = profile
        self.sensor = Sensor(MapFeatures(static_map).hues)
        self.last_servo, self.changed = None, None

    def step(self, *, t, rgb, delta, servo):
        import cv2
        from harness.self_map_closed_loop import own_measurement
        if not np.isfinite(t) or (self.pf.last_t is not None and t <= self.pf.last_t):
            raise ValueError('CAUSAL_FINITE_OWN_PACKET_REQUIRED')
        view = tuple(sorted(servo.items()))
        if view != self.last_servo:
            self.last_servo, self.changed = view, t
        settled = t-self.changed >= .7-1e-9
        due = self.pf.measurement_due(delta, servo)
        points, features = [], []
        with self.metrics.measure('pipeline'):
            if settled and (self.profile == 'off' or due):
                with self.metrics.measure('rgb_features'):
                    measurement = own_measurement(rgb, servo)
                    points = measurement['points']
                    if self.pf.landmark_map is not None:
                        features = self.sensor.measure(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), servo, measurement)
            with self.metrics.measure('filter_other'):
                state = self.pf.step(t=t, points=points, features=features, delta=delta, servo=servo)
        state['amcl4'] = dict(profile=self.profile, settled=settled, measurement_due=due,
            extracted=settled and (self.profile == 'off' or due),
            points_before_limit=len(points), landmarks_before_limit=len(features),
            resampled=state['sensor'] is not None and 'samples_after' in state['sensor'])
        return state
