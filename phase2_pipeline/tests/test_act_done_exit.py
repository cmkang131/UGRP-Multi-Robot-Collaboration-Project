"""--act-done-exit (DEFAULT off, 2026-11-19): the grasp-failure exit on the learned done bit. No world, actor or planner service."""
import argparse
import json
import unittest

from harness import exec_opt
from harness.grasp_act_rollout import ACT_DONE_EXIT_ROWS, GraspTransitionRule, act_done_exit_row


def parsed(*argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--overhead', action='store_true')
    exec_opt.add_arguments(parser)
    return exec_opt.from_args(parser, parser.parse_args(list(argv)))


def feed(rows, rule=None, skill='grasp', state=None):
    """Feed done rows (booleans); return (state, index of the first row that fires or None)."""
    state = {} if state is None else state
    rule = GraspTransitionRule() if rule is None else rule
    for i, done in enumerate(rows):
        if act_done_exit_row(state, done, skill=skill, rule=rule):
            return state, i
    return state, None


class Switch(unittest.TestCase):
    def test_default_off_and_absent_from_the_settings(self):
        self.assertIsNone(parsed())
        self.assertFalse(exec_opt.Options().act_done_exit)
        self.assertNotIn('act_done_exit', exec_opt.Options().settings())

    def test_flag_sets_only_its_field(self):
        self.assertEqual(parsed('--act-done-exit'), exec_opt.Options(act_done_exit=True))
        self.assertEqual(parsed('--act-done-exit').settings(), {'act_done_exit': True})

    def test_constant(self):
        self.assertEqual(ACT_DONE_EXIT_ROWS, 100)


class ExitRows(unittest.TestCase):
    def test_fires_on_the_100th_row_of_done_without_the_rule(self):
        state, at = feed([True] * 150)
        self.assertEqual(at, 99)
        self.assertEqual(state['done_run'], 100)
        self.assertEqual(state['done_run_max'], 100)

    def test_99_rows_do_not_fire(self):
        state, at = feed([True] * 99)
        self.assertIsNone(at)
        self.assertEqual(state['done_run_max'], 99)

    def test_a_dropped_done_resets_the_run(self):
        state, at = feed([True] * 99 + [False] + [True] * 99)
        self.assertIsNone(at)
        self.assertEqual((state['done_run'], state['done_run_max']), (99, 99))
        state, at = feed([True] * 99 + [False] + [True] * 100)
        self.assertEqual(at, 199)

    def test_does_not_fire_when_the_rule_fired(self):
        rule = GraspTransitionRule()
        rule.fired = True
        state, at = feed([True] * 300, rule=rule)
        self.assertIsNone(at)
        self.assertEqual(state['done_run'], 0)

    def test_a_rule_that_fires_mid_run_ends_the_run(self):
        rule, state = GraspTransitionRule(), {}
        fired = [act_done_exit_row(state, True, skill='grasp', rule=rule) for _ in range(60)]
        rule.fired = True
        fired += [act_done_exit_row(state, True, skill='grasp', rule=rule) for _ in range(200)]
        self.assertFalse(any(fired))

    def test_not_armed_or_other_skill_never_fires_and_resets(self):
        state, at = feed([True] * 300, rule=GraspTransitionRule(), skill='release')
        self.assertIsNone(at)
        state = {'done_run': 50}
        self.assertFalse(act_done_exit_row(state, True, skill='grasp', rule=None))
        self.assertEqual(state['done_run'], 0)

    def test_state_is_plain_ints_for_the_report(self):
        state, _ = feed([True] * 120)
        json.dumps(state)
        self.assertEqual(set(state), {'done_run', 'done_run_max'})


if __name__ == '__main__':
    unittest.main()
