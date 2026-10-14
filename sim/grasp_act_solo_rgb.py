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
              'observed': held.get('observed')}
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
