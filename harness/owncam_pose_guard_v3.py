"""Memory v3 pose confidence: own commands + measurement consistency, never truth.

The guard inflates reports, not the frozen PF or its particles. The interim adapter
uses the PF's pre-reset per-feature likelihood and prior/posterior innovation.
A future vision source must supply the same scalar evidence contract explicitly.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from harness.owncam_pose_source import OwnCamPoseSource
from harness.wall_tags import observed_tag_in_camera

FIX_MAX_AGE_S = 8.
FIX_MAX_TRAVEL_M = .12
EVIDENCE_MAX_AGE_S = 8.
MIN_GOOD_FRAMES = 2
MAX_NIS = 11.345  # chi-square(3), 99%; approximate diagnostic, not calibrated coverage
MIN_LOG_LIKELIHOOD = -6.
UNTRUSTED_XY_M = .12
UNTRUSTED_YAW_RAD = math.radians(8.)
CONFIG = {k: v for k, v in dict(globals()).items() if k.isupper() and isinstance(v, (int, float))}


class PoseGuardV3:
    def __init__(self):
        self.command_travel_m = 0.
        self.pose_travel_m = 0.
        self.command_t = 0.
        self.expires = 0.
        self.speed = 0.
        self.last_xy = None
        self.last_pose_t = None
        self.last_evidence_t = None
        self.last_frame = -1
        self.good_times = []
        self.evidence = None

    def advance(self, now):
        if not math.isfinite(now) or now < self.command_t:
            raise ValueError('non-monotonic command clock')
        self.command_travel_m += self.speed * max(0., min(now, self.expires) - self.command_t)
        self.command_t = float(now)

    def on_command(self, row, motion):
        self.advance(float(row['t']))
        if row['kind'] in ('mecanum', 'drive'):
            u = np.array([row['forward'], row.get('left', 0.), row['turn']], float)
            duration = float(row['duration_s'])
            if not np.isfinite(u).all() or not math.isfinite(duration) or duration < 0:
                raise ValueError('invalid issued drive command')
            velocity = np.asarray(motion['gain'], float) @ u
            self.speed = float(np.linalg.norm(velocity[:2]))
            self.expires = self.command_t + duration
        elif row['kind'] not in ('arm', 'look', 'initial_servo_command'):
            self.speed, self.expires = 0., self.command_t

    def observe_pose(self, report):
        if not report.initialized:
            return
        xy = np.array([report.x_m, report.y_m], float)
        if not np.isfinite(xy).all():
            return
        if self.last_pose_t is not None and report.t_est <= self.last_pose_t:
            return
        if self.last_xy is not None:
            self.pose_travel_m += float(np.linalg.norm(xy - self.last_xy))
        self.last_xy, self.last_pose_t = xy, float(report.t_est)

    def observe_evidence(self, now, frame_id, *, nis, log_likelihood, settled):
        """One own image's evidence. Duplicate frames cannot build confidence."""
        if not math.isfinite(now) or frame_id <= self.last_frame or (
                self.last_evidence_t is not None and now <= self.last_evidence_t):
            raise ValueError('non-monotonic pose evidence')
        self.last_frame = int(frame_id)
        self.last_evidence_t = float(now)
        good = (settled and nis is not None and log_likelihood is not None
                and math.isfinite(nis) and math.isfinite(log_likelihood)
                and 0 <= nis <= MAX_NIS and MIN_LOG_LIKELIHOOD <= log_likelihood <= 0)
        if good:
            if self.good_times and now - self.good_times[-1] > EVIDENCE_MAX_AGE_S:
                self.good_times = []
            self.good_times = (self.good_times + [float(now)])[-MIN_GOOD_FRAMES:]
        elif settled and (nis is not None or log_likelihood is not None):
            self.good_times = []  # arm motion / no feature is not contradiction
        self.evidence = {'t': float(now), 'frame_id': int(frame_id), 'nis': nis,
                         'log_likelihood': log_likelihood, 'settled': bool(settled), 'good': bool(good)}

    def consistent(self, now, since=None):
        return (len(self.good_times) >= MIN_GOOD_FRAMES
                and -1e-8 <= now - self.good_times[-1] <= EVIDENCE_MAX_AGE_S + 1e-8
                and (since is None or self.good_times[0] >= since - 1e-8))

    def effective_estimate(self, est, now):
        if not est.get('initialized'):
            return dict(est)
        out = dict(est)
        cov = np.asarray(est['cov'], float).copy().reshape(3, 3)
        if not self.consistent(now):
            # Never let small reported spread erase contradictory/missing evidence.
            # A floor makes this idempotent when a guarded report reaches memory.
            extra_xy = max(0., UNTRUSTED_XY_M**2 - cov[0, 0] - cov[1, 1])/2
            extra_yaw = max(0., UNTRUSTED_YAW_RAD**2 - cov[2, 2])
            cov += np.diag([extra_xy, extra_xy, extra_yaw])
        out['cov'] = cov.tolist()
        out['std_xy_m'] = max(float(est['std_xy_m']), math.sqrt(max(float(cov[0, 0] + cov[1, 1]), 0.)))
        out['std_yaw_rad'] = max(float(est['std_yaw_rad']), math.sqrt(max(float(cov[2, 2]), 0.)))
        return out

    def effective_report(self, report, now):
        if not report.initialized:
            return report
        est = self.effective_estimate({'initialized': True, 'cov': report.cov,
                                      'std_xy_m': report.std_xy_m, 'std_yaw_rad': report.std_yaw_rad}, now)
        return replace(report, cov=tuple(map(tuple, est['cov'])), std_xy_m=est['std_xy_m'],
                       std_yaw_rad=est['std_yaw_rad'])

    def stamp(self):
        return {'command_travel_m': self.command_travel_m, 'pose_travel_m': self.pose_travel_m}

    def travel_since(self, stamp):
        return max(self.command_travel_m - stamp['command_travel_m'],
                   self.pose_travel_m - stamp['pose_travel_m'])


class GuardedLocalizerV3:
    """Driver read facade. Commands still go to the shared PF once."""
    def __init__(self, loc, guard):
        self.inner, self.guard = loc, guard

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def estimate(self):
        return self.guard.effective_estimate(self.inner.estimate(), self.inner.t)


class OwnCamPoseSourceV3(OwnCamPoseSource):
    def __init__(self, *args, guard, **kwargs):
        self.guard = guard
        super().__init__(*args, **kwargs)

    def on_command(self, row):
        self.guard.on_command(row, self.loc._motion_params())
        super().on_command(row)

    def on_frame(self, now, rgb):
        self.guard.advance(now)
        self.loc.predict_to(now)
        prior = self.loc.estimate()
        # Use the inherited detector/update path, but get the raw report below.
        super().on_frame(now, rgb)
        raw = OwnCamPoseSource.report(self, now)
        self.last_raw_report = raw
        self.guard.observe_pose(raw)
        current = self.loc.estimate()
        measured = self.loc.last_tag_t is not None and abs(self.loc.last_tag_t - now) < 1e-8
        nis, ll = None, None
        if measured:
            # The PF saves likelihood BEFORE sensor resetting: a reset cannot hide
            # inconsistency behind a compact posterior cloud in the same frame.
            dets = getattr(self.detector, 'last', ())
            max_range = self.params['measurement'].get('max_range_m')
            usable = [d for d in dets if int(d['id']) in self.loc.tags and d.get('solutions')
                      and (not max_range or np.linalg.norm(observed_tag_in_camera(d)[0]) <= max_range)]
            count = len(usable)
            if count and self.loc.last_best_loglik is not None:
                temper = self.params['measurement'].get('tag_temper', 0.)
                ll = float(self.loc.last_best_loglik) / count**(1. - temper)
            if prior.get('initialized') and current.get('initialized'):
                delta = np.array([current['x'] - prior['x'], current['y'] - prior['y'],
                                  math.atan2(math.sin(current['yaw'] - prior['yaw']),
                                             math.cos(current['yaw'] - prior['yaw']))])
                cov = np.asarray(prior['cov']) + np.diag([.01**2, .01**2, math.radians(1.)**2])
                nis = float(delta @ np.linalg.solve(cov, delta))
        self.guard.observe_evidence(now, self.frames, nis=nis, log_likelihood=ll,
                                    settled=now - self.loc.last_servo_cmd_t >= .3)
        return self.guard.effective_report(raw, now)

    def report(self, now):
        return self.guard.effective_report(super().report(now), now)
