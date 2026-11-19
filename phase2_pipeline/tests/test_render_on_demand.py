"""Tests of the speed switch --render-on-demand (default off). No simulator, no mujoco, no network.

  * harness/render_on_demand_v1.pixels_idle: every tick kind that skips the picture, and every state that must not (a robot that renders on any doubt);
    overhead_cameras_needed (which ceiling cameras can hold a robot card); Stats;
  * SurveyApproach.needs_frame: on a stub, step() reads the picture exactly on the ticks where needs_frame() said True (init, the 13 pan poses with their
    settle ticks, restore, the chooser's wait, approach, align);
  * run_team_carry hooks gate.idle(): True only when gate() answers False without asking the planner and without changing the state;
  * run_team_carry.main: the switch reaches run_steps only when given, and is refused without --overhead / --robot-tags and with --multi-carry / --llm-moves;
    run_steps takes the argument (default False).
Run:  python3 -B -m unittest discover -s tests -p 'test_render_on_demand.py' -v   (in the worktree root)"""
import sys
sys.dont_write_bytecode = True

import contextlib
import importlib.util
import inspect
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.run_grasp_act_student as SOLO  # noqa: E402
import scripts.run_team_carry as TEAM  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ROD = load(ROOT / 'harness' / 'render_on_demand_v1.py', 'render_on_demand_v1_test')
SURVEY = load(ROOT / 'harness' / 'approach_survey_v1.py', 'approach_survey_v1_rod_test')
NS = types.SimpleNamespace


def approach(arrived=True, stage='approach', needs=None):
    a = NS(arrived=arrived, stage=stage)
    if needs is not None:
        a.needs_frame = lambda: needs
    return a


def nav(finished=False, held_result=None):
    return NS(finished=finished, held_result=held_result)


def call(**kw):
    base = dict(approach=approach(), skill='release', carry_nav=None, carry_state={'started_at_s': None}, carry_to_state={'rule': None},
                gate_idle=None, release_on=True)
    base.update(kw)
    return ROD.pixels_idle(**base)


class PixelsIdle(unittest.TestCase):
    def test_no_approach_or_unknown_approach_renders(self):
        self.assertIsNone(call(approach=None))
        self.assertIsNone(call(approach=approach(arrived=False)))            # an approach without needs_frame (the plain servo)

    def test_look_around_follows_needs_frame(self):
        self.assertIsNone(call(approach=approach(False, 'survey', needs=True)))
        self.assertEqual(call(approach=approach(False, 'survey', needs=False)), 'survey_survey')
        self.assertEqual(call(approach=approach(False, 'init', needs=False)), 'survey_init')
        self.assertEqual(call(approach=approach(False, 'restore', needs=False)), 'survey_restore')

    def test_grasp_always_renders(self):
        self.assertIsNone(call(skill='grasp'))
        self.assertIsNone(call(skill='grasp', carry_nav=nav(finished=True)))

    def test_decide_wait_only_without_a_rule_or_a_note(self):
        self.assertEqual(call(carry_to_state={'rule': None}), 'decide_wait')
        self.assertIsNone(call(carry_to_state={'rule': None, 'note': 'nothing to carry'}))
        self.assertIsNone(call(carry_to_state=None))
        self.assertIsNone(call(carry_to_state={'rule': 'zone_sign12'}))      # decided, but no carry navigation (a planned route): renders

    def test_release_replay_after_the_carry(self):
        self.assertEqual(call(carry_nav=nav(finished=True), carry_state={'held': {}, 'started_at_s': 3.}), 'release_replay')
        self.assertEqual(call(carry_nav=nav(finished=True, held_result=None), carry_state={'started_at_s': 3.}), 'release_replay')
        # a held check that answered but is not in carry_state yet reads one picture
        self.assertIsNone(call(carry_nav=nav(finished=True, held_result='held'), carry_state={'started_at_s': 3.}))
        self.assertIsNone(call(carry_nav=nav(finished=True), carry_state={'held': {}}, release_on=False))

    def test_door_wait_needs_an_idle_gate_and_no_watcher(self):
        state = {'started_at_s': None}
        rule = {'rule': 'zone_sign12'}
        self.assertEqual(call(carry_nav=nav(), carry_state=state, carry_to_state=rule, gate_idle=lambda: True), 'door_wait')
        self.assertIsNone(call(carry_nav=nav(), carry_state=state, carry_to_state=rule, gate_idle=lambda: False))      # the gate may ask this tick
        self.assertIsNone(call(carry_nav=nav(), carry_state=state, carry_to_state=rule, gate_idle=None))
        self.assertIsNone(call(carry_nav=nav(), carry_state={'started_at_s': 12.}, carry_to_state=rule, gate_idle=lambda: True))       # carrying
        self.assertIsNone(call(carry_nav=nav(), carry_state={'started_at_s': None, 'held': {}}, carry_to_state=rule, gate_idle=lambda: True))
        self.assertIsNone(call(carry_nav=nav(), carry_state=state, carry_to_state={'rule': 'zone_sign12', 'note': 'x'}, gate_idle=lambda: True))
        self.assertIsNone(call(carry_nav=nav(), carry_state=state, carry_to_state={'rule': None}, gate_idle=lambda: True))

    def test_carry_ticks_render(self):
        # a carry in progress: the held watcher (every tick), the navigation's look windows
        self.assertIsNone(call(carry_nav=nav(), carry_state={'started_at_s': 20., 'held': {'holding': True}}, carry_to_state={'rule': 'zone_sign12'}, gate_idle=lambda: True))
        self.assertIsNone(call(carry_nav=nav(), carry_state={'started_at_s': 20.}, carry_to_state={'rule': 'zone_sign12'}, gate_idle=lambda: True))


class Cameras(unittest.TestCase):
    CAMS = [('top', (0., 0.)), ('top_1', (4., 0.)), ('top_2', (0., 6.)), ('top_3', (4., 6.))]

    def test_only_cameras_with_a_robot_in_reach(self):
        self.assertEqual(ROD.overhead_cameras_needed(self.CAMS, [(1., 1.)], 2., 2.), {'top'})
        self.assertEqual(ROD.overhead_cameras_needed(self.CAMS, [(1., 1.), (4.5, 5.5)], 2., 2.), {'top', 'top_3'})
        self.assertEqual(ROD.overhead_cameras_needed(self.CAMS, [], 2., 2.), set())

    def test_margin_beyond_the_picture_edge(self):
        # half span 2: a card centre at x = 4.0 (2.0 from 'top' and 0 from 'top_1'): both; at 2.34 from 'top_2': kept by the 0.35 margin; at 2.36: not
        self.assertEqual(ROD.overhead_cameras_needed(self.CAMS, [(2.0, 0.)], 2., 2.), {'top', 'top_1'})
        self.assertIn('top', ROD.overhead_cameras_needed(self.CAMS, [(2.34, 0.)], 2., 2.))
        self.assertNotIn('top', ROD.overhead_cameras_needed(self.CAMS, [(2.36, 0.)], 2., 2.))
        self.assertIn('top_1', ROD.overhead_cameras_needed(self.CAMS, [(2.0, 2.34)], 2., 2.))

    def test_every_robot_is_covered_by_some_camera_of_a_tiling(self):
        # four tiles of half span 2 side by side (the picture edges touch): a robot anywhere in the covered area is in at least one needed picture
        import itertools
        tiles = [('a', (0., 0.)), ('b', (4., 0.)), ('c', (0., 4.)), ('d', (4., 4.))]
        for x, y in itertools.product([i * 0.5 - 2. for i in range(17)], repeat=2):
            self.assertTrue(ROD.overhead_cameras_needed(tiles, [(x, y)], 2., 2.), (x, y))


class StatsRecord(unittest.TestCase):
    def test_counts(self):
        s = ROD.Stats()
        for kind in (None, 'door_wait', 'door_wait', 'decide_wait', None):
            s.tick(kind)
        self.assertEqual(s.record(), {'ticks': 5, 'pictures_reused': 3, 'by_kind': {'door_wait': 2, 'decide_wait': 1}, 'share_reused': 0.6})
        self.assertIsNone(ROD.Stats().record()['share_reused'])


class StubContract:
    SERVOS = (1, 3, 4, 5, 6)

    @staticmethod
    def command(row):
        return row


class SurveyNeedsFrame(unittest.TestCase):
    """step() on a stub reads the picture (survey.observe / servo.step / aligner.step) exactly on the ticks where needs_frame() was True before the call."""

    def make(self):
        a = SURVEY.SurveyApproach.__new__(SURVEY.SurveyApproach)
        a.c, a._select, a.places = StubContract(), (lambda entries: 'wait'), None
        a.stage, a.arrived, a.reason, a._count, a._pose = 'init', False, None, 0, 0
        a._ticks = {'init': 0, 'survey': 0, 'restore': 0, 'approach': 0, 'align': 0}
        a._issued = dict(SURVEY.FAR_POSTURE)
        a.stage_log, a.index, a.entries = [], None, None
        a.reads = []
        outer = a

        class Survey:
            def observe(self, jpeg, posture):
                outer.reads.append('survey')

            def entries(self):
                return []
        a.survey = Survey()
        return a

    def test_init_survey_restore_wait(self):
        a = self.make()
        expected_survey_reads = len(SURVEY.PAN_SEQUENCE) * SURVEY.POSE_FRAMES
        n_reads, n_idle, kinds = 0, 0, []
        for tick in range(SURVEY.INIT_TICKS + len(SURVEY.PAN_SEQUENCE) * (SURVEY.POSE_SETTLE_TICKS + SURVEY.POSE_FRAMES) + SURVEY.RESTORE_TICKS + 5):
            before = len(a.reads)
            needs = a.needs_frame()
            kinds.append((a.stage, needs))
            a.step(b'jpeg', 0.1 * tick)
            read = len(a.reads) > before
            self.assertEqual(read, needs, 'tick %d stage %s' % (tick, kinds[-1]))
            n_reads += read
            n_idle += not needs
        self.assertEqual(n_reads, expected_survey_reads)
        self.assertEqual(a.stage, 'restore')                 # the chooser answers 'wait' for ever: restore ticks, no picture
        self.assertFalse(a.needs_frame())
        self.assertGreater(n_idle, 0.5 * len(kinds))

    def test_approach_and_align_read_every_tick_and_arrived_never(self):
        a = self.make()
        for stage in ('approach', 'align'):
            a.stage = stage
            self.assertTrue(a.needs_frame())
        a.arrived = True
        self.assertFalse(a.needs_frame())


class GateIdle(unittest.TestCase):
    class Brain:
        """Raises on every call: an idle gate must not touch the planner."""
        chooses_moves = False

        def decide(self, *a, **k):
            raise AssertionError('the planner was asked')

        def tell(self, *a, **k):
            raise AssertionError('the planner was told')

        def poll(self, *a, **k):
            raise AssertionError('the planner was polled')

    def make(self):
        clock = [0.]
        choose, destination, gate, state = TEAM.hooks('r1', self.Brain(), lambda: clock[0], [])
        return clock, gate, state

    def test_idle_exactly_while_gate_answers_false_for_free(self):
        clock, gate, state = self.make()
        state.update(next=10., poll=5., dest='zone_sign12')
        clock[0] = 3.
        before = dict(state)
        self.assertTrue(gate.idle())
        self.assertFalse(gate())                 # same tick: False, nobody asked (the Brain raises), nothing changed
        self.assertEqual(state, before)
        clock[0] = 5.0
        self.assertFalse(gate.idle())            # a poll of the planner is due: the tick may change state
        clock[0] = 11.
        self.assertFalse(gate.idle())            # the wait is over: the gate asks
        clock[0] = 3.
        state['go'] = True
        self.assertFalse(gate.idle())
        self.assertTrue(gate())
        state['go'] = False
        state['dest'] = TEAM.PUT_DOWN
        self.assertFalse(gate.idle())
        self.assertTrue(gate())


class Switch(unittest.TestCase):
    def run_main(self, *flags):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ('plan.json', 'protocol.json'):
                (tmp / name).write_text('{}')
            calls = {}

            def fake_run_team(plan, protocol, model, output, **kw):
                calls['kw'] = kw
                Path(output).mkdir(parents=True)

            argv = ['run_team_carry.py', '--plan', str(tmp / 'plan.json'), '--protocol', str(tmp / 'protocol.json'), '--model', str(tmp / 'm'),
                    '--output', str(tmp / 'out'), '--actor-python', 'py', '--scene-source', str(tmp), *flags]
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(TEAM, 'run_team', fake_run_team), \
                    mock.patch('scripts.run_grasp_act_recovery.dependency_modules', lambda root: contextlib.nullcontext()), \
                    contextlib.redirect_stderr(io.StringIO()):
                try:
                    TEAM.main()
                    code = None
                except SystemExit as e:
                    code = e.code
            return calls.get('kw'), code

    def test_default_off_passes_nothing(self):
        kw, code = self.run_main()
        self.assertNotIn('render_on_demand', kw)
        self.assertIsNone(code)

    def test_on_reaches_run_team(self):
        kw, code = self.run_main('--render-on-demand', '--overhead', '--robot-tags')
        self.assertIs(kw['render_on_demand'], True)

    def test_refused_without_overhead_tags_or_with_moves(self):
        for flags in (['--render-on-demand'], ['--render-on-demand', '--overhead'], ['--render-on-demand', '--robot-tags'],
                      ['--render-on-demand', '--overhead', '--robot-tags', '--multi-carry'], ['--render-on-demand', '--overhead', '--robot-tags', '--llm-moves']):
            kw, code = self.run_main(*flags)
            self.assertEqual((kw, code), (None, 2), flags)

    def test_run_steps_takes_the_argument_default_off(self):
        self.assertIs(inspect.signature(SOLO.run_steps).parameters['render_on_demand'].default, False)


if __name__ == '__main__':
    unittest.main()
