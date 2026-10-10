"""CSM v2: decouple memory-map insertion from pose-matching scheduling.

Keep v1's immutable matching keyframes and all pose/covariance decisions. Mapping
stores eligible deferred scans at the current DR-plus-corrections estimate. This
separates the confirmed insertion-loss cause without silently retuning matching.
See ego-wall-map-probe README section 18 for primary sources and exact policy.
"""
from __future__ import annotations

import hashlib

import numpy as np

from harness.self_map_csm import CorrectedOdomGrid
from harness.self_odom_grid import transform


class CorrectedOdomGridV2(CorrectedOdomGrid):
    """Dense memory grid, unchanged sparse frozen matching-reference submap.

    Distinct new scans deferred by interval/duplicate geometry are inserted, but
    never become extra independent localization measurements. A repeated frame
    ID/time remains a complete no-op. All actual matching rejections, unsettled
    observations and absent near geometry remain excluded. Valid short scans
    lacking six samples may map without matching; their covariance is untouched.
    """
    def _observe(self, rec, segments, *, camera_xy, robot_id):
        before = len(self.decisions)
        admitted = super()._observe(rec, segments, camera_xy=camera_xy, robot_id=robot_id)
        if len(self.decisions) == before:
            return admitted  # Duplicate source frame: no cells/confidence/events.
        event = self.decisions[-1]
        event['matching_attempted'] = 'candidates' in event
        if event['inserted']:
            event['insertion_policy'] = 'matched_or_bootstrap'
            self.ledger[-1]['matching_keyframe'] = True
            return admitted
        camera = np.asarray(camera_xy, float)
        cutoff = min(4., self.max_range_m if self.max_range_m is not None else 4.)
        local = [np.asarray(s) for s in segments if np.linalg.norm(np.asarray(s)-camera, axis=1).max() < cutoff]
        # No match attempt occurred for short valid geometry. Distinguish this
        # case from actual failed matches and from no usable near geometry.
        if event['reason'] == 'insufficient_near_points' and local:
            event.update(status='deferred', reason='insufficient_match_points')
        allowed = event['status'] == 'deferred' and event['reason'] in (
            'keyframe_interval', 'duplicate_geometry', 'insufficient_match_points')
        if not allowed or not local:
            event['insertion_policy'] = 'exclude_rejected_or_invalid'
            return []
        pose = self.odom.pose
        world = [transform(s, pose) for s in local]
        self.insert(transform([camera], pose)[0], world)
        self.revision += 1
        row = {'robot_id': self.robot_id, 't': rec['t_sim'], 'frame_id': rec['view_index'],
               'map_revision': self.revision, 'submap_id': self.submap_id, 'pose': list(pose),
               'camera': camera.tolist(), 'segments': [s.tolist() for s in local],
               'covariance': self.odom.covariance.tolist(),
               'signature': hashlib.sha256(np.round(np.asarray(local)/.02).astype('<i8').tobytes()).hexdigest(),
               'world_segments': [s.tolist() for s in world], 'matching_keyframe': False}
        self.ledger.append(row)
        # Do not change self.keyframes, last_attempt, pose or covariance. The
        # existing reference subset is the control of this insertion-only change.
        event.update(inserted=True, map_revision_after=self.revision, submap_id=self.submap_id,
                     pose=list(pose), covariance=self.odom.covariance.tolist(),
                     insertion_policy='deferred_at_current_estimate')
        return local

    def export(self):
        out = super().export()
        out.update(pose_correction='own_map_csm_v2',
                   insertion_policy={'accepted_bootstrap': 'insert_and_reference',
                                     'deferred': 'insert_current_estimate_without_pose_update',
                                     'matching_rejected': 'exclude', 'invalid_or_unsettled': 'exclude',
                                     'duplicate_source_frame': 'no_op',
                                     'matching_reference': 'unchanged_v1_keyframes'})
        return out
