"""Opt-in T13 identity grounding from an authored public visual catalogue.

The catalogue describes the complete set of possible cargo, not their runtime
positions. A name alone never grounds a detection. This version recognizes
34 x 40 x 32 mm colour boxes; same-colour boxes remain ambiguous even if their declared
sizes differ (monocular size discrimination is not qualified).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from harness.zone_identity_jobs import Detection, OwnFrame
from harness.zone_item_recovery import RecoveryJobs
from harness.zone_study_contract import ContractViolation, digest

BOX_KINDS = ('cyan', 'red', 'green')
BOX_SIZE = (.034, .040, .032)


@dataclass(frozen=True)
class CueDetection(Detection):
    shape: str = 'unknown'
    dimensions_m: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class CueFrame(OwnFrame):
    # Partial, clipped or non-fitting colour components cannot be ignored when
    # deciding whether a cue is unique, even if one other component fits well.
    ambiguous_kinds: tuple[str, ...] = ()


class PublicVisualCatalogue:
    def __init__(self, value):
        if (not isinstance(value, dict) or set(value) != {'schema', 'complete', 'objects'}
                or value['schema'] != 'ugrp.public_visual_catalogue.v1'
                or value['complete'] is not True or not isinstance(value['objects'], list)
                or not value['objects']):
            raise ContractViolation('a complete authored public visual catalogue is required')
        self.rows = {}
        for row in value['objects']:
            if (not isinstance(row, dict) or set(row) != {'item_id', 'kind', 'shape', 'color', 'dimensions_m'}
                    or not all(isinstance(row[k], str) and row[k] for k in ('item_id', 'kind', 'shape', 'color'))
                    or row['item_id'] in self.rows):
                raise ContractViolation('invalid public visual descriptor')
            dims = row['dimensions_m']
            if (not isinstance(dims, list) or len(dims) != 3
                    or any(type(v) not in (int, float) or not 0 < v <= 2 for v in dims)):
                raise ContractViolation('invalid public object dimensions')
            self.rows[row['item_id']] = copy.deepcopy(row)
        self.sha256 = digest(value)

    def resolve(self, item_id, frame, detection_id):
        row = self.rows.get(item_id)
        if row is None:
            return 'SPECIFIC_DESCRIPTOR_MISSING'
        if (row['kind'] not in BOX_KINDS or row['shape'] != 'box'
                or row['color'] != row['kind'] or tuple(row['dimensions_m']) != BOX_SIZE):
            return 'VISUAL_DESCRIPTOR_UNSUPPORTED'
        # Publicly known indistinguishable items outside this view still matter.
        if sum(r['color'] == row['color'] for r in self.rows.values()) != 1:
            return 'PUBLIC_CUE_AMBIGUOUS'
        if not isinstance(frame, CueFrame) or row['kind'] in frame.ambiguous_kinds:
            return 'OWN_CUE_AMBIGUOUS'
        matches = [d for d in frame.detections if d.kind == row['kind']]
        if len(matches) != 1 or matches[0].detection_id != detection_id:
            return 'OWN_CUE_NOT_UNIQUE'
        d = matches[0]
        if not isinstance(d, CueDetection) or d.shape != row['shape'] or d.dimensions_m != BOX_SIZE:
            return 'OWN_SHAPE_SIZE_UNGROUNDED'
        return None


class TargetRecoveryJobs(RecoveryJobs):
    """RecoveryJobs with explicit, auditable specific re-identification.

    Existing IdentityJobs/RecoveryJobs retain their refusal-only defaults.
    Re-identification happens AFTER their cancellation path; a lost active job
    never silently switches to a newly recognized component.
    """

    def __init__(self, robot_id, orders, executor, *, visual_catalogue):
        super().__init__(robot_id, orders, executor)
        self.catalogue = PublicVisualCatalogue(visual_catalogue)
        self._specific_tokens = {}
        for order in self._orders.values():
            for item_id in order['item_ids']:
                descriptor = self.catalogue.rows.get(item_id)
                if descriptor is None or descriptor['kind'] != order['kind']:
                    raise ContractViolation('specific public order and visual descriptor differ')

    def observe(self, frame, *, pickup=None):
        # New ambiguity must cancel before the base class refreshes the lower
        # skill. Treat it as missing evidence, not a backend exception.
        try:
            self._validate_frame(frame)
        except ContractViolation:
            self._evidence_invalid = True
            self._stop('INVALID_OWN_RECOVERY_FRAME')
            raise
        if self._active is not None and isinstance(frame, CueFrame):
            job = self._active['job']
            d = self._continuing_target(frame, job)
            ambiguous = job.kind in frame.ambiguous_kinds
            if d is not None and job.identity == 'specific_item':
                ambiguous |= self.catalogue.resolve(job.requested_item_id, frame, d.detection_id) is not None
            if ambiguous:
                self._need_recovery(job.order_id, frame, 'OWN_CUE_AMBIGUOUS', 'unknown')
                self._stop('OWN_CUE_AMBIGUOUS')
        super().observe(frame, pickup=pickup)
        # A public unique cue can re-identify a specific item after an occlusion.
        # Fungible lost tracks retain the original non-recycling tombstones.
        for order in self._orders.values():
            if order['identity'] != 'specific_item':
                continue
            for item_id in order['item_ids']:
                for d in self._frame.detections:
                    if self.catalogue.resolve(item_id, self._frame, d.detection_id) is not None:
                        continue
                    token = self._specific_tokens.get(item_id)
                    if token is None:
                        token = self._tracks.get(d.detection_id)
                        if token is None:
                            token = f'{self.robot_id}-track-{len(self._kinds) + 1}'
                            self._kinds[token] = d.kind
                        self._specific_tokens[item_id] = token
                    self._tracks[d.detection_id] = token

    def select(self, order_id, detection_id, *, item_id=None, now_sim_s):
        # Retain the original order/item-id/clock validation and stale refusal.
        result = super().select(order_id, detection_id, item_id=item_id, now_sim_s=now_sim_s)
        order = self._orders[order_id]
        if result['reason'] == 'OWN_FRAME_MISSING_OR_STALE':
            return result
        if order['required_robots'] != 1 or order['kind'] not in BOX_KINDS:
            return {**result, 'state': 'unsupported', 'reason': 'TARGET_SKILL_UNSUPPORTED', 'next_action': 'stop'}
        f = self._frame
        if order['identity'] == 'specific_item':
            reason = self.catalogue.resolve(item_id, f, detection_id)
            if reason is not None:
                return {**result, 'state': 'unknown', 'reason': reason, 'next_action': 'reobserve'}
        elif not isinstance(f, CueFrame) or order['kind'] in f.ambiguous_kinds:
            return {**result, 'state': 'unknown', 'reason': 'OWN_CUE_AMBIGUOUS', 'next_action': 'reobserve'}
        d = next((d for d in f.detections if d.detection_id == detection_id), None)
        token = self._tracks.get(detection_id)
        if (not isinstance(d, CueDetection) or token is None or d.kind != order['kind']
                or d.shape != 'box' or d.dimensions_m != BOX_SIZE):
            return {**result, 'state': 'unknown', 'reason': 'TRACK_UNKNOWN_OR_KIND_MISMATCH', 'next_action': 'reobserve'}
        if token in self._receipts or self._owners.get(token, order_id) != order_id:
            return {**result, 'state': 'failed', 'reason': 'TARGET_ALREADY_COUNTED_OR_ASSIGNED', 'next_action': 'stop'}
        if self.claim(order_id)['observed_count'] >= order['count']:
            return {**result, 'state': 'failed', 'reason': 'ORDER_COUNT_ALREADY_MET', 'next_action': 'stop'}
        return {**result, 'state': 'ready', 'reason': None, 'local_token': token,
                'resolved_item_id': item_id, 'next_action': 'submit_target',
                'visual_catalogue_sha256': self.catalogue.sha256}
