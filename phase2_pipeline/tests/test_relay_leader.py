"""Star route: the leader stays in the conversation after its own run (run_team_carry relay_step). No simulator, no network.

The planner (--leader-route star) marks every decision answer of the leader with relay=True. When that robot's run_steps has ended (carry delivered, box put down, finish)
and a teammate still runs, the runner polls the planner once per RELAY_POLL_S simulated seconds and, on a new message, asks the point 'relay' (option wait; the planner adds
its say entries). The body is not touched. Without relay in any answer (every other planner, the star route off) nothing is polled, asked or recorded.

Run:  python3 -B -m unittest discover -s tests -p 'test_relay_leader.py' -v   (in the worktree root)"""
import sys
sys.dont_write_bytecode = True

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


def message(text, t=95.0, to=('r2',)):
    return {'time': t, 'deliver_at': t + 2.0, 'from': 'r1', 'to': list(to), 'text': text}


class RelayBrain:
    """A planner stand-in. The leader (r1) is answered at its pick with relay=True (or not: `mark=False`). `new_at`: simulated times from which a poll of r1 says
    `new` (each True is consumed by one relay decision)."""
    sends_messages = True

    def __init__(self, mark=True, new_at=(), relay_answers=(), halt_at_relay=None, fail_relay=False):
        self.mark, self.new_at, self.relay_answers = mark, list(new_at), list(relay_answers)
        self.halt_at_relay, self.fail_relay = halt_at_relay, fail_relay
        self.calls, self.told = [], []

    def tell(self, rid, facts):
        self.told.append((rid, facts))

    def decide(self, rid, now_s, point, options):
        self.calls.append(['decide', rid, round(now_s, 2), point, [o['key'] for o in options]])
        if point == 'relay':
            if self.fail_relay:
                raise ValueError('Unknown decision point')
            if self.halt_at_relay is not None and len([c for c in self.calls if c[0] == 'decide' and c[3] == 'relay']) >= self.halt_at_relay:
                return {'option': 'wait', 'wait_s': 2.0, 'sent': [], 'calls': 1, 'halted': True, 'reason': 'Robot call cap reached', 'relay': True}
            answer = self.relay_answers.pop(0) if self.relay_answers else {'option': 'wait', 'wait_s': 2.0, 'sent': [], 'calls': 1}
            return dict(answer, relay=True)
        answer = {'option': 'box:0', 'wait_s': 0.0, 'sent': [], 'calls': 1}
        if point == 'report':
            answer['option'] = 'continue'
        if self.mark and rid == 'r1':
            answer['relay'] = True
        return answer

    def poll(self, rid, now_s):
        self.calls.append(['poll', rid, round(now_s, 2)])
        if rid == 'r1' and self.new_at and now_s >= self.new_at[0]:
            self.new_at.pop(0)
            return True
        return False

    def record(self):
        return {'kind': 'relay-script'}


class RelayRun(unittest.TestCase):
    """run_team with fake robot generators (as tests/test_talk_stand.py): r1 asks its pick at tick 2 and ends at tick `r1_ticks`; r2 runs `r2_ticks` ticks of 0.1 s."""

    def run_team(self, brain, r1_ticks=20, r2_ticks=400, **kw):
        sim = types.ModuleType('sim.zone_scenario_scene')
        sim.ScenarioFinalV3Scene = types.SimpleNamespace(from_scenario=lambda sid, seed: types.SimpleNamespace(config={'setup_only': {'objects': {}}}))
        wheels_of = {'r1': [], 'r2': []}

        def run_steps(plan, protocol, model, output, **run_kw):
            shared = run_kw['shared']
            if 'world' not in shared:
                shared['world'] = V39.FakeWorld()
            world, rid = shared['world'], plan['robot_id']
            port = V39.FakePort(rid)
            yield {'world': world, 'robot': rid, 'port': port, 'wheels': None, 'deadlines': None, 'until': 1.0}
            for k in range(r1_ticks if rid == 'r1' else r2_ticks):
                if rid == 'r1' and k == 2:
                    run_kw['choose_box']([V39.entry('red', 1., 0.)])           # the leader's pick decision: the planner's answer carries the marker
                wheels_of[rid].append(round(world.data.time, 2))
                yield {'world': world, 'robot': rid, 'port': port, 'wheels': [.35] * 4, 'deadlines': [world.data.time + .1] * 4, 'until': 1.0 + .1 * (k + 1)}
            return {'status': 'complete', 'rid': rid}

        def advance(world, requests, until):
            world.data.time = until

        scene = {'id': 'T', 'boxes': [{'colour': 'red', 'x': 1., 'y': 1., 'id': 'b1'}],
                 'robots': [{'rid': 'r1', 'x': 0., 'y': 0., 'yaw': 0.}, {'rid': 'r2', 'x': 0., 'y': 1., 'yaw': 0.}],
                 'orders': [{'id': 'o1', 'colour': 'red', 'count': 1, 'sign': 11}], 'knows': {'r1': ['o1'], 'r2': ['o1']}}
        plan = {'scenario_id': 'x', 'seed': 1, 'robot_id': 'r1', 'spawns': {'r1': [0., 0., .03, 0.]}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'sim.zone_scenario_scene': sim}), \
                mock.patch.object(TEAM.solo, 'run_steps', run_steps), mock.patch.object(TEAM.solo, 'advance_physics', advance):
            record = TEAM.run_team(plan, {}, 'model', Path(tmp) / 'out', brain=brain, orders={}, knows={}, scene=scene, **kw)
        self.wheels_of = wheels_of
        return record

    @staticmethod
    def calls_of(brain, kind, rid='r1'):
        return [c for c in brain.calls if c[0] == kind and c[1] == rid]

    def test_the_marked_leader_polls_after_its_run_and_is_asked_the_relay_point_on_a_new_message(self):
        brain = RelayBrain(new_at=[8.0], relay_answers=[{'option': 'wait', 'wait_s': 2.0, 'sent': [message('relayed words')], 'calls': 1}])
        record = self.run_team(brain)
        self.assertEqual(sorted(record['finished']), ['r1', 'r2'])
        polls = self.calls_of(brain, 'poll')
        run_over = 0.1 * 20                                                          # the leader's last tick, simulated seconds since t0 (2 s)
        self.assertGreater(len(polls), 20)                                           # polled for as long as r2 ran (about 40 s at one poll per second: more with the 0.1 s ticks)
        self.assertGreaterEqual(polls[0][2], run_over - 0.2)                          # nothing before its own run is over
        gaps = [round(b[2] - a[2], 1) for a, b in zip(polls, polls[1:])]
        self.assertTrue(all(g >= TEAM.RELAY_POLL_S - 0.15 for g in gaps), gaps)       # once per second, not every tick
        relays = [c for c in brain.calls if c[0] == 'decide' and c[3] == 'relay']
        self.assertEqual(len(relays), 1)
        self.assertEqual(relays[0][4], ['wait'])
        self.assertGreaterEqual(relays[0][2], 8.0)                                    # only after a poll said `new`
        self.assertEqual(record['relay'], {'r1': {'start_s': record['relay']['r1']['start_s'], 'decisions': 1, 'sent': 1}})
        row = [d for d in record['decisions'] if d['point'] == 'relay']
        self.assertEqual((len(row), row[0]['rid'], row[0]['sent'][0]['text']), (1, 'r1', 'relayed words'))
        self.assertEqual(self.wheels_of['r1'][-1] < self.wheels_of['r2'][-1], True)    # the body of r1 was not ticked after its run (r2 ran on)

    def test_no_polls_after_the_last_teammate_has_finished(self):
        brain = RelayBrain(new_at=[])
        record = self.run_team(brain)
        last = max(self.wheels_of['r2'])
        self.assertLessEqual(max(c[2] for c in self.calls_of(brain, 'poll')), last + 0.2)
        self.assertEqual(sorted(record['finished']), ['r1', 'r2'])

    def test_a_planner_that_never_marks_is_never_polled_for_a_finished_robot(self):
        brain = RelayBrain(mark=False, new_at=[0.0])
        record = self.run_team(brain)
        self.assertEqual(self.calls_of(brain, 'poll'), [])
        self.assertEqual([c for c in brain.calls if c[0] == 'decide' and c[3] == 'relay'], [])
        self.assertNotIn('relay', record)
        self.assertEqual(sorted(record['finished']), ['r1', 'r2'])

    def test_a_robot_without_the_marker_is_not_relayed_even_when_a_teammate_is_marked(self):
        brain = RelayBrain(new_at=[3.0])
        self.run_team(brain)
        self.assertEqual(self.calls_of(brain, 'poll', 'r2'), [])                      # only r1 carries the marker

    def test_a_halted_relay_answer_ends_the_relay(self):
        brain = RelayBrain(new_at=[3.0, 6.0, 9.0], halt_at_relay=1)
        record = self.run_team(brain)
        self.assertEqual(len([c for c in brain.calls if c[0] == 'decide' and c[3] == 'relay']), 1)
        self.assertEqual(record['relay']['r1']['halted'], 'Robot call cap reached')
        last_poll = self.calls_of(brain, 'poll')[-1][2]
        self.assertLess(last_poll, 6.0)                                               # no more polls after the halt
        self.assertEqual(sorted(record['finished']), ['r1', 'r2'])

    def test_a_planner_host_that_does_not_know_the_point_turns_the_relay_off_and_the_run_goes_on(self):
        brain = RelayBrain(new_at=[3.0, 6.0], fail_relay=True)
        record = self.run_team(brain)
        self.assertEqual(record['relay']['r1']['error'], 'ValueError')
        self.assertEqual(len([c for c in brain.calls if c[0] == 'decide' and c[3] == 'relay']), 1)
        self.assertEqual(sorted(record['finished']), ['r1', 'r2'])

    def test_a_leader_that_is_still_running_is_not_relayed(self):
        brain = RelayBrain(new_at=[0.0])
        self.run_team(brain, r1_ticks=400, r2_ticks=400)
        self.assertEqual(self.calls_of(brain, 'poll'), [])                           # r1 never ended before r2: nothing to relay for
        self.assertEqual([c for c in brain.calls if c[0] == 'decide' and c[3] == 'relay'], [])


if __name__ == '__main__':
    unittest.main()
