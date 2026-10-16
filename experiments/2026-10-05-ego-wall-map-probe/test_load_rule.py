"""Own-command load state used to pick the camera elevation bias (``wall_probe.loaded_for``). Refs #216.

Standalone: ``python test_load_rule.py``. The rule ``servo[3] >= 900`` is an arm *pose* (it is true
for the open-gripper search pose), not a load; a closed gripper pulse (~1500) is.

The rule is an OPTION (``--load-rule s3|gripper``). The default ``s3`` is the behaviour before #405; ``gripper``
is the fix (``wall_probe.is_loaded``).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'code'))
import wall_probe as wp  # noqa: E402


class LoadRuleTest(unittest.TestCase):
    def test_open_gripper_is_not_loaded_even_with_the_arm_raised(self):
        self.assertFalse(wp.is_loaded({1: 2000, 3: 1320, 4: 2320, 5: 1320}))

    def test_closed_gripper_is_loaded_whatever_the_arm_pose(self):
        self.assertTrue(wp.is_loaded({1: 1500, 3: 740}))
        self.assertTrue(wp.is_loaded({1: 1500, 3: 120}))

    def test_string_keys_from_json(self):
        self.assertTrue(wp.is_loaded({'1': 1500, '3': 120}))
        self.assertFalse(wp.is_loaded({'1': 2000, '3': 1320}))

    def test_missing_gripper_command_is_unloaded(self):
        self.assertFalse(wp.is_loaded({3: 1320}))


class LoadRuleOptionTest(unittest.TestCase):
    def tearDown(self):
        wp.set_load_rule(wp.LOAD_RULE_DEFAULT)

    def test_default_is_the_rule_before_405(self):
        self.assertEqual(wp.LOAD_RULE_DEFAULT, 's3')
        # open-gripper search pose: s3 = 1072 -> the old rule says loaded, the gripper rule does not
        pose = {1: 2000, 3: 1072}
        self.assertTrue(wp.loaded_for(pose))
        self.assertTrue(wp.loaded_for(pose, 's3'))
        self.assertFalse(wp.loaded_for(pose, 'gripper'))
        # closed gripper at a low arm pose: the old rule says unloaded
        held = {1: 1500, 3: 740}
        self.assertFalse(wp.loaded_for(held))
        self.assertTrue(wp.loaded_for(held, 'gripper'))

    def test_default_rule_matches_servo3_threshold_exactly(self):
        for s3 in (0, 120, 899, 900, 901, 1320, 1500):
            self.assertEqual(wp.loaded_for({3: s3}), s3 >= 900)
            self.assertEqual(wp.loaded_for({3: s3}, 's3'), s3 >= 900)

    def test_legacy_string_key_never_loaded_on_int_keyed_servo(self):
        # wall_probe.run / coverage / overlay / diag_rows read ``servo.get('3', 0)`` on an int-keyed dict
        self.assertFalse(wp.loaded_for({3: 1500}, legacy_str_key=True))
        self.assertTrue(wp.loaded_for({'3': 1500}, legacy_str_key=True))

    def test_process_wide_rule(self):
        wp.set_load_rule('gripper')
        self.assertFalse(wp.loaded_for({1: 2000, 3: 1072}))
        self.assertTrue(wp.loaded_for({1: 1500, 3: 740}))
        wp.set_load_rule('s3')
        self.assertTrue(wp.loaded_for({1: 2000, 3: 1072}))

    def test_unknown_rule_is_an_error(self):
        with self.assertRaises(ValueError):
            wp.set_load_rule('arm')
        with self.assertRaises(ValueError):
            wp.loaded_for({3: 1}, 'arm')


if __name__ == '__main__':
    unittest.main(verbosity=2)
