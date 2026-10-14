"""Own-RGB lift confirmation for the solo teacher (no truth contact, height or pose).

Evidence order, both from the own wrist frame, the own issued arm pulses and the
pose the teacher froze at the grasp:

1. ``held_item_at_grip`` (harness.zone_own_perception_v3_1.judge_held_item with
   ``grasp_pose``): the predicted at-grip silhouette of the ordered kind carries
   its colour. Works in any arm posture, behind the v3.1 image-information gate.
2. Only when step 1 cannot frame the kind at all (the 50 mm can: its at-grip
   silhouette is 0 px in the wrist frame at every reachable tool pitch, so the
   v1 CARRY region and v3 band both stay ``unknown``), a look back at the floor
   spot the cargo was visibly standing on (``judge_slot_item``, the spot comes
   from the teacher's frozen visible measurement): bare floor there means the
   cargo is no longer on the floor. This is weaker than seeing the cargo in the
   gripper (it cannot tell "held" from "knocked away"); the record names the
   evidence so a report can separate the two. The physical lift is scored by the
   separate evaluator, never by this function.
"""
from __future__ import annotations

NOT_FRAMED = 'EXPECTED_KIND_NOT_FRAMED_AT_GRIP'


def lift_answer(frame_bgr, pwm, kind, grasp_pose, floor_xy, *, held_judge=None, slot_judge=None):
    """Return ``(answer, record)`` with answer in ``yes`` / ``no`` / ``unknown``."""
    if held_judge is None:
        from harness.zone_own_perception_v3_1 import judge_held_item as held_judge
    pose = {int(s): int(pwm[s]) for s in (3, 4, 5, 6)}
    held = held_judge(frame_bgr, pose, expected_kind=kind, grasp_pose=dict(grasp_pose))
    answer = held['answer']
    record = {'evidence': 'kind_in_at_grip_band', 'answer': answer,
              'reason': held.get('reason'), 'v3_reason': held.get('v3_reason'),
              'observed': held.get('observed'), 'image_information': held.get('image_information')}
    if answer in ('yes', 'no'):
        return answer, record
    if held.get('v3_reason') != NOT_FRAMED:
        return 'unknown', record
    if slot_judge is None:
        from harness.zone_own_perception import judge_slot_item as slot_judge
    slot = slot_judge(frame_bgr, pose, slot_base_xy=[float(floor_xy[0]), float(floor_xy[1])],
                      expected_kind=kind)
    record = {'evidence': 'original_floor_spot', 'held_check': record, 'answer': slot['answer'],
              'reason': slot.get('reason'), 'observed': slot.get('observed')}
    if slot['answer'] == 'no' and slot.get('observed') == 'empty':
        return 'yes', record          # bare floor where the cargo stood: it left the floor
    if slot['answer'] == 'yes':
        return 'no', record           # the ordered kind is still standing there
    return 'unknown', record


class SoloLiftObserver:
    """Opt-in solo_rgb_lift_v2: own BGR and issued command history only.

    Capture at close->lift before the raise command, after its scheduled
    completion, and after three seconds stationary. Recheck every hold tick so
    an earlier confirmation cannot authorize set-down after a visual loss.
    """
    def __init__(self, kind):
        if kind not in ('cyan', 'red', 'green', 'yellow', 'can', 'tile'):
            raise ValueError('solo cargo kind required')
        self.kind = kind
        self.before = self.after = None
        self.completed_at = None
        self.commands = []
        self.samples = {}
        self.answer_counts = {'yes': 0, 'no': 0, 'unknown': 0}
        self.last = None

    def _masks(self, bgr):
        import cv2
        from harness.zone_own_perception import hue_mask, _usable_region
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        return ((hue_mask(hsv, self.kind) > 0) & _usable_region(bgr.shape[1], bgr.shape[0]),)

    def start(self, frame, command, save):
        import copy
        self.before = frame.copy()
        self.commands = [copy.deepcopy(command)]
        self.samples['before_lift'] = save('before_lift', frame, command['t'])

    def observe(self, frame, command, *, complete, save):
        import copy
        from sim.rgb_lift_evidence import SETTLE_S, confirm_parts_v2
        out = {'evidence': 'solo_rgb_lift_v2', 'answer': 'unknown', 'verdict': 'undetermined',
               'reason': 'before lift frame missing'}
        if self.before is not None:
            if self.after is None:
                self.commands.append(copy.deepcopy(command))
                if complete:
                    self.after = frame.copy()
                    self.completed_at = command['t']
                    self.samples['lift_complete'] = save('lift_complete', frame, command['t'])
            if self.after is None:
                out['reason'] = 'issued lift completion pending'
            else:
                settled = frame if command['t']-self.completed_at >= SETTLE_S-1e-8 else None
                if settled is not None and 'settled_hold' not in self.samples:
                    self.samples['settled_hold'] = save('settled_hold', frame, command['t'])
                rec = confirm_parts_v2(self.before, self.after, commands=self.commands,
                                      masks=self._masks, names=(self.kind,), settled=settled,
                                      rule='solo_rgb_lift_v2')
                # A later incompatible command cannot reuse a cached yes.
                current = {int(s): v for s, v in command['pwm'].items()}
                final = {int(s): v for s, v in self.commands[-1]['pwm'].items()}
                if any(command['wheels']) or current != final:
                    rec.update(verdict='undetermined', reason='hold issued command changed')
                out = {**rec, 'evidence': 'solo_rgb_lift_v2',
                       'answer': {'confirmed': 'yes', 'not_confirmed': 'no', 'undetermined': 'unknown'}[rec['verdict']],
                       'samples': dict(self.samples), 'completed_at': self.completed_at,
                       'settled_s': command['t']-self.completed_at}
        self.answer_counts[out['answer']] += 1
        self.last = out
        return out

    def record(self):
        return {'mode': 'solo_rgb_lift_v2', 'samples': self.samples,
                'answer_counts': self.answer_counts, 'last': self.last}
