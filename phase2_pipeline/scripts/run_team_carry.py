"""Two or three robots (up to nine with a generated map scene), one world, and a planner that decides (development run).

Each robot runs the unchanged Solo motions. The robots are the ones of the designed scene (2 or 3, in the scene's order). Three things are decided by the team planner instead of by the task:
which box of its own look-around list a robot picks, which floor-colour zone it carries the held box to, and when it
goes to the door. The planner is reached through three calls (tell / decide / record); it may be an LLM team on
another host or the fixed reference plan below. It gets only what each robot has: its own list, the orders the task
gave that robot, its own progress, and the messages the planner itself delivered.

Evaluation side only (never passed to the planner): which object a chosen entry is, where the boxes end up.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.request

from harness.grasp_act_data import write_json
import scripts.run_grasp_act_student as solo
from scripts.run_duo_carry import second_task

import importlib.util as _ilu


class _LazyMapScene:
    """harness/map_scene_v1.py (generated map scenes, DEFAULT off), loaded BY FILE PATH on the first use of one of its names (standard library
    only). A scene without an `arena` key never touches it, so the module is not even read in a run without the switch."""
    _module = None

    def __getattr__(self, name):
        if _LazyMapScene._module is None:
            spec = _ilu.spec_from_file_location('map_scene_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'map_scene_v1.py'))
            module = _ilu.module_from_spec(spec)
            spec.loader.exec_module(module)
            _LazyMapScene._module = module
        return getattr(_LazyMapScene._module, name)


map_scene_v1 = _LazyMapScene()


class _LazyRenderCull:
    """harness/render_cull_v1.py (output-exact frustum culling of the camera renders, DEFAULT off), loaded BY FILE PATH on the first use of one of its names
    (the frozen scene package replaces `harness` during a run). Without --render-cull / --render-cull-verify the file is not even read."""
    _module = None

    def __getattr__(self, name):
        if _LazyRenderCull._module is None:
            spec = _ilu.spec_from_file_location('render_cull_v1', str(Path(__file__).resolve().parent.parent / 'harness' / 'render_cull_v1.py'))
            module = _ilu.module_from_spec(spec)
            spec.loader.exec_module(module)
            _LazyRenderCull._module = module
        return getattr(_LazyRenderCull._module, name)


render_cull_v1 = _LazyRenderCull()

NAME = {'cyan': 'blue', 'red': 'red', 'green': 'red'}   # the 'green' task object is drawn red
ZONES = ('orange', 'blue', 'purple')
SIGN_ZONES = ('sign11', 'sign12', 'sign13')   # destinations marked by number signs on walls (with --robot-tags)
SIGN_RECT = {'sign11': (4.72, 5.375, -0.10, 0.90), 'sign12': (4.72, 5.375, -2.60, -1.60), 'sign13': (2.90, 3.90, -3.125, -2.47)}
RETHINK_S = 20.
DOOR_GO_TEXT = 'carry the box through the door now (one robot at a time fits)'
DOOR_GO_TEXT_MAP = 'carry the box through its door now (one robot at a time fits through a door)'    # a map scene with several doors


def PATCH_FROZEN_WORLD(ids):
    """Generated map scenes: let the frozen multi-robot world build the robots `ids` (harness/map_scene_v1.patch_frozen_world). An offline test
    with a fake motion replaces this name."""
    return map_scene_v1.patch_frozen_world(ids)


def natural_robots(robots):
    """Robot ids in number order (plain string order puts 'r10' before 'r2'). The same as sorted() for the ids r1..r9 (and for any ids that are
    not 'r<number>': those sort by plain string after the numbered ones)."""
    def key(rid):
        m = re.fullmatch(r'r([0-9]+)', rid)
        return (0, int(m.group(1)), rid) if m else (1, 0, rid)
    return sorted(robots, key=key)
RECT = {'orange': (4.3, 4.9, -0.3, 1.1), 'blue': (4.3, 4.9, -2.8, -1.4), 'purple': (2.7, 3.3, -1.55, -0.15)}


class ChanceHostError(RuntimeError):
    """The planner host cannot answer a chance poll (it is older than the one that marks replies written at a chance)."""


class RemoteBrain:
    """The planner runs on another host (it holds the model key); calls go over a forwarded local port."""
    def __init__(self, url):
        self.url = url.rstrip('/')

    def _post(self, path, body):
        request = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=600) as reply:
            return json.loads(reply.read())

    def tell(self, rid, facts):
        self._post('/tell', {'rid': rid, 'facts': facts})

    def decide(self, rid, now_s, point, options):
        return self._post('/decide', {'rid': rid, 'now_s': now_s, 'point': point, 'options': options})

    def poll(self, rid, now_s):
        return bool(self._post('/poll', {'rid': rid, 'now_s': now_s}).get('new'))

    def chance(self, rid, now_s):
        """A message chance between decisions (planner side: TeamBrain.chance; an older planner host answers 404 and the bridge stops asking)."""
        return self._post('/chance', {'rid': rid, 'now_s': now_s})

    def chance_poll(self, rid, now_s):
        """Has a message written at a teammate's decision point reached the robot since its last planner contact (decision or chance)? Only
        such a message opens a message chance; a reply written at a chance (via='chance') does not (the same /poll with chance=true; the
        plain poll above counts every message). A host that does not know the flag answers without the echo: ChanceHostError."""
        out = self._post('/poll', {'rid': rid, 'now_s': now_s, 'chance': True})
        if not out.get('chance'):
            raise ChanceHostError('the planner host does not know the chance poll (older brain_server.py)')
        return bool(out.get('new'))

    def record(self):
        return self._post('/record', {})


def nearest_listed_box(colour, options):
    """Key of the nearest box of `colour` in the robot's own look-around list (the distance is the 'N.N m away' of the option
    text, from the robot's own camera list; the lowest entry on a tie), or 'wait'. Taking the first box of the colour let two
    robots take the same box when a scene has two boxes of one colour (3-robot gate on 274d748: K303 r2/r3, L301 r1/r3,
    L302 r2/r3 chose the box that belongs to the lower-numbered robot; the nearest box is the scene's oracle box for 15/15
    robots of K301-K303, L301, L302)."""
    found = []
    for i, o in enumerate(options):
        if '<%s box>' % colour in o['text']:
            m = re.search(r'([0-9]+(?:\.[0-9]+)?) m away', o['text'])
            found.append((float(m.group(1)) if m else float('inf'), i, o['key']))
    return min(found)[2] if found else 'wait'


# Generated map scenes (phase 2): the reference plan names the BOX of every robot (its world place), not "the nearest box of the colour". Two robots of one
# colour whose nearest box of that colour is the same box would both go for it (phase2 maps VM run N=4: r1 and r2 on one box, 0/4 delivered).
PICK_OPTION_RE = re.compile(r'<(\w+) box> in the box room, ([0-9]+(?:\.[0-9]+)?) m away, (?:straight ahead of me|([0-9]+)\u00b0 (left|right) of me)')
ASSIGNED_TOL_M = 0.30          # an option is the assigned box when its place is this close to the box (the text rounds to 0.1 m and 1 degree: < 0.09 m up to 3.5 m;
                               # generated maps keep their boxes >= 0.6 m apart, so 0.30 m never fits two boxes)
ASSIGNED_REPICK_TOL_M = 1.0    # after an empty gripper the box may have been pushed: the same rule with this tolerance (an option that is another robot's target is never taken)


def option_world_xy(text, pose):
    """(colour, (x, y)) of the box a pick option names, in the frame of `pose` = (x, y, yaw) of the robot when it looked around ('<red box> in the box room,
    1.6 m away, 16 deg left of me': bearing positive = left). None for any other option text."""
    found = PICK_OPTION_RE.search(text)
    if not found:
        return None
    dist = float(found.group(2))
    bearing = 0. if found.group(3) is None else (1 if found.group(4) == 'left' else -1) * math.radians(int(found.group(3)))
    x, y, yaw = pose
    return found.group(1), (x + dist * math.cos(yaw + bearing), y + dist * math.sin(yaw + bearing))


def world_pose(shared, rid):
    """(x, y, yaw) of the robot in the world right now, or None (no world yet, or a stand-in world without robot poses)."""
    world = shared.get('world')
    try:
        xyz, rpy = world.robot(rid).base_xyz(), world.robot(rid).base_rpy()
        return float(xyz[0]), float(xyz[1]), float(rpy[2])
    except (AttributeError, KeyError, TypeError, IndexError):
        return None


class FixedPlan:
    """Reference condition, not a planner: a fixed assignment and a fixed door order (first robot, then the next; for
    three robots the robot numbers in order)."""
    sends_messages = False      # nothing is ever delivered to a robot: a destination is never asked again
    chooses_moves = False       # --llm-moves does nothing for a reference plan: it is never offered a move and never asked while it waits

    def __init__(self, assignment, order, doors=None, targets=None, after=None, starts=None):
        self.assignment, self.order, self.done, self.log = assignment, list(order), set(), []
        # generated map scenes (phase 2). Without `targets` nothing below is used and the plan answers as before.
        # targets: robot -> {'box': box id, 'xy': (x, y)}, the box the plan sends the robot to; the pick answer is the listed box at that place.
        # after: robot -> robots whose carry must have finished (or whose run is over) before it goes to the door (a precedence rule: the later box is
        #   carried only after the prior one). starts: robot -> (x, y, yaw), where it looks around the first time. pose_source: rid -> (x, y, yaw) now
        #   (the bridge sets it from the world; a robot that looks around again after an empty gripper stands somewhere else).
        self.targets, self.after, self.starts, self.pose_source, self.pick_log = dict(targets or {}), {r: list(v) for r, v in (after or {}).items()}, dict(starts or {}), None, []
        self.ended = set()     # robots whose run is over, for any reason: they will not use the door again
        # one queue per door (generated map scenes): robot -> the door it carries through. `doors` is the guess from the scene (the box place);
        # the motion code names the door it really chose (set_door, at the door question). Without it (the old arena: one door) every robot
        # has the door None and the queue is the one of before: the same robots, so the same answers.
        self.doors = dict(doors or {})

    def set_door(self, rid, door):
        """The motion code's choice of door for the robot's carry (generated map scenes)."""
        self.doors[rid] = door

    def same_door(self, a, b):
        return self.doors.get(a) == self.doors.get(b)

    def tell(self, rid, facts):
        if facts.get('milestone') == 'carry_finished':
            self.done.add(rid)

    def robot_ended(self, rid):
        """The bridge calls this when a robot's run is over (carried and finished, or an empty gripper with no regrasp left, which
        never produces 'carry_finished'). Such a robot does not use the door again, so it must not hold the later robots back:
        baseline diag 20261116, L2-02 and L2-04 stood at the door until the 900 s cap behind an r1 that had ended without a carry.
        The door order itself is not changed."""
        self.ended.add(rid)

    def assigned_box(self, rid, colour, options, now_s, other_xy=None):
        """The pick answer of a robot that has a target box: the option of `colour` whose place (from the robot's pose when it looked around) is the nearest to
        the target and within the tolerance. The first look-around is at the start pose unless the bridge gives the live pose; a later one (empty gripper) needs
        the live pose. A box that is not listed, or no pose: the robot FINISHES (never the nearest box of the colour: that is the bug this replaces), the reason
        is in the pick log."""
        target = self.targets[rid]
        first = not any(e['rid'] == rid and e['option'] != LOOK_AROUND_KEY and (other_xy is None or e['box'] == target['box'])
                        for e in self.pick_log)
        if other_xy is None:
            other_xy = [t['xy'] for r, t in self.targets.items() if r != rid]
        pose, source = (self.pose_source(rid) if self.pose_source else None), 'live'
        if pose is None and first:
            pose, source = self.starts.get(rid), 'start'
        entry = {'rid': rid, 't': now_s, 'box': target['box'], 'target_xy': list(target['xy']), 'first': first, 'pose_source': source if pose is not None else None}
        best = None
        for o in options if pose is not None else ():
            seen = option_world_xy(o['text'], pose)
            if seen and seen[0] == colour and not any(math.dist(seen[1], xy) <= ASSIGNED_TOL_M for xy in other_xy):
                gap = math.hypot(seen[1][0] - target['xy'][0], seen[1][1] - target['xy'][1])
                if best is None or gap < best[0]:
                    best = (gap, o['key'], seen[1])
        tol = ASSIGNED_TOL_M if first and not (getattr(self, 'wide_second_pick', False) and getattr(self, 'trip', {}).get(rid, 0) >= 1) else ASSIGNED_REPICK_TOL_M
        if best is not None and best[0] <= tol:
            entry.update(option=best[1], resolved_xy=[round(best[2][0], 3), round(best[2][1], 3)], residual_m=round(best[0], 3), reason='assigned_box')
        else:
            entry.update(option='finish', residual_m=None if best is None else round(best[0], 3),
                         reason='no_pose' if pose is None else 'assigned_box_not_listed')
        self.pick_log.append(entry)
        return entry['option']

    def pick_option(self, rid, colour, options, now_s, other_xy=None):
        can_look = any(o['key'] == LOOK_AROUND_KEY for o in options)
        if rid not in self.targets:
            pick = nearest_listed_box(colour, options)
            return LOOK_AROUND_KEY if pick == 'wait' and can_look else pick
        pick = self.assigned_box(rid, colour, options, now_s, other_xy)
        if pick == 'finish' and can_look and self.pick_log[-1]['reason'] == 'assigned_box_not_listed':
            self.pick_log[-1]['option'] = pick = LOOK_AROUND_KEY
        return pick

    def decide(self, rid, now_s, point, options):
        if rid not in self.assignment:
            # this robot has nothing to do in the plan (a designed scene can leave one robot idle): it ends
            self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': 'none'})
            return {'option': 'none', 'wait_s': 2.0, 'sent': [], 'calls': 0}
        colour, zone = self.assignment[rid]
        keys = [o['key'] for o in options]
        if point == 'pick':
            pick = self.pick_option(rid, colour, options, now_s)
        elif point == 'destination':
            pick = 'zone:' + zone
        elif point == 'door':
            ahead = [r for r in self.order[:self.order.index(rid)] if r not in self.ended and self.same_door(r, rid)]
            pick = 'go' if all(r in self.done for r in ahead) else 'wait'
            if pick == 'go' and any(r not in self.done and r not in self.ended for r in self.after.get(rid, ())):
                pick = 'wait'                 # a precedence rule: the robot that carries the prior box has not finished its carry
        else:
            pick = keys[0]
        self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': pick})
        return {'option': pick, 'wait_s': 2.0, 'sent': [], 'calls': 0}

    def poll(self, rid, now_s):
        return True

    def record(self):
        return dict({'kind': 'fixed_plan', 'assignment': self.assignment, 'door_order': self.order, 'decisions': self.log},
                    **({'doors': self.doors} if self.doors else {}),
                    **({'targets': {r: dict(t) for r, t in self.targets.items()}, 'after': self.after, 'picks': self.pick_log} if self.targets or self.after else {}))


class MultiFixedPlan(FixedPlan):
    """--multi-carry reference condition (not a planner): every robot has a list of carries (colour, zone) in trip order (the scene's
    oracle_plan, robot by robot). The pick and destination answers follow the robot's current carry; at 'next' it goes back while
    carries are left and finishes after the last one (FixedPlan.decide's else branch would answer the first option, 'back').
    The door queue serves ready, precedence-eligible robots in plan order. The oracle identifies each trip's box by place.
    Only an at-zone release satisfies a predecessor. A robot is
    'on its way' from its 'go' until it tells the plan that its carry has finished, and a robot that is between carries (picking, on
    its way back) or whose run is over does not hold the others back. Meetings at the door from opposite sides are the motion code's
    (harness/carry_nav_v1.door_right_of_way), not the plan's."""

    def __init__(self, assignment, order, doors=None, *, itinerary=None, starts=None, prerequisites=None):
        self.itinerary = itinerary or {}
        super().__init__({r: list(v) for r, v in assignment.items() if v}, order, doors,
                         targets={r: trips[0] for r, trips in self.itinerary.items()}, starts=starts)
        self.prerequisites = prerequisites or {}      # order -> box ids that must already have been set down at their zones
        self.delivered_boxes = set()
        self.trip = {r: 0 for r in assignment}                  # index of the robot's current carry
        self.ready, self.went, self.ended = set(), set(), set()

    def current(self, rid):
        carries = self.assignment[rid]
        return carries[min(self.trip[rid], len(carries) - 1)]

    def tell(self, rid, facts):
        if rid in self.trip and facts.get('trip', self.trip[rid] + 1) != self.trip[rid] + 1:
            return
        if rid in self.targets and facts.get('milestone') == 'carry_finished' and facts.get('outcome') == 'at_zone':
            self.delivered_boxes.add(self.targets[rid]['box'])
        if facts.get('milestone') in ('carry_finished', 'grasp_failed'):
            self.went.discard(rid)                              # its carry is over (or it holds nothing again): not on its way
            self.ready.discard(rid)

    def eligible(self, rid):
        order = self.targets.get(rid, {}).get('order')
        return self.delivered_boxes.issuperset(self.prerequisites.get(order, ()))

    def robot_ended(self, rid):
        """The bridge calls this when a robot's run is over: it will not use the door again."""
        self.ended.add(rid)
        self.went.discard(rid)
        self.ready.discard(rid)

    def decide(self, rid, now_s, point, options):
        if rid not in self.assignment:
            self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': 'none'})
            return {'option': 'none', 'wait_s': 2.0, 'sent': [], 'calls': 0}
        colour, zone = self.current(rid)
        keys = [o['key'] for o in options]
        if point == 'pick':
            other_xy = [t['xy'] for trips in self.itinerary.values() for t in trips if t['box'] != self.targets[rid]['box']]
            pick = self.pick_option(rid, colour, options, now_s, other_xy)
        elif point == 'destination':
            pick = 'zone:' + zone
            self.ready.add(rid)
        elif point == 'door':
            ahead = [r for r in self.order[:self.order.index(rid)] if r not in self.ended and self.same_door(r, rid)]
            on_the_way = any(r in self.went for r in self.order if r != rid and self.same_door(r, rid))
            ahead_waits = any(r in self.ready and r not in self.went and self.eligible(r) for r in ahead)
            pick = 'wait' if on_the_way or ahead_waits or not self.eligible(rid) else 'go'
            if pick == 'go':
                self.went.add(rid)
                self.ready.discard(rid)
        elif point == 'next':
            self.trip[rid] += 1
            pick = 'back' if self.trip[rid] < len(self.assignment[rid]) else 'finish'
            if pick == 'back' and rid in self.itinerary:
                self.targets[rid] = self.itinerary[rid][self.trip[rid]]
                self.starts.pop(rid, None)    # subsequent lists are relative to the return pose
                if 'door' in self.targets[rid]:
                    self.set_door(rid, self.targets[rid]['door'])
        else:
            pick = keys[0]
        self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': pick})
        return {'option': pick, 'wait_s': 2.0, 'sent': [], 'calls': 0}

    def return_hint(self, rid):
        """--oracle-return-face: where the plan says the robot's next box is (world frame), once the robot has been sent back for it."""
        target = self.targets.get(rid)
        return None if target is None else list(target['xy'])

    def record(self):
        record = dict(super().record(), multi_carry=True)
        if self.itinerary:
            record.update(itinerary=self.itinerary, prerequisites={o: sorted(boxes) for o, boxes in self.prerequisites.items()},
                          delivered_boxes=sorted(self.delivered_boxes))
        return record


def room_of(events):
    """What the planner is told about its own position (room level), from the robot's own progress only: in the box room
    until its own 'door_passed' event exists, then in the destination room (no ceiling camera, no 'near the door' hint)."""
    return 'in the destination room' if 'door_passed' in events else 'in the box room'


DEST_LISTEN_S = 4.0   # message delay 2 s (brain): a higher-numbered robot listens twice that before choosing a destination
# With three robots the listening time is rank-based: the lowest-numbered robot listens 0 s, the next DEST_LISTEN_S (4 s),
# the highest 2 * DEST_LISTEN_S (8 s). Each robot then hears what every lower-numbered robot sent when it chose.
# (Two robots: 0 s and 4 s, as before.)
CAPABLE_COLOURS = ('red', 'blue')


def listen_scale(unit=None):
    """Factor on the listening time DEST_LISTEN_S * rank for the experiment condition --listen-s (the listening unit in
    seconds instead of DEST_LISTEN_S; 0 = nobody listens). 1 without the switch, so the default rule is unchanged."""
    return 1. if unit is None else unit / DEST_LISTEN_S


def full_info_knows(orders, robots):
    """Experiment condition --full-info (full-information control): every robot is told every order of the team, as its own."""
    return {r_: tuple(o['id'] for o in orders) for r_ in robots}


def box_label(rid, index, trip=1, look=1):
    """Robot-scoped name of an entry of the robot's own look-around list. The bare entry number is private to each robot,
    and robots wrote "please take entry 1" that the receiver read as its own entry 1 (analysis:
    a work record). The label names the owner; option keys ('box:%d') are unchanged.
    It is only a secondary handle: a receiver cannot match it to its own list, so a box is described first by its colour,
    its room and where it is relative to the robot (adopted external review: a work record)."""
    if look != 1:
        # --llm-moves: the robot looked around again where it stood (its list restarts at 0 and may list other entries)
        return '%s-t%d-l%d-box%d' % (rid, trip, look, index) if trip != 1 else '%s-l%d-box%d' % (rid, look, index)
    if trip != 1:
        return '%s-t%d-box%d' % (rid, trip, index)    # --multi-carry: a later carry of the robot (its list restarts at 0 every look-around)
    return '%s-box%d' % (rid, index)


def relation_text(bearing_deg):
    """Where a box is relative to the robot (bearing: positive = left of the robot's heading)."""
    if abs(bearing_deg) < 5:
        return 'straight ahead of me'
    return '%d\u00b0 %s of me' % (abs(bearing_deg), 'left' if bearing_deg > 0 else 'right')


def box_where(entry):
    """'in the box room, 0.8 m away, 20 deg left of me': boxes are seen at the start, and the robot starts in the box room."""
    return 'in the box room, %.1f m away, %s' % (entry['distance_m'], relation_text(round(math.degrees(entry['bearing_rad']))))


# Carry outcomes the motion code computes from the ceiling-camera positions of OTHER robots (door busy, something beyond the
# door). The planner is not told which of them it was (input-leak audit: a work record): a structure
# that can relay messages (T1/T2) would otherwise pass other robots' positions on, one that cannot (T0) would not.
OTHER_ROBOT_OUTCOMES = ('something_stands_beyond_the_door', 'no_clear_way_to_door')


def carry_end_text(outcome):
    """What the robot tells its planner when its carry has ended (own-camera outcomes as they are)."""
    if outcome in OTHER_ROBOT_OUTCOMES:
        return 'I could not get through the door.'
    return 'My carry has ended (%s).' % outcome


# Ordinary early stops release the box in place. A failed close confirmation ends with the gripper closed.
# The planner used to be told only the outcome and went on believing the robot held
# the box (action audit 2026-11-15, 7 of 7 reports read). 'box_not_held': the gripper was empty, the robot looks around and picks again.
CARRY_STOPPED_TEXT = 'My carry stopped before the zone. I set the box down where I stand and my run ends here.'
CARRY_NOT_STOPPED_OUTCOMES = ('at_zone', 'box_not_held')


def carry_end_report(outcome, dest=None, multi_carry=False):
    """What the planner is told when the carry has ended. Delivered (at_zone): where the robot set the box down, its own destination
    ('zone_sign12' -> 'I set the box down at the <sign12 zone>; my run ends here.', the bracket written as in the destination options;
    nothing about whether that was the right place). Stopped before the zone: carry_end_text(outcome) (the door outcomes still do not say where the other robots are) and the
    plain fact that the box was set down in place and the run ends. box_not_held: carry_end_text only (the robot looks around again)."""
    if outcome == 'zone_unconfirmed':
        return 'I could not confirm my destination. I have stopped with the box still in my gripper. My run ends here.'
    text = carry_end_text(outcome)
    if multi_carry and outcome == 'at_zone':
        # --multi-carry: the robot may go on after a delivery, so the text does not say that its run ends
        return 'I set the box down at the <%s zone>.' % dest[5:] if dest and dest.startswith('zone_') else text
    if multi_carry and outcome == PUT_DOWN:
        return 'I set the box down where I stand.'
    if outcome == 'at_zone':
        return 'I set the box down at the <%s zone>; my run ends here.' % dest[5:] if dest and dest.startswith('zone_') else text
    return text if outcome in CARRY_NOT_STOPPED_OUTCOMES else text + ' ' + CARRY_STOPPED_TEXT


def carry_end_option_text(outcome):
    """The only choice at the report that follows a carry: the run ends there (box_not_held: the robot looks around and picks again)."""
    return 'continue my task' if outcome == 'box_not_held' else 'finish my run'


def capability_text(allowed):
    """The robot's own capability, told to its planner at the start (a robot knows its own capability, not the others')."""
    if not allowed:
        return 'I cannot grasp any box.'
    return 'I can only grasp %s boxes.' % ' and '.join('<%s>' % c for c in allowed)


CHANCE_POLL_S = 1.    # a robot between decision points looks for a new message once per this many simulated seconds (as REDECIDE_POLL_S)
# Star route (planner --leader-route star; no switch here): the planner marks every decision answer of the leader with relay=True. When such a robot's own run is over
# (carry delivered, box put down, finish, any end of its run_steps) it stays in the conversation while a teammate is still running: once per RELAY_POLL_S it asks the
# planner whether a message is new (brain.poll) and, when so, asks the point 'relay' (the one option 'wait', plus the planner's say entries). The body is not moved.
RELAY_POLL_S = 1.
RELAY_OPTIONS = [{'key': 'wait', 'text': 'stay here and keep relaying for the team'}]


def talk_stand_until(now, answer):
    """Free talk (planner --talk free): the time until which the body stands because the planner's answer is a speech, or None. A speech is marked by
    say_s in the answer (only the free-talk planner writes it) together with a message that used the turn (sent, not sent_with_action). The stand is the
    rule of ask() (turn_used): max(2, wait_s) simulated seconds from the answer, wait_s being the say time t_say. Any other answer (an older planner,
    free talk off, a message sent together with an action) gives None: nothing is changed for it."""
    if answer.get('say_s') is None or not answer.get('sent') or answer.get('sent_with_action'):
        return None
    return now + max(2., float(answer.get('wait_s') or 2.))


def talk_stand(state, now, answer, path, hold=True):
    """Free talk: note a speech of the robot (state['talk_stands'], written to team.json only when one happened) and, with hold, let the body stand until
    its end (state['stand_until'], read by run_steps through stand_hold and by ask()). hold=False for the decision points whose own wait already stands
    the body (ask(): turn_used). Returns the end time or None (not a speech; the state is then not touched)."""
    until = talk_stand_until(now, answer)
    if until is None:
        return None
    if hold:
        state['stand_until'] = until if state.get('stand_until') is None else max(state['stand_until'], until)
    state.setdefault('talk_stands', []).append({'t': round(now, 1), 'path': path, 'say_s': answer.get('say_s'), 'stand_s': round(until - now, 3),
                                                'via': 'stand_hold' if hold else 'wait'})
    return until



def message_chance(rid, brain, clock, chances, state):
    """A reply chance between decision points (user decision 2026-11-15, replaces the chance every 15 simulated s): when a message
    has been delivered to the robot since its last planner contact (a decision, a report or the last chance) and its own hooks have
    no decision point open (state['decision_open'](): see hooks), the planner may let it answer (one draft step; an empty draft is
    silence). No new message, no chance. Only a message written at a teammate's DECISION POINT counts (brain.chance_poll, the poll of
    the destination re-decision with chance=true): a reply written at a chance does not open a chance for its receivers, so a message gets
    at most one reply per teammate and the replies do not chain (the receivers still read it at their next decision, and the re-decision
    poll, brain.poll, still reacts to it). The poll is made once per CHANCE_POLL_S simulated seconds and only while no decision
    point is open. A chance counts as a planner contact like a decision: the planner host moves its 'seen' marks (brain_server.py
    /chance), so the same message is answered once; a host that does not (poll still true right after the chance) would be asked again
    every poll, so the robot's chances are turned off then ('poll_still_new' in chances). A brain without chance_poll (or a host that does
    not know the flag: ChanceHostError, recorded like any error) gets no chances. The call is made between two control ticks of the
    shared world, so the simulated clock does not run while the planner thinks, exactly as at a decision point. Nothing is told to the planner (no new text, no position); a brain
    without chance() (the fixed plan, an older planner) never gets one. The optional step cannot end a run: an error turns this robot's
    chances off. T0 gets none (no message ever reaches it). No chance once the robot's run is over: run_team turns them off at the
    carry end (delivered, stopped, put down) and a chosen put-down does too, because the robot still moves (lowers the arm, releases the
    box) for a while. Returns True when the planner called the model."""
    chance, new_message = getattr(brain, 'chance', None), getattr(brain, 'chance_poll', None)
    if (chance is None or new_message is None or not getattr(brain, 'sends_messages', True) or state.get('chance_off') or state.get('halted')
            or state.get('dest') == PUT_DOWN):
        return False
    now = clock()
    if now < state.get('chance_poll', 0.):
        return False
    decision_open = state.get('decision_open')
    if decision_open is not None and decision_open():
        return False                      # the robot's own decision point will take the new message (with its own draft)
    state['chance_poll'] = now + CHANCE_POLL_S
    try:
        if not new_message(rid, now):
            return False                  # nothing new (from a decision point of a teammate) since the last planner contact: no chance
        answer = chance(rid, now)
        talk_stand(state, now, answer, 'chance')      # free talk: the robot speaks, so its body stands (no effect for an answer without say_s)
        if answer.get('final'):
            state['chance_off'] = True
        if answer.get('asked') or answer.get('sent'):
            chances.append({'t': round(now, 1), 'rid': rid, 'sent': answer.get('sent', []), 'calls': answer.get('calls')})
        if not state.get('chance_off') and new_message(rid, now):
            state['chance_off'] = True
            chances.append({'t': round(now, 1), 'rid': rid, 'error': 'poll_still_new'})
    except Exception as exc:
        state['chance_off'] = True
        chances.append({'t': round(now, 1), 'rid': rid, 'error': type(exc).__name__})
        return False
    return bool(answer.get('asked'))


# --look-around-option (DEFAULT off): the pick point also offers to look around again (the planner's option key and text; the key is passed through
# by the planner copy unchanged). Chosen, the motion code runs the look-around routine again and the pick point is asked again with the new list.
# Offered at most LOOK_AROUND_MAX times per robot. Without a box of a colour the robot can grasp in the list the planner is asked as well (the robot's
# run does not end there) while looks are left.
LOOK_AROUND_KEY = 'look_around'
LOOK_AROUND_TEXT = 'look around again (turn in place and refresh my box list)'
LOOK_AROUND_MAX = 3

PUT_DOWN = 'put_down'     # destination option 'put the box I am holding down here and finish' (key; also the value in choices/dest)
REDECIDE_POLL_S = 1.      # while carrying towards the door the robot looks for a new message once per this many seconds
REDECIDE_MAX_ASKS = 3     # asks of the destination point for one batch of new messages (the planner may send a message first)


def put_down_text(multi_carry=False):
    """--multi-carry: after a put-down the robot is asked what to do next, so the option does not say that it finishes."""
    return 'put the box I am holding down here' if multi_carry else 'put the box I am holding down here and finish'


# --llm-moves (DEFAULT off): small moves the planner may choose. The planner names the move, the motion code does it (harness/llm_moves_v1.py).
# key -> (kind, option text). Offered at: the pick question (with the list; also when nothing graspable is in sight), the door question
# (holding the box: back off / step aside only, a look-around would open the gripper), and the 'blocked' question the motion code puts while it
# keeps the robot still on the way to its box. Not at the destination question and not at 'next'.
MOVE_OPTIONS = {'move:back': ('back', 'back off a little'),
                'move:aside': ('aside', 'step aside to let a teammate pass'),
                'move:look': ('look', 'look around here')}
MOVES_MAX, LOOKS_MAX, EMPTY_ASKS_MAX = 3, 2, 3     # moves per robot and run (any kind), of them look-arounds; asks at an empty list (then the run ends as before)
BLOCKED = 'blocked'                                # decision point of the yield stop (planner side: brain/__init__.py)
KEEP_WAITING = {'key': 'wait', 'text': 'keep waiting here'}


def move_options(kinds):
    return [{'key': k, 'text': t} for k, (kind, t) in MOVE_OPTIONS.items() if kind in kinds]


def move_result_text(result):
    """What the robot tells its planner after a move: its own outcome only (no cause beyond 'something in the way', nothing about where anybody is)."""
    kind, status = result['kind'], result['status']
    name = {'back': 'back off a little', 'aside': 'step aside', 'look': 'look around again here'}[kind]
    if status == 'refused':
        why = {'no_room_behind': 'there is no room behind me', 'no_room_beside': 'there is no room beside me'}.get(result.get('reason'), 'I could not do it now')
        return 'I could not %s: %s.' % (name, why)
    if status == 'stopped':
        return 'I started to %s but stopped early because something was in the way.' % name
    return {'back': 'I backed off a little.', 'aside': 'I stepped aside.', 'look': 'I looked around again here.'}[kind]


def destination_options(multi_carry=False):
    return [{'key': 'zone:' + z, 'text': 'transport the box I am holding to the <%s zone>' % z} for z in ZONES] \
        + [{'key': 'wait', 'text': 'wait here, holding the box'},
           # a box that no order asks for must not be carried to a zone (counts as an error); the robot may put it down and finish
           # (same for all structures, like 'finish' at the pick point)
           {'key': PUT_DOWN, 'text': put_down_text(multi_carry)}]


def door_options(multi_carry=False, moves=()):
    return [{'key': 'go', 'text': DOOR_GO_TEXT},
            {'key': 'wait', 'text': 'wait here before going to the door'},
            # the same line as at the destination question (a robot that holds a box no order asks for is stuck at both)
            {'key': PUT_DOWN, 'text': put_down_text(multi_carry)}] + list(moves)


MAX_TRIPS = 3        # --multi-carry: the most carries one robot makes; the planner is asked 'next' only below this
NEXT = 'next'        # --multi-carry decision point after a delivery or a put-down: go back for another box, or finish


def next_options(in_destination_room):
    """--multi-carry: the choice after a delivery (the robot is in the destination room) or a put-down (still in the box room)."""
    return [{'key': 'back', 'text': 'go back to the box room for another box' if in_destination_room
             else 'look around the box room again for another box'},
            {'key': 'finish', 'text': 'finish my run'}]


def hooks(rid, brain, clock, log, where=None, listen_s=0., can_grasp=None, redecide=False, passed=None, multi_carry=False, llm_moves=False,
          door_of=None, look_around=False):
    """can_grasp (DEFAULT None = every colour): the colours this robot is able to grasp. Only the pick options are
    limited to those colours; the seen-boxes fact still lists every box the robot saw, each box of another colour with the
    note 'I cannot grasp this colour' (so the planner can tell a teammate about it; scene design DESIGN-COOP.md).

    redecide (DEFAULT False = the destination is chosen once and stays): when a new message has been delivered to the
    robot after it chose its destination and before it passes the door (passed() true), the planner is asked the
    destination point again with the same options, once per batch of new messages (a robot that cannot get messages,
    such as T0 or the fixed plan, never triggers it). Option 'wait' or no option keeps the destination chosen before.
    The answer is handed to the motion code through the same carry_to callable (run_steps(redecide=True)).

    look_around (DEFAULT False): the pick point also offers LOOK_AROUND_KEY (at most LOOK_AROUND_MAX times per robot); the callable then answers
    'look_around' (the motion code looks around again) and lists the box list again afterwards.

    The destination question, its re-decision and the door question also offer 'put the box I am holding down here and finish'
    (key PUT_DOWN, every structure). The callable then answers 'put_down' (choices dest 'put_down'): the motion code releases the
    box where the robot stands (before the door is passed) and the robot ends; the box stays outside every zone (not moved, not a
    wrong place). No further door question, re-decision or carry-end report follows, and the planner is told nothing new.

    llm_moves (DEFAULT False = nothing changes): the planner may also choose a small move (MOVE_OPTIONS): at the pick question, at the door question
    (holding the box) and, through state['move_ask'], while the motion code keeps the robot still on its way to its box. A reference plan
    (brain.chooses_moves False) is never offered one. The chosen move is handed to the motion code through state['move_source'] (the runner polls it
    once per tick); state['move_done'] takes its outcome, tells the planner what happened and, before the pick, starts a new list (a new look-around
    follows the move, labels get a look number). No question and no message chance while a move is on its way. Each robot makes at most MOVES_MAX moves.

    door_of (DEFAULT None = nothing changes; generated map scenes): returns the door the motion code chose for this robot's carry (events['door']),
    or None before it has chosen. At the door question the reference plan is told that door (brain.set_door, if it has the call), so it keeps one
    queue per door. A planner host has no such call and is told nothing: it decides when to go, as before."""
    state = {'next': 0., 'poll': 0., 'listed': False, 'picked': None, 'dest': None, 'go': False, 'waits': False}
    moves_on = bool(llm_moves) and getattr(brain, 'chooses_moves', True)
    if moves_on:
        state.update(move_req=None, move_busy=False, moves_n=0, looks_n=0, look=1, empty_asks=0, moves=[])
    if multi_carry:
        # --multi-carry: 'trip' counts the robot's carries (box labels), 'next_answer' is the planner's answer at the 'next' point
        # ('back' / 'finish') that the motion code polls once the release is over (trip_next)
        state.update(trip=1, next_answer=None, empty_asks=0)
        state['trip_next'] = lambda: state.get('next_answer')

    def speaking():
        return clock() < state.get('stand_until', -math.inf)

    def waiting():
        """True while the robot keeps waiting. It asks its planner again when a new message has reached it, or after
        RETHINK_S without one; a waiting robot does not call the planner every tick."""
        now = clock()
        if (multi_carry or moves_on) and speaking():
            return True
        if now >= state['next']:
            return False
        if now >= state['poll']:
            state['poll'] = now + 1.
            if now >= state.get('asked', 0.) + 2. and brain.poll(rid, now):
                return False
        return True

    def maybe_redecide(force=False):
        if (not redecide or not state['dest'] or state['dest'] == PUT_DOWN or state.get('halted') or (passed is not None and passed())
                or not getattr(brain, 'sends_messages', True)):
            return
        if ((multi_carry or moves_on) and speaking()) or (moves_on and (state['move_req'] or state['move_busy'])):
            return                            # llm_moves: a move is on its way (the runner still asks carry_to() every tick); a new message waits
        now = clock()
        episode = state.get('redecide')
        if episode is None:
            if not force and now < state.get('redecide_poll', 0.):
                return
            state['redecide_poll'] = now + REDECIDE_POLL_S
            if not brain.poll(rid, now):          # nothing new since the planner was last asked
                return
            episode = state['redecide'] = {'next': now, 'asks': 0}
            brain.tell(rid, {'progress': 'I am holding the <%s box>, I chose the <%s zone> and I have not passed the door yet. '
                                         'I may choose the destination again.' % (state['picked'], state['dest'][5:])})
        if now < episode['next']:
            return
        episode['asks'] += 1
        options = destination_options(multi_carry)
        before = state['dest']
        answer = brain.decide(rid, now, 'destination', options)
        talk_stand(state, now, answer, 'redecision')    # free talk: the robot speaks, so its body stands (no effect for an answer without say_s)
        if answer.get('reason') == 'robot_failed':
            state['failed'] = True
        state['asked'] = now
        log.append({'t': round(now, 1), 'rid': rid, 'point': 'destination', 'redecision': True, 'previous': before,
                    'options': [o['key'] for o in options], 'option': answer.get('option'), 'sent': answer.get('sent', []),
                    'calls': answer.get('calls'), 'halted': bool(answer.get('halted'))})
        if answer.get('halted'):
            state['halted'] = True
        keys = [o['key'] for o in options if o['key'] != 'wait']
        if answer.get('option') == PUT_DOWN:
            # the robot ends here: the motion code drops the rest of the carry and sets the box down; nothing is told to the
            # planner (no new text), and the robot is not asked again (no door question, no re-decision, no report)
            state['redecide'] = None
            state['dest'] = PUT_DOWN
            state['put_down'] = {'t': round(now, 1), 'redecision': True, 'point': 'destination', 'from': before}
            state.setdefault('redecisions', []).append({'t': round(now, 1), 'from': before, 'to': PUT_DOWN})
        elif answer.get('option') in keys:
            state['redecide'] = None
            chosen = 'zone_' + answer['option'].split(':')[1]
            if chosen != before:
                state['dest'] = chosen
                state.setdefault('redecisions', []).append({'t': round(now, 1), 'from': before, 'to': chosen})
                brain.tell(rid, {'progress': 'I changed my decision: I will take the <%s box> to the <%s zone>.'
                                             % (state['picked'], answer['option'].split(':')[1])})
        elif (answer.get('sent') and not answer.get('sent_with_action') and episode['asks'] < REDECIDE_MAX_ASKS
              and not state.get('halted')):
            # a message that used up the turn (older planner, pre-exchange): ask again once it is out. A message sent together with
            # the answer 'wait' (sent_with_action) does not use the turn: the destination stays, as with any 'wait'.
            episode['next'] = now + max(2., float(answer.get('wait_s') or 2.))   # the message is out: ask again
        else:
            state['redecide'] = None          # keeps the destination chosen before

    def ask(point, options):
        if point == 'door':
            maybe_redecide(force=True)        # a message that arrives while the robot waits for the door counts first
            if state['dest'] == PUT_DOWN:
                return None                   # it just chose to put the box down here: the door is not asked
        now = clock()
        if state.get('stand_until') is not None and now < state['stand_until']:
            return None                       # free talk: the robot is still speaking (a say at a report, a chance or a re-decision): no new decision until it is done
        here = where() if where is not None else None
        if here and here != state.get('told_where'):
            brain.tell(rid, {'progress': 'I am %s.' % here})
            state['told_where'] = here
        if point == 'door' and door_of is not None and door_of() is not None:
            getattr(brain, 'set_door', lambda _r, _d: None)(rid, door_of())
        answer = brain.decide(rid, now, point, options)
        stand = talk_stand(state, now, answer, 'ask:' + point, hold=multi_carry or moves_on)
        if answer.get('reason') == 'robot_failed':
            state['failed'] = True            # the planner halted this robot as failed (--fail-robot); run_team stops its body when asked to
        log.append({'t': round(now, 1), 'rid': rid, 'point': point, 'options': [o['key'] for o in options],
                    'option': answer.get('option'), 'sent': answer.get('sent', []), 'calls': answer.get('calls'),
                    'halted': bool(answer.get('halted'))})
        state['asked'] = now
        if answer.get('halted'):
            state['halted'] = True
        if answer.get('relay'):
            state['relay'] = True            # star route: the planner wants this robot (the leader) kept in the conversation after its own run is over (run_team relay_step)
        if (multi_carry or moves_on) and stand is not None:
            state.update(next=stand, waits=True)
            return None                     # speech consumes the decision, even if the answer also names a body action
        if answer.get('option') == 'none':
            return 'none'                    # the fixed plan gives this robot nothing to do
        if answer.get('option') == 'wait' or answer.get('option') not in [o['key'] for o in options]:
            # after a message that used up the turn the planner is asked again once the message is out (2 s); after choosing to
            # wait (also with a message sent together with it: sent_with_action), when something new arrives or RETHINK_S later
            turn_used = answer.get('sent') and not answer.get('sent_with_action')
            state['next'] = now + (max(2., float(answer.get('wait_s') or 2.)) if turn_used else RETHINK_S)
            state['waits'] = True            # waiting() lets a new message end the wait (state['next'] itself is not cleared by a real answer)
            if state.get('halted'):
                state['next'] = float('inf')
            return None
        state['waits'] = False
        return answer['option']

    def offered_kinds(holding):
        """Moves the robot is offered now: none once it has made MOVES_MAX moves; no look-around while it holds a box (it would open the gripper)
        or after LOOKS_MAX look-arounds."""
        if not moves_on or state['moves_n'] >= MOVES_MAX or state.get('halted'):
            return ()
        kinds = ['back', 'aside'] if holding else ['look', 'back', 'aside']
        if state['looks_n'] >= LOOKS_MAX and 'look' in kinds:
            kinds.remove('look')
        return tuple(kinds)

    def request_move(key, where):
        kind = MOVE_OPTIONS[key][0]
        state['move_req'] = {'kind': kind, 'where': where}
        state['moves_n'] += 1
        if kind == 'look':
            state['looks_n'] += 1

    def move_source():
        """The runner polls this once per tick: the move the planner chose (taken once), or None."""
        req = state.get('move_req')
        if req is None:
            return None
        state['move_req'], state['move_busy'] = None, True
        return req

    def move_done(result):
        """The runner's outcome of a move. The planner is told what happened to the robot itself; before the pick a new look-around follows
        (the motion code starts it), so the list is told again, the entries are numbered again and the chosen box (if any) is forgotten."""
        state['move_busy'] = False
        state['moves'].append(result)
        restart = result['where'] in ('pick', 'blocked') and result['status'] != 'refused' and (result['kind'] == 'look' or result['motion_rows_done'] > 0)
        text = move_result_text(result) + (' I will look around again.' if restart and result['kind'] != 'look' else '')
        brain.tell(rid, {'progress': text})
        if restart:
            state.update(listed=False, picked=None, label=None, next=0., waits=False, look=state['look'] + 1)

    def blocked_ask(waited_s):
        """The motion code has kept the robot still on its way to its box for waited_s seconds. The planner chooses what to do meanwhile: keep
        waiting (the code goes on as before) or a move. Told: only that the robot stopped and for how long, never why or who. Returns the move
        request (the runner starts it) or None."""
        kinds = offered_kinds(False)
        if not kinds or state['move_req'] or state['move_busy'] or state['picked'] is None or speaking():
            return None
        now = clock()
        brain.tell(rid, {'progress': 'I am on my way to the <%s box> and I have stopped for %d s because my way is not free.' % (state['picked'], round(waited_s))})
        options = [dict(KEEP_WAITING)] + move_options(kinds)
        answer = brain.decide(rid, now, BLOCKED, options)
        log.append({'t': round(now, 1), 'rid': rid, 'point': BLOCKED, 'options': [o['key'] for o in options], 'option': answer.get('option'),
                    'sent': answer.get('sent', []), 'calls': answer.get('calls'), 'halted': bool(answer.get('halted'))})
        if answer.get('halted'):
            state['halted'] = True
        if answer.get('reason') == 'robot_failed':
            state['failed'] = True
        if answer.get('relay'):
            state['relay'] = True
        if talk_stand(state, now, answer, 'ask:blocked') is not None or answer.get('halted') or answer.get('option') not in {o['key'] for o in options[1:]}:
            return None
        request_move(answer['option'], 'blocked')
        req = state['move_req']
        state['move_req'], state['move_busy'] = None, True
        return req

    if moves_on:
        state.update(move_source=move_source, move_done=move_done, move_ask=blocked_ask)

    def choose_box(entries):
        if moves_on and (state['move_req'] or state['move_busy']):
            return 'wait'                     # a move is on its way: the motion code owns the robot, nobody is asked
        seen = [(i, e) for i, e in enumerate(entries) if e['kind'] in NAME]
        boxes = [(i, e) for i, e in seen if can_grasp is None or NAME[e['kind']] in can_grasp]
        can_look = look_around and state.get('looks', 0) < LOOK_AROUND_MAX
        if not boxes and not can_look:
            if (multi_carry or (moves_on and offered_kinds(False))) and state['empty_asks'] < EMPTY_ASKS_MAX:
                return pick_nothing_in_sight(seen)
            return None                       # nothing it can grasp in sight: its run ends (the planner is not asked)
        if waiting():
            return 'wait'
        if not state['listed']:
            brain.tell(rid, {'seen_boxes': [dict({'entry': box_label(rid, i, state.get('trip', 1), state.get('look', 1)), 'colour': NAME[e['kind']], 'distance_m': round(e['distance_m'], 2),
                                                  'bearing_deg': round(math.degrees(e['bearing_rad'])), 'room': 'box room',
                                                  'relation': relation_text(round(math.degrees(e['bearing_rad'])))},
                                                 **({'note': 'I cannot grasp this colour'}
                                                    if can_grasp is not None and NAME[e['kind']] not in can_grasp else {}))
                                             for i, e in seen]})
            state['listed'] = True
        option = ask('pick', [{'key': 'box:%d' % i, 'text': 'go grasp target object <%s box> %s (my label %s)'
                               % (NAME[e['kind']], box_where(e), box_label(rid, i, state.get('trip', 1), state.get('look', 1)))} for i, e in boxes]
                     + ([{'key': LOOK_AROUND_KEY, 'text': LOOK_AROUND_TEXT}] if can_look else [])
                     + (move_options(offered_kinds(False)) if moves_on else [])
                     + [{'key': 'wait', 'text': 'wait here for now'},
                        # the task tells every robot that moving a box no order asks for counts as an error and that it may
                        # finish when there is nothing useful for it to do (same for all structures)
                        {'key': 'finish', 'text': 'finish: there is nothing useful for me to do'}])
        if moves_on and option in MOVE_OPTIONS:
            request_move(option, 'pick')
            return 'wait'                    # the motion code takes the move on its next tick and then looks around again
        if option is None:
            return 'wait'
        if option == LOOK_AROUND_KEY:
            state['looks'] = state.get('looks', 0) + 1
            state.setdefault('look_log', []).append(round(clock(), 1))
            state['listed'] = False           # the new list is told to the planner as a new seen_boxes fact
            brain.tell(rid, {'progress': 'I am looking around again to refresh my list of boxes.'})
            return LOOK_AROUND_KEY
        if option in ('none', 'finish'):
            state['ended'] = option          # the fixed plan gives the robot nothing ('none'), or it chose to finish
            return None                      # nothing for this robot: its run ends without grasping
        index = int(option.split(':')[1])
        state['picked'] = NAME[entries[index]['kind']]
        state['label'] = box_label(rid, index, state.get('trip', 1), state.get('look', 1))
        brain.tell(rid, {'progress': 'I am going to grasp the <%s box> %s (my label %s).' % (state['picked'], box_where(entries[index]), state['label'])})
        return index

    def pick_nothing_in_sight(seen):
        """--llm-moves: no box it can grasp is in the list (the run used to end here without asking). The planner is asked once per look-around
        (at most EMPTY_ASKS_MAX times in the run): a move, wait, or finish. After the last ask the run ends as before."""
        if waiting():
            return 'wait'
        if not state['listed']:
            if seen:
                brain.tell(rid, {'seen_boxes': [{'entry': box_label(rid, i, state.get('trip', 1), state.get('look', 1)), 'colour': NAME[e['kind']],
                                                 'distance_m': round(e['distance_m'], 2), 'bearing_deg': round(math.degrees(e['bearing_rad'])),
                                                 'room': 'box room', 'relation': relation_text(round(math.degrees(e['bearing_rad']))),
                                                 'note': 'I cannot grasp this colour'} for i, e in seen]})
            else:
                brain.tell(rid, {'progress': 'I looked around and I see no box.'})
            state['listed'] = True
        option = ask('pick', move_options(offered_kinds(False)) + [{'key': 'wait', 'text': 'wait here for now'},
                                                                   {'key': 'finish', 'text': 'finish: there is nothing useful for me to do'}])
        if not speaking():
            state['empty_asks'] += 1
        if option in MOVE_OPTIONS:
            request_move(option, 'pick')
            return 'wait'
        if option in ('none', 'finish'):
            state['ended'] = option
            return None
        return 'wait'

    def destination():
        if state['dest']:
            maybe_redecide()
            return state['dest']
        if waiting():
            return state['dest']
        if not state.get('holding'):
            brain.tell(rid, {'progress': 'I am holding the <%s box> that I picked up in the box room (my label %s).'
                                         % (state['picked'], state.get('label')), 'holding': state['picked']})
            state['holding'] = True
            state['listen_until'] = clock() + listen_s
        if clock() < state.get('listen_until', 0.):
            # check teammates' messages before choosing (user decision 2026-11-15): a higher-numbered robot listens
            # for twice the message delay after lifting its box, so a message the lower-numbered robot sent when it
            # chose has arrived (C01: r2 chose 2 s before r1's 'the other blue box is for sign12' reached it)
            return None
        option = ask('destination', destination_options(multi_carry))
        if option is None:
            return None
        if option == PUT_DOWN:
            state['dest'] = PUT_DOWN             # the motion code releases the box where the robot stands and the run ends
            state['put_down'] = {'t': round(clock(), 1), 'redecision': False, 'point': 'destination'}
            return state['dest']
        state['dest'] = 'zone_' + option.split(':')[1]
        brain.tell(rid, {'progress': 'I decided to take the <%s box> to the <%s zone>.' % (state['picked'], option.split(':')[1])})
        return state['dest']

    def gate():
        if state['go'] or state['dest'] == PUT_DOWN:
            return True                       # put_down: nothing to wait for; the motion code ends the carry where the robot stands
        if moves_on and (state['move_req'] or state['move_busy']):
            return False                       # a move is on its way: nobody is asked
        if waiting():
            return False
        option = ask('door', door_options(multi_carry, move_options(offered_kinds(True)) if moves_on else ()))
        if option is None:
            return False
        if moves_on and option in MOVE_OPTIONS:
            request_move(option, 'gate')       # holding the box: back off / step aside; the runner moves, then the door question comes again
            return False
        if option == PUT_DOWN:
            # same answer as at the destination question; the motion code hears it through carry_to() on the next tick (also with
            # redecide off) and drops the carry before it has started; this tick the gate still holds the robot
            state['put_down'] = {'t': round(clock(), 1), 'redecision': False, 'point': 'door', 'from': state['dest']}
            state['dest'] = PUT_DOWN
            return False
        state['go'] = True
        brain.tell(rid, {'progress': 'I am carrying the <%s box> through the door.' % state['picked']})
        return True

    def decision_open():
        """True while the robot's own hooks take a new message into a decision (its draft answers it, so message_chance() stays out):
        the robot has not picked a box (choose_box waits or asks on every tick), it holds the box without a destination (listening,
        waiting or asking), it waits after a 'wait' answer (a new message ends the wait), or it carries towards the door with
        re-decision on (maybe_redecide). Otherwise (walking to the box, carrying with re-decision off, beyond the door) no decision
        point reads the message and the planner may offer the chance."""
        if (multi_carry or moves_on) and (speaking() or state.get('next_pending')):
            return True
        if moves_on and (state['move_req'] or state['move_busy']):
            return True                       # llm_moves: a move is on its way, the robot is not between decisions
        if state['picked'] is None or (state.get('holding') and not state['dest']):
            return True
        if state['waits'] and clock() < state['next']:
            return True
        return bool(redecide and state['dest'] and state['dest'] != PUT_DOWN and not state.get('halted')
                    and not (passed is not None and passed()))

    def gate_idle():
        """True when gate() will answer False this tick without asking anybody and without changing anything (a move is on its way, or the robot waits and
        neither the wait is over nor a poll of the planner is due). Pure; --render-on-demand skips the picture of such a tick."""
        if state['go'] or state['dest'] == PUT_DOWN:
            return False
        if moves_on and (state['move_req'] or state['move_busy']):
            return True
        now = clock()
        return now < state['next'] and now < state['poll']

    gate.idle = gate_idle
    state['decision_open'] = decision_open
    return choose_box, destination, gate, state


def run_team(plan, protocol, model, output, **kw):
    """One team run (see _run_team). A generated map scene (`arena` in the scene) sets the destination tables, the door wording and the map
    environment variable for the run and puts them back afterwards; any other scene is run exactly as before."""
    scene = kw.get('scene')
    if scene is None or 'arena' not in scene:
        return _run_team(plan, protocol, model, output, **kw)
    global ZONES, RECT, DOOR_GO_TEXT
    saved = (ZONES, RECT, DOOR_GO_TEXT, os.environ.get(map_scene_v1.ENV))
    try:
        return _run_team(plan, protocol, model, output, **kw)
    finally:
        ZONES, RECT, DOOR_GO_TEXT = saved[:3]
        if saved[3] is None:
            os.environ.pop(map_scene_v1.ENV, None)
        else:
            os.environ[map_scene_v1.ENV] = saved[3]


def _run_team(plan, protocol, model, output, *, brain, orders, knows, scene_without=(), second_item=None, scene=None,
              redecide_destination=False, listen_unit_s=None, full_info=False, multi_carry=False, llm_moves=False, aside_mode='strafe',
              held_edge_fix=False, look_around=False, fail_robot=None, fail_at_s=None, stop_failed_body=False, decision_audit=False, **kw):
    """scene (DEFAULT None): a designed scene (scene design format): boxes, robot starts, orders with
    counts and signs, which orders each robot knows. Without it, the old colour orders on the staged scene.
    With a scene the robots are the scene's robots (2 or 3, in the scene's order); the optional scene field
    `can_grasp` {rid: [colours]} limits which box colours a robot can grasp.
    redecide_destination (DEFAULT False here; the command line turns it on): a robot that is told something new after it
    chose its destination and before it passes the door is asked the destination again (see hooks).
    Experiment conditions (DEFAULT None / False = unchanged behaviour; the record gets a 'conditions' entry only when one is set):
    listen_unit_s: the destination listening unit in seconds instead of DEST_LISTEN_S (rank times unit; 0 = nobody listens);
    full_info: every robot is told every order of the team as its own (the scene's `knows` is kept in the record).
    Execution-layer experiment switches v39 (all DEFAULT off; the run is then byte-identical to v38):
    held_edge_fix: the held check does not read the sliver of the held box's rim along the lens border as a box left on the floor
    (harness/place_memory_v1.py HELD_EDGE_PX; run_steps held_edge_fix).
    look_around: the pick point also offers to look around again (LOOK_AROUND_KEY; run_steps look_around).
    fail_robot / fail_at_s (together; the planner is started with the same --fail-robot / --fail-at-s): from that simulated time the robot's body
    stops (wheels 0, arm held, no more decisions) and it counts as an ended robot (the fixed plan's door order skips it); it stays in the world as a
    physical obstacle. stop_failed_body: also stop the body of any robot the planner answers with reason 'robot_failed' (without the runner knowing
    the time; the stop is then at that answer, which comes at the robot's next decision). A robot with a failure is listed in record['failed'].
    Free talk (planner --talk free; no switch here: the planner marks a speech with say_s in its answer, see talk_stand_until): the robot's body stands for
    max(2, wait_s) s after a speech on every path the planner can answer with one: the pick / destination / door question (its own wait), the report after
    a milestone, the destination re-decision and the message chance. Multi-carry and move choices also hold return, move, grasp and
    release commands, and retry a spoken 'next' before any return or finish.
    record['talk_stands'] {rid: [{t, path, say_s, stand_s, via}]} exists only when a speech happened. Without say_s in an answer nothing is changed.
    Star route (planner --leader-route star; no switch here: the planner marks every decision answer of the leader with relay=True): the leader stays in the conversation
    after its own run is over (delivered, put down, finish) while a teammate is still running (relay_step: poll once per RELAY_POLL_S, point 'relay' on a new message; its
    body is not moved). record['relay'] {rid: {start_s, decisions, sent}} exists only then; log rows have point 'relay'. Without relay in an answer nothing is changed.
    multi_carry (DEFAULT False = every run is unchanged): a robot may carry more than one box (phase 2, 'go back'). After a delivery or a
    put-down the planner is asked the new point 'next' (go back for another box / finish my run) instead of the report; on 'back' the
    motion code (run_steps multi_carry) returns through the door if the robot is in the destination room, looks around the box room again
    and the hooks start a new carry (trip). The record gets conditions.multi_carry and `carries` {rid: [{trip, picked, label, dest, go}]};
    choices keep the values of the robot's last carry, events keep the milestones of the last carry and hold all of them in events.trips.
    A robot makes at most MAX_TRIPS carries. Needs the ceiling cameras (overhead): the way back is driven on the measured pose.
    llm_moves (DEFAULT False = every run is unchanged, byte for byte; independent of multi_carry): the planner may choose a small move (back off a
    little, step aside to let a teammate pass, look around here) at the pick question, at the door question (holding the box) and while the motion
    code holds the robot still on its way to its box (new decision point 'blocked'). The planner names the move, harness/llm_moves_v1.py does it
    (aside_mode 'strafe' or 'detour'). A reference plan (FixedPlan, MultiFixedPlan) is never offered one. The record gets conditions.llm_moves and
    `moves` {rid: [outcome of every move]}. Needs the ceiling cameras (overhead): the room check and the new look-around use the measured pose."""
    allowed = {}
    map_cfg = None
    if scene is not None:
        kw['layout'] = {'boxes': [{'colour': b['colour'], 'x': b['x'], 'y': b['y'], 'id': b['id']} for b in scene['boxes']]}
        orders = [{'id': o['id'], 'colour': o['colour'], 'count': o['count'], 'dest': 'sign%d' % o['sign']} for o in scene['orders']]
        knows = {r: tuple(v) for r, v in scene['knows'].items()}
        robots = tuple(r['rid'] for r in scene['robots'])
        if 'arena' in scene:
            # generated map scene (a work record, schema mapgen.scene.v1): the world is built from the scene (harness/map_scene_v1.py)
            map_cfg = map_scene_v1.config(scene)
            map_scene_v1.check_supported(map_cfg)
        elif not 2 <= len(robots) <= 3 or len(set(robots)) != len(robots) or any(r_ not in ('r1', 'r2', 'r3') for r_ in robots):
            raise ValueError('a scene needs 2 or 3 distinct robots among r1, r2, r3: %s' % (robots,))
        for r_, colours in (scene.get('can_grasp') or {}).items():
            if r_ not in robots or any(c_ not in CAPABLE_COLOURS for c_ in colours):
                raise ValueError('can_grasp: unknown robot or colour: %s %s' % (r_, colours))
            if set(colours) != set(CAPABLE_COLOURS):         # a robot that can grasp both colours has no limit
                allowed[r_] = tuple(c_ for c_ in CAPABLE_COLOURS if c_ in colours)
        assignment = getattr(brain, 'assignment', None)
        if assignment is not None and any(r_ not in robots for r_ in assignment):
            raise ValueError('the fixed plan names a robot that is not in the scene: %s' % (sorted(assignment),))
        for r_, carries_ in (assignment or {}).items():
            for colour_, _zone in (carries_ if isinstance(carries_, list) else [carries_]):      # a multi-carry plan lists its carries
                if r_ in allowed and colour_ not in allowed[r_]:
                    raise ValueError('the fixed plan gives %s a <%s box> it cannot grasp' % (r_, colour_))
    else:
        orders = [{'id': colour, 'colour': colour, 'count': 1, 'dest': zone} for colour, zone in orders.items()]
    if (fail_robot is None) != (fail_at_s is None):
        raise ValueError('fail_robot and fail_at_s go together')
    if fail_robot is not None and fail_robot not in (robots if scene is not None else ('r1', 'r2', 'r3')):
        raise ValueError('fail_robot %s is not a robot of the run' % fail_robot)
    if held_edge_fix:
        kw['held_edge_fix'] = True
    if look_around:
        kw['look_around'] = True
    global ZONES, RECT, DOOR_GO_TEXT
    if map_cfg is not None:
        if not kw.get('robot_tags'):
            raise ValueError('a map scene needs --robot-tags: its destinations are wall signs')
        # the signs of the scene (up to 8, anywhere on its walls) and the rectangles in front of them
        ZONES, RECT = map_scene_v1.zone_tables(map_cfg)
        DOOR_GO_TEXT = DOOR_GO_TEXT_MAP if len(map_cfg['doors']) > 1 else DOOR_GO_TEXT
    elif kw.get('robot_tags'):
        # destinations are the wall signs, not floor paint (user decision 2026-11-15)
        ZONES, RECT = SIGN_ZONES, SIGN_RECT
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    objects = ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']).config['setup_only']['objects']
    if map_cfg is not None:
        objects.update(map_scene_v1.cargo_items(map_cfg, objects))       # the boxes beyond the pool of the scene package (cloned in the scene XML) are scored too
        (output / 'map-cfg.json').write_text(json.dumps(map_cfg, indent=1))
        os.environ[map_scene_v1.ENV] = str(output / 'map-cfg.json')    # harness/robot_tags_v1.py, overhead_v1.py read it at import
        kw['map_scene'] = map_cfg
        # the frozen world builds the robots r1..r3 and a stiffness transform for them: tell it the robots of this scene before the runner
        # imports from it (this is inside dependency_modules(); the patched module is dropped with it)
        map_patch = PATCH_FROZEN_WORLD(map_cfg['world_robots'])
    if scene is not None:
        first, second = robots[0], robots[1]
        z = plan['spawns'][plan['robot_id']][2]
        starts = {r['rid']: [r['x'], r['y'], z, r['yaw']] for r in scene['robots']}
        if map_cfg is not None and hasattr(brain, 'doors') and not brain.doors:
            # the reference plan keeps one queue per door: until the motion code names the door of a robot (set_door), the nearest door of its start
            brain.doors.update({r_: map_scene_v1.choose_door(map_cfg, starts[r_][:2])['id'] for r_ in getattr(brain, 'assignment', {}) if r_ in starts})
        spawn = starts[second]
        base = dict(plan, spawns=dict(plan['spawns'], **starts))
        plans = {r_: dict(base, robot_id=r_) for r_ in robots}
    else:
        first, second = plan['robot_id'], ('r2' if plan['robot_id'] != 'r2' else 'r3')
        robots = (first, second)
        item, spawn = second_task(plan, objects, second_item)
        box = objects[item]
        plans = {first: dict(plan, spawns=dict(plan['spawns'], **{second: spawn}))}
        plans[second] = dict(plans[first], robot_id=second, item_id=item, object_kind=box['kind'],
                             target_setup_xy=list(box['position_m'][:2]), cargo_pose_m=list(box['position_m'][:2]) + [0.],
                             start_to_cargo_m=math.dist(spawn[:2], box['position_m'][:2]))
    shared = {'robots': robots}
    if getattr(brain, 'targets', None):
        brain.pose_source = lambda r_: world_pose(shared, r_)      # the reference plan picks its box by place: it needs where the robot looks around from
    conditions = {}
    if kw.get('zone_confirm_close'):
        conditions['zone_confirm_close'] = True
    if listen_unit_s is not None:
        conditions['listen_s'] = listen_unit_s
    if held_edge_fix:
        conditions['held_check_edge_fix'] = True
    if look_around:
        conditions['look_around_option'] = True
    if fail_robot is not None or stop_failed_body:
        conditions['body_stop'] = {'fail_robot': fail_robot, 'fail_at_s': fail_at_s, 'stop_failed_body': bool(stop_failed_body)}
    if multi_carry:
        if not kw.get('overhead'):
            raise ValueError('multi_carry needs overhead: the way back through the door is driven on the measured pose')
        conditions['multi_carry'] = True
    if llm_moves:
        if not kw.get('overhead'):
            raise ValueError('llm_moves needs overhead: the room check and the new look-around use the measured pose')
        if aside_mode not in ('strafe', 'detour'):
            raise ValueError('aside_mode must be strafe or detour')
        conditions['llm_moves'] = True
        conditions['aside_mode'] = aside_mode
    if full_info:
        conditions['full_info'] = True
        conditions['knows_in_scene'] = {r_: list(v) for r_, v in knows.items()}
        knows = full_info_knows(orders, robots)
    events, told, log, chances = {r_: {} for r_ in robots}, {r_: set() for r_ in robots}, [], []
    clock = lambda: float(shared['world'].data.time) - shared.get('t0', 0.)
    kw['redecide'] = redecide_destination             # the motion code takes a changed destination until the door is passed
    record = {'schema': 'ugrp.team.carry.v1', 'seed': plan['seed'], 'robots': list(robots), 'redecide_destination': redecide_destination,
              'scene': None if scene is None else scene['id'], 'orders': orders, 'knows': knows, 'second_spawn': spawn, 'scene_without': list(scene_without), 'status': 'running'}
    if scene is not None:
        record['starts'] = starts
        if allowed:
            record['can_grasp'] = {r_: list(c_) for r_, c_ in allowed.items()}
    if conditions:
        record['conditions'] = conditions
    write_json(output / 'team.json', record)
    fixed_trips = isinstance(brain, MultiFixedPlan)
    if decision_audit:
        brain = solo.execution_options.DecisionTrace(brain, output / 'decision-inputs.jsonl')
    for rid in robots:
        mine = [o for o in orders if o['id'] in knows.get(rid, ()) or o['colour'] in knows.get(rid, ())]
        facts = {'orders': [{'box': o['colour'], 'count': o['count'], 'zone': o['dest']} for o in mine]}
        if rid in allowed:
            facts['capability'] = capability_text(allowed[rid])      # its own capability only; others' arrive by message
        facts['progress'] = 'I am in the box room and I am not holding anything.'
        brain.tell(rid, facts)
    steps, states = {}, {}
    for rid in robots:
        # room from own progress, not the ceiling camera (user decision 2026-11-15); the same with or without --overhead
        _where = (lambda r_=rid: room_of(events[r_]))
        choose_box, destination, gate, states[rid] = hooks(rid, brain, clock, log, where=_where,
                                                           listen_s=DEST_LISTEN_S * natural_robots(robots).index(rid) * listen_scale(listen_unit_s),
                                                           can_grasp=allowed.get(rid), redecide=redecide_destination,
                                                           passed=lambda r_=rid: 'door_passed' in events[r_], multi_carry=multi_carry,
                                                           llm_moves=llm_moves, look_around=look_around,
                                                           door_of=(lambda r_=rid: events[r_].get('door')) if map_cfg is not None else None)
        extra = {'multi_carry': True, 'trip_next': states[rid]['trip_next']} if multi_carry else {}
        if 'move_source' in states[rid]:
            # llm_moves, for a planner that chooses moves (a reference plan gets none): the motion code polls the move, asks while it holds the robot still
            extra.update(llm_moves=True, aside_mode=aside_mode, move_source=states[rid]['move_source'], move_ask=states[rid]['move_ask'],
                         move_done=states[rid]['move_done'])
        steps[rid] = solo.run_steps(plans[rid], protocol, model, output / ('out-' + rid), carry_to=destination,
                                    choose_box=choose_box, carry_gate=gate,
                                    stand_hold=(lambda r_=rid: states[r_].get('stand_until') is not None and clock() < states[r_]['stand_until']),
                                    shared=shared, events=events[rid],
                                    scene_without=scene_without, **kw, **extra)
    requests, reports = {}, {}
    frozen, failed = {}, {}       # failed robots: their body is stopped (wheels 0, arm as it was) and they are no longer stepped

    def freeze(rid_, why):
        request = requests.pop(rid_)
        frozen[rid_] = dict(request, wheels=[0.] * 4, deadlines=[0.] * 4)     # still ticked by the physics so that the arm holds and the wheels stay off
        failed[rid_] = {'t': round(clock(), 1), 'by': why}
        failed[rid_]['xy_at_stop'] = [round(float(v), 3) for v in shared['world'].robot(rid_).base_xyz()[:2]]      # evaluation side only
        states[rid_].update(halted=True, chance_off=True)
        getattr(brain, 'robot_ended', lambda _r: None)(rid_)

    carries = {r_: [] for r_ in robots}     # multi_carry: what each robot chose in the carries it has finished

    def carry_now(rid):
        st = states[rid]
        return {'trip': st.get('trip', 1), 'picked': st['picked'], 'label': st.get('label'), 'dest': st['dest'], 'go': st['go']}

    def next_decision(rid, outcome):
        """Called after release. Tell the outcome once, then retry the same menu after any speech until a body choice is made."""
        st = states[rid]
        now = clock()
        in_destination_room = 'door_passed' in events[rid]
        if not st.get('next_pending'):
            st.update(next_pending=True, next_answer='wait')
            facts = dict(progress=carry_end_report(outcome, st['dest'], multi_carry=True), milestone='carry_finished',
                         trip=st['trip'], outcome=outcome, box=st['picked'])
            if outcome == 'at_zone' and st['dest'] and st['dest'].startswith('zone_'):
                facts['zone'] = st['dest'].removeprefix('zone_')
            brain.tell(rid, facts)
        if now < max(st.get('stand_until', -math.inf), st.get('next_retry', -math.inf)):
            return False
        # Free planners have a three-trip cap. An oracle must be allowed to finish its supplied list.
        at_cap = st['trip'] >= MAX_TRIPS and not fixed_trips
        point = 'report' if at_cap else NEXT
        options = [{'key': 'continue', 'text': 'finish my run'}] if at_cap else next_options(in_destination_room)
        answer = brain.decide(rid, now, point, options)
        log.append({'t': round(now, 1), 'rid': rid, 'point': point, 'milestone': 'carry_finished', 'options': [o['key'] for o in options],
                    'option': answer.get('option'), 'sent': answer.get('sent', []), 'calls': answer.get('calls'),
                    'halted': bool(answer.get('halted'))})
        if answer.get('relay'):
            st['relay'] = True
        if answer.get('halted'):
            st['halted'] = True
        if answer.get('reason') == 'robot_failed':
            st['failed'] = True
        until = talk_stand(st, now, answer, 'report:carry_finished' if at_cap else 'ask:next')
        if not at_cap and not st.get('halted') and (until is not None or answer.get('option') == 'wait'):
            st['next_retry'] = until if until is not None else now + max(2., float(answer.get('wait_s') or 2.))
            return False
        back = not at_cap and answer.get('option') == 'back' and not st.get('halted')
        st['next_pending'] = False
        st['next_answer'] = 'back' if back else 'finish'
        if back and in_destination_room and getattr(kw.get('exec_options'), 'oracle_return_face', False):
            hint = getattr(brain, 'return_hint', lambda _r: None)(rid)
            if hint is not None:
                events[rid]['return_face_world'] = hint
        if back:
            brain.tell(rid, {'progress': 'I am going back to the box room for another box.' if in_destination_room
                             else 'I am going to look around the box room again for another box.'})
        else:
            st['chance_off'] = True          # the run ends here (no message chances once it is over)
        return True

    def new_trip(rid, trip):
        """multi_carry: the motion code has started the robot's next carry (it stands in the box room, empty, and looks around). The
        hooks start afresh like after an empty gripper; what the robot chose in the finished carry goes to `carries`."""
        carries[rid].append(carry_now(rid))
        told[rid].clear()
        states[rid].update(listed=False, picked=None, dest=None, go=False, holding=False, next=0., waits=False, label=None,
                           next_answer=None, trip=trip, chance_off=False, redecide=None, fails_told=0)
        if 'look' in states[rid]:
            states[rid]['look'] = 1          # llm_moves: a new carry numbers its look-arounds afresh (the label has the carry number)
        states[rid]['put_down'] = None
        brain.tell(rid, {'progress': 'I am in the box room and I am not holding anything.', 'milestone': 'trip_started', 'trip': trip})

    relays = {}        # star route: {rid: {start_s, decisions, sent[, halted | error]}} of the robots kept in the conversation after their own run (only exists when one was)

    def relay_step(rid):
        """A robot whose run is over but which the planner marked relay=True (the star leader): while a teammate is still running, ask the planner once per RELAY_POLL_S
        whether a message is new and, when so, the point 'relay' (RELAY_OPTIONS; the planner's say entries come with it). Its body is not touched. Ends with the run, when the
        robot halts, fails, or the planner cannot answer (the host that does not know the point: recorded as error, no more relay)."""
        st = states[rid]
        if not requests or not st.get('relay') or st.get('halted') or st.get('failed') or st.get('relay_off') or rid in failed:
            return
        now = clock()
        info = relays.setdefault(rid, {'start_s': round(now, 1), 'decisions': 0, 'sent': 0})
        if now < st.get('relay_poll', 0.) or (multi_carry and now < st.get('stand_until', -math.inf)):
            return
        st['relay_poll'] = now + RELAY_POLL_S
        try:
            if not brain.poll(rid, now):
                return
            answer = brain.decide(rid, now, 'relay', RELAY_OPTIONS)
        except Exception as exc:
            st['relay_off'] = True
            info['error'] = type(exc).__name__
            return
        info['decisions'] += 1
        if multi_carry:
            talk_stand(st, now, answer, 'relay')
        info['sent'] += len(answer.get('sent', []))
        log.append({'t': round(now, 1), 'rid': rid, 'point': 'relay', 'options': [o['key'] for o in RELAY_OPTIONS], 'option': answer.get('option'),
                    'sent': answer.get('sent', []), 'calls': answer.get('calls'), 'halted': bool(answer.get('halted'))})
        if answer.get('halted'):
            st['halted'] = True
            info['halted'] = answer.get('reason')

    def planner_feedback(rid):
        if multi_carry and events[rid].get('trip', 1) != states[rid]['trip']:
            new_trip(rid, events[rid]['trip'])
        if (multi_carry or llm_moves) and clock() < states[rid].get('stand_until', -math.inf):
            return
        # Own milestones are taken once, including those that arrived while speaking.
        fails = events[rid].get('not_holding', [])
        if len(fails) > states[rid].get("fails_told", 0):
            # empty gripper: the robot says so to its planner, which picks again from a fresh look-around
            states[rid]['fails_told'] = len(fails)
            brain.tell(rid, {'progress': 'I lost the <%s box>: my gripper is empty. I will look around again and '
                                         'choose a box again.' % states[rid]['picked'], 'milestone': 'grasp_failed'})
            answer = brain.decide(rid, clock(), 'report', [{'key': 'continue', 'text': 'continue my task'}])
            if answer.get('reason') == 'robot_failed':
                states[rid]['failed'] = True
            log.append({'t': round(clock(), 1), 'rid': rid, 'point': 'report', 'milestone': 'grasp_failed',
                        'sent': answer.get('sent', []), 'calls': answer.get('calls')})
            states[rid].update(listed=False, picked=None, dest=None, go=False, holding=False, next=0.)
            states[rid]['put_down'] = None
            talk_stand(states[rid], clock(), answer, 'report:grasp_failed')   # free talk: after the state reset above, the robot stands while it speaks
        for name in ('door_passed', 'carry_finished'):
            if (multi_carry or llm_moves) and clock() < states[rid].get('stand_until', -math.inf):
                break
            if name in events[rid]:
                outcome = events[rid][name].get('outcome') if name == 'carry_finished' else None
                marker = (name, outcome) if multi_carry and name == 'carry_finished' else name
                if marker in told[rid]:
                    continue
                if multi_carry and outcome in ('at_zone', PUT_DOWN):
                    if next_decision(rid, events[rid][name]['outcome']):
                        told[rid].add(marker)
                    continue
                told[rid].add(marker)
                if name == 'carry_finished' and events[rid][name].get('outcome') != 'box_not_held':
                    states[rid]['chance_off'] = True      # the run ends at the carry end (the robot may still lower its arm and release)
                if name == 'carry_finished' and events[rid][name].get('outcome') == PUT_DOWN:
                    continue      # the robot chose to put its box down and finish: no report, no new text for the planner
                text = ('I have passed the door with the <%s box>.' % states[rid]['picked'] if name == 'door_passed' else
                        carry_end_report(outcome, states[rid]['dest']))
                brain.tell(rid, {'progress': text, 'milestone': name})
                answer = brain.decide(rid, clock(), 'report', [{'key': 'continue', 'text': 'continue my task' if name == 'door_passed'
                                                                else carry_end_option_text(outcome)}])
                if answer.get('reason') == 'robot_failed':
                    states[rid]['failed'] = True
                log.append({'t': round(clock(), 1), 'rid': rid, 'point': 'report', 'milestone': name,
                            'sent': answer.get('sent', []), 'calls': answer.get('calls')})
                talk_stand(states[rid], clock(), answer, 'report:' + name)    # free talk: the robot speaks, so its body stands
        if rid in requests:
            message_chance(rid, brain, clock, chances, states[rid])

    delivery_audit = None
    try:
        for rid in robots:
            requests[rid] = next(steps[rid])
        world = shared['world']
        if decision_audit and scene is not None:
            scoring_keys = {obj['body_name']: key for key, obj in objects.items() if 'body_name' in obj}
            delivery_audit = solo.execution_options.DeliveryAudit(world, shared['layout'], RECT, solo.SoloScore.RELEASE_CRITERIA, scoring_keys)
        shared['t0'] = float(world.data.time) + 1.   # the settle second ends here for both robots
        while requests:
            until = min(r['until'] for r in requests.values())
            solo.advance_physics(world, list(requests.values()) + list(frozen.values()), until)
            if delivery_audit is not None:
                delivery_audit.sample(world, clock())
            for rid in list(requests):
                if fail_robot == rid and clock() >= fail_at_s:
                    freeze(rid, 'time')
                elif states[rid].get('failed') and (stop_failed_body or fail_robot is not None):
                    freeze(rid, 'planner')
            if not requests:
                break
            for rid in [r for r in robots if r in requests and requests[r]['until'] <= until + 1e-8]:
                if multi_carry or llm_moves:
                    # The last row has finished. A speech now holds the very next command, including a return or a move.
                    planner_feedback(rid)
                    if states[rid].get('failed') and (stop_failed_body or fail_robot is not None):
                        freeze(rid, 'planner')
                        continue
                try:
                    requests[rid] = next(steps[rid])
                except StopIteration as stop:
                    reports[rid] = stop.value
                    del requests[rid]
                    getattr(brain, 'robot_ended', lambda _r: None)(rid)    # a fixed plan frees its door order (6cbd3db, with or without multi_carry); a planner host has no such call
                if not (multi_carry or llm_moves) or rid in reports:
                    planner_feedback(rid)
            for rid in robots:
                if rid in reports:
                    relay_step(rid)       # star route only: a robot whose run is over and that the planner marked (never true for any other planner)
        record['status'] = 'complete'
    finally:
        placed = {}
        if delivery_audit is not None:
            record['delivery_audit'] = delivery_audit.record()
        if 'world' in shared:
            world = shared['world']
            for rid_, info in failed.items():
                info['xy_at_end'] = [round(float(v), 3) for v in world.robot(rid_).base_xyz()[:2]]      # evaluation side only: where the stopped body stands at the end
            for key, obj in objects.items():
                if obj.get('kind') in NAME and 'body_name' in obj:
                    x, y = (float(v) for v in world.data.xpos[world.model.body(obj['body_name']).id][:2])
                    if x < -20:
                        continue                # not in this scene
                    zone = next((z for z, (x0, x1, y0, y1) in RECT.items() if x0 <= x <= x1 and y0 <= y <= y1), None)
                    placed[key] = {'colour': NAME[obj['kind']], 'end_xy': [round(x, 3), round(y, 3)], 'zone': zone}
            # an order is met by as many boxes of its colour lying at its destination as it asks for
            used = set()
            for o in orders:
                o['met'] = 0
                for key, b in sorted(placed.items()):
                    if key not in used and b['colour'] == o['colour'] and b['zone'] == o['dest'] and o['met'] < o['count']:
                        used.add(key)
                        o['met'] += 1
            for key, b in placed.items():
                b['correct'] = key in used
                b['wrong_place'] = b['zone'] is not None and key not in used
        for rid_, gen in steps.items():
            if rid_ in failed:
                try:
                    gen.send('body_stopped')      # the stopped robot's report is written normally (termination 'body_stopped'), not as HOST_ERROR / GeneratorExit
                except StopIteration:
                    pass
                except Exception as exc:
                    failed[rid_]['finalize_error'] = type(exc).__name__
        for gen in steps.values():
            gen.close()
        if 'world' in shared:
            end_s = clock()
            shared['world'].close()
            record['end_s'] = end_s
        try:
            record['brain'] = brain.record()
        except Exception as exc:   # the planner host may be gone; the physical record must still be written
            record['brain'] = {'error': type(exc).__name__}
        record.update(events=events, finished=sorted(reports), decisions=log, boxes=placed,
                      correct_boxes=sum(1 for b in placed.values() if b['correct']),
                      required_boxes=sum(o['count'] for o in orders), wrong_place_boxes=sum(1 for b in placed.values() if b.get('wrong_place')),
                      choices={rid: {k: states[rid][k] for k in ('picked', 'dest', 'go')} for rid in states},      # multi_carry: the robot's last carry
                      redecisions={rid: states[rid].get('redecisions', []) for rid in states},
                      ended_without_grasp={rid: states[rid]['ended'] for rid in states if states[rid].get('ended')})
        if failed:
            record['failed'] = failed         # only when a body stop happened (default record keys unchanged)
        if look_around:
            record['look_arounds'] = {rid: states[rid].get('look_log', []) for rid in states}
        if llm_moves:
            record['moves'] = {rid: states[rid].get('moves', []) for rid in states}      # only with the switch (default record keys unchanged)
        if map_cfg is not None:
            # generated map scene only: which door each robot's carry went through (the motion code's choice, the key of the door queues)
            record['map'] = {'scene': map_cfg['scene_id'], 'family': map_cfg['family'], 'robots': len(robots), 'world_robots': map_cfg['world_robots'],
                             'doors': {rid: events[rid].get('door') for rid in robots}, 'frozen_world_patch': map_patch}
        if multi_carry:
            record['carries'] = {rid: carries[rid] + ([carry_now(rid)] if states[rid]['picked'] is not None else []) for rid in states}
        if chances:
            record['chances'] = chances       # message chances between decisions (T1/T2), only when one was asked (default record keys unchanged)
        if relays:
            record['relay'] = relays          # only when the planner kept a robot in the conversation after its run (star route); default record keys unchanged
        talk_stands = {rid: states[rid]['talk_stands'] for rid in states if states[rid].get('talk_stands')}
        if talk_stands:
            record['talk_stands'] = talk_stands      # only when a robot spoke under free talk (an answer with say_s): requested stand per speech and how it was applied
        put_down = {rid: states[rid]['put_down'] for rid in states if states[rid].get('put_down')}
        if put_down:
            record['put_down'] = put_down     # only when a robot chose it (default record keys unchanged); choices[rid]['dest'] is 'put_down'
        write_json(output / 'team.json', record)
    return record


def oracle_fixed_plan(sc, multi_carry=False):
    """The reference plan main() runs for `--fixed oracle`: the scene's all-knowing plan (oracle_plan, first assignment per robot), door order = robot number
    order (r1, r2, r3). A generated map scene (`arena`): one queue per door (the plan's guess of each robot's door is the one nearest its box; the motion code
    names the door it really chose when the robot asks to go), and the plan names the BOX of every robot by its place (FixedPlan.targets), not 'the nearest box of
    the colour'. A phase-2 scene's `oracle` block adds the door order (earliest planned go first) and the precedence waits (`after`)."""
    colour = {b['id']: b['colour'] for b in sc['boxes']}
    sign = {o['id']: 'sign%d' % o['sign'] for o in sc['orders']}
    doors = None
    if 'arena' in sc:
        _cfg = map_scene_v1.config(sc)
        where = {b['id']: (b['x'], b['y']) for b in sc['boxes']}
        doors = {r: map_scene_v1.choose_door(_cfg, where[v[0][0]])['id'] for r, v in sc['oracle_plan'].items() if v}
    if multi_carry:
        plan = {r: trips for r, trips in sc['oracle_plan'].items() if trips}
        assignment = {r: [(colour[b], sign[o]) for b, o in trips] for r, trips in plan.items()}
        positions = {b['id']: (b['x'], b['y']) for b in sc['boxes']}
        itinerary, boxes_by_order = {}, {}
        for rid, trips in plan.items():
            itinerary[rid] = []
            for box, order in trips:
                target = dict(box=box, order=order, xy=positions[box])
                if doors is not None:
                    target['door'] = map_scene_v1.choose_door(_cfg, target['xy'])['id']
                itinerary[rid].append(target)
                boxes_by_order.setdefault(order, set()).add(box)
        prerequisites = {}
        for rule in sc.get('constraints', ()):
            if rule['type'] == 'order':
                prior, later = rule['orders']
                prerequisites.setdefault(later, set()).update(boxes_by_order[prior])
        meta = sc.get('oracle') or {}
        order = list(dict.fromkeys(r for r in meta.get('door_order', ()) if r in plan))
        order += [r for r in natural_robots(plan) if r not in order]
        starts = {r['rid']: (r['x'], r['y'], r['yaw']) for r in sc['robots']}
        return MultiFixedPlan(assignment, order, doors, itinerary=itinerary, starts=starts, prerequisites=prerequisites)
    assignment = {r: (colour[v[0][0]], sign[v[0][1]]) for r, v in sc['oracle_plan'].items() if v}
    if 'arena' not in sc:
        return FixedPlan(assignment, natural_robots(assignment), doors)
    meta = sc.get('oracle') or {}
    targets = {r: {'box': v[0][0], 'xy': where[v[0][0]]} for r, v in sc['oracle_plan'].items() if v}
    order = [r for r in meta.get('door_order', ()) if r in assignment] or natural_robots(assignment)
    return FixedPlan(assignment, order, doors, targets=targets, after=meta.get('after'),
                     starts={r['rid']: (r['x'], r['y'], r['yaw']) for r in sc['robots']})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--actor-python', required=True)
    p.add_argument('--cap-s', type=float, default=600.)
    p.add_argument('--actor-threads', type=int, default=2)
    p.add_argument('--orders', default='red:orange,blue:blue', help='box colour:zone colour, comma separated (task)')
    p.add_argument('--knows', default='r1:red+blue,r2:red+blue', help='which orders each robot is given, e.g. r1:red,r2:blue')
    p.add_argument('--brain-url', help='planner on another host (forwarded port); without it the fixed reference plan runs')
    p.add_argument('--fixed', default='r1:blue:blue,r2:red:orange', help='reference plan: robot:box colour:zone, in door order')
    p.add_argument('--second-item')
    p.add_argument('--scenes', type=Path, help='designed scenes file (task definition)')
    p.add_argument('--scene-id', help='which designed scene')
    p.add_argument('--robot-tags', action='store_true', help='task definition: number tags on the robots')
    p.add_argument('--overhead', action='store_true', help='ceiling cameras measure the robots for the motion code')
    p.add_argument('--redecide-destination', action=argparse.BooleanOptionalAction, default=True,
                   help='ask the destination again when a new message reached the robot after it chose and before it passes '
                        'the door (default on; --no-redecide-destination reproduces the earlier behaviour)')
    p.add_argument('--listen-s', type=float, default=None,
                   help='experiment condition: listening unit before a robot chooses its destination, in seconds (rank times unit: '
                        '2 robots r1 0 / r2 unit, 3 robots 0 / unit / 2 unit); default %s s, 0 = nobody listens' % DEST_LISTEN_S)
    p.add_argument('--dest-listen-zero', action='store_true',
                   help='execution-layer speed switch (DEFAULT off): nobody waits for teammates\' messages before choosing a destination '
                        '(the same as --listen-s 0; with a fixed reference plan the wait is idle time)')
    p.add_argument('--full-info', action='store_true',
                   help='experiment condition (full-information control): every robot is told every order of the team as its own')
    p.add_argument('--held-check-edge-fix', action='store_true',
                   help='execution-layer experiment v39: the held check does not read the rim of the held box along the lens border as a box left on the floor')
    p.add_argument('--look-around-option', action='store_true',
                   help='execution-layer experiment v39: the pick point also offers "look around again" (the planner may choose it; the look-around routine then runs again)')
    p.add_argument('--fail-robot', default=None, help='experiment v39: this robot\'s body stops at --fail-at-s (use the same values as the planner host)')
    p.add_argument('--fail-at-s', type=float, default=None, help='simulated time of the body stop (with --fail-robot)')
    p.add_argument('--stop-failed-body', action='store_true',
                   help='experiment v39: also stop the body of a robot the planner answers with reason robot_failed (at that answer)')
    p.add_argument('--multi-carry', action='store_true',
                   help='phase 2 (default off = every run unchanged): a robot may carry more than one box. After a delivery or a put-down it '
                        'chooses at the point "next" between going back for another box and finishing; --fixed oracle then follows the '
                        "scene's oracle_plan carry by carry. Needs --overhead and --robot-tags; the planner host runs brain_server.py --multi-carry")
    p.add_argument('--llm-moves', action='store_true',
                   help='phase 2 middle moves (default off = every run unchanged): the planner may also choose back off a little / step aside to let a '
                        'teammate pass / look around here (pick question, door question while holding the box, and while the robot is held still on '
                        'its way to its box). Needs --overhead and --robot-tags; the planner host needs the point "blocked" (brain/__init__.py)')
    p.add_argument('--aside-mode', choices=('strafe', 'detour'), default='strafe',
                   help='with --llm-moves: how "step aside" moves: strafe = one mecanum sideways leg (the sideways step per pulse at the carry level '
                        'is an estimate, to be measured), detour = turn 90 degrees, forward, turn back (measured units)')
    p.add_argument('--regrasp-max', type=int, default=1, help='after an empty-gripper check, look around and pick again this many times')
    p.add_argument('--truth-every', type=int, default=0, help='evaluation side: true depth and object ids every N ticks')
    p.add_argument('--scene-without', default='beam,can,tile,frame,crate,robots')
    p.add_argument('--scene-source', type=Path, required=True)
    p.add_argument('--render-cull', action='store_true',
                   help='speed switch (default off = every run unchanged): the camera renders draw only the geoms that can be inside the camera\'s view frustum '
                        '(harness/render_cull_v1.py; the pictures are pixel-identical, the run is faster). Writes render-cull.json into the output folder')
    p.add_argument('--render-cull-verify', action='store_true',
                   help='check mode (slow; implies --render-cull): every culled picture is also rendered from the full scene and compared; any difference '
                        'ends the run with exit code 3 after it (render-cull.json lists them)')
    p.add_argument('--wall-cap-s', type=float, default=None,
                   help='wall-clock safety cap of one robot\'s rollout in seconds (default: the old 14400 s, 1800 s without the look-around); a 900 sim s run '
                        'of nine robots needs more than 14400 s')
    p.add_argument('--zone-confirm-close', action='store_true', help='require a close camera fix before the final zone approach and release')
    p.add_argument('--render-on-demand', action='store_true',
                   help='speed switch (default off = every run unchanged; perception change): a robot\'s camera is rendered only on ticks where something reads the picture '
                        '(not while the robot waits for the destination / the door, in the look-around settle ticks and in the release replay), and a ceiling camera '
                        'without a robot card in its picture is not rendered (harness/render_on_demand_v1.py). Needs --overhead and --robot-tags; not with --multi-carry / --llm-moves')
    solo.execution_options.add_arguments(p)
    p.add_argument('--decision-audit', action='store_true',
                   help='record actual decision inputs and evaluation-only physical setdown times for scene boxes')
    a = p.parse_args()
    opts = solo.execution_options.from_args(p, a)
    if a.dest_listen_zero:
        if a.listen_s not in (None, 0.):
            p.error('--dest-listen-zero and --listen-s %s disagree' % a.listen_s)
        a.listen_s = 0.
    if a.listen_s is not None and not (math.isfinite(a.listen_s) and a.listen_s >= 0):
        p.error('--listen-s must be a finite number of seconds >= 0')
    if (a.fail_robot is None) != (a.fail_at_s is None):
        p.error('--fail-robot and --fail-at-s go together')
    if a.fail_at_s is not None and not (math.isfinite(a.fail_at_s) and a.fail_at_s >= 0):
        p.error('--fail-at-s must be a finite number of seconds >= 0')
    if a.wall_cap_s is not None and not (math.isfinite(a.wall_cap_s) and a.wall_cap_s > 0):
        p.error('--wall-cap-s must be a finite number of seconds > 0')
    if a.render_on_demand and not (a.overhead and a.robot_tags):
        p.error('--render-on-demand needs --overhead and --robot-tags')
    if a.render_on_demand and (a.multi_carry or a.llm_moves):
        p.error('--render-on-demand is not supported with --multi-carry / --llm-moves')
    if a.multi_carry and not (a.overhead and a.robot_tags):
        p.error('--multi-carry needs --overhead and --robot-tags')
    if a.llm_moves and not (a.overhead and a.robot_tags):
        p.error('--llm-moves needs --overhead and --robot-tags')
    orders = dict(pair.split(':') for pair in a.orders.split(','))
    knows = {pair.split(':')[0]: tuple(pair.split(':')[1].split('+')) for pair in a.knows.split(',')}
    if a.brain_url:
        brain = RemoteBrain(a.brain_url)
    else:
        if a.fixed == 'oracle' and a.scenes:
            # the scene's all-knowing reference plan (first assignment per robot), door order = robot number order (r1, r2, r3)
            data = json.loads(a.scenes.read_text())
            sc = next(s_ for s_ in (data['scenes'] if isinstance(data, dict) else data) if s_['id'] == a.scene_id)
            brain = oracle_fixed_plan(sc, a.multi_carry)
            brain.wide_second_pick = bool(opts is not None and opts.oracle_wide_pick)       # --oracle-wide-pick (DEFAULT off)
        else:
            fixed = [f.split(':') for f in a.fixed.split(',')]
            if a.multi_carry:
                # robot:colour:zone entries; a robot named again gets another carry
                assignment = {}
                for r, colour, zone in fixed:
                    assignment.setdefault(r, []).append((colour, zone))
                brain = MultiFixedPlan(assignment, list(assignment))
            else:
                brain = FixedPlan({r: (colour, zone) for r, colour, zone in fixed}, [r for r, _, _ in fixed])
    from scripts.run_grasp_act_recovery import dependency_modules
    # speed switches (DEFAULT off: nothing is patched, no extra argument reaches run_team, the run is byte-identical to one without them)
    cull = render_cull_v1.install(verify=a.render_cull_verify) if (a.render_cull or a.render_cull_verify) else None
    extra = {} if a.wall_cap_s is None else {'wall_cap_s': a.wall_cap_s}
    if opts is not None:
        extra['exec_options'] = opts
    if a.decision_audit:
        extra['decision_audit'] = True
    if a.render_on_demand:
        extra['render_on_demand'] = True
    if a.zone_confirm_close:
        extra['zone_confirm_close'] = True
    try:
        with dependency_modules(a.scene_source):
            scene = None
            if a.scenes:
                data = json.loads(a.scenes.read_text())
                scene = next(s_ for s_ in (data['scenes'] if isinstance(data, dict) else data) if s_['id'] == a.scene_id)
            run_team(json.loads(a.plan.read_text()), json.loads(a.protocol.read_text()), a.model, a.output,
                     brain=brain, orders=orders, knows=knows, second_item=a.second_item, scene=scene,
                     scene_without=tuple(k for k in a.scene_without.split(',') if k),
                     actor_python=a.actor_python, cap_s=a.cap_s, n_action_steps=8, actor_threads=a.actor_threads,
                     teacher_start_v1=True, grasp_transition_rule=True, approach_survey_v1=True,
                     robot_tags=a.robot_tags, truth_every=a.truth_every, regrasp_max=a.regrasp_max, overhead=a.overhead,
                     redecide_destination=a.redecide_destination, listen_unit_s=a.listen_s, full_info=a.full_info,
                     multi_carry=a.multi_carry, llm_moves=a.llm_moves, aside_mode=a.aside_mode,
                     held_edge_fix=a.held_check_edge_fix, look_around=a.look_around_option,
                     fail_robot=a.fail_robot, fail_at_s=a.fail_at_s, stop_failed_body=a.stop_failed_body, **extra)
    finally:
        if cull is not None:
            try:
                cull.uninstall()
                if Path(a.output).is_dir():
                    write_json(Path(a.output) / 'render-cull.json', cull.report())
            except Exception as error:     # the report must never hide the error of the run
                print('render-cull report failed: %r' % (error,), file=sys.stderr)
    if cull is not None and cull.mismatches:
        print('RENDER_CULL_VERIFY_FAILED: %d culled pictures differ from the full-scene picture (render-cull.json)' % cull.mismatches, file=sys.stderr)
        raise SystemExit(3)


if __name__ == '__main__':
    main()
