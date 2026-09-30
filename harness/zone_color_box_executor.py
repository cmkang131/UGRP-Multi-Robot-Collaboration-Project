"""Opt-in T03 executor; import this class explicitly from an unsealed caller.

Selecting only a wrist skill on the legacy host does NOT enable this executor.
The legacy executor, host and registration remain byte-for-byte unchanged.
This module contains no world/peer access, global patch or condition dispatch.
"""
from harness.m1_color_contract import validate_box_profile
from harness.zone_color_box_delivery import ColorDeliverController
from harness.zone_own_executor import ZoneOwnExecutor, TERMINAL_STOP
from harness.zone_own_contract import ExecutorContractError, zone_slot
from harness.zone_own_status import (
    CARRY_PHASES, GRIPPER_OPEN_MIN_PWM, HOLDING_CHECK_MAX_AGE_S, COMMIT_CONFIDENCE,
)


def controller_source_record():
    """Audit-only closure for this explicit executor and its selected color skill.

    This is not an execution bundle or a physical qualification. An unsealed
    caller must also record its own entrypoint, config, provider and model.
    """
    import hashlib
    import json
    from pathlib import Path
    from harness.python_source_closure import source_closure
    root = Path(__file__).resolve().parents[1]
    files = source_closure(root, ('harness/zone_color_box_executor.py',),
                           modules=('harness.wrist_color_boxes',))
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'controller_source_sha256': digest, 'controller_source_files': hashes}


class ZoneColorBoxExecutor(ZoneOwnExecutor):
    """Same per-robot job API, with explicitly selected color kind wiring."""

    def __init__(self, *args, skill_factory, **kwargs):
        self.box_profile = getattr(skill_factory, 'box_perception_profile', 'legacy_cyan_v1')
        validate_box_profile(self.box_profile, 'cyan', 'own_rgb_bay')
        self._holding_kind = 'cyan'
        super().__init__(*args, skill_factory=skill_factory, **kwargs)

    def deliver(self, item_ref, zone_slot_id) -> dict:
        """Deliver the order line ``item_ref`` to a zone slot ('A2') or a zone ('A': next own slot)."""
        arguments = {'order_id': self._token(item_ref), 'target_ref': self._token(zone_slot_id)}
        if self.stopped is not None:
            return self._ack('deliver', arguments, False, TERMINAL_STOP)
        order = self.orders.get(item_ref) if isinstance(item_ref, str) else None
        if order is None:
            return self._ack('deliver', arguments, False, 'UNKNOWN_ORDER')
        from harness.m1_color_contract import BOX_KINDS
        supported = BOX_KINDS if self.box_profile == 'm1_color_boxes_v1' else ('cyan',)
        if order['kind'] not in supported:
            return self._ack('deliver', arguments, False, 'KIND_NOT_SUPPORTED_BY_M1_SKILL')
        if not isinstance(zone_slot_id, str) or not zone_slot_id:
            return self._ack('deliver', arguments, False, 'UNKNOWN_ZONE_SLOT')
        slot_id = zone_slot_id
        if zone_slot_id in self.map['zone_slots']:
            zone_slots = self.map['zone_slots'][zone_slot_id]
            slot_id = zone_slots[min(self._delivered_per_zone.get(zone_slot_id, 0), len(zone_slots) - 1)]['slot_id']
        try:
            slot = zone_slot(self.map, slot_id)
        except KeyError:
            return self._ack('deliver', arguments, False, 'UNKNOWN_ZONE_SLOT')
        if slot_id[0] != order['destination_zone']:
            return self._ack('deliver', arguments, False, 'SLOT_OUTSIDE_ORDER_DESTINATION')
        pickup = (order.get('initial_location') or {}).get('slot')
        if pickup is None:
            return self._ack('deliver', arguments, False, 'ORDER_WITHOUT_PICKUP_SLOT')
        if self.holding()['answer'] != 'no':
            return self._ack('deliver', arguments, False, 'NOT_EMPTY_HANDED')
        ack = self._start('deliver', 'deliver', arguments, slot_id=slot_id, slot_xy=list(slot['center_m']),
                          pickup_slot=pickup, box_kind=order['kind'])
        if ack['accepted']:
            self._holding_kind = order['kind']
            if self.box_profile == 'm1_color_boxes_v1':
                self._last_holding_check = None
        return ack

    def _step_deliver(self, now, job):
        if job.ctl is None:
            # A robot that idled (hold) localised only from passive frames; like M1's own start,
            # the delivery begins with a fresh wide own look (plumbing dev-s703: idle r3 p50 12 cm, std 6 cm).
            decision = self._tick_sweep(now, job)
            if decision is not None:
                return decision
            slot = self.slots[job.args['pickup_slot']]
            rect = (tuple(slot['x_range_m']), tuple(slot['y_range_m']))
            rows = [y for y in self.search_rows_y if slot['y_range_m'][0] <= y < slot['y_range_m'][1]]
            job.ctl = ColorDeliverController(self.map, self.params, box_kind=job.args['box_kind'], box_profile=self.box_profile, slot_id=job.args['slot_id'],
                                         slot_xy=job.args['slot_xy'], skill_factory=self._skill_for(job),
                                         pose_estimate_cls=self.pose_estimate_cls, search_rows_y=rows,
                                         robot_id=self.robot_id, seed=self.seed, order_kind='own_rgb_bay',
                                         shared_pose=self.pose, servo=self.servo, slot_rect=rect,
                                         all_rows_y=self.search_rows_y, gate=self.gate, guard=self.guard,
                                         static_keepouts=self.static_keepouts)
            job.ctl.last_obs, job.ctl.last_frame_id = self.last_obs, self.last_frame_id
            job.phase = 'm1_delivery'
        decision = job.ctl.decide(now)
        if decision['mode'] != 'done':
            return decision
        outcome = decision['outcome']
        placement = getattr(job.ctl.skill, 'placement', None) or {}
        detail = {'order_id': job.args['order_id'], 'slot_id': job.args['slot_id'],
                  'placement_reason': placement.get('reason'), 'slot_error_m': placement.get('slot_error_m')}
        if (outcome == 'SKILL_OWN_RGB_PLACEMENT_IN_SLOT' and self.box_profile == 'm1_color_boxes_v1'
                and placement.get('kind') != job.args['box_kind']):
            self._fail(now, 'PLACEMENT_KIND_MISMATCH', **detail)
        elif outcome == 'SKILL_OWN_RGB_PLACEMENT_IN_SLOT':
            zone = job.args['slot_id'][0]
            self._delivered_per_zone[zone] = self._delivered_per_zone.get(zone, 0) + 1
            gate = next((g for g in job.ctl.lookback_gates if g.get('frame_id') == placement.get('frame_id')), None)
            self._finish(now, 'own_camera_confirmed', outcome, look_back_gate_frame=None if gate is None
                         else gate['frame_id'], **detail)
        elif outcome.startswith('SKILL_OWN_RGB_PLACEMENT_') and outcome != 'SKILL_OWN_RGB_PLACEMENT_OUTSIDE_SLOT':
            self._finish(now, 'unconfirmed', outcome, **detail)
        else:
            leg = job.ctl.leg
            self._fail(now, outcome, stall_keepouts=[] if leg is None else leg.stall_keepouts, **detail)
        return {'mode': 'tick', 'commands': [{'kind': 'hold'}]}

    def _skill_for(self, job):
        factory = self.skill_factory

        def make(order):
            skill = factory(order, robot_id=self.robot_id)
            if self.box_profile == 'm1_color_boxes_v1':
                if (getattr(skill, 'box_perception_profile', None) != self.box_profile
                        or getattr(getattr(skill, 'box', None), 'box_kind', None) != order.kind):
                    raise ExecutorContractError('color-box factory returned a different profile or kind')
                if getattr(skill, 'mode', None) != self.mode:
                    raise ExecutorContractError('color-box factory returned a different mode')
            return skill
        return make

    def _held_kind(self):
        job = self.job
        if job is not None and job.kind == 'deliver':
            return self.orders[job.args['order_id']]['kind']
        return self._holding_kind

    def holding(self) -> dict:
        job = self.job
        sk = job.ctl.skill if job is not None and job.ctl is not None else None
        if sk is not None:
            phase = sk.phase
            box = getattr(sk, 'box', None)
            if (phase in CARRY_PHASES and box is not None and box.held
                    and (self.box_profile == 'legacy_cyan_v1' or getattr(box, 'box_kind', None) == self._held_kind())):
                base = {'answer': 'yes', 'source': 'own_rgb_attachment_check (wrist skill)', 'skill_phase': phase}
            elif phase in ('look_back', 'finished') and any(e.get('event') == 'release_confirmed'
                                                              for e in getattr(sk, 'events', ())):
                base = {'answer': 'no', 'source': 'own_rgb_release_confirmed (wrist skill)', 'skill_phase': phase}
            elif phase in ('nav_pregrasp',) and self.servo.get(1, 0) >= GRIPPER_OPEN_MIN_PWM:
                base = {'answer': 'no', 'source': 'gripper_open_issued_since_last_release', 'skill_phase': phase}
            else:
                base = {'answer': 'unknown', 'source': 'wrist skill mid-manipulation', 'skill_phase': phase}
        else:
            base = dict(self._holding_after)
        check = self._last_holding_check
        if check is not None and self.now - check['t'] <= HOLDING_CHECK_MAX_AGE_S:
            base['camera_check'] = {k: check[k] for k in ('answer', 'confidence', 'reason', 't')}
            if (check['answer'] in ('yes', 'no') and base['answer'] in ('yes', 'no') and check['answer'] != base['answer']
                    and check['confidence'] >= COMMIT_CONFIDENCE):
                base['answer'], base['conflict'] = 'unknown', True
        return base
