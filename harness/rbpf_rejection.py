"""Optional rejected-scan guard + GMapping default motion noise, own inputs only.

Source/code-line audit and required deviations: egomap24 README.
Reject-skip is a user requirement, NOT the OpenSLAM likelihood failure policy.
"""
from types import MethodType
import math
import numpy as np
from scipy.special import logsumexp
from harness.self_map_rbpf import RaoBlackwellizedGrid, CloudOdometry, GridField, improved_proposal
from harness.self_map_csm import sample_segments
from harness.self_map_prob import wrap
from harness.self_odom_grid import transform
from harness.self_pulse_odom import PulseOdometry

OPTION = 'gmapping_selective_v1'
NOISE = dict(srr=.1, srt=.2, str=.1, stt=.2, sxy=.03)


def motion_variance(delta):
    """OpenSLAM motionmodel.cpp:25-35; ROS defaults:224-239, no GT fit."""
    x, y, theta = np.abs(delta)
    return np.square([.1*x+.1*theta+.03*y, .1*y+.1*theta+.03*x,
                      .2*theta+.2*math.hypot(x, y)])


def install(grid, *, rbpf_rejection='off'):
    if rbpf_rejection == 'off':
        return grid
    if (rbpf_rejection != OPTION or not isinstance(grid, RaoBlackwellizedGrid)
            or not isinstance(grid.odom.driver, PulseOdometry) or not hasattr(grid, '_motion_gate')):
        raise ValueError('REJECTION_REQUIRES_PULSE_RBPF_MOTION_GATE')
    if hasattr(grid, '_gmapping_insertion'):
        raise ValueError('REJECTION_CONFLICTING_INSERTION_POLICY')
    if hasattr(grid, '_selective_state'):
        raise ValueError('REJECTION_ALREADY_INSTALLED')
    grid._selective_state = dict(previous=list(grid.odom.driver.pose), noise_frames=0,
                                 rejected_frames=0, sensor_updates=0)
    grid._admitted_scan_observer = _observe
    grid.odom.driver.step_callback = MethodType(_command_propagate, grid)
    grid.odom.advance = MethodType(_advance, grid.odom)
    grid._selective_export_base = grid.export
    grid.export = MethodType(_export, grid)
    return grid


def _command_propagate(self, delta, ignored_v122_variance):
    # Mean / F Jacobian at .05s integration steps; do not double-count v122 Q.
    RaoBlackwellizedGrid.propagate(self, delta, np.zeros(3))


def _advance(self, t):
    CloudOdometry.advance(self, t)
    g = self.owner
    state = g._selective_state
    old, now = np.asarray(state['previous']), np.asarray(self.driver.pose)
    delta = now-old
    c, s = math.cos(old[2]), math.sin(old[2])
    delta[:2] = np.array([[c, s], [-s, c]])@delta[:2]
    delta[2] = wrap(delta[2])
    variance = motion_variance(delta)
    if np.any(variance):
        # Each own scan's delta is expressed at its starting particle heading.
        c, s = np.cos(g.poses[:, 2]-delta[2]), np.sin(g.poses[:, 2]-delta[2])
        R = np.zeros_like(g.pending_cov)
        R[:, 0, 0], R[:, 0, 1], R[:, 1, 0], R[:, 1, 1], R[:, 2, 2] = c, -s, s, c, 1.
        g.pending_cov += (R*variance)@R.transpose(0, 2, 1)
        state['noise_frames'] += 1
    state['previous'] = now.tolist()
    return self.pose


def _proposals(self, points, camera, attempt):
    """Two-phase update: rejected frames cannot mutate weights or maps."""
    priors = self.poses.copy()
    covs = self.pending_cov + (np.eye(3)*1e-10 if attempt else 0.)
    poses, events, increments = {}, {}, np.zeros(len(priors))
    def propose(i):
        past = self.maps[i].occupied_points()
        past = past[np.linalg.norm(past-priors[i, :2], axis=1) <= 6.]
        local_reference = getattr(self, '_local_reference', None)
        if local_reference is not None:
            past = local_reference(past, points, priors[i])
        if attempt and len(past) >= self.options.min_points:
            proposal = getattr(self, '_selective_proposal', improved_proposal)
            pose, increment, pe = proposal(GridField(past), points, camera,
                priors[i], covs[i], self.rng, self.options)
            # A rejected particle contributes no sensor evidence.
            increments[i] = increment if pe['reason'] == 'improved_proposal' else 0.
            pe['applied_log_weight_increment'] = float(increments[i])
        else:
            pose = self.rng.multivariate_normal(priors[i], covs[i])
            pe = dict(reason='bootstrap' if attempt else 'keyframe_interval' if len(points) >= self.options.min_points
                      else 'insufficient_match_points', proposal='motion_bootstrap' if attempt else 'motion_deferred_no_sensor_weight')
        pose[2] = wrap(pose[2])
        pe['particle'] = i
        poses[i], events[i] = pose, pe
    def rejected(i):
        return events[i]['reason'] not in ('improved_proposal', 'bootstrap')
    reference = self.best
    propose(reference)
    reject = attempt and rejected(reference)
    if not reject:
        for i in range(len(priors)):
            if i != reference:
                propose(i)
        candidate = int(np.argmax(self.log_weights+increments))
        reject = attempt and rejected(candidate)
        if reject:
            reference = candidate
    if reject:
        reason = events[reference]['reason']
        for i in range(len(priors)):
            pe = events.get(i, dict(particle=i, reason='frame_rejected', proposal='not_evaluated'))
            # Keep only motion-distributed samples; discard accepted proposals
            # too when the entire observation has been declared invalid.
            if pe.get('proposal') != 'motion_fallback':
                poses[i] = self.rng.multivariate_normal(priors[i], covs[i])
                poses[i][2] = wrap(poses[i][2])
            pe.update(frame_rejection_reason=reason, applied_log_weight_increment=0., inserted=False)
            events[i] = pe
        self._selective_state['rejected_frames'] += 1
        update = False
    else:
        update = attempt and any(e['reason'] == 'improved_proposal' for e in events.values())
        for pe in events.values():
            pe['inserted'] = not attempt or pe['reason'] in ('bootstrap', 'improved_proposal')
        if update:
            self.log_weights += increments
            self.log_weights -= logsumexp(self.log_weights)
            self.weights = np.exp(self.log_weights)
            self.best = int(np.argmax(self.weights))
            self._selective_state['sensor_updates'] += 1
    self.poses = np.array([poses[i] for i in range(len(priors))])
    self.pending_cov[:] = np.eye(3)*1e-10
    return [events[i] for i in range(len(priors))], update, events[reference]['reason'] if reject else None


def _observe(self, rec, segments, *, camera_xy, robot_id):
    # Same legacy validation, range, settling, insertion and reporting contracts.
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
    event = dict(t=rec['t_sim'], frame_id=rec['view_index'], robot_id=robot_id,
                 status='rejected', reason='unsettled', inserted=False)
    self.decisions.append(event)
    if self.settle_s is not None and (not self.odom.has_servo or
            self.odom.t-self.odom.servo_since+1e-8 < self.settle_s[int(self.odom.loaded)]):
        self.rejected['unsettled'] += 1
        return []
    cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
    indices = [i for i, s in enumerate(segments) if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
    local = [np.asarray(segments[i]) for i in indices]
    self.rejected['range_segments'] += len(segments)-len(local)
    if not local:
        event['reason'] = 'no_near_geometry'
        return []
    confidence_rows = None
    if self.wall_confidence != 'off':
        from harness.wall_confidence import confidence
        if self._wall_features is None or len(self._wall_features) != len(segments):
            raise ValueError('WALL_CONFIDENCE_FEATURES_REQUIRED')
        cov, yaw = self.odom.covariance, self.odom.pose[2]
        confidence_rows = [confidence(s, camera, self._wall_features[i], cov, yaw, self.resolution_m)
                           for i, s in zip(indices, local)]
        event['wall_confidence'] = confidence_rows
    points = sample_segments(local)
    attempt = rec['t_sim']-self.last_attempt >= 1.-1e-8 and len(points) >= self.options.min_points
    if attempt:
        self.last_attempt = rec['t_sim']
    proposals = getattr(self, '_selective_proposals', _proposals)
    particle_events, update, rejection = proposals(self, points, camera, attempt)
    for i, (grid, pe) in enumerate(zip(self.maps, particle_events)):
        pose = self.poses[i]
        pe['pose'] = pose.tolist()
        if not pe['inserted']:
            continue
        if confidence_rows is None:
            grid.insert(transform([camera], pose)[0], [transform(s, pose) for s in local])
        else:
            from harness.wall_confidence import weighted_insert
            weighted_insert(grid, transform([camera], pose)[0], [transform(s, pose) for s in local],
                            [c['weight'] for c in confidence_rows])
        self.histories[i].append(dict(t=rec['t_sim'], frame_id=rec['view_index'], pose=pose.tolist(),
                                      camera=camera.tolist(), segments=[s.tolist() for s in local]))
        if confidence_rows is not None:
            self.histories[i][-1].update(insertion_weights=[c['weight'] for c in confidence_rows], wall_confidence=confidence_rows)
    selected = self.best
    # Even a pre-existing low Neff cannot trigger resampling on an invalid scan.
    neff, parents = self.resample_if_needed() if update else (float(1/(self.weights@self.weights)), None)
    self.cells, self.frames, self.ledger = self.maps[self.best].cells, self.maps[self.best].frames, self.histories[self.best]
    chosen = particle_events[selected]
    self.revision += bool(chosen['inserted'])
    reason = rejection or chosen['reason']
    event.update(reason=reason, status='rejected' if rejection else 'bootstrap' if reason == 'bootstrap'
                 else 'accepted' if reason == 'improved_proposal' else 'deferred',
                 inserted=chosen['inserted'], matching_attempted=attempt, particle_events=particle_events,
                 selected_before_resampling=selected, selected_after_resampling=self.best,
                 neff=neff, resampled=parents is not None, parent_indices=parents, sensor_weight_update=update,
                 pose=list(self.odom.pose), covariance=self.odom.covariance.tolist(),
                 inserted_particles=sum(p['inserted'] for p in particle_events), map_revision_after=self.revision)
    return local if chosen['inserted'] else []


def _export(self):
    out = self._selective_export_base()
    out.update(rbpf_rejection=OPTION, selective_resampling=dict(self._selective_state),
               noise_source='OpenSLAM c716f019 motionmodel.cpp:25-35 + ROS eec86068 defaults:224-239',
               command_sigma=NOISE, noise_interval='own RGB delta; Gaussian covariance propagation')
    return out
