"""T13a: conservative, actor-local identity/count gate for target-aware jobs.

This is an opt-in logic seam, not a recognizer or a physical executor. A caller
supplies own-RGB detections and *all* plausible associations to the immediately
previous accepted frame. Hashes bind evidence; they do not prove perception.
There is deliberately no scene inventory, item lookup, referee or peer input.

The existing public order vocabulary has no visually grounded specific-item
descriptor. Such requests remain unknown, then fail after bounded re-looks.
An item name, a colour, an initial slot or a reused tracker label is not identity.
Fungible instances get local tokens only while visually distinguishable from
every previously seen instance of that kind. A lost token is never recycled.
"""
from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Protocol

from harness.zone_study_contract import ContractViolation, ROBOTS, ZONE_IDS
from harness.zone_study_inputs import _order

VERSION = 'ugrp.zone_identity_jobs.v1'
TARGET_API = 'ugrp.own_rgb_target_job.v1'
STATES = ('unknown', 'ready', 'running', 'observed_delivered', 'failed', 'unsupported')
MAX_RELOOKS = 3
MAX_FRAME_AGE_S = 1.0
SETTLE_OBSERVATIONS = 2
SETTLE_CADENCE_S = 1.0


def _token(value):
    if not isinstance(value, str) or not value or not value.isascii() or any(c.isspace() for c in value):
        raise ContractViolation('expected a non-empty ASCII token')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


@dataclass(frozen=True)
class Detection:
    """Own-RGB inference, never a physical item ID or measured contact.

    ``previous`` names all plausible detection IDs in the preceding frame.
    Empty means new/unmatched, not proof of a new object. Bboxes are normalized
    image rectangles. Region/holding/resting are fallible own-image judgments.
    """
    detection_id: str
    kind: str
    bbox: tuple[float, float, float, float]
    previous: tuple[str, ...] = ()
    zone: str | None = None
    holding: str = 'unknown'
    resting: str = 'unknown'


@dataclass(frozen=True)
class OwnFrame:
    robot_id: str
    sequence: int
    captured_at_sim_s: float
    rgb_sha256: str
    previous_rgb_sha256: str | None
    detections: tuple[Detection, ...]


@dataclass(frozen=True)
class TargetJob:
    schema: str
    job_id: str
    robot_id: str
    order_id: str
    requested_item_id: str | None
    identity: str
    kind: str
    destination_zone: str
    local_token: str
    detection_id: str
    frame_sequence: int
    rgb_sha256: str


class TargetExecutor(Protocol):
    """No fallback to colour-only deliver(order, zone) is safe.

    A backend must follow only the refreshed detection in its own frame and
    stop on cancel. This PR implements/tests the seam with a fake backend only.
    """
    target_api: str

    def submit_target(self, job: TargetJob) -> bool: ...
    def refresh_target(self, job_id: str, frame: OwnFrame, detection_id: str) -> None: ...
    def cancel_target(self, job_id: str, reason: str) -> None: ...


class IdentityJobs:
    """One robot, one shared policy for all four communication conditions.

    No condition-specific knobs or communication channel: these are local
    beliefs. Existing peer enum channels and P05 message ledgers stay unchanged.
    Public order rows are normalized by the existing study input contract.
    """

    def __init__(self, robot_id: str, orders, executor: TargetExecutor):
        if robot_id not in ROBOTS:
            raise ContractViolation('unknown robot')
        if not isinstance(orders, (tuple, list)) or not orders:
            raise ContractViolation('expected non-empty public orders')
        seen = set()
        self._orders = {o['order_id']: o for o in
                        (_order(raw, bays=None, slots=None, seen=seen) for raw in orders)}
        specific_ids = [i for o in self._orders.values() for i in o['item_ids']]
        if len(specific_ids) != len(set(specific_ids)):
            raise ContractViolation('item_id is assigned to multiple public orders')
        self.robot_id, self._executor = robot_id, executor
        self._frame: OwnFrame | None = None
        self._tracks: dict[str, str] = {}  # current detection -> local token
        self._kinds: dict[str, str] = {}   # persistent tombstones, never recycled
        self._owners: dict[str, str] = {}  # one order per token, even after failure
        self._receipts: dict[str, dict] = {}
        self._relooks: dict[tuple, set] = {}
        self._active: dict | None = None
        self._job_counter = 0
        self._command_ids: set[str] = set()
        self._backend_fault = False
        self._last_job_status = {'state': 'unknown', 'reason': 'NO_JOB'}

    def _validate_frame(self, f: OwnFrame):
        if not isinstance(f, OwnFrame) or f.robot_id != self.robot_id:
            raise ContractViolation('only this robot own RGB is accepted')
        if (type(f.sequence) is not int or f.sequence < 0 or not _number(f.captured_at_sim_s)
                or not _sha(f.rgb_sha256) or not isinstance(f.detections, tuple)):
            raise ContractViolation('invalid own-frame evidence')
        if self._frame is None:
            if f.previous_rgb_sha256 is not None:
                raise ContractViolation('first frame cannot claim prior evidence')
        elif (f.sequence <= self._frame.sequence or f.captured_at_sim_s <= self._frame.captured_at_sim_s
              or f.previous_rgb_sha256 != self._frame.rgb_sha256):
            raise ContractViolation('stale/reordered frame or broken evidence chain')
        ids = set()
        old = {d.detection_id: d for d in self._frame.detections} if self._frame else {}
        for d in f.detections:
            if not isinstance(d, Detection):
                raise ContractViolation('expected own-RGB Detection')
            _token(d.detection_id)
            _token(d.kind)
            if d.detection_id in ids:
                raise ContractViolation('duplicate detection_id')
            ids.add(d.detection_id)
            b = d.bbox
            if (not isinstance(b, tuple) or len(b) != 4 or not all(_number(x) and x <= 1 for x in b)
                    or not b[0] < b[2] or not b[1] < b[3]):
                raise ContractViolation('invalid normalized image bbox')
            if (not isinstance(d.previous, tuple) or any(not isinstance(x, str) for x in d.previous)
                    or len(d.previous) != len(set(d.previous))
                    or any(x not in old or old[x].kind != d.kind for x in d.previous)):
                raise ContractViolation('invalid previous-frame candidates')
            if d.zone not in (*ZONE_IDS, None) or d.holding not in ('yes', 'no', 'unknown') \
                    or d.resting not in ('yes', 'no', 'unknown'):
                raise ContractViolation('invalid own-image judgment')

    def observe(self, frame: OwnFrame):
        """Advance only on own observations; loss/ambiguity cancels a live target.

        The adapter must supply every frame used for control. Sequence gaps break
        continuity even when a reused detector label or colour looks identical.
        """
        try:
            self._validate_frame(frame)
        except ContractViolation:
            self._stop('INVALID_OWN_FRAME')
            raise
        f = copy.deepcopy(frame)
        candidates = Counter(p for d in f.detections for p in d.previous)
        ambiguous = set()
        for a in f.detections:
            for b in f.detections:
                if a.detection_id == b.detection_id or a.kind != b.kind:
                    continue
                if max(a.bbox[0], b.bbox[0]) < min(a.bbox[2], b.bbox[2]) \
                        and max(a.bbox[1], b.bbox[1]) < min(a.bbox[3], b.bbox[3]):
                    ambiguous.add(a.detection_id)
        tracks = {}
        contiguous = self._frame is not None and f.sequence == self._frame.sequence + 1
        for d in f.detections:
            if contiguous and d.detection_id not in ambiguous and len(d.previous) == 1:
                p = d.previous[0]
                if candidates[p] == 1 and p in self._tracks:
                    tracks[d.detection_id] = self._tracks[p]
        # New tokens require simultaneous distinction from ALL historical tokens
        # of that kind, including delivered/lost ones. This intentionally refuses
        # late births behind occlusion; no appearance re-ID is implemented.
        for kind in sorted({d.kind for d in f.detections}):
            historical = {t for t, k in self._kinds.items() if k == kind}
            if not historical <= set(tracks.values()):
                continue
            for d in f.detections:
                if d.kind == kind and not d.previous and d.detection_id not in ambiguous:
                    token = f'{self.robot_id}-track-{len(self._kinds) + 1}'
                    self._kinds[token] = kind
                    tracks[d.detection_id] = token
        self._tracks, self._frame = tracks, f
        by_token = {tracks[d.detection_id]: d for d in f.detections if d.detection_id in tracks}
        # Receipts are beliefs at the last own observation, never referee truth.
        # A later missing/contradictory view revokes credit but keeps the tombstone.
        for token, receipt in list(self._receipts.items()):
            d = by_token.get(token)
            if d is None or not self._landed(d, receipt['destination_zone']):
                del self._receipts[token]
        active = self._active
        if active is None:
            return
        job = active['job']
        d = by_token.get(job.local_token)
        if d is None:
            self._stop('TRACK_LOST_OR_AMBIGUOUS')
            return
        try:
            self._executor.refresh_target(job.job_id, f, d.detection_id)
        except Exception:
            self._stop('TARGET_REFRESH_ERROR')
            raise
        if d.holding == 'yes':
            active['held_sequence'] = f.sequence
            active['held_evidence'] = {'sequence': f.sequence, 'rgb_sha256': f.rgb_sha256}
            active['released_after'] = None
            active['settled'] = []
        elif (active['released_after'] is not None and f.sequence > active['released_after']
              and f.captured_at_sim_s > active['open_command']['issued_at_sim_s']):
            if d.holding == 'no' and d.resting == 'yes' and d.zone is not None \
                    and d.zone != job.destination_zone:
                self._stop('MISDELIVERY_OBSERVED')
            elif self._landed(d, job.destination_zone):
                settled = active['settled']
                if not settled or f.captured_at_sim_s - settled[-1]['sim_s'] >= SETTLE_CADENCE_S:
                    settled.append({'sequence': f.sequence, 'sim_s': f.captured_at_sim_s,
                                    'rgb_sha256': f.rgb_sha256})
                if len(settled) >= SETTLE_OBSERVATIONS:
                    self._receipts[job.local_token] = {
                        'order_id': job.order_id, 'destination_zone': job.destination_zone,
                        'job_id': job.job_id, 'holding_evidence': copy.deepcopy(active['held_evidence']),
                        'open_command': copy.deepcopy(active['open_command']),
                        'evidence': copy.deepcopy(settled)}
                    self._stop('OWN_OBSERVATION_COMPLETE')
            else:
                active['settled'] = []
        elif d.holding != 'yes':
            active['held_sequence'] = None

    @staticmethod
    def _landed(d, zone):
        return d.zone == zone and d.holding == 'no' and d.resting == 'yes'

    def _stop(self, reason):
        active, self._active = self._active, None
        if active is not None:
            self._last_job_status = {
                'job_id': active['job'].job_id, 'reason': reason,
                'state': 'observed_delivered' if reason == 'OWN_OBSERVATION_COMPLETE' else 'failed'}
            try:
                self._executor.cancel_target(active['job'].job_id, reason)
            except Exception:
                self._backend_fault = True
                self._last_job_status.update(state='failed', reason='TARGET_CANCEL_ERROR')
                raise

    def select(self, order_id, detection_id, *, item_id=None, now_sim_s):
        """Resolve an actor-chosen candidate. No host partner/target selection."""
        if order_id not in self._orders:
            raise ContractViolation('unknown order_id (item_id is not an order_id)')
        order = self._orders[order_id]
        if order['identity'] == 'specific_item':
            if item_id not in order['item_ids']:
                raise ContractViolation('specific item_id must belong to this public order')
        elif item_id is not None:
            raise ContractViolation('fungible orders do not name a physical item_id')
        if not _number(now_sim_s):
            raise ContractViolation('invalid own clock')
        result = {'state': 'unknown', 'reason': None, 'order_id': order_id,
                  'requested_item_id': item_id, 'resolved_item_id': None,
                  'local_token': None, 'next_action': 'reobserve'}
        f = self._frame
        if f is None or not 0 <= now_sim_s - f.captured_at_sim_s <= MAX_FRAME_AGE_S:
            result['reason'] = 'OWN_FRAME_MISSING_OR_STALE'
        elif order['identity'] == 'specific_item':
            result['reason'] = 'SPECIFIC_IDENTITY_UNGROUNDED'
        elif order['required_robots'] != 1 or order['kind'] != 'cyan':
            result.update(state='unsupported', reason='TARGET_SKILL_UNSUPPORTED', next_action='stop')
        else:
            d = next((d for d in f.detections if d.detection_id == detection_id), None)
            token = self._tracks.get(detection_id)
            if d is None or token is None or d.kind != order['kind']:
                result['reason'] = 'TRACK_UNKNOWN_OR_KIND_MISMATCH'
            elif token in self._receipts or self._owners.get(token, order_id) != order_id:
                result.update(state='failed', reason='TARGET_ALREADY_COUNTED_OR_ASSIGNED', next_action='stop')
            elif self.claim(order_id)['observed_count'] >= order['count']:
                result.update(state='failed', reason='ORDER_COUNT_ALREADY_MET', next_action='stop')
            else:
                result.update(state='ready', local_token=token, next_action='submit_target')
        return result

    def reobserve(self, order_id, detection_id, *, item_id=None, now_sim_s):
        result = self.select(order_id, detection_id, item_id=item_id, now_sim_s=now_sim_s)
        if result['state'] == 'unknown':
            frames = self._relooks.setdefault((order_id, item_id), set())
            if self._frame is not None and result['reason'] != 'OWN_FRAME_MISSING_OR_STALE':
                frames.add(self._frame.sequence)
            if len(frames) >= MAX_RELOOKS:
                result.update(state='failed', next_action='stop', reason='IDENTITY_RELOOK_LIMIT')
        return result

    def submit(self, order_id, detection_id, *, item_id=None, now_sim_s):
        result = self.reobserve(order_id, detection_id, item_id=item_id, now_sim_s=now_sim_s)
        if result['state'] != 'ready':
            return result
        if self._backend_fault:
            return {**result, 'state': 'failed', 'reason': 'TARGET_BACKEND_FAULT', 'next_action': 'stop'}
        if self._active is not None:
            return {**result, 'state': 'failed', 'reason': 'OWN_JOB_BUSY', 'next_action': 'stop'}
        if getattr(self._executor, 'target_api', None) != TARGET_API or any(
                not callable(getattr(self._executor, m, None)) for m in
                ('submit_target', 'refresh_target', 'cancel_target')):
            return {**result, 'state': 'unsupported', 'reason': 'TARGET_API_UNSUPPORTED', 'next_action': 'stop'}
        self._job_counter += 1
        order, f = self._orders[order_id], self._frame
        job = TargetJob(TARGET_API, f'{self.robot_id}-identity-job-{self._job_counter}',
                        self.robot_id, order_id, item_id, order['identity'], order['kind'],
                        order['destination_zone'], result['local_token'], detection_id,
                        f.sequence, f.rgb_sha256)
        self._active = {'job': job, 'held_sequence': None, 'released_after': None, 'settled': []}
        self._owners[job.local_token] = order_id
        try:
            accepted = self._executor.submit_target(job)
        except Exception:
            self._stop('TARGET_SUBMIT_ERROR')
            raise
        if accepted is not True:
            self._stop('TARGET_SUBMIT_REFUSED')
            return {**result, 'state': 'failed', 'reason': 'TARGET_SUBMIT_REFUSED', 'next_action': 'stop'}
        self._last_job_status = {'job_id': job.job_id, 'state': 'running', 'reason': None}
        return {**result, 'state': 'running', 'next_action': 'observe', 'job': asdict(job)}

    def issued_open(self, job_id, *, command_id, issued_at_sim_s):
        """Record OWN release command, never measured gripper/holding truth."""
        if self._active is None or self._active['job'].job_id != job_id:
            raise ContractViolation('release command belongs to another/inactive job')
        _token(command_id)
        if command_id in self._command_ids or not _number(issued_at_sim_s) \
                or issued_at_sim_s < self._frame.captured_at_sim_s:
            raise ContractViolation('duplicate/invalid own command evidence')
        self._command_ids.add(command_id)
        self._active['released_after'] = None
        self._active['settled'] = []
        if self._active['held_sequence'] == self._frame.sequence \
                and issued_at_sim_s - self._frame.captured_at_sim_s <= MAX_FRAME_AGE_S:
            self._active['released_after'] = self._frame.sequence
            self._active['open_command'] = {'command_id': command_id, 'job_id': job_id,
                                           'robot_id': self.robot_id, 'issued_at_sim_s': issued_at_sim_s}

    def terminal(self, job_id, *, failed=False):
        """A backend done signal cannot create a delivery/identity claim."""
        if type(failed) is not bool:
            raise ContractViolation('invalid terminal status')
        if self._active is None or self._active['job'].job_id != job_id:
            raise ContractViolation('terminal belongs to another/inactive job')
        if failed:
            self._stop('LOWER_JOB_FAILED')
        else:
            self._last_job_status['reason'] = 'AWAITING_OWN_OBSERVATION'

    def job_status(self):
        return copy.deepcopy(self._last_job_status)

    def claim(self, order_id):
        if order_id not in self._orders:
            raise ContractViolation('unknown order_id')
        order = self._orders[order_id]
        receipts = [r for r in self._receipts.values() if r['order_id'] == order_id]
        return {'order_id': order_id, 'identity': order['identity'], 'item_ids': list(order['item_ids']),
                'observed_count': len(receipts), 'required_count': order['count'],
                'state': 'observed_delivered' if len(receipts) == order['count'] else 'unknown',
                'basis': 'own_rgb_belief_only', 'receipts': copy.deepcopy(receipts)}
