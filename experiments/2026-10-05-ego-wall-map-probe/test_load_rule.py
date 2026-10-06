"""Own-command load state used to pick the camera elevation bias (``wall_probe.is_loaded``). Refs #216.

Standalone: ``python test_load_rule.py``. The legacy rule ``servo[3] >= 900`` is an arm *pose* (it is true
for the open-gripper search pose), not a load; a closed gripper pulse (~1500) is.
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
