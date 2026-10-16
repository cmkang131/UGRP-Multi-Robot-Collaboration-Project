"""Optional per-camera-frame map consumer; never feeds the pose estimator.

Hornung 2013 §3.2/5.1, OctoMap v1.10.0 insertPointCloud/computeUpdate.
Reuse the existing 2D clamped inverse sensor model and confidence factors.
This is an online selected-pose map, not a new RBPF particle proposal/map.
"""
import copy
import math
from types import SimpleNamespace

import numpy as np

from harness.self_odom_grid import OdomGrid, transform
from harness.wall_confidence import confidence, weighted_insert

OPTION = 'camera_every_frame_v1'


class CameraGrid(OdomGrid):
    """Consumes own, calibrated, positive-depth contacts and contemporaneous pose."""
    def __init__(self, robot_id, *, resolution_m=.1, max_range_m=4.):
        super().__init__(robot_id, resolution_m=resolution_m, max_range_m=max_range_m)
        # No command predictor or measurement update is used by this consumer.
        self.odom = SimpleNamespace(pose=(0., 0., 0.), t=0., covariance=np.zeros((3, 3)))
        self.ledger = []
        self.events = []
        self.rejected.update(empty=0, duplicate=0)

    def integrate(self, *, t, frame_id, robot_id, segments, camera_xy, pose,
                  covariance, settled, features=None, weights=None):
        if robot_id != self.robot_id:
            raise ValueError('CAMERA_MAP_PEER_INPUT_FORBIDDEN')
        local = np.asarray(segments, float).reshape(-1, 2, 2)
        camera, pose, cov = np.asarray(camera_xy, float), np.asarray(pose, float), np.asarray(covariance, float)
        if (camera.shape != (2,) or pose.shape != (3,) or cov.shape != (3, 3) or
                not np.isfinite(np.r_[local.ravel(), camera, pose, cov.ravel(), t]).all() or
                not np.allclose(cov, cov.T) or np.linalg.eigvalsh(cov).min() < -1e-10):
            raise ValueError('INVALID_CAMERA_MAP_OBSERVATION')
        if float(t) < self.odom.t-1e-8:
            raise ValueError('CAMERA_MAP_NON_MONOTONIC_TIME')
        if features is not None and len(features) != len(local):
            raise ValueError('CAMERA_MAP_FEATURE_COUNT')
        if weights is not None and (len(weights) != len(local) or
                any(not math.isfinite(w) or not 0 <= w <= 1 for w in weights)):
            raise ValueError('CAMERA_MAP_WEIGHT_COUNT_OR_VALUE')
        key = (float(t), frame_id)
        if key in self.seen:
            self.rejected['duplicate'] += 1
            return []
        self.seen.add(key)
        self.odom = SimpleNamespace(pose=tuple(pose), t=float(t), covariance=cov.copy())
        event = dict(t=float(t), frame_id=frame_id, robot_id=robot_id, inserted=False)
        self.events.append(event)
        if not settled:
            self.rejected['unsettled'] += 1
            event['reason'] = 'unsettled'
            return []
        cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
        keep = [i for i, s in enumerate(local) if np.linalg.norm(s-camera, axis=1).max() < cutoff]
        self.rejected['range_segments'] += len(local)-len(keep)
        if not keep:
            self.rejected['empty'] += 1
            event['reason'] = 'no_in_range_segments' if len(local) else 'empty_detection'
            return []
        selected = local[keep]
        if weights is None:
            weights = ([confidence(s, camera, f, cov, pose[2], self.resolution_m)['weight']
                        for s, f in zip(local, features)] if features is not None else [1.]*len(local))
        ws = [float(weights[i]) for i in keep]
        world = [transform(s, pose) for s in selected]
        weighted_insert(self, transform([camera], pose)[0], world, ws)
        self.ledger.append(dict(t=float(t), frame_id=frame_id, robot_id=robot_id,
            pose=pose.tolist(), covariance=cov.tolist(), camera=camera.tolist(),
            segments=selected.tolist(), insertion_weights=ws))
        event.update(inserted=True, reason='camera_frame', segments=len(selected))
        return selected.tolist()

    def export(self):
        result = super().export()
        result.update(map_update=OPTION, pose_source='contemporaneous_own_estimate',
                      estimator_feedback=False, covariance=self.odom.covariance.tolist())
        return result


def install(grid, *, map_update='off'):
    """Attach a separate map to both public observation APIs. Off is identity.

    Wrapping the public APIs preserves the independently installed _observe
    motion/CSM/Manhattan stack, RNG, decisions and original export bytes.
    Contacts must already have passed the caller's positive-depth guard.
    """
    if map_update == 'off':
        return grid
    if map_update != OPTION or not hasattr(grid, 'observe_contacts'):
        raise ValueError('CAMERA_MAP_REQUIRES_CORRECTED_OWN_GRID')
    if hasattr(grid, 'camera_map'):
        raise ValueError('CAMERA_MAP_ALREADY_INSTALLED')
    grid.camera_map = CameraGrid(grid.robot_id, resolution_m=grid.resolution_m,
                                max_range_m=grid.max_range_m)

    def consume(t, fid, segments, camera, robot_id):
        odom = grid.odom
        settled = grid.settle_s is None or (odom.has_servo and
            odom.t-odom.servo_since+1e-8 >= grid.settle_s[int(odom.loaded)])
        event = grid.decisions[-1] if grid.decisions else {}
        evidence = event.get('wall_confidence') if (event.get('frame_id') == fid and
                                                    abs(event.get('t', -1)-t) < 1e-8) else None
        # Keep the original prior-predictive sensor weights on admitted scans.
        weights = None
        if evidence is not None:
            cutoff = min(4., grid.max_range_m if grid.max_range_m is not None else 4.)
            keep = [i for i, s in enumerate(segments)
                    if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
            if len(keep) != len(evidence):
                raise ValueError('CAMERA_MAP_ESTIMATOR_EVIDENCE_MISMATCH')
            weights = [0.]*len(segments)
            for i, v in zip(keep, evidence):
                weights[i] = v['weight']
        grid.camera_map.integrate(t=t, frame_id=fid, robot_id=robot_id,
            segments=segments, camera_xy=camera, pose=odom.pose, covariance=odom.covariance,
            settled=settled, features=copy.deepcopy(getattr(grid, '_wall_features', None)), weights=weights)

    original_record, original_contacts = grid.observe, grid.observe_contacts

    def observe(record, *, camera_xy, robot_id):
        result = original_record(record, camera_xy=camera_xy, robot_id=robot_id)
        local = [[[r1*math.cos(a1), r1*math.sin(a1)], [r2*math.cos(a2), r2*math.sin(a2)]]
                 for r1, a1, r2, a2, _ in record['seg']]
        consume(record['t_sim'], record['view_index'], local, camera_xy, robot_id)
        return result

    def observe_contacts(*, t, frame_id, segments, camera_xy, robot_id):
        result = original_contacts(t=t, frame_id=frame_id, segments=segments,
                                   camera_xy=camera_xy, robot_id=robot_id)
        consume(t, frame_id, segments, camera_xy, robot_id)
        return result

    grid.observe, grid.observe_contacts = observe, observe_contacts
    return grid
