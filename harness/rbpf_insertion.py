"""Opt-in GMapping scan registration lifecycle with existing range tempering.

Only admitted scans reach this observer. Match failure rejects the correction,
not the scan. Frozen proposal/noise/weights and hit/free model are reused.
Original source audit: experiments/2026-10-08-rbpf-insertion/README.md.
"""
from types import MethodType
import numpy as np
from scipy.special import logsumexp
from harness.self_map_rbpf import RaoBlackwellizedGrid, GridField, improved_proposal
from harness.self_map_csm import sample_segments
from harness.self_map_prob import wrap
from harness.self_odom_grid import transform

OPTION = 'gmapping_range_v1'


def install(grid, *, rbpf_insertion='off'):
    if rbpf_insertion == 'off':
        return grid
    if (rbpf_insertion != OPTION or not isinstance(grid, RaoBlackwellizedGrid)
            or not hasattr(grid, '_motion_gate') or grid.wall_confidence != 'inverse_sensor_v1'):
        raise ValueError('INSERTION_REQUIRES_RBPF_MOTION_GATE_INVERSE_SENSOR')
    if hasattr(grid, '_admitted_scan_observer'):
        raise ValueError('INSERTION_CONFLICTING_SCAN_POLICY')
    grid._gmapping_insertion = OPTION
    grid._admitted_scan_observer = _observe
    grid._insertion_export_base = grid.export
    grid.export = MethodType(_export, grid)
    return grid


def _export(self):
    out = self._insertion_export_base()
    out['rbpf_insertion'] = OPTION
    return out


def _observe(self, rec, segments, *, camera_xy, robot_id):
    if robot_id != self.robot_id:
        raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
    key = (rec['t_sim'], rec['view_index'])
    if key in self.seen:
        return []
    camera = np.asarray(camera_xy, float)
    if camera.shape != (2,) or not np.isfinite(camera).all():
        raise ValueError('SELF_MAP_INVALID_CAMERA_ORIGIN')
    self.odom.advance(rec['t_sim'])
    self.seen.add(key)
    event = {'t': rec['t_sim'], 'frame_id': rec['view_index'], 'robot_id': robot_id,
             'status': 'rejected', 'reason': 'unsettled', 'inserted': False}
    self.decisions.append(event)
    if self.settle_s is not None and (not self.odom.has_servo or
            self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)]):
        self.rejected['unsettled'] += 1
        return []
    cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
    local = [np.asarray(s) for s in segments if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
    self.rejected['range_segments'] += len(segments)-len(local)
    if not local:
        event['reason'] = 'no_near_geometry'
        return []
    confidence_rows = None
    if self.wall_confidence != 'off':
        from harness.wall_confidence import confidence
        if self._wall_features is None or len(self._wall_features) != len(segments):
            raise ValueError('WALL_CONFIDENCE_FEATURES_REQUIRED')
        indices = [i for i,s in enumerate(segments) if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
        # Predictive cloud (including pending command noise), before this
        # scan's proposal. No truth, peer pose or posterior look-ahead.
        cov, yaw = self.odom.covariance, self.odom.pose[2]
        confidence_rows = [confidence(s, camera, self._wall_features[i], cov, yaw, self.resolution_m)
                           for i,s in zip(indices,local)]
        event['wall_confidence'] = confidence_rows
    points = sample_segments(local)
    attempt = rec['t_sim']-self.last_attempt >= 1.-1e-8 and len(points) >= self.options.min_points
    if attempt:
        self.last_attempt = rec['t_sim']
    particle_events = []
    inserted = []
    for i, grid in enumerate(self.maps):
        reason = 'keyframe_interval' if len(points) >= self.options.min_points else 'insufficient_match_points'
        pe = {'particle': i, 'reason': reason, 'proposal': 'deferred'}
        eligible = True
        if attempt:
            past = grid.occupied_points()
            past = past[np.linalg.norm(past-self.poses[i, :2], axis=1) <= 6.]
            cov = self.pending_cov[i]+np.eye(3)*1e-10
            if len(past) >= self.options.min_points:
                field = GridField(past)
                pose, increment, details = improved_proposal(field, points, camera, self.poses[i], cov, self.rng, self.options)
                self.poses[i] = pose
                self.log_weights[i] += increment
                pe.update(details)
                # OpenSLAM registers motion-fallback scans too (hxx:141-167).
                eligible = True
            else:
                # First scan conditions only on motion, no fabricated likelihood.
                self.poses[i] = self.rng.multivariate_normal(self.poses[i], cov)
                self.poses[i, 2] = wrap(self.poses[i, 2])
                pe.update(reason='bootstrap', proposal='motion_bootstrap')
            self.pending_cov[i] = np.eye(3)*1e-10
        else:
            # Each inserted scan must be conditioned on a sampled trajectory,
            # not an unsampled Gaussian mean shared by all deferred maps.
            self.poses[i] = self.rng.multivariate_normal(self.poses[i], self.pending_cov[i])
            self.poses[i, 2] = wrap(self.poses[i, 2])
            self.pending_cov[i] = np.eye(3)*1e-10
            pe['proposal'] = 'motion_deferred_no_sensor_weight'
        pe.update(inserted=eligible, pose=self.poses[i].tolist())
        if eligible:
            pose = self.poses[i]
            if confidence_rows is None:
                grid.insert(transform([camera], pose)[0], [transform(s, pose) for s in local])
            else:
                from harness.wall_confidence import weighted_insert
                weighted_insert(grid, transform([camera], pose)[0], [transform(s, pose) for s in local],
                                [c['weight'] for c in confidence_rows])
            self.histories[i].append({'t': rec['t_sim'], 'frame_id': rec['view_index'], 'pose': pose.tolist(),
                                      'camera': camera.tolist(), 'segments': [s.tolist() for s in local]})
            if confidence_rows is not None:
                self.histories[i][-1].update(insertion_weights=[c['weight'] for c in confidence_rows],
                                            wall_confidence=confidence_rows)
            inserted.append(i)
        particle_events.append(pe)
    self.log_weights -= logsumexp(self.log_weights)
    self.weights = np.exp(self.log_weights)
    self.best = int(np.argmax(self.weights))
    selected = self.best
    neff, parents = self.resample_if_needed() if attempt else (float(1/(self.weights@self.weights)), None)
    self.cells = self.maps[self.best].cells
    self.frames = self.maps[self.best].frames
    self.ledger = self.histories[self.best]
    chosen = particle_events[selected]
    self.revision += bool(chosen['inserted'])
    event.update(insertion_policy=OPTION,
                 insertion_reason='motion_fallback' if chosen['reason'] not in ('bootstrap','improved_proposal') else chosen['reason'],
                 reason=chosen['reason'], status=('bootstrap' if chosen['reason'] == 'bootstrap' else
                 'accepted' if chosen['reason'] == 'improved_proposal' else 'deferred' if not attempt else 'rejected'),
                 inserted=chosen['inserted'], matching_attempted=attempt, particle_events=particle_events,
                 selected_before_resampling=selected, selected_after_resampling=self.best,
                 neff=neff, resampled=parents is not None, parent_indices=parents,
                 pose=list(self.odom.pose), covariance=self.odom.covariance.tolist(),
                 inserted_particles=len(inserted), map_revision_after=self.revision)
    return local if chosen['inserted'] else []

