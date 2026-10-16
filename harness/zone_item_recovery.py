"""T13b opt-in own-RGB recovery decisions on the T13a target-job gate.

No event clock, effect, holder truth, world, peer state or item lookup enters
this module. PickupView is a fallible own-image judgment, not a detector: the
adapter must preserve its RGB/ROI evidence. Nothing here claims physical
recovery. Existing sealed executors and communication enums are unchanged.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from harness.zone_identity_jobs import IdentityJobs, OwnFrame, MAX_RELOOKS, _number
from harness.zone_study_contract import ContractViolation

VERSION = 'ugrp.zone_item_recovery.v1'
MAX_RECOVERIES = 3


@dataclass(frozen=True)
class PickupView:
    """Entire named pickup region is visible in this own frame's image ROI.

    A missing detection alone cannot establish empty. Unknown/occluded views
    invalidate consecutive empty evidence; two contiguous clear empty views
    establish only regional absence, never a specific object's new location.
    """
    order_id: str
    frame_sequence: int
    rgb_sha256: str
    location_ref: str
    roi: tuple[float, float, float, float]
    visibility: str  # clear / occluded / unknown
    occupancy: str  # empty / occupied / unknown


def _overlap(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


class RecoveryJobs(IdentityJobs):
    """Same policy/config for every actor and communication condition.

    Recovery never picks a new object or partner. The actor explicitly submits
    a candidate, which still passes T13a identity/count and backend checks.
    In particular, track loss cannot be repaired by relabeling a detection.
    """

    def __init__(self, robot_id, orders, executor):
        super().__init__(robot_id, orders, executor)
        self._recovery = {oid: {'pickup': 'unknown', 'cargo': 'unknown',
                               'reason': 'NO_OWN_EVIDENCE', 'next_action': 'observe',
                               'evidence': [], 'attempts': 0}
                          for oid in self._orders}
        self._empty = {}
        self._pending = {}
        self._looks = {}
        self._evidence_invalid = False

    def _validate_pickup(self, frame, view):
        if not isinstance(view, PickupView) or not isinstance(view.order_id, str) \
                or view.order_id not in self._orders:
            raise ContractViolation('unknown own pickup observation')
        where = self._orders[view.order_id]['initial_location']
        if (type(view.frame_sequence) is not int or view.frame_sequence != frame.sequence
                or not isinstance(view.rgb_sha256, str) or view.rgb_sha256 != frame.rgb_sha256
                or not isinstance(view.location_ref, str)
                or view.location_ref != (where['slot'] or where['pickup_bay'])):
            raise ContractViolation('pickup evidence must bind this frame and public initial region')
        b = view.roi
        if (not isinstance(b, tuple) or len(b) != 4 or not all(_number(x) and x <= 1 for x in b)
                or not b[0] < b[2] or not b[1] < b[3]
                or not isinstance(view.visibility, str) or view.visibility not in ('clear', 'occluded', 'unknown')
                or not isinstance(view.occupancy, str) or view.occupancy not in ('empty', 'occupied', 'unknown')):
            raise ContractViolation('invalid own pickup judgment/ROI')
        if view.visibility == 'clear' and view.occupancy == 'empty' \
                and any(_overlap(b, d.bbox) for d in frame.detections):
            raise ContractViolation('empty pickup contradicts own detection in ROI')

    def _continuing_target(self, frame, job):
        # Screen before refresh_target can issue any lower command. Only the
        # same conservative one-to-one association as T13a permits drop belief.
        if self._frame is None or frame.sequence != self._frame.sequence + 1:
            return None
        old = {d for d, token in self._tracks.items() if token == job.local_token}
        possible = [d for d in frame.detections if old.intersection(d.previous)]
        if len(possible) != 1 or len(possible[0].previous) != 1:
            return None
        d = possible[0]
        if any(x.detection_id != d.detection_id and x.kind == d.kind and _overlap(x.bbox, d.bbox)
               for x in frame.detections):
            return None
        return d

    def _need_recovery(self, oid, frame, reason, cargo):
        row = self._recovery[oid]
        row.update(cargo=cargo, reason=reason, next_action='reobserve',
                   evidence=[{'sequence': frame.sequence, 'rgb_sha256': frame.rgb_sha256}])
        if oid not in self._pending:
            self._pending[oid] = frame.sequence
            self._looks[oid] = set()

    def observe(self, frame: OwnFrame, *, pickup: PickupView | None = None):
        try:
            self._validate_frame(frame)
            if pickup is not None:
                self._validate_pickup(frame, pickup)
        except ContractViolation:
            self._evidence_invalid = True
            self._stop('INVALID_OWN_RECOVERY_FRAME')
            raise
        active = self._active
        if active is not None:
            job = active['job']
            d = self._continuing_target(frame, job)
            if d is None:
                self._need_recovery(job.order_id, frame, 'TRACK_UNCERTAIN', 'unknown')
                self._stop('TRACK_LOST_OR_AMBIGUOUS')
            elif active['held_sequence'] is not None and active['released_after'] is None \
                    and d.holding != 'yes':
                dropped = d.holding == 'no' and d.resting == 'yes'
                reason = 'OWN_RGB_DROP_OBSERVED' if dropped else 'OWN_HOLDING_UNCERTAIN'
                self._need_recovery(job.order_id, frame, reason, 'dropped' if dropped else 'unknown')
                self._stop(reason)
            elif d.holding == 'yes':
                self._recovery[job.order_id].update(cargo='held', reason='OWN_RGB_HELD',
                    evidence=[{'sequence': frame.sequence, 'rgb_sha256': frame.rgb_sha256}])
            else:
                self._recovery[job.order_id].update(
                    cargo='unheld' if d.holding == 'no' else 'unknown', reason='OWN_RGB_HOLDING_UPDATE',
                    evidence=[{'sequence': frame.sequence, 'rgb_sha256': frame.rgb_sha256}])
        super().observe(frame)
        self._evidence_invalid = False
        # No inferred absence from an image without a clear regional judgment.
        for oid in self._empty.keys() - ({pickup.order_id} if pickup else set()):
            self._empty[oid] = []
        if pickup is not None:
            oid = pickup.order_id
            row = self._recovery[oid]
            if pickup.visibility == 'clear' and pickup.occupancy == 'empty':
                prior = self._empty.get(oid, [])
                if prior and prior[-1]['sequence'] != frame.sequence - 1:
                    prior = []
                evidence = {'sequence': frame.sequence, 'rgb_sha256': frame.rgb_sha256,
                            'location_ref': pickup.location_ref, 'roi': pickup.roi}
                self._empty[oid] = (prior + [evidence])[-2:]
                if len(self._empty[oid]) == 2:
                    if self._active is None or self._active['job'].order_id != oid:
                        self._need_recovery(oid, frame, 'OWN_PICKUP_ABSENT', row['cargo'])
                    row.update(pickup='absent', evidence=copy.deepcopy(self._empty[oid]))
                    # Regional absence is not proof the currently tracked cargo
                    # disappeared: a live tracked delivery may continue.
                else:
                    row['pickup'] = 'unknown'
            else:
                self._empty[oid] = []
                row['pickup'] = 'occupied' if pickup.visibility == 'clear' \
                    and pickup.occupancy == 'occupied' else 'unknown'

    def submit(self, order_id, detection_id, *, item_id=None, now_sim_s):
        # Validate public identity and own clock even on the recovery path.
        selected = self.select(order_id, detection_id, item_id=item_id, now_sim_s=now_sim_s)
        if self._backend_fault:
            return {**selected, 'state': 'failed', 'next_action': 'stop', 'reason': 'TARGET_BACKEND_FAULT'}
        if self._evidence_invalid:
            return {**selected, 'state': 'failed', 'next_action': 'stop', 'reason': 'INVALID_RECOVERY_EVIDENCE'}
        if order_id in self._pending and self._active is None:
            row = self._recovery[order_id]
            failure = {**selected, 'state': 'unknown', 'next_action': 'reobserve',
                       'reason': 'RECOVERY_REOBSERVE_REQUIRED'}
            if row['attempts'] >= MAX_RECOVERIES or len(self._looks[order_id]) >= MAX_RELOOKS:
                row.update(next_action='stop', reason='RECOVERY_LIMIT')
                return {**failure, 'state': 'failed', 'next_action': 'stop', 'reason': 'RECOVERY_LIMIT'}
            if self._frame is None or self._frame.sequence <= self._pending[order_id]:
                return failure
            if selected['reason'] == 'OWN_FRAME_MISSING_OR_STALE':
                return selected
            self._looks[order_id].add(self._frame.sequence)
        result = super().submit(order_id, detection_id, item_id=item_id, now_sim_s=now_sim_s)
        if result['state'] == 'running' and order_id in self._pending:
            self._recovery[order_id]['attempts'] += 1
            self._recovery[order_id].update(next_action='observe', reason='RECOVERY_COMMAND_ONLY')
            del self._pending[order_id]
        elif result['state'] == 'unknown' and order_id in self._pending \
                and len(self._looks[order_id]) >= MAX_RELOOKS:
            self._recovery[order_id].update(next_action='stop', reason='RECOVERY_LIMIT')
            result.update(state='failed', next_action='stop', reason='RECOVERY_LIMIT')
        return result

    def recovery_status(self, order_id):
        if order_id not in self._orders:
            raise ContractViolation('unknown order_id')
        return {'order_id': order_id, 'basis': 'own_rgb_belief_only',
                **copy.deepcopy(self._recovery[order_id])}
