"""Multi-trip bridge and oracle contracts with a manual clock and scripted body events."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import run_team_carry as team
from test_exec_v39 import FakeWorld, entry
from test_talk_stand import ScriptBrain, say


def scene():
    # Two orders for red boxes at different places. r1's second job waits for r2's second release.
    boxes = [('a', 'red', 2.), ('b', 'red', 1.), ('c', 'blue', 3.), ('d', 'blue', 4.)]
    return dict(id='test', robots=[dict(rid=r, x=0., y=0., yaw=0.) for r in ('r1', 'r2')],
                boxes=[dict(id=b, colour=c, x=x, y=0.) for b, c, x in boxes],
                orders=[dict(id=b, colour=c, count=1, sign=z) for (b, c, _), z in zip(boxes, (11, 12, 12, 13))],
                knows={'r1': [], 'r2': []}, oracle_plan={'r1': [['a', 'a'], ['b', 'b']], 'r2': [['c', 'c'], ['d', 'd']]},
                constraints=[dict(type='order', orders=['d', 'b'])], oracle={'door_order': ['r1', 'r2']})


def release(brain, rid, trip, outcome='at_zone'):
    brain.tell(rid, dict(milestone='carry_finished', outcome=outcome, trip=trip))


class OracleTrips(unittest.TestCase):
    def setUp(self):
        self.plan = team.oracle_fixed_plan(scene(), True)

    def answer(self, rid, point, options=()):
        return self.plan.decide(rid, 0., point, options)['option']

    def test_named_box_with_same_colour_on_each_trip_and_live_return_pose(self):
        opts = [dict(key=f'box:{i}', text=f'<red box> in the box room, {d} m away, straight ahead of me') for i, d in enumerate((1., 2.))]
        self.assertEqual(self.answer('r1', 'pick', opts), 'box:1')
        self.assertEqual(self.answer('r1', 'destination'), 'zone:sign11')
        release(self.plan, 'r1', 1)
        self.assertEqual(self.answer('r1', 'next'), 'back')
        self.assertEqual(self.answer('r1', 'pick', opts), 'finish')   # no start-pose fallback on a return
        self.plan.pose_source = lambda _: (-1., 0., 0.)
        self.assertEqual(self.answer('r1', 'pick', opts), 'box:1')
        self.assertEqual(self.answer('r1', 'destination'), 'zone:sign12')
        release(self.plan, 'r1', 2)
        self.assertEqual(self.answer('r1', 'next'), 'finish')
        self.assertEqual([p['box'] for p in self.plan.pick_log], ['a', 'b', 'b'])

    def test_repick_will_not_take_a_nearby_future_box(self):
        sc = scene()
        sc['boxes'][1]['x'] = 1.2              # inside the retry tolerance of box a
        p = team.oracle_fixed_plan(sc, True)
        p.pose_source = lambda _: (0., 0., 0.)
        box = lambda d: [dict(key='box:0', text=f'<red box> in the box room, {d} m away, straight ahead of me')]
        self.assertEqual(p.decide('r1', 0, 'pick', box(2))['option'], 'box:0')
        self.assertEqual(p.decide('r1', 1, 'pick', box(1.2) + [dict(key='look_around', text='look')])['option'], 'look_around')
        self.assertEqual(p.decide('r1', 2, 'pick', box(1.2))['option'], 'finish')

    def test_waits_for_the_required_trip_and_lets_the_predecessor_use_the_same_door(self):
        for rid in ('r1', 'r2'):
            release(self.plan, rid, 1)
            self.answer(rid, 'next')
            self.answer(rid, 'destination')
        self.assertEqual(self.answer('r1', 'door'), 'wait')
        self.assertEqual(self.answer('r2', 'door'), 'go')             # r1 is ahead in the queue but cannot go yet
        release(self.plan, 'r2', 1)                                  # stale first-trip report
        self.assertEqual(self.answer('r1', 'door'), 'wait')
        release(self.plan, 'r2', 2)
        self.assertEqual(self.answer('r1', 'door'), 'go')

    def test_ending_or_putting_down_does_not_satisfy_an_order_even_at_another_door(self):
        release(self.plan, 'r1', 1)
        self.answer('r1', 'next')
        release(self.plan, 'r2', 1)
        self.answer('r2', 'next')
        self.plan.set_door('r2', 'other')
        for outcome in ('put_down', 'box_not_held', 'zone_unconfirmed'):
            release(self.plan, 'r2', 2, outcome)
        self.plan.robot_ended('r2')
        self.assertEqual(self.answer('r1', 'door'), 'wait')
        self.assertNotIn('d', self.plan.record()['delivered_boxes'])


class SpeechAtMoves(unittest.TestCase):
    def hooks(self, script, moves=True):
        self.clock = 0.
        self.brain = ScriptBrain(decide=script, polls=[True] * 10)
        self.pick, self.dest, self.door, self.state = team.hooks('r1', self.brain, lambda: self.clock, [],
                                                                multi_carry=True, llm_moves=moves)

    def test_empty_list_speech_does_not_use_up_move_or_empty_look_budget(self):
        self.hooks({'pick': [say('no box here', 4., option='move:look'), {'option': 'move:look'}]})
        self.assertEqual(self.pick([]), 'wait')
        self.assertEqual(self.state['stand_until'], 4.)
        self.clock = 3.
        self.assertEqual(self.pick([]), 'wait')
        self.assertIsNone(self.state['move_source']())
        self.assertEqual(self.state['empty_asks'], 0)
        self.clock = 4.
        self.assertEqual(self.pick([]), 'wait')
        self.assertEqual(self.state['move_source'](), {'kind': 'look', 'where': 'pick'})
        self.assertEqual(self.state['empty_asks'], 1)

    def test_empty_list_still_allows_talk_with_moves_off(self):
        self.hooks({'pick': [say('nothing in view', 1.), {'option': 'finish'}]}, moves=False)
        self.assertEqual(self.pick([]), 'wait')
        self.assertEqual(self.state['stand_until'], 2.)
        self.clock = 2.
        self.assertIsNone(self.pick([]))
        self.assertEqual(self.brain.calls[-1][-1], ['wait', 'finish'])

    def test_blocked_speech_holds_even_if_the_reply_also_names_a_move(self):
        self.hooks({'pick': [{'option': 'box:0'}], 'blocked': [say('please pass', 4., option='move:back'), {'option': 'move:aside'}]})
        self.assertEqual(self.pick([entry('red', 1., 0.)]), 0)
        self.assertIsNone(self.state['move_ask'](6))
        self.assertEqual(self.state['talk_stands'][0]['path'], 'ask:blocked')
        self.clock = 3.
        self.assertIsNone(self.state['move_ask'](9))
        self.assertTrue(self.state['decision_open']())
        self.assertEqual(self.state['moves_n'], 0)
        self.clock = 4.
        self.assertEqual(self.state['move_ask'](10), {'kind': 'aside', 'where': 'blocked'})

    def test_gate_speech_cannot_be_interrupted_by_an_incoming_message(self):
        self.hooks({'pick': [{'option': 'box:0'}], 'destination': [{'option': 'zone:' + team.ZONES[0]}],
                    'door': [say('let me pass', 5.), {'option': 'move:back'}]})
        self.pick([entry('red', 1., 0.)])
        self.dest()
        self.assertFalse(self.door())
        self.clock = 2.1
        self.assertFalse(self.door())
        self.assertIsNone(self.state['move_source']())
        self.clock = 5.
        self.assertFalse(self.door())
        self.assertEqual(self.state['move_source'](), {'kind': 'back', 'where': 'gate'})


class ReturnCommands(unittest.TestCase):
    def test_speech_and_pending_next_preserve_wheels_arm_and_return_cursor(self):
        pwm = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
        nav = mock.Mock()
        nav.step.side_effect = [([.35] * 4, .1, 0.), None]
        for now, speaking, waiting, expected in [(0., True, False, 'talk_stand'), (.1, False, True, 'next_wait')]:
            row, source = team.solo.return_or_stand_command(nav, b'', pwm, pwm, now, speaking=speaking, waiting=waiting)
            self.assertEqual((source, row['wheels'], row['duration_s'], row['pwm']), (expected, [0.] * 4, [0.] * 4, pwm))
        nav.step.assert_not_called()
        row, source = team.solo.return_or_stand_command(nav, b'', pwm, pwm, .2, speaking=False, waiting=False)
        self.assertEqual((source, row['wheels']), ('return_code', [.35] * 4))
        self.assertEqual(team.solo.return_or_stand_command(nav, b'', pwm, pwm, .3, speaking=False, waiting=False), (None, None))


class ReleasedTripBridge(unittest.TestCase):
    def run_trips(self, brain, outcomes, return_rows=0):
        clock = FakeWorld()
        transitions = []
        self.return_commands = []

        def steps(plan, protocol, model, output, *, shared, events, trip_next, stand_hold, choose_box, carry_to, **kw):
            shared['world'] = clock
            tick = lambda: {'until': clock.data.time + .5}
            yield {'until': 1.}
            if plan['robot_id'] == 'r2':
                while clock.data.time < 35.:
                    yield tick()
                return
            for trip, outcome in enumerate(outcomes, 1):
                if trip > 1:
                    events.clear()
                    events['trip'] = trip
                    yield tick()
                self.assertEqual(choose_box([entry('red', 1., 0.)]), 0)
                carry_to()
                if outcome == 'at_zone':
                    events['door_passed'] = clock.data.time
                    yield tick()
                events['carry_finished'] = {'outcome': outcome, 'at_s': clock.data.time}
                yield tick()
                while stand_hold() or trip_next() == 'wait':
                    self.assertLess(clock.data.time, 30.)
                    yield tick()
                transitions.append((trip, trip_next(), clock.data.time - 1.))
                if trip_next() != 'back':
                    return
                if outcome == 'at_zone' and return_rows:
                    pwm = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
                    nav = mock.Mock()
                    nav.step.return_value = ([.35] * 4, .1, 0.)
                    while nav.step.call_count < return_rows:
                        now = clock.data.time - 1.
                        self.assertLess(now, 30.)
                        row, source = team.solo.return_or_stand_command(nav, b'', pwm, pwm, now, speaking=stand_hold(), waiting=False)
                        self.return_commands.append((now, source, row['wheels']))
                        yield tick()

        stub = SimpleNamespace(ScenarioFinalV3Scene=SimpleNamespace(from_scenario=lambda *_: SimpleNamespace(config={'setup_only': {'objects': {}}})))
        plan = dict(robot_id='r1', scenario_id='stub', seed=1, spawns={'r1': [0., 0., .03, 0.]})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'sim.zone_scenario_scene': stub}), \
                mock.patch.object(team, 'ZONES', team.SIGN_ZONES), mock.patch.object(team, 'RECT', team.SIGN_RECT), \
                mock.patch.object(team.solo, 'run_steps', steps), mock.patch.object(team.solo, 'advance_physics', lambda w, req, t: setattr(w.data, 'time', t)):
            record = team.run_team(plan, {}, 'stub', Path(tmp) / 'out', brain=brain, orders={}, knows={}, scene=scene(),
                                   multi_carry=True, robot_tags=True, overhead=True)
        return record, transitions

    def test_next_speech_retries_once_per_choice_and_finished_leader_still_relays(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0'}] * 2,
                                    'destination': [{'option': 'put_down'}, {'option': 'zone:sign12'}],
                                    'next': [say('another job', 3., option='finish'), {'option': 'back'},
                                             say('last box down', 4.), {'option': 'finish', 'relay': True}],
                                    'relay': [say('answer', 2.)]}, polls=[True])
        record, transitions = self.run_trips(brain, ['put_down', 'at_zone'])
        self.assertEqual([a for _, a, _ in transitions], ['back', 'finish'])
        next_rows = [d for d in record['decisions'] if d['point'] == 'next']
        self.assertEqual([next_rows[i+1]['t'] - next_rows[i]['t'] for i in (0, 2)], [3., 4.])
        reports = [f for _, f in brain.told if f.get('milestone') == 'carry_finished']
        self.assertEqual([(f['trip'], f['outcome'], f.get('zone')) for f in reports], [(1, 'put_down', None), (2, 'at_zone', 'sign12')])
        self.assertEqual([c['label'] for c in record['carries']['r1']], ['r1-box0', 'r1-t2-box0'])
        self.assertEqual([s['path'] for s in record['talk_stands']['r1']], ['ask:next', 'ask:next', 'relay'])
        self.assertGreaterEqual(record['relay']['r1']['start_s'], transitions[-1][2])

    def test_call_cap_or_failure_at_next_never_starts_another_trip(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0'}], 'destination': [{'option': 'zone:sign11'}],
                                    'next': [{'option': 'back', 'halted': True, 'reason': 'robot_failed', 'relay': True}]}, polls=[True])
        record, transitions = self.run_trips(brain, ['at_zone'])
        self.assertEqual([a for _, a, _ in transitions], ['finish'])
        self.assertNotIn('relay', record)

    def test_cap_reports_the_last_delivery_and_holds_for_the_final_speech(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0'}] * 3, 'destination': [{'option': 'put_down'}] * 3,
                                    'next': [{'option': 'back'}] * 2, 'report': [say('all done', 3., option='continue')]})
        record, transitions = self.run_trips(brain, ['put_down'] * 3)
        self.assertEqual([a for _, a, _ in transitions], ['back', 'back', 'finish'])
        self.assertEqual([d['point'] for d in record['decisions'] if d.get('milestone') == 'carry_finished'], ['next', 'next', 'report'])
        stand = record['talk_stands']['r1'][-1]
        self.assertEqual(stand['path'], 'report:carry_finished')
        self.assertGreaterEqual(transitions[-1][2], stand['t'] + 3.)

    def test_mid_return_chance_stops_the_first_issued_row_of_the_speech(self):
        brain = ScriptBrain(decide={'pick': [{'option': 'box:0'}] * 2, 'destination': [{'option': 'zone:sign11'}] * 2,
                                    'next': [{'option': 'back'}, {'option': 'finish'}]}, chance=[say('on my way back', 3.)])
        brain.chance_poll = lambda rid, now: rid == 'r1' and bool(self.return_commands and brain.chances)
        record, _ = self.run_trips(brain, ['at_zone'] * 2, return_rows=6)
        stand, = record['talk_stands']['r1']
        self.assertEqual(stand['path'], 'chance')
        rows = [(source, wheels) for t, source, wheels in self.return_commands if stand['t'] <= t < stand['t'] + 3.]
        self.assertEqual(rows, [('talk_stand', [0.] * 4)] * 6)
        self.assertEqual(self.return_commands[-1][1], 'return_code')
