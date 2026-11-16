"""Two or three robots, one world, and a planner that decides (development run).

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
from pathlib import Path
import re
import urllib.request

from harness.grasp_act_data import write_json
import scripts.run_grasp_act_student as solo
from scripts.run_duo_carry import second_task

NAME = {'cyan': 'blue', 'red': 'red', 'green': 'red'}   # the 'green' task object is drawn red
ZONES = ('orange', 'blue', 'purple')
SIGN_ZONES = ('sign11', 'sign12', 'sign13')   # destinations marked by number signs on walls (with --robot-tags)
SIGN_RECT = {'sign11': (4.72, 5.375, -0.10, 0.90), 'sign12': (4.72, 5.375, -2.60, -1.60), 'sign13': (2.90, 3.90, -3.125, -2.47)}
RETHINK_S = 20.
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
    robots take the same box when a scene has two boxes of one colour (seen in a three-robot gate: two robots of one scene chose
    the box that belongs to the lower-numbered robot; the nearest box is the scene's oracle box)."""
    found = []
    for i, o in enumerate(options):
        if '<%s box>' % colour in o['text']:
            m = re.search(r'([0-9]+(?:\.[0-9]+)?) m away', o['text'])
            found.append((float(m.group(1)) if m else float('inf'), i, o['key']))
    return min(found)[2] if found else 'wait'


class FixedPlan:
    """Reference condition, not a planner: a fixed assignment and a fixed door order (first robot, then the next; for
    three robots the robot numbers in order)."""
    sends_messages = False      # nothing is ever delivered to a robot: a destination is never asked again

    def __init__(self, assignment, order):
        self.assignment, self.order, self.done, self.log = assignment, list(order), set(), []
        self.ended = set()     # robots whose run is over, for any reason: they will not use the door again

    def tell(self, rid, facts):
        if facts.get('milestone') == 'carry_finished':
            self.done.add(rid)

    def robot_ended(self, rid):
        """The bridge calls this when a robot's run is over (carried and finished, or an empty gripper with no regrasp left, which
        never produces 'carry_finished'). Such a robot does not use the door again, so it must not hold the later robots back:
        baseline diag 20261116, L2-02 and L2-04 stood at the door until the 900 s cap behind an r1 that had ended without a carry.
        The door order itself is not changed."""
        self.ended.add(rid)

    def decide(self, rid, now_s, point, options):
        if rid not in self.assignment:
            # this robot has nothing to do in the plan (a designed scene can leave one robot idle): it ends
            self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': 'none'})
            return {'option': 'none', 'wait_s': 2.0, 'sent': [], 'calls': 0}
        colour, zone = self.assignment[rid]
        keys = [o['key'] for o in options]
        if point == 'pick':
            pick = nearest_listed_box(colour, options)
        elif point == 'destination':
            pick = 'zone:' + zone
        elif point == 'door':
            ahead = [r for r in self.order[:self.order.index(rid)] if r not in self.ended]
            pick = 'go' if all(r in self.done for r in ahead) else 'wait'
        else:
            pick = keys[0]
        self.log.append({'rid': rid, 't': now_s, 'point': point, 'option': pick})
        return {'option': pick, 'wait_s': 2.0, 'sent': [], 'calls': 0}

    def poll(self, rid, now_s):
        return True

    def record(self):
        return {'kind': 'fixed_plan', 'assignment': self.assignment, 'door_order': self.order, 'decisions': self.log}


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


def box_label(rid, index):
    """Robot-scoped name of an entry of the robot's own look-around list. The bare entry number is private to each robot,
    and robots wrote "please take entry 1" that the receiver read as its own entry 1 (found in a
    decision analysis of the development runs). The label names the owner; option keys ('box:%d') are unchanged.
    It is only a secondary handle: a receiver cannot match it to its own list, so a box is described first by its colour,
    its room and where it is relative to the robot (adopted from an external review)."""
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
# door). The planner is not told which of them it was (from an input-leak audit of the planner inputs): a structure
# that can relay messages (T1/T2) would otherwise pass other robots' positions on, one that cannot (T0) would not.
OTHER_ROBOT_OUTCOMES = ('something_stands_beyond_the_door', 'no_clear_way_to_door')


def carry_end_text(outcome):
    """What the robot tells its planner when its carry has ended (own-camera outcomes as they are)."""
    if outcome in OTHER_ROBOT_OUTCOMES:
        return 'I could not get through the door.'
    return 'My carry has ended (%s).' % outcome


# A carry that stopped anywhere but at its zone ends with the box set down where the robot stands (the release replay follows every
# such outcome) and the robot's run ends there. The planner used to be told only the outcome and went on believing the robot held
# the box (found in an action audit of the planner reports, 2026-11-15). 'box_not_held': the gripper was empty, the robot looks around and picks again.
CARRY_STOPPED_TEXT = 'My carry stopped before the zone. I set the box down where I stand and my run ends here.'
CARRY_NOT_STOPPED_OUTCOMES = ('at_zone', 'box_not_held')


def carry_end_report(outcome, dest=None):
    """What the planner is told when the carry has ended. Delivered (at_zone): where the robot set the box down, its own destination
    ('zone_sign12' -> 'I set the box down at the <sign12 zone>; my run ends here.', the bracket written as in the destination options;
    nothing about whether that was the right place). Stopped before the zone: carry_end_text(outcome) (the door outcomes still do not say where the other robots are) and the
    plain fact that the box was set down in place and the run ends. box_not_held: carry_end_text only (the robot looks around again)."""
    text = carry_end_text(outcome)
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


PUT_DOWN = 'put_down'     # destination option 'put the box I am holding down here and finish' (key; also the value in choices/dest)
REDECIDE_POLL_S = 1.      # while carrying towards the door the robot looks for a new message once per this many seconds
REDECIDE_MAX_ASKS = 3     # asks of the destination point for one batch of new messages (the planner may send a message first)


def destination_options():
    return [{'key': 'zone:' + z, 'text': 'transport the box I am holding to the <%s zone>' % z} for z in ZONES] \
        + [{'key': 'wait', 'text': 'wait here, holding the box'},
           # a box that no order asks for must not be carried to a zone (counts as an error); the robot may put it down and finish
           # (same for all structures, like 'finish' at the pick point)
           {'key': PUT_DOWN, 'text': 'put the box I am holding down here and finish'}]


def door_options():
    return [{'key': 'go', 'text': 'carry the box through the door now (one robot at a time fits)'},
            {'key': 'wait', 'text': 'wait here before going to the door'},
            # the same line as at the destination question (a robot that holds a box no order asks for is stuck at both)
            {'key': PUT_DOWN, 'text': 'put the box I am holding down here and finish'}]


def hooks(rid, brain, clock, log, where=None, listen_s=0., can_grasp=None, redecide=False, passed=None):
    """can_grasp (DEFAULT None = every colour): the colours this robot is able to grasp. Only the pick options are
    limited to those colours; the seen-boxes fact still lists every box the robot saw, each box of another colour with the
    note 'I cannot grasp this colour' (so the planner can tell a teammate about it; scene design DESIGN-COOP.md).

    redecide (DEFAULT False = the destination is chosen once and stays): when a new message has been delivered to the
    robot after it chose its destination and before it passes the door (passed() true), the planner is asked the
    destination point again with the same options, once per batch of new messages (a robot that cannot get messages,
    such as T0 or the fixed plan, never triggers it). Option 'wait' or no option keeps the destination chosen before.
    The answer is handed to the motion code through the same carry_to callable (run_steps(redecide=True)).

    The destination question, its re-decision and the door question also offer 'put the box I am holding down here and finish'
    (key PUT_DOWN, every structure). The callable then answers 'put_down' (choices dest 'put_down'): the motion code releases the
    box where the robot stands (before the door is passed) and the robot ends; the box stays outside every zone (not moved, not a
    wrong place). No further door question, re-decision or carry-end report follows, and the planner is told nothing new."""
    state = {'next': 0., 'poll': 0., 'listed': False, 'picked': None, 'dest': None, 'go': False, 'waits': False}

    def waiting():
        """True while the robot keeps waiting. It asks its planner again when a new message has reached it, or after
        RETHINK_S without one; a waiting robot does not call the planner every tick."""
        now = clock()
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
        options = destination_options()
        before = state['dest']
        answer = brain.decide(rid, now, 'destination', options)
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
        here = where() if where is not None else None
        if here and here != state.get('told_where'):
            brain.tell(rid, {'progress': 'I am %s.' % here})
            state['told_where'] = here
        answer = brain.decide(rid, now, point, options)
        log.append({'t': round(now, 1), 'rid': rid, 'point': point, 'options': [o['key'] for o in options],
                    'option': answer.get('option'), 'sent': answer.get('sent', []), 'calls': answer.get('calls'),
                    'halted': bool(answer.get('halted'))})
        state['asked'] = now
        if answer.get('halted'):
            state['halted'] = True
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

    def choose_box(entries):
        seen = [(i, e) for i, e in enumerate(entries) if e['kind'] in NAME]
        boxes = [(i, e) for i, e in seen if can_grasp is None or NAME[e['kind']] in can_grasp]
        if not boxes:
            return None                       # nothing it can grasp in sight: its run ends (the planner is not asked)
        if waiting():
            return 'wait'
        if not state['listed']:
            brain.tell(rid, {'seen_boxes': [dict({'entry': box_label(rid, i), 'colour': NAME[e['kind']], 'distance_m': round(e['distance_m'], 2),
                                                  'bearing_deg': round(math.degrees(e['bearing_rad'])), 'room': 'box room',
                                                  'relation': relation_text(round(math.degrees(e['bearing_rad'])))},
                                                 **({'note': 'I cannot grasp this colour'}
                                                    if can_grasp is not None and NAME[e['kind']] not in can_grasp else {}))
                                             for i, e in seen]})
            state['listed'] = True
        option = ask('pick', [{'key': 'box:%d' % i, 'text': 'go grasp target object <%s box> %s (my label %s)'
                               % (NAME[e['kind']], box_where(e), box_label(rid, i))} for i, e in boxes]
                     + [{'key': 'wait', 'text': 'wait here for now'},
                        # the task tells every robot that moving a box no order asks for counts as an error and that it may
                        # finish when there is nothing useful for it to do (same for all structures)
                        {'key': 'finish', 'text': 'finish: there is nothing useful for me to do'}])
        if option is None:
            return 'wait'
        if option in ('none', 'finish'):
            state['ended'] = option          # the fixed plan gives the robot nothing ('none'), or it chose to finish
            return None                      # nothing for this robot: its run ends without grasping
        index = int(option.split(':')[1])
        state['picked'] = NAME[entries[index]['kind']]
        state['label'] = box_label(rid, index)
        brain.tell(rid, {'progress': 'I am going to grasp the <%s box> %s (my label %s).' % (state['picked'], box_where(entries[index]), state['label'])})
        return index

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
        option = ask('destination', destination_options())
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
        if waiting():
            return False
        option = ask('door', door_options())
        if option is None:
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
        if state['picked'] is None or (state.get('holding') and not state['dest']):
            return True
        if state['waits'] and clock() < state['next']:
            return True
        return bool(redecide and state['dest'] and state['dest'] != PUT_DOWN and not state.get('halted')
                    and not (passed is not None and passed()))

    state['decision_open'] = decision_open
    return choose_box, destination, gate, state


def run_team(plan, protocol, model, output, *, brain, orders, knows, scene_without=(), second_item=None, scene=None,
             redecide_destination=False, listen_unit_s=None, full_info=False, **kw):
    """scene (DEFAULT None): a designed scene (the format of scenes/*.json): boxes, robot starts, orders with
    counts and signs, which orders each robot knows. Without it, the old colour orders on the staged scene.
    With a scene the robots are the scene's robots (2 or 3, in the scene's order); the optional scene field
    `can_grasp` {rid: [colours]} limits which box colours a robot can grasp.
    redecide_destination (DEFAULT False here; the command line turns it on): a robot that is told something new after it
    chose its destination and before it passes the door is asked the destination again (see hooks).
    Experiment conditions (DEFAULT None / False = unchanged behaviour; the record gets a 'conditions' entry only when one is set):
    listen_unit_s: the destination listening unit in seconds instead of DEST_LISTEN_S (rank times unit; 0 = nobody listens);
    full_info: every robot is told every order of the team as its own (the scene's `knows` is kept in the record)."""
    allowed = {}
    if scene is not None:
        kw['layout'] = {'boxes': [{'colour': b['colour'], 'x': b['x'], 'y': b['y'], 'id': b['id']} for b in scene['boxes']]}
        orders = [{'id': o['id'], 'colour': o['colour'], 'count': o['count'], 'dest': 'sign%d' % o['sign']} for o in scene['orders']]
        knows = {r: tuple(v) for r, v in scene['knows'].items()}
        robots = tuple(r['rid'] for r in scene['robots'])
        if not 2 <= len(robots) <= 3 or len(set(robots)) != len(robots) or any(r_ not in ('r1', 'r2', 'r3') for r_ in robots):
            raise ValueError('a scene needs 2 or 3 distinct robots among r1, r2, r3: %s' % (robots,))
        for r_, colours in (scene.get('can_grasp') or {}).items():
            if r_ not in robots or any(c_ not in CAPABLE_COLOURS for c_ in colours):
                raise ValueError('can_grasp: unknown robot or colour: %s %s' % (r_, colours))
            if set(colours) != set(CAPABLE_COLOURS):         # a robot that can grasp both colours has no limit
                allowed[r_] = tuple(c_ for c_ in CAPABLE_COLOURS if c_ in colours)
        assignment = getattr(brain, 'assignment', None)
        if assignment is not None and any(r_ not in robots for r_ in assignment):
            raise ValueError('the fixed plan names a robot that is not in the scene: %s' % (sorted(assignment),))
        for r_, (colour_, _zone) in (assignment or {}).items():
            if r_ in allowed and colour_ not in allowed[r_]:
                raise ValueError('the fixed plan gives %s a <%s box> it cannot grasp' % (r_, colour_))
    else:
        orders = [{'id': colour, 'colour': colour, 'count': 1, 'dest': zone} for colour, zone in orders.items()]
    global ZONES, RECT
    if kw.get('robot_tags'):
        # destinations are the wall signs, not floor paint (user decision 2026-11-15)
        ZONES, RECT = SIGN_ZONES, SIGN_RECT
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    objects = ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']).config['setup_only']['objects']
    if scene is not None:
        first, second = robots[0], robots[1]
        z = plan['spawns'][plan['robot_id']][2]
        starts = {r['rid']: [r['x'], r['y'], z, r['yaw']] for r in scene['robots']}
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
    conditions = {}
    if listen_unit_s is not None:
        conditions['listen_s'] = listen_unit_s
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
                                                           listen_s=DEST_LISTEN_S * sorted(robots).index(rid) * listen_scale(listen_unit_s),
                                                           can_grasp=allowed.get(rid), redecide=redecide_destination,
                                                           passed=lambda r_=rid: 'door_passed' in events[r_])
        steps[rid] = solo.run_steps(plans[rid], protocol, model, output / ('out-' + rid), carry_to=destination,
                                    choose_box=choose_box, carry_gate=gate, shared=shared, events=events[rid],
                                    scene_without=scene_without, **kw)
    requests, reports = {}, {}
    try:
        for rid in robots:
            requests[rid] = next(steps[rid])
        world = shared['world']
        shared['t0'] = float(world.data.time) + 1.   # the settle second ends here for both robots
        while requests:
            until = min(r['until'] for r in requests.values())
            solo.advance_physics(world, list(requests.values()), until)
            for rid in [r for r in robots if r in requests and requests[r]['until'] <= until + 1e-8]:
                try:
                    requests[rid] = next(steps[rid])
                except StopIteration as stop:
                    reports[rid] = stop.value
                    del requests[rid]
                    getattr(brain, 'robot_ended', lambda _r: None)(rid)    # the fixed plan frees its door order; a planner host has no such call
                # own milestones: the robot learns them itself and may report them (a decision point without motion)
                fails = events[rid].get('not_holding', [])
                if len(fails) > states[rid].get("fails_told", 0):
                    # empty gripper: the robot says so to its planner, which picks again from a fresh look-around
                    states[rid]['fails_told'] = len(fails)
                    brain.tell(rid, {'progress': 'I lost the <%s box>: my gripper is empty. I will look around again and '
                                                 'choose a box again.' % states[rid]['picked'], 'milestone': 'grasp_failed'})
                    answer = brain.decide(rid, clock(), 'report', [{'key': 'continue', 'text': 'continue my task'}])
                    log.append({'t': round(clock(), 1), 'rid': rid, 'point': 'report', 'milestone': 'grasp_failed',
                                'sent': answer.get('sent', []), 'calls': answer.get('calls')})
                    states[rid].update(listed=False, picked=None, dest=None, go=False, holding=False, next=0.)
                    states[rid]['put_down'] = None
                for name in ('door_passed', 'carry_finished'):
                    if name in events[rid] and name not in told[rid]:
                        told[rid].add(name)
                        if name == 'carry_finished' and events[rid][name].get('outcome') != 'box_not_held':
                            states[rid]['chance_off'] = True      # the run ends at the carry end (the robot may still lower its arm and release)
                        if name == 'carry_finished' and events[rid][name].get('outcome') == PUT_DOWN:
                            continue      # the robot chose to put its box down and finish: no report, no new text for the planner
                        outcome = events[rid][name].get('outcome') if name == 'carry_finished' else None
                        text = ('I have passed the door with the <%s box>.' % states[rid]['picked'] if name == 'door_passed' else
                                carry_end_report(outcome, states[rid]['dest']))
                        brain.tell(rid, {'progress': text, 'milestone': name})
                        answer = brain.decide(rid, clock(), 'report', [{'key': 'continue', 'text': 'continue my task' if name == 'door_passed'
                                                                        else carry_end_option_text(outcome)}])
                        log.append({'t': round(clock(), 1), 'rid': rid, 'point': 'report', 'milestone': name,
                                    'sent': answer.get('sent', []), 'calls': answer.get('calls')})
                if rid in requests:
                    message_chance(rid, brain, clock, chances, states[rid])
        record['status'] = 'complete'
    finally:
        placed = {}
        if 'world' in shared:
            world = shared['world']
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
                      choices={rid: {k: states[rid][k] for k in ('picked', 'dest', 'go')} for rid in states},
                      redecisions={rid: states[rid].get('redecisions', []) for rid in states},
                      ended_without_grasp={rid: states[rid]['ended'] for rid in states if states[rid].get('ended')})
        if chances:
            record['chances'] = chances       # message chances between decisions (T1/T2), only when one was asked (default record keys unchanged)
        put_down = {rid: states[rid]['put_down'] for rid in states if states[rid].get('put_down')}
        if put_down:
            record['put_down'] = put_down     # only when a robot chose it (default record keys unchanged); choices[rid]['dest'] is 'put_down'
        write_json(output / 'team.json', record)
    return record


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
    p.add_argument('--full-info', action='store_true',
                   help='experiment condition (full-information control): every robot is told every order of the team as its own')
    p.add_argument('--regrasp-max', type=int, default=1, help='after an empty-gripper check, look around and pick again this many times')
    p.add_argument('--truth-every', type=int, default=0, help='evaluation side: true depth and object ids every N ticks')
    p.add_argument('--scene-without', default='beam,can,tile,frame,crate,robots')
    p.add_argument('--scene-source', type=Path, required=True)
    a = p.parse_args()
    if a.listen_s is not None and not (math.isfinite(a.listen_s) and a.listen_s >= 0):
        p.error('--listen-s must be a finite number of seconds >= 0')
    orders = dict(pair.split(':') for pair in a.orders.split(','))
    knows = {pair.split(':')[0]: tuple(pair.split(':')[1].split('+')) for pair in a.knows.split(',')}
    if a.brain_url:
        brain = RemoteBrain(a.brain_url)
    else:
        if a.fixed == 'oracle' and a.scenes:
            # the scene's all-knowing reference plan (first assignment per robot), door order = robot number order (r1, r2, r3)
            data = json.loads(a.scenes.read_text())
            sc = next(s_ for s_ in (data['scenes'] if isinstance(data, dict) else data) if s_['id'] == a.scene_id)
            colour = {b['id']: b['colour'] for b in sc['boxes']}
            sign = {o['id']: 'sign%d' % o['sign'] for o in sc['orders']}
            assignment = {r: (colour[v[0][0]], sign[v[0][1]]) for r, v in sc['oracle_plan'].items() if v}
            brain = FixedPlan(assignment, sorted(assignment))
        else:
            fixed = [f.split(':') for f in a.fixed.split(',')]
            brain = FixedPlan({r: (colour, zone) for r, colour, zone in fixed}, [r for r, _, _ in fixed])
    from scripts.run_grasp_act_recovery import dependency_modules
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
                 redecide_destination=a.redecide_destination, listen_unit_s=a.listen_s, full_info=a.full_info)


if __name__ == '__main__':
    main()
