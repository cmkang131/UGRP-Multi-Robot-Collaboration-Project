"""Idle-tick speed switches (all DEFAULT off): --sign-scan-early-stop, --align-fast, --survey-fast, --act-hold-short, --dest-listen-zero.
No world, actor or planner service. Run:  python3 -B -m unittest discover -s tests -p 'test_speed_switches.py' -v
"""
import argparse
import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import carry_nav_v1 as nav_module, exec_opt as opt  # noqa: E402
from harness.grasp_act_rollout import GraspTransitionRule, SoloSequence  # noqa: E402
from scripts import run_grasp_act_student as solo, run_team_carry as team  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SURVEY = load(ROOT / 'harness' / 'approach_survey_v1.py', 'approach_survey_v1_speed_test')
PARTS = ROOT / 'harness' / 'approach_survey_v1_parts'
load(PARTS / 'survey_observe.py', 'survey_observe')
ALIGN = load(PARTS / 'face_align.py', 'face_align_speed_test')

FAR = (3.2303529323434597, -5.917830660554822)
START = (-0.572923491472707, -3.60178399733168, -1.6539375586833371)
HOLD = {'1': 1860, '3': 1060, '4': 1850, '5': 1600, '6': 1500}


def parsed(*argv):
    p = argparse.ArgumentParser()
    p.add_argument('--overhead', action='store_true')
    opt.add_arguments(p)
    return opt.from_args(p, p.parse_args(argv))


class Readings:
    """Stub place memory: a sighting (30 points) is stored at the given 1-based look frames of the sweep."""

    def __init__(self, sighted_at):
        self.sighted_at = set(sighted_at)
        self.obstacles, self.frames, self.points = {}, {}, 0

    def door(self, phase):
        return None

    def observe_zone(self, jpeg, posture, colour, *, phase, close=False, **kwargs):
        n = self.frames.get(phase, 0) + 1
        self.frames[phase] = n
        if phase == 'zone_scan' and n in self.sighted_at:
            self.points += 30

    def zone(self, colour, phase):
        if phase == 'zone_scan' and self.points >= 30:
            return {'kind': 'zone_' + colour, 'x': FAR[0], 'y': FAR[1], 'points': self.points, 'spread_m': [0., 0.]}


def replay(sighted_at, early_stop):
    places = Readings(sighted_at)
    nav = nav_module.CarryNav(solo, places, dict(zip(('x', 'y', 'yaw'), START)), [], 'zone_sign12', held_kind='cyan')
    nav.sign_scan_early_stop = early_stop
    nav._extend('arm:far')
    nav.phase = 'pass'
    commands, pwm = [], HOLD
    for tick in range(2000):
        command = solo.carry_navigation_command(nav, b'', pwm, HOLD, {}, tick / 10.)
        if command is None:
            break
        commands.append(command)
        pwm = command[0]['pwm']
    else:
        raise AssertionError('carry exceeded the bounded replay')
    return nav, places, commands


class SignScanEarlyStop(unittest.TestCase):
    """The sweep is 12 x (6 turn pulses + 5 gap rows + 8 pause rows: 5 rest + 3 look frames) after 25 arm rows, then 5 trailing gap rows."""

    def test_off_is_the_full_sweep(self):
        nav, places, commands = replay({4, 5, 6}, False)
        self.assertEqual(places.frames['zone_scan'], 36)
        self.assertNotIn('zone_scan_early_stop', [s.get('decision') for s in nav.steps])
        self.assertEqual(nav.outcome, 'at_zone')

    def test_on_stops_at_the_end_of_the_window_that_holds_the_sighting(self):
        full, _, full_commands = replay({4, 5, 6}, False)
        nav, places, commands = replay({4, 5, 6}, True)
        self.assertEqual(places.frames['zone_scan'], 6)                 # the 3 frames of the window of the sighting, nothing after
        stop = [s for s in nav.steps if s.get('decision') == 'zone_scan_early_stop']
        self.assertEqual(len(stop), 1)
        cut = stop[0]['row'] + 1
        self.assertEqual(cut, 25 + 2 * 19)                              # arm rows, two turns with their pauses
        self.assertEqual(stop[0]['rows_dropped'], 25 + 12 * 19 + 5 - cut)
        self.assertEqual(commands[:cut], full_commands[:cut])           # up to the cut the rows are the same bytes
        self.assertEqual(nav.outcome, 'at_zone')
        self.assertTrue(all(look['rows'][1] <= cut for look in nav.looks if look['phase'] == 'zone_scan'))
        self.assertEqual(len([g for g in nav.segments if g['first_row'] < cut]), 5)        # arm, turn, pause, turn, pause
        self.assertEqual(min(g['first_row'] for g in nav.segments if g['first_row'] >= cut), cut)   # the way to the zone follows at once
        # the way to the zone is planned from the nominal pose of that pause: two 30 degree turns done, not twelve
        turned = dict(x=START[0], y=START[1], yaw=START[2] - 2 * 0.5309999999999999)
        expected = solo.carry_to_plan(turned, [FAR[0], FAR[1]], [], stop_m=.9)['spec']
        go = next(s for s in nav.steps if s.get('decision') == 'go_to_zone')
        self.assertEqual(go['spec'], expected)
        self.assertNotEqual(go['spec'], next(s for s in full.steps if s.get('decision') == 'go_to_zone')['spec'])
        self.assertLess(len(commands), len(full_commands) - 150)

    def test_no_sighting_keeps_the_whole_sweep_byte_for_byte(self):
        full, _, full_commands = replay(set(), False)
        nav, places, commands = replay(set(), True)
        self.assertEqual(places.frames['zone_scan'], 36)
        self.assertEqual(commands, full_commands)
        self.assertEqual(nav.record(), full.record())

    def test_sighting_in_the_last_window_drops_only_the_trailing_gap_rows(self):
        full, _, full_commands = replay({34, 35, 36}, False)
        nav, places, commands = replay({34, 35, 36}, True)
        stop = [s for s in nav.steps if s.get('decision') == 'zone_scan_early_stop']
        self.assertEqual([s['rows_dropped'] for s in stop], [5])
        self.assertEqual(places.frames, full.places.frames)
        self.assertEqual(len(commands), len(full_commands) - 5)

    def test_only_signs(self):
        places = Readings({1, 2, 3, 4, 5, 6})
        nav = nav_module.CarryNav(solo, places, dict(zip(('x', 'y', 'yaw'), START)), [], 'zone_blue', held_kind='cyan')
        nav.sign_scan_early_stop = True
        nav._extend('arm:far')
        nav.phase = 'scan'
        nav._extend(','.join(['right:30,pause:0.8'] * 12), looks=[(n, 'zone_scan', False) for n in range(12)])
        planned = len(nav.rows)
        nav.i = nav.looks[1]['rows'][1] - 1
        places.points = 30
        nav._stop_scan_early()
        self.assertEqual(len(nav.rows), planned)                       # a paint colour is not cut


class AlignFast(unittest.TestCase):
    def run_aligner(self, fast):
        class Contract:
            @staticmethod
            def command(row):
                return row

        entries = [{'kind': 'cyan', 'x': .5, 'y': 0., 'range_m': .5, 'bearing_deg': 0., 'frames': 3}]
        with mock.patch.object(ALIGN, '_validate_entry', lambda e: None):
            aligner = ALIGN.FaceAligner(None, Contract, entries, 0, {1: 2000, 3: 500, 4: 2500, 5: 1320, 6: 1500}, **({'fast': True} if fast else {}))
        # the box stands 100 px off centre: every batch asks for a turn pulse, the next batch comes after the stand-still ticks
        estimate = {'valid': True, 'yaw_rad': 0., 'cx': 286.9 + 100., 'cy': 300., 'area': 9000, 'contact_x_m': .203, 'long_edge_m': None,
                    'hint': None, 'two_edges': False, 'lengths_m': [.04, .0], 'residual_m': 0.}
        ticks = []
        with mock.patch.object(ALIGN, 'estimate', lambda *a, **k: dict(estimate)):
            for tick in range(40):
                row = aligner.step(b'jpeg', tick / 10.)
                if any(row['duration_s']):
                    ticks.append(tick)
        return aligner, ticks

    def test_default_is_three_rest_ticks_fast_is_two(self):
        base, base_ticks = self.run_aligner(False)
        fast, fast_ticks = self.run_aligner(True)
        self.assertEqual(base.rest_ticks, 3)
        self.assertEqual(fast.rest_ticks, 2)
        self.assertEqual([b - a for a, b in zip(base_ticks, base_ticks[1:])], [6] * (len(base_ticks) - 1))   # 3 rest + 3 pictures
        self.assertEqual([b - a for a, b in zip(fast_ticks, fast_ticks[1:])], [5] * (len(fast_ticks) - 1))
        self.assertEqual([p['mode'] for p in base.pulses][:3], [p['mode'] for p in fast.pulses][:3])         # same control law

    def test_flag_reaches_the_aligner_only_when_given(self):
        for flag, expected in ((False, 3), (True, 2)):
            a = SURVEY.SurveyApproach.__new__(SURVEY.SurveyApproach)
            a.align_fast = flag
            a.align_mod = mock.Mock()
            a.baseline, a.c, a.entries, a.index = None, mock.Mock(command=lambda row: row, SERVOS=(1, 3, 4, 5, 6)), [], 0
            a.align_mod.FaceAligner.side_effect = lambda *args, **kw: kw
            a.servo = mock.Mock(arrived=True, reason='arrived', visible_ticks=1, trace=[])
            a.servo.step.return_value = None
            a.stage, a.arrived, a._ticks, a.stage_log = 'approach', False, {'approach': 0}, []
            a._issued = {1: 2000, 3: 500, 4: 2500, 5: 1320, 6: 1500}
            a.step(b'jpeg', 0.)
            self.assertEqual(a.aligner, {'fast': True} if flag else {})


class SurveyFast(unittest.TestCase):
    def run_survey(self, **kw):
        class Contract:
            SERVOS = (1, 3, 4, 5, 6)

            @staticmethod
            def command(row):
                return row

        with mock.patch.object(SURVEY, '_load', return_value=mock.MagicMock()):
            a = SURVEY.SurveyApproach(Contract, lambda entries: 'wait', **kw)
        reads = []
        a.survey = mock.Mock(observe=lambda jpeg, posture: reads.append((a._pose, posture[6])), entries=lambda: [])
        first_restore = None
        for tick in range(300):
            needs = a.needs_frame()
            before = len(reads)
            a.step(b'jpeg', tick / 10.)
            if a.stage == 'survey':
                self.assertEqual(len(reads) > before, needs)
            if a.stage == 'restore' and first_restore is None:
                first_restore = tick
        return a, reads, first_restore

    def test_same_pictures_in_fewer_ticks(self):
        base, base_reads, base_restore = self.run_survey()
        fast, fast_reads, fast_restore = self.run_survey(survey_fast=True)
        self.assertEqual(base_reads, fast_reads)                          # three pictures at each of the 13 pan poses, the same pans
        self.assertEqual(len(fast_reads), 13 * SURVEY.POSE_FRAMES)
        self.assertEqual(base_restore - fast_restore, 13 * (SURVEY.POSE_SETTLE_TICKS - SURVEY.POSE_SETTLE_TICKS_FAST))
        self.assertEqual((base.settle_ticks, base.restore_ticks), (SURVEY.POSE_SETTLE_TICKS, SURVEY.RESTORE_TICKS))
        self.assertEqual((fast.settle_ticks, fast.restore_ticks), (3, 1))
        # the chooser is first asked restore_ticks after the first restore tick (it answers 'wait' for ever here)
        self.assertEqual(fast._ticks['restore'], 300 - fast_restore - 1)


class ActHoldShort(unittest.TestCase):
    def feed(self, sequence, end_pwm, ticks):
        """Rows at the end posture with still wheels; returns the tick at which the grasp skill ends (skill turns to 'release')."""
        for tick in range(ticks):
            sequence.update(1. + tick * .1, False, {'wheels': [0.] * 4, 'pwm': end_pwm})
            if sequence.skill == 'release':
                return tick
        return None

    def test_default_is_45_rows_then_3_1_s(self):
        sequence = SoloSequence(True, grasp_rule=True)
        self.assertEqual((sequence.rule.hold_rows, sequence.grasp_settle_s), (45, None))
        end = self.feed(sequence, dict(GraspTransitionRule.END_PWM), 200)
        self.assertEqual(end, 44 + 31)                                    # fires at row 45, the carry may start 3.1 s later

    def test_short_is_25_rows_then_1_5_s_and_release_keeps_3_1(self):
        sequence = SoloSequence(True, grasp_rule=True, grasp_settle_s=SoloSequence.GRASP_SETTLE_SHORT_S, hold_rows=GraspTransitionRule.HOLD_ROWS_SHORT)
        end = self.feed(sequence, dict(GraspTransitionRule.END_PWM), 200)
        self.assertEqual(end, 24 + 15)
        self.assertEqual(sequence.settle_s(), SoloSequence.SETTLE_S)      # the release skill keeps the long settle

    def test_runner_arms_the_short_rule_only_with_the_flag(self):
        self.assertEqual(parsed('--act-hold-short'), opt.Options(act_hold_short=True))
        self.assertIsNone(parsed())


class Flags(unittest.TestCase):
    def test_each_flag_is_one_option_and_none_means_off(self):
        self.assertIsNone(parsed())
        for flag, name in (('--sign-scan-early-stop', 'sign_scan_early_stop'), ('--align-fast', 'align_fast'),
                           ('--survey-fast', 'survey_fast'), ('--act-hold-short', 'act_hold_short')):
            options = parsed(flag)
            self.assertEqual(options.settings(), {name: True})
            xml = '<mujoco/>'
            self.assertIs(options.transform(xml), xml)
            self.assertEqual(options.build_settings(), ({}, {}))

    def test_dest_listen_zero_is_listen_s_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'empty.json'
            src.write_text('{}')
            argv = ['team', '--plan', str(src), '--protocol', str(src), '--scene-source', tmp, '--model', tmp, '--actor-python', 'python', '--output', tmp]
            for flags, expected in (([], None), (['--dest-listen-zero'], 0.), (['--dest-listen-zero', '--listen-s', '0'], 0.), (['--listen-s', '2'], 2.)):
                with mock.patch('sys.argv', argv + flags), mock.patch.object(team, 'run_team') as run, \
                     mock.patch('scripts.run_grasp_act_recovery.dependency_modules', return_value=contextlib.nullcontext()):
                    team.main()
                self.assertEqual(run.call_args.kwargs['listen_unit_s'], expected, flags)
            with mock.patch('sys.argv', argv + ['--dest-listen-zero', '--listen-s', '2']), self.assertRaises(SystemExit), \
                 contextlib.redirect_stderr(io.StringIO()):
                team.main()


if __name__ == '__main__':
    unittest.main()
