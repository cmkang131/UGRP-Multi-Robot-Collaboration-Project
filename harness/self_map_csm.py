"""Opt-in own-map local CSM (Olson 2009), never a static/peer/GT localizer.

Frozen settings/provenance: ego-wall-map-probe README section 17. Short, immutable
keyframes precede each query. Rejected scans cannot write the map. No past pose
is edited: the source ledger is sufficient to rebuild every inserted grid cell.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np
from scipy.ndimage import distance_transform_edt, map_coordinates

from harness.self_odom_grid import CommandOdometry, OdomGrid, motion_profiles, transform


@dataclass(frozen=True)
class CSMOptions:
    field_resolution_m: float = .05
    translation_window_m: float = .50
    yaw_window_deg: float = 8.
    yaw_step_deg: float = 1.
    submap_age_s: float = 15.
    submap_radius_m: float = 6.
    submap_keyframes: int = 12
    keyframe_interval_s: float = 1.
    min_points: int = 6
    min_overlap: float = .60
    overlap_distance_m: float = .20
    max_residual_m: float = .15
    mode_distance_m: float = .15
    mode_gap: float = .50
    hessian_ratio: float = .03
    effective_points: float = 12.
    calibration_floor_m: float = .08
    pixel_sigma: float = 2.
    focal_y_px: float = 622.1654884818748
    height_lower_bound_m: float = .15
    covariance_floor_xy_m: float = .10
    covariance_floor_yaw_deg: float = 2.
    loaded_unexplained_xy_m_sqrt_s: float = .02

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError('INVALID_CSM_OPTION: '+key)
        if self.min_overlap > 1 or self.hessian_ratio >= 1:
            raise ValueError('INVALID_CSM_RATIO')
        if any(not isinstance(v, int) for v in (self.min_points, self.submap_keyframes)):
            raise ValueError('INVALID_CSM_COUNT')
        # Bound the exhaustive search and preserve separate mode resolution.
        if self.translation_window_m / self.field_resolution_m > 40 or \
                self.yaw_window_deg / self.yaw_step_deg > 40 or \
                self.mode_distance_m < 2*self.field_resolution_m:
            raise ValueError('INVALID_CSM_SEARCH_SIZE')

    def floor(self):
        return np.diag([self.covariance_floor_xy_m**2]*2 +
                       [math.radians(self.covariance_floor_yaw_deg)**2])


class UncertainCommandOdometry(CommandOdometry):
    """Same mean predictor; analytic covariance only, no sampled particles/MCL.

    M1 velocity noise and scale_std are retained for uncertainty. Velocity noise
    contributes (std*dt)^2 at the original 50 ms cadence. Scale error is treated
    as a 1 s correlated rate process; loaded unexplained motion is an explicit
    conservative design floor, not a fitted or measured partner motion.
    """
    def __init__(self, start_time=0., profiles=None, options=None):
        super().__init__(start_time, profiles)
        self.options = options or CSMOptions()
        self.profiles = motion_profiles() if profiles is None else profiles
        self.covariance = self.options.floor()

    def advance(self, t):
        t = float(t)
        if not math.isfinite(t) or t < self.t-1e-8:
            raise ValueError('SELF_MAP_NON_MONOTONIC_TIME')
        while self.t < t-1e-9:
            before = np.asarray(self.pose)
            begin = self.t
            end = min(t, begin+.05)
            expiry = self._predictor.cmd_expires
            if begin < expiry < end:
                end = expiry
            super().advance(end)
            dt = self.t-begin
            dx, dy = np.asarray(self.pose)[:2]-before[:2]
            F = np.eye(3)
            F[:2, 2] = [-dy, dx]
            c, s = math.cos(before[2]), math.sin(before[2])
            R = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
            profile = self.profiles.get('motion_loaded', self.profiles['motion']) if self.loaded else self.profiles['motion']
            velocity = np.abs(self._predictor.vel)
            std = np.asarray(profile.get('noise_rel', [0., 0., 0.]))*velocity + profile.get('noise_abs', [0., 0., 0.])
            variance = (std*dt)**2 + (profile.get('scale_std', 0.)*velocity)**2*dt
            if self.loaded:
                variance[:2] += self.options.loaded_unexplained_xy_m_sqrt_s**2*dt
            self.covariance = F@self.covariance@F.T + R@np.diag(variance)@R.T
        super().advance(t)
        return self.pose

    def correct(self, pose, covariance):
        self._predictor.px[0] = pose
        self._predictor.px[0, 2] = (pose[2]+math.pi) % (2*math.pi)-math.pi
        self.covariance = np.asarray(covariance).copy()


def sample_segments(segments, spacing=.10):
    parts = [np.linspace(a, b, max(2, int(math.ceil(np.linalg.norm(b-a)/spacing))+1))
             for a, b in np.asarray(segments).reshape(-1, 2, 2) if np.linalg.norm(b-a) > 1e-6]
    if not parts:
        return np.empty((0, 2))
    points = np.vstack(parts)
    # One contribution per sensor cell; long/densely sampled faces cannot create
    # arbitrary information. We additionally cap effective sample count in cost.
    _, idx = np.unique(np.floor(points/spacing).astype(int), axis=0, return_index=True)
    return points[np.sort(idx)]


class DistanceField:
    """Frozen past own segments -> EDT table; segment normals for observability."""
    def __init__(self, segments, resolution, margin):
        self.segments = np.asarray(segments).reshape(-1, 2, 2)
        self.resolution = resolution
        points = sample_segments(self.segments, resolution/2)
        self.origin = np.floor((points.min(0)-margin)/resolution)*resolution
        size = np.ceil((points.max(0)+margin-self.origin)/resolution).astype(int)+1
        grid = np.ones(tuple(size), bool)
        indices = np.rint((points-self.origin)/resolution).astype(int)
        grid[indices[:, 0], indices[:, 1]] = False
        self.distance = distance_transform_edt(grid)*resolution

    def query(self, points):
        shape = points.shape[:-1]
        ij = ((points.reshape(-1, 2)-self.origin)/self.resolution).T
        return map_coordinates(self.distance, ij, order=1, mode='constant', cval=10.).reshape(shape)

    def information(self, points, relative_points, sigmas, max_distance, effective_points):
        a, b = self.segments[:, 0], self.segments[:, 1]
        v = b-a
        length = np.linalg.norm(v, axis=1)
        direction = v/np.maximum(length[:, None], 1e-9)
        along = np.einsum('psi,si->ps', points[:, None, :]-a, direction)
        foot = a+np.clip(along, 0, length)[..., None]*direction
        distances = np.linalg.norm(points[:, None, :]-foot, axis=2)
        nearest = distances.argmin(1)
        d = distances[np.arange(len(points)), nearest]
        n = direction[nearest][:, ::-1]*[-1., 1.]
        # Endpoint correspondence cannot make translation along a wall observable.
        jac = np.column_stack([n, np.sum(n*relative_points[:, ::-1]*[-1., 1.], axis=1)])
        weight = (d <= max_distance).astype(float)/sigmas**2
        weight *= min(1., effective_points/len(points))
        return jac.T@(weight[:, None]*jac)


class CorrelativeMatcher:
    def __init__(self, options=None):
        self.options = options or CSMOptions()

    def match(self, pose, covariance, points, camera, reference, anchor_covariance):
        o = self.options
        pose, points, covariance = np.asarray(pose), np.asarray(points), np.asarray(covariance)
        radii = np.linalg.norm(points-camera, axis=1)
        sigma = np.sqrt(o.calibration_floor_m**2 + o.field_resolution_m**2/12 +
                        (o.pixel_sigma*radii**2/(o.focal_y_px*o.height_lower_bound_m))**2)
        step = np.array([o.field_resolution_m, o.field_resolution_m, math.radians(o.yaw_step_deg)])
        limits = np.array([o.translation_window_m]*2 + [math.radians(o.yaw_window_deg)])
        window = np.minimum(limits, np.maximum(3*step, 3*np.sqrt(np.diag(covariance))))
        counts = np.floor(window/step+1e-8).astype(int)
        window = counts*step
        candidates = np.stack(np.meshgrid(*[np.arange(-n, n+1)*s for n, s in zip(counts, step)],
                                         indexing='ij'), axis=-1).reshape(-1, 3)
        field = DistanceField(reference, o.field_resolution_m, o.translation_window_m+1.)
        c, s = np.cos(pose[2]+candidates[:, 2]), np.sin(pose[2]+candidates[:, 2])
        rotated = np.stack([c[:, None]*points[:, 0]-s[:, None]*points[:, 1],
                            s[:, None]*points[:, 0]+c[:, None]*points[:, 1]], axis=-1)
        world = rotated + (pose[:2]+candidates[:, :2])[:, None, :]
        distances = field.query(world)
        z = distances/sigma
        # Huber rho with transition at 1.5 sensor std; normalized independent count.
        sensor = np.sum(np.where(z <= 1.5, z*z, 3*z-2.25), axis=1)*min(1., o.effective_points/len(points))
        prior = np.einsum('ni,ij,nj->n', candidates, np.linalg.inv(covariance), candidates)
        cost = sensor+prior
        best = int(np.argmin(cost))
        H = field.information(world[best], rotated[best], sigma, o.overlap_distance_m, o.effective_points)
        # Scale yaw to displacement at 2 m before comparing Hessian eigenvalues.
        D = np.diag([1., 1., 2.])
        S = np.diag([1., 1., .5])
        eigen, axes = np.linalg.eigh(S@H@S)
        observable = eigen > max(.5, o.hessian_ratio*eigen[-1])
        V, N = axes[:, observable], axes[:, ~observable]
        projector = V@V.T
        delta = S@projector@D@candidates[best]
        projected_separation = (candidates-candidates[best])@D@projector
        separated = np.linalg.norm(projected_separation, axis=1) >= o.mode_distance_m-1e-9
        second = int(np.argmin(np.where(separated, sensor, np.inf))) if separated.any() else None
        gap = float(sensor[second]-sensor[best]) if second is not None else None
        corrected = pose+delta
        projected_distances = field.query(transform(points, corrected))
        overlap = float(np.mean(projected_distances <= o.overlap_distance_m))
        residual = float(np.sqrt(np.mean(projected_distances**2)))
        boundary = bool(np.any((np.abs(candidates[best]) >= window-step*.49) & (np.diag(projector) > .1)))
        reason = ('unobservable' if not observable.any() else
                  'search_boundary' if boundary else
                  'low_overlap' if overlap < o.min_overlap else
                  'high_residual' if residual > o.max_residual_m else
                  'ambiguous_modes' if gap is not None and gap < o.mode_gap else 'accepted')
        posterior = covariance.copy()
        if reason == 'accepted':
            C = D@covariance@D
            block = V.T@C@V
            measured = np.linalg.inv(np.linalg.inv(block)+np.diag(eigen[observable]))
            # Preserve variance in null directions; discard cross-correlation
            # rather than allow it to shrink unobservable along-wall uncertainty.
            floor = V.T@D@(anchor_covariance+o.floor())@D@V
            ev, vec = np.linalg.eigh(measured-floor)
            measured = floor+vec@np.diag(np.maximum(ev, 0.))@vec.T
            posterior = S@(V@measured@V.T + N@(N.T@C@N)@N.T)@S
        return {'status': 'accepted' if reason == 'accepted' else 'rejected', 'reason': reason,
                'delta': delta.tolist(), 'pose': (corrected if reason == 'accepted' else pose).tolist(),
                'covariance': posterior.tolist(), 'prior_covariance': covariance.tolist(),
                'overlap': overlap, 'residual_m': residual, 'best_cost': float(cost[best]),
                'best_sensor_cost': float(sensor[best]), 'second_sensor_gap': gap,
                'second_delta': candidates[second].tolist() if second is not None else None,
                'hessian_eigenvalues': eigen.tolist(), 'observable_axes_scaled': V.T.tolist(),
                'search_window': window.tolist(), 'search_boundary': boundary, 'candidates': len(candidates)}


class CorrectedOdomGrid(OdomGrid):
    """The on-only map; immutable keyframe ledger and explicit rejection trace."""
    def __init__(self, robot_id, *, correction_options=None, **kwargs):
        super().__init__(robot_id, **kwargs)
        self.options = CSMOptions(**(correction_options or {}))
        self.odom = UncertainCommandOdometry(kwargs.get('start_time', 0.), kwargs.get('profiles'), self.options)
        self.matcher = CorrelativeMatcher(self.options)
        self.keyframes, self.ledger, self.decisions = [], [], []
        self.revision, self.submap_id = 0, 0
        self.last_attempt = -math.inf

    def observe(self, record, *, camera_xy, robot_id):
        from harness.self_wall_memory import validate_record
        rec = validate_record(record)
        local = [np.array([[r1*math.cos(a1), r1*math.sin(a1)], [r2*math.cos(a2), r2*math.sin(a2)]])
                 for r1, a1, r2, a2, _ in rec['seg']]
        return self._observe(rec, local, camera_xy=camera_xy, robot_id=robot_id)

    def observe_contacts(self, *, t, frame_id, segments, camera_xy, robot_id):
        """Already calibrated own Cartesian contacts, e.g. frozen detector cache.

        Deliberately has no pose/map/peer-report argument. Same settle/range gates
        as observe(); avoids lossy Cartesian->polar->Cartesian replay conversion.
        """
        from harness.self_wall_memory import validate_record
        rec = validate_record({'t_sim': t, 'view_index': frame_id, 'seg': [[1., 0., 1., 0., None]],
                               'posture': 'cached_own_contacts', 'load': self.odom.loaded})
        local = np.asarray(segments, float)
        if local.ndim != 3 or local.shape[1:] != (2, 2) or not 1 <= len(local) <= 16 or not np.isfinite(local).all():
            raise ValueError('INVALID_SELF_WALL_CONTACTS')
        return self._observe(rec, local, camera_xy=camera_xy, robot_id=robot_id)

    def _observe(self, rec, segments, *, camera_xy, robot_id):
        if robot_id != self.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        key = (rec['t_sim'], rec['view_index'])
        if key in self.seen:
            return []
        camera = np.asarray(camera_xy, float)
        if camera.shape != (2,) or not np.isfinite(camera).all():
            raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
        prior = np.array(self.odom.advance(rec['t_sim']))
        self.seen.add(key)
        event = {'robot_id': self.robot_id, 't': rec['t_sim'], 'frame_id': rec['view_index'],
                 'prior_pose': prior.tolist(), 'prior_covariance': self.odom.covariance.tolist(),
                 'map_revision_before': self.revision, 'status': 'rejected', 'reason': None,
                 'reference_frames': [], 'inserted': False}
        self.decisions.append(event)
        if self.settle_s is not None and (not self.odom.has_servo or
                self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)]):
            self.rejected['unsettled'] += 1
            event['reason'] = 'unsettled'
            return []
        local = []
        # On path cannot disable the design's 4 m metric/free-space exclusion.
        cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
        for ends in segments:
            if np.linalg.norm(ends-camera, axis=1).max() >= cutoff:
                self.rejected['range_segments'] += 1
            else:
                local.append(ends)
        points = sample_segments(local)
        if len(points) < self.options.min_points:
            event['reason'] = 'insufficient_near_points'
            return []
        if rec['t_sim']-self.last_attempt < self.options.keyframe_interval_s-1e-8:
            event.update(status='deferred', reason='keyframe_interval')
            return []
        self.last_attempt = rec['t_sim']
        signature = hashlib.sha256(np.round(np.asarray(local)/.02).astype('<i8').tobytes()).hexdigest()
        past = [k for k in self.keyframes if rec['t_sim']-k['t'] <= self.options.submap_age_s
                and np.linalg.norm(prior[:2]-np.array(k['pose'])[:2]) <= self.options.submap_radius_m]
        event['reference_frames'] = [k['frame_id'] for k in past]
        if past:
            last = past[-1]
            if last['signature'] == signature and np.linalg.norm(prior[:2]-np.array(last['pose'])[:2]) < .05 \
                    and abs((prior[2]-last['pose'][2]+math.pi)%(2*math.pi)-math.pi) < math.radians(1):
                event.update(status='deferred', reason='duplicate_geometry')
                return []
            reference = np.concatenate([k['world_segments'] for k in past])
            event.update(self.matcher.match(prior, self.odom.covariance, points, camera, reference,
                                            np.asarray(past[0]['anchor_covariance'])))
            if event['status'] != 'accepted':
                return []
            self.odom.correct(event['pose'], event['covariance'])
            anchor_covariance = past[0]['anchor_covariance']
        else:
            self.submap_id += 1
            anchor_covariance = self.odom.covariance.tolist()
            event.update(status='bootstrap', reason='new_submap_dr_anchor', pose=prior.tolist(),
                         covariance=self.odom.covariance.tolist())
        pose = self.odom.pose
        world = [transform(s, pose) for s in local]
        # No map cell or reference scan is written until matching/gating ends.
        self.insert(transform([camera], pose)[0], world)
        self.revision += 1
        row = {'robot_id': self.robot_id, 't': rec['t_sim'], 'frame_id': rec['view_index'],
               'map_revision': self.revision, 'submap_id': self.submap_id, 'pose': list(pose),
               'camera': camera.tolist(), 'segments': [s.tolist() for s in local],
               'covariance': self.odom.covariance.tolist(), 'anchor_covariance': anchor_covariance,
               'signature': signature, 'world_segments': [s.tolist() for s in world]}
        self.ledger.append(row)
        self.keyframes = (past+[row])[-self.options.submap_keyframes:]
        event.update(inserted=True, map_revision_after=self.revision, submap_id=self.submap_id)
        return local

    def text(self):
        return super().text().replace('drift uncorrected', 'drift uncertain')

    def export(self):
        out = super().export()
        out.update(pose_correction='own_map_csm_v1', covariance=self.odom.covariance.tolist(),
                   map_revision=self.revision, submap_id=self.submap_id,
                   correction_counts=dict(Counter(e['reason'] for e in self.decisions)),
                   correction_options=asdict(self.options), ledger_entries=len(self.ledger))
        return out
