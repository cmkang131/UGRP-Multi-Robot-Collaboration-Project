import json
import unittest
from pathlib import Path

from scripts import real_skill_test as t

PLAN = Path(__file__).resolve().parents[1] / 'experiments/2026-10-15-act-train/act14-plans/91421.json'


def row(base, box_xyz):
    return {'t': 0., 'base': base, 'boxes': {'red_1': {'kind': 'red', 'xyz': box_xyz}}}


class SkillTestEvaluation(unittest.TestCase):
    def test_sign_plan_places_r1_past_the_door(self):
        plan, objects = t.sign_plan(json.loads(PLAN.read_text()), 'red')
        self.assertAlmostEqual(plan['spawns']['r1'][0], 2.8)
        self.assertEqual(plan['spawns']['r1'][1:], [0.05, t.SPAWN_Z, 0.0])
        self.assertAlmostEqual(objects['red_1'][0], 3.4)
        self.assertEqual(t.sign_plan(json.loads(PLAN.read_text()))[1], {})

    def test_sign_area_check(self):
        # sign 12 on the east wall: facing east 0.48 m from the wall puts the set-down point inside the area
        ok = t.sim_sign([row([4.89, -2.0, 0.0], [0, 0, .016])] * 2, 12)
        self.assertTrue(ok['point_in_area'])
        self.assertEqual(ok['heading_error_deg'], 0.0)
        far = t.sim_sign([row([3.8, -2.1, -0.37], [0, 0, .016])] * 2, 13)
        self.assertFalse(far['point_in_area'])

    def test_place_needs_box_at_rest_inside(self):
        start = row([4.89, -2.0, 0.0], [3.8, 0.05, .016])
        placed = t.sim_sign([start, row([4.89, -2.0, 0.0], [5.2, -2.0, .017])], 12, 'red_1')
        held = t.sim_sign([start, row([4.89, -2.0, 0.0], [5.1, -2.0, .07])], 12, 'red_1')
        self.assertTrue(placed['placed'])
        self.assertFalse(held['placed'])


if __name__ == '__main__':
    unittest.main()
