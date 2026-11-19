"""Free-talk speech stops the body on every decision path (run_team_carry): tests. No simulator, no network.

The planner answers a speech of free talk (--talk free) with {option: wait key, sent: [message], wait_s: t_say, say_s: t_say}. The runner stands the body for
max(2, wait_s) s after it, wherever the answer came from (pick / destination / door ask, report, destination re-decision, message chance). Without say_s in the
answer (every older planner, free talk off) nothing changes: tests/golden_talk_off.json holds a trace of old-style answers through every path, captured on
the commit before this change (b7d2c13) and compared byte for byte here.

Run:  python3 -B -m unittest discover -s tests -p 'test_talk_stand.py' -v   (in the worktree root)
Rewrite the golden file (only on a commit that is the reference):  python3 -B tests/test_talk_stand.py --write-golden"""
import sys
sys.dont_write_bytecode = True

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripts.run_team_carry as TEAM  # noqa: E402
import test_exec_v39 as V39  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / 'golden_talk_off.json'
GOLDEN_LOOK = Path(__file__).resolve().parent / 'golden_look_ticks_talk_off.json'


def message(text, t=12.0, to=('r2',)):
    return {'time': t, 'deliver_at': t + 2.0, 'from': 'r1', 'to': list(to), 'text': text}


class ScriptBrain:
    """A planner stand-in with scripted answers per point (decide), per call (chance) and a scripted poll."""
    sends_messages = True

    def __init__(self, decide=None, chance=None, polls=None, chance_polls=None):
        self.script = {k: list(v) for k, v in (decide or {}).items()}
        self.chances, self.polls, self.chance_polls = list(chance or []), list(polls or []), list(chance_polls or [])
        self.calls, self.told, self.ended = [], [], []

    def tell(self, rid, facts):
        self.told.append((rid, facts))

    def decide(self, rid, now_s, point, options):
        self.calls.append(['decide', rid, round(now_s, 3), point, [o['key'] for o in options]])
        queue = self.script.get(point) or []
        answer = queue.pop(0) if queue else {'option': 'wait' if point != 'report' else 'continue', 'wait_s': 2.0 if point != 'report' else 0.0, 'sent': [], 'calls': 1}
        return dict(answer)

    def poll(self, rid, now_s):
        self.calls.append(['poll', rid, round(now_s, 3)])
        return self.polls.pop(0) if self.polls else False

    def chance_poll(self, rid, now_s):
        self.calls.append(['chance_poll', rid, round(now_s, 3)])
        return self.chance_polls.pop(0) if self.chance_polls else False

    def chance(self, rid, now_s):
        self.calls.append(['chance', rid, round(now_s, 3)])
        return dict(self.chances.pop(0)) if self.chances else {'sent': [], 'calls': 0, 'asked': False, 'final': False}

    def robot_ended(self, rid):
        self.ended.append(rid)

    def record(self):
        return {'kind': 'script', 'calls': self.calls}


def old_say(text, wait_s=2.0, sent_with_action=False, **extra):
    """An answer of the planners before free talk (and of free talk off): a message sent at a point (no say_s)."""
    answer = {'option': 'wait', 'wait_s': wait_s, 'sent': [message(text)], 'calls': 1}
    if sent_with_action:
        answer['sent_with_action'] = True
    answer.update(extra)
    return answer


def snap(value):
    """The hooks state as plain JSON (a callable is written as 'fn', its address changes from run to run)."""
    return json.loads(json.dumps(value, sort_keys=True, default=lambda v: 'fn' if callable(v) else str(v)))


def hooks_trace(brain_module):
    """Scenario A: one robot through pick / destination / re-decision / door with old-style answers, another through a message chance."""
    out = {}
    clock = [12.0]
    log = []
    brain = ScriptBrain(decide={
        'pick': [old_say('first'), {'option': 'box:1', 'wait_s': 2.0, 'sent': [], 'calls': 1}],
        'destination': [old_say('sent with the action', sent_with_action=True, option='zone:orange'),
                        old_say('redecide one'), {'option': 'zone:blue', 'wait_s': 2.0, 'sent': [], 'calls': 1}],
        'door': [{'option': 'wait', 'wait_s': 2.0, 'sent': [], 'calls': 1}, old_say('at the door', option='wait')]},
        polls=[False, True, False, True, False, False, False, False])
    choose, destination, gate, state = brain_module.hooks('r1', brain, lambda: clock[0], log, redecide=True, passed=lambda: False)
    steps = []
    for t, name in ((12.0, 'choose'), (13.0, 'choose'), (14.5, 'choose'), (15.0, 'destination'), (16.0, 'destination'), (17.0, 'destination'),
                    (18.5, 'destination'), (19.5, 'destination'), (21.0, 'gate'), (24.0, 'gate'), (25.0, 'gate'), (26.0, 'gate')):
        clock[0] = t
        if name == 'choose':
            result = choose([V39.entry('red', 1., 0.), V39.entry('cyan', 1.2, 0.4)])
        elif name == 'destination':
            result = destination()
        else:
            result = gate()
        steps.append([t, name, result, snap(state)])
    out['hooks'] = {'steps': steps, 'log': log, 'calls': brain.calls}
    # a robot that carries without a re-decision: a message chance reaches it
    clock[0], chances, log2 = 30.0, [], []
    brain2 = ScriptBrain(decide={'pick': [{'option': 'box:0', 'wait_s': 2.0, 'sent': [], 'calls': 1}],
                                 'destination': [{'option': 'zone:orange', 'wait_s': 2.0, 'sent': [], 'calls': 1}]},
                         chance=[{'sent': [message('reply')], 'calls': 1, 'asked': True, 'final': False},
                                 {'sent': [], 'calls': 1, 'asked': True, 'final': True}],
                         chance_polls=[True, False, True, False, False, True, False])
    choose2, destination2, gate2, state2 = brain_module.hooks('r2', brain2, lambda: clock[0], log2, redecide=False)
    choose2([V39.entry('red', 1., 0.)])
    clock[0] = 31.0
    destination2()
    results = []
    for t in (32.0, 32.5, 33.5, 35.0, 36.5):
        clock[0] = t
        results.append([t, brain_module.message_chance('r2', brain2, lambda: clock[0], chances, state2),
                        snap(state2)])
    out['chance'] = {'results': results, 'chances': chances, 'log': log2, 'calls': brain2.calls}
    return out


def team_trace(brain_module):
    """Scenario B: run_team with fake robot generators that raise the milestones (grasp_failed, door_passed, carry_finished); the planner answers old-style."""
    sim = types.ModuleType('sim.zone_scenario_scene')
    sim.ScenarioFinalV3Scene = types.SimpleNamespace(from_scenario=lambda sid, seed: types.SimpleNamespace(config={'setup_only': {'objects': {}}}))
    wheels = []

    def run_steps(plan, protocol, model, output, **kw):
        shared = kw['shared']
        if 'world' not in shared:
            shared['world'] = V39.FakeWorld()
        world, rid, events = shared['world'], plan['robot_id'], kw['events']
        port = V39.FakePort(rid)
        yield {'world': world, 'robot': rid, 'port': port, 'wheels': None, 'deadlines': None, 'until': 1.0}
        for k in range(30):
            if rid == 'r1' and k == 5:
                events.setdefault('not_holding', []).append(0.5)
            if rid == 'r1' and k == 10:
                events['door_passed'] = 1.0
            if rid == 'r1' and k == 20:
                events['carry_finished'] = {'at_s': 2.0, 'outcome': 'at_zone'}
            if rid == 'r2' and k == 8:
                events['door_passed'] = 1.0
            yield {'world': world, 'robot': rid, 'port': port, 'wheels': [.35] * 4, 'deadlines': [world.data.time + .1] * 4, 'until': 1.0 + .1 * (k + 1)}
        return {'status': 'complete', 'rid': rid}

    def advance(world, requests, until):
        wheels.append([round(until, 3), {r['port'].rid: (list(r['wheels']) if r['wheels'] is not None else None) for r in requests}])
        world.data.time = until

    scene = {'id': 'T', 'boxes': [{'colour': 'red', 'x': 1., 'y': 1., 'id': 'b1'}],
             'robots': [{'rid': 'r1', 'x': 0., 'y': 0., 'yaw': 0.}, {'rid': 'r2', 'x': 0., 'y': 1., 'yaw': 0.}],
             'orders': [{'id': 'o1', 'colour': 'red', 'count': 1, 'sign': 11}], 'knows': {'r1': ['o1'], 'r2': ['o1']}}
    plan = {'scenario_id': 'x', 'seed': 1, 'robot_id': 'r1', 'spawns': {'r1': [0., 0., .03, 0.]}}
    brain = ScriptBrain(decide={'report': [old_say('after the lost box', option='continue', wait_s=0.0), old_say('passed the door', option='continue', wait_s=0.0),
                                           {'option': 'continue', 'wait_s': 0.0, 'sent': [], 'calls': 1}, old_say('the other robot', option='continue', wait_s=0.0)]})
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'sim.zone_scenario_scene': sim}), \
            mock.patch.object(brain_module.solo, 'run_steps', run_steps), mock.patch.object(brain_module.solo, 'advance_physics', advance):
        record = brain_module.run_team(plan, {}, 'model', Path(tmp) / 'out', brain=brain, orders={}, knows={}, scene=scene)
    keep = {k: record[k] for k in sorted(record) if k not in ('brain',)}
    return {'record': json.loads(json.dumps(keep, sort_keys=True, default=str)), 'wheels': wheels, 'brain_calls': brain.calls, 'ended': brain.ended}


def switch_off_trace(brain_module=TEAM):
    return json.loads(json.dumps({'hooks_and_chance': hooks_trace(brain_module), 'run_team': team_trace(brain_module)}, sort_keys=True, default=str))


def structured_rows(back=29, turn=0, waits=(), pre=3):
    """Command rows of a held check as CarryNav issues them (arm raise 20, back-off `back` + 5, pause 10 with the look, 5 trailing, then a turn of `turn` moving
    rows and its own look), `pre` rows of another source before, a robot_ahead_wait row inserted before each block position in `waits`; ends with the held_check row."""
    block = [('carry_code', 0.)] * 20 + [('carry_code', -.35)] * back + ([('carry_code', 0.)] * 5 if back else []) + [('carry_code', 0.)] * 15
    if turn:
        block += [('carry_code', .35)] * turn + [('carry_code', 0.)] * 15
    block += [('carry_code', 0.)] * 6
    spec = [('act', 0.)] * pre
    for i, row in enumerate(block):
        spec += [('robot_ahead_wait', 0.)] * waits.count(i)
        spec.append(row)
    return spec + [('held_check', 0.)]


def look_battery():
    """Command-row lists without a talk_stand row (a run with free talk off): short blocks, with and without a back-off, with a turn, with robot_ahead_wait rows."""
    import random
    rng = random.Random(7)
    cases = {}
    for back in (0, 1, 10, 29, 40):
        for turn in (0, 3, 12):
            cases['back%d-turn%d' % (back, turn)] = structured_rows(back, turn)
            cases['back%d-turn%d-waits' % (back, turn)] = structured_rows(back, turn, sorted(rng.randrange(0, 90) for _ in range(6)))
    cases['short'] = structured_rows(0, 0)[-20:]
    cases['empty'] = [('held_check', 0.)]
    for n in range(20):
        cases['random%02d' % n] = [(rng.choice(['carry_code', 'carry_code', 'carry_code', 'robot_ahead_wait', 'act']), rng.choice([0., 0., -.35, .35]))
                                   for _ in range(rng.randint(1, 80))] + [('held_check', 0.)]
    return cases


def look_trace(look_ticks=V39.OFF.look_ticks):
    return {name: look_ticks(V39.OfflineHelpers.rows(spec), len(spec) - 1) for name, spec in sorted(look_battery().items())}


def with_stands(spec, before):
    """spec with a talk_stand row inserted before each spec index in `before` (the held_check row is the last index); returns (rows, {old index: new index})."""
    out, where = [], {}
    for i, row in enumerate(spec):
        out += [('talk_stand', 0.)] * before.count(i)
        where[i] = len(out)
        out.append(row)
    return out, where


class LookTicksTalkStand(unittest.TestCase):
    """A speech during the held check puts talk_stand rows (wheels 0) into the carry rows: look_ticks must skip them like robot_ahead_wait rows, not fail with 'rows do not fit'."""

    def check(self, spec, before):
        base = V39.OFF.look_ticks(V39.OfflineHelpers.rows(spec), len(spec) - 1)
        rows, where = with_stands(spec, before)
        got = V39.OFF.look_ticks(V39.OfflineHelpers.rows(rows), len(rows) - 1)
        self.assertIsNotNone(base)
        self.assertIsNotNone(got, 'rows do not fit')
        self.assertEqual(got, [where[i] for i in base])                   # the same carry rows, at their shifted places
        self.assertTrue(all(rows[i][0] == 'carry_code' for i in got))     # never a stand row
        return got

    def test_a_stand_right_before_the_held_check_row(self):
        spec = structured_rows(29, 0)
        self.check(spec, [len(spec) - 1])

    def test_stands_inside_the_look_and_the_back_off(self):
        spec = structured_rows(29, 0)
        self.check(spec, [3 + 25, 3 + 20 + 29 + 5 + 7, 3 + 20 + 29 + 5 + 7, 3 + 20 + 29 + 5 + 8, len(spec) - 1])      # during the back-off, inside the 5 look frames, at the end

    def test_stands_with_a_turn_and_with_robot_ahead_waits(self):
        spec = structured_rows(10, 12, waits=[30, 31, 70])
        self.check(spec, [3 + 5, 3 + 60, 3 + 61, len(spec) - 1])

    def test_a_stand_row_that_was_the_only_difference_was_a_false_failure_before(self):
        spec = structured_rows(29, 0)
        rows, _ = with_stands(spec, [len(spec) - 1])
        self.assertEqual(rows[-2][0], 'talk_stand')                       # the row just before held_check is a stand row: the old loop stopped there and found no block
        self.assertIsNotNone(V39.OFF.look_ticks(V39.OfflineHelpers.rows(rows), len(rows) - 1))

    def test_too_few_carry_rows_still_do_not_fit(self):
        spec = structured_rows(0, 0)[-20:]
        rows, _ = with_stands(spec, [5, 6, 19])
        self.assertIsNone(V39.OFF.look_ticks(V39.OfflineHelpers.rows(rows), len(rows) - 1))             # stand rows are not carry rows: they do not make a short block long enough


class SwitchOff(unittest.TestCase):
    def test_old_style_answers_behave_exactly_as_before_the_change(self):
        """Old-style answers (a message without say_s) through every path: pick / destination / door asks, report, re-decision, chance, run_team."""
        self.assertEqual((json.dumps(switch_off_trace(), indent=1, sort_keys=True) + '\n').encode(), GOLDEN.read_bytes())

    def test_look_ticks_of_rows_without_a_talk_stand_are_unchanged(self):
        """held_edge_offline.look_ticks on rows of a run with free talk off (the battery has none): the same answers as before it knew talk_stand (b7d2c13)."""
        golden = json.loads(GOLDEN_LOOK.read_text())
        self.assertEqual((json.dumps(look_trace(), indent=1, sort_keys=True) + '\n').encode(), GOLDEN_LOOK.read_bytes())
        self.assertGreater(sum(1 for v in golden.values() if v is not None), 10)      # the battery has real answers, not only 'rows do not fit'
        self.assertGreater(sum(1 for v in golden.values() if v is None), 5)           # and rows that really do not fit


def say(text, say_s, **extra):
    """An answer of the free-talk planner to a speech: the wait key, the message, wait_s = say_s = t_say."""
    answer = {'option': 'wait', 'wait_s': say_s, 'say_s': say_s, 'sent': [message(text)], 'calls': 1}
    answer.update(extra)
    return answer


class Helper(unittest.TestCase):
    def test_a_speech_stands_the_body_for_the_say_time_with_the_two_second_floor(self):
        self.assertEqual(TEAM.talk_stand_until(10.0, {'say_s': 5.0, 'wait_s': 5.0, 'sent': [message('x')]}), 15.0)
        self.assertEqual(TEAM.talk_stand_until(10.0, {'say_s': 0.5, 'wait_s': 0.5, 'sent': [message('x')]}), 12.0)      # the runner's 2 s floor (ask(): turn_used)
        self.assertEqual(TEAM.talk_stand_until(10.0, {'say_s': 1.6, 'sent': [message('x')]}), 12.0)                      # no wait_s: 2 s

    def test_nothing_else_stands_the_body(self):
        self.assertIsNone(TEAM.talk_stand_until(10.0, {'wait_s': 5.0, 'sent': [message('x')]}))                          # an older planner / free talk off: no say_s
        self.assertIsNone(TEAM.talk_stand_until(10.0, {'say_s': 5.0, 'wait_s': 5.0, 'sent': [message('x')], 'sent_with_action': True}))
        self.assertIsNone(TEAM.talk_stand_until(10.0, {'say_s': 5.0, 'wait_s': 5.0, 'sent': []}))
        self.assertIsNone(TEAM.talk_stand_until(10.0, {'option': 'wait', 'wait_s': 2.0, 'sent': [], 'calls': 1}))
        state = {}
        self.assertIsNone(TEAM.talk_stand(state, 10.0, {'wait_s': 5.0, 'sent': [message('x')]}, 'chance'))
        self.assertEqual(state, {})                                                                                      # not even an empty key is added


class HookPaths(unittest.TestCase):
    ENTRIES = [V39.entry('red', 1., 0.), V39.entry('cyan', 1.2, 0.4)]

    def carrying(self, brain, redecide):
        clock, log = [12.0], []
        choose, destination, gate, state = TEAM.hooks('r1', brain, lambda: clock[0], log, redecide=redecide, passed=(lambda: False) if redecide else None)
        choose(self.ENTRIES)
        clock[0] = 13.0
        destination()
        return clock, log, choose, destination, gate, state

    def test_a_speech_at_the_destination_re_decision_stands_the_body_and_holds_the_door_question(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0', 'wait_s': 2.0, 'sent': [], 'calls': 1}],
                                    'destination': [{'option': 'zone:orange', 'wait_s': 2.0, 'sent': [], 'calls': 1}, say('so I tell r2', 4.2)],
                                    'door': [{'option': 'go', 'wait_s': 2.0, 'sent': [], 'calls': 1}]},
                            polls=[True, False, False, False])
        clock, log, choose, destination, gate, state = self.carrying(brain, True)
        clock[0] = 14.0
        destination()                                                  # poll: a new message -> re-decision -> the planner answers with a speech
        self.assertEqual(state['stand_until'], 14.0 + 4.2)
        self.assertEqual(state['talk_stands'], [{'t': 14.0, 'path': 'redecision', 'say_s': 4.2, 'stand_s': 4.2, 'via': 'stand_hold'}])
        asked = len(brain.calls)
        clock[0] = 14.0
        self.assertFalse(gate())                                       # the door question comes at the same time: held while the robot speaks
        clock[0] = 17.0
        self.assertFalse(gate())
        self.assertFalse([c for c in brain.calls[asked:] if c[0] == 'decide' and c[3] == 'door'])
        clock[0] = 18.3
        self.assertTrue(gate())                                        # the speech is over: the door question is asked
        self.assertEqual([c[3] for c in brain.calls if c[0] == 'decide'], ['pick', 'destination', 'destination', 'destination', 'door'])   # the re-decision asks again once the speech is out

    def test_a_speech_at_a_message_chance_stands_the_body(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0', 'wait_s': 2.0, 'sent': [], 'calls': 1}],
                                    'destination': [{'option': 'zone:orange', 'wait_s': 2.0, 'sent': [], 'calls': 1}]},
                            chance=[dict(say('reply', 3.0), asked=True, final=False)], chance_polls=[True, False])
        clock, log, choose, destination, gate, state = self.carrying(brain, False)
        chances = []
        clock[0] = 20.0
        self.assertTrue(TEAM.message_chance('r1', brain, lambda: clock[0], chances, state))
        self.assertEqual(state['stand_until'], 23.0)
        self.assertEqual(state['talk_stands'], [{'t': 20.0, 'path': 'chance', 'say_s': 3.0, 'stand_s': 3.0, 'via': 'stand_hold'}])
        self.assertEqual(len(chances), 1)

    def test_a_speech_at_a_decision_point_keeps_its_own_wait_and_is_only_noted(self):
        brain = ScriptBrain(decide={'pick': [say('hello', 3.2)]})
        clock, log = [12.0], []
        choose, destination, gate, state = TEAM.hooks('r1', brain, lambda: clock[0], log)
        self.assertEqual(choose(self.ENTRIES), 'wait')
        self.assertEqual(state['next'], 12.0 + 3.2)                   # ask(): turn_used, max(2, wait_s)
        self.assertNotIn('stand_until', state)
        self.assertEqual(state['talk_stands'], [{'t': 12.0, 'path': 'ask:pick', 'say_s': 3.2, 'stand_s': 3.2, 'via': 'wait'}])

    def test_the_pick_question_waits_while_the_robot_speaks_after_a_report(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0', 'wait_s': 2.0, 'sent': [], 'calls': 1}]})
        clock, log = [12.0], []
        choose, destination, gate, state = TEAM.hooks('r1', brain, lambda: clock[0], log)
        TEAM.talk_stand(state, 12.0, say('after the lost box', 3.0), 'report:grasp_failed')
        self.assertEqual(choose(self.ENTRIES), 'wait')                # still speaking: no question to the planner
        self.assertEqual(brain.calls, [])
        clock[0] = 15.1
        self.assertEqual(choose(self.ENTRIES), 0)


class RunTeamStand(unittest.TestCase):
    """run_team with fake robot generators that ask stand_hold on every tick like run_steps does: wheels 0 while it is True."""

    def run_team(self, report_answers, events_at, ticks=70):
        sim = types.ModuleType('sim.zone_scenario_scene')
        sim.ScenarioFinalV3Scene = types.SimpleNamespace(from_scenario=lambda sid, seed: types.SimpleNamespace(config={'setup_only': {'objects': {}}}))
        timeline = {'r1': [], 'r2': []}
        holds = []

        def run_steps(plan, protocol, model, output, **kw):
            shared = kw['shared']
            if 'world' not in shared:
                shared['world'] = V39.FakeWorld()
            world, rid, events, hold = shared['world'], plan['robot_id'], kw['events'], kw['stand_hold']
            holds.append(rid)
            port = V39.FakePort(rid)
            yield {'world': world, 'robot': rid, 'port': port, 'wheels': None, 'deadlines': None, 'until': 1.0}
            for k in range(ticks):
                for (r_, k_), (name, value) in events_at.items():
                    if r_ == rid and k_ == k:
                        events[name] = value
                wheels = [0.] * 4 if hold() else [.35] * 4
                timeline[rid].append((round(world.data.time - shared.get('t0', 0.), 3), hold()))
                yield {'world': world, 'robot': rid, 'port': port, 'wheels': wheels, 'deadlines': [world.data.time + .1] * 4, 'until': 1.0 + .1 * (k + 1)}
            return {'status': 'complete', 'rid': rid}

        def advance(world, requests, until):
            world.data.time = until

        scene = {'id': 'T', 'boxes': [{'colour': 'red', 'x': 1., 'y': 1., 'id': 'b1'}],
                 'robots': [{'rid': 'r1', 'x': 0., 'y': 0., 'yaw': 0.}, {'rid': 'r2', 'x': 0., 'y': 1., 'yaw': 0.}],
                 'orders': [{'id': 'o1', 'colour': 'red', 'count': 1, 'sign': 11}], 'knows': {'r1': ['o1'], 'r2': ['o1']}}
        plan = {'scenario_id': 'x', 'seed': 1, 'robot_id': 'r1', 'spawns': {'r1': [0., 0., .03, 0.]}}
        brain = ScriptBrain(decide={'report': list(report_answers)})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'sim.zone_scenario_scene': sim}), \
                mock.patch.object(TEAM.solo, 'run_steps', run_steps), mock.patch.object(TEAM.solo, 'advance_physics', advance):
            record = TEAM.run_team(plan, {}, 'model', Path(tmp) / 'out', brain=brain, orders={}, knows={}, scene=scene)
        self.assertEqual(sorted(holds), ['r1', 'r2'])                  # run_steps got stand_hold for every robot
        return record, timeline, brain

    @staticmethod
    def stood(timeline, rid):
        times = [t for t, held in timeline[rid] if held]
        return (min(times), max(times)) if times else None

    def test_every_report_speech_stands_that_robot_only(self):
        for milestone, event in (('grasp_failed', ('not_holding', [0.5])), ('door_passed', ('door_passed', 1.0)), ('carry_finished', ('carry_finished', {'at_s': 2.0, 'outcome': 'at_zone'}))):
            record, timeline, brain = self.run_team([say('about %s' % milestone, 5.0, option='continue')], {('r1', 10): event})
            lo, hi = self.stood(timeline, 'r1')
            self.assertIsNone(self.stood(timeline, 'r2'), milestone)
            rows = record['talk_stands']['r1']
            self.assertEqual(len(rows), 1, milestone)
            self.assertEqual((rows[0]['path'], rows[0]['say_s'], rows[0]['stand_s'], rows[0]['via']), ('report:' + milestone, 5.0, 5.0, 'stand_hold'))
            self.assertAlmostEqual(hi - lo, 5.0 - 0.1, delta=0.15, msg=milestone)         # held from the report on for 5 s
            self.assertAlmostEqual(lo, rows[0]['t'], delta=0.15, msg=milestone)
            self.assertNotIn('r2', record['talk_stands'])

    def test_a_short_speech_stands_two_seconds_like_the_main_path(self):
        record, timeline, brain = self.run_team([say('ok', 0.5, option='continue')], {('r1', 10): ('door_passed', 1.0)})
        lo, hi = self.stood(timeline, 'r1')
        self.assertAlmostEqual(hi - lo, 2.0 - 0.1, delta=0.15)
        self.assertEqual(record['talk_stands']['r1'][0]['stand_s'], 2.0)
        self.assertEqual(record['talk_stands']['r1'][0]['say_s'], 0.5)                 # the actual say time stays in the record

    def test_a_report_without_a_speech_stands_nothing_and_leaves_no_key(self):
        for answer in ({'option': 'continue', 'wait_s': 0.0, 'sent': [], 'calls': 1},
                       {'option': 'continue', 'wait_s': 0.0, 'sent': [message('old planner message')], 'calls': 1},           # no say_s: an older planner
                       say('with an action', 5.0, option='continue', sent_with_action=True)):
            record, timeline, brain = self.run_team([answer], {('r1', 10): ('door_passed', 1.0)})
            self.assertIsNone(self.stood(timeline, 'r1'))
            self.assertNotIn('talk_stands', record)


if __name__ == '__main__':
    if '--write-golden' in sys.argv:
        GOLDEN.write_text(json.dumps(switch_off_trace(), indent=1, sort_keys=True) + '\n')
        print('wrote', GOLDEN)
        GOLDEN_LOOK.write_text(json.dumps(look_trace(), indent=1, sort_keys=True) + '\n')
        print('wrote', GOLDEN_LOOK)
    else:
        unittest.main()
