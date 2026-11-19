"""Tests of the side-step look of harness/carry_nav_v1.py (destination not seen from the door because another robot parked in
front of the same sign hides it).

No simulator, no network. Three layers:
  * the pure geometry (sight_masks, shadowed_wall_points, cluster_points, path_gap, plan_sidestep) on small made-up rooms;
  * three recorded failures of the 2026-11-16 investigation (a work record: poses and robot places in the arena
    frame, from the ceiling-camera records). The sign's place is used here only to JUDGE the choice, never passed to the planner;
  * the real CarryNav with the real carry_rows / carry_legs_spec of the runner: the new branch fires only after both scans of the
    room failed, up to that point the rows are those of the base commit 676768a, and without the measured robots nothing changes.
Run:  python3 -B -m unittest discover -s tests -p 'test_carry_sidestep.py' -v   (in the worktree root)"""
import sys
sys.dont_write_bytecode = True

import importlib.util
import math
import subprocess
import types
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.run_grasp_act_student as REAL  # noqa: E402  (the runner: its carry helpers are the kit of CarryNav)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CN = load(ROOT / 'harness' / 'carry_nav_v1.py', 'carry_nav_v1_sidestep_test')


def line(x0, y0, x1, y1, step=.1):
    n = int(round(max(abs(x1 - x0), abs(y1 - y0)) / step))
    return [(x0 + (x1 - x0) * i / max(n, 1), y0 + (y1 - y0) * i / max(n, 1), 0.) for i in range(n + 1)]


# the arena of the three-robot scenes (maps/zones/zone_wide_door_tags_v3a1.json): outer walls, divider at x 2.2 with the door y -0.2..0.3
ARENA = (line(-1.075, 1.45, 5.425, 1.45) + line(-1.075, -3.15, 5.425, -3.15) + line(-1.05, -3.15, -1.05, 1.45)
         + line(5.4, -3.15, 5.4, 1.45) + line(2.2, -3.15, 2.2, -0.2) + line(2.2, 0.3, 2.2, 1.45))
DOOR = (2.2, 0.05)


def wall(points):
    return [tuple(p[:2]) for p in points]


class Sight(unittest.TestCase):
    def test_a_wall_point_in_between_hides(self):
        walls = line(2., -1., 2., 1.) + line(4., -1., 4., 1.)
        geometric, clear = CN.sight_masks((0., 0.), [(4., 0.), (2., 0.)], walls, [])
        self.assertEqual(list(geometric), [False, True])          # the far one lies behind the first wall
        self.assertEqual(list(clear), [False, True])

    def test_grazing_view_along_a_wall_is_not_a_view(self):
        walls = line(0., 2., 6., 2.)
        geometric, _ = CN.sight_masks((0., 1.9), [(5., 2.)], walls, [])      # 1 degree off the wall's own line
        self.assertFalse(geometric[0])
        geometric, _ = CN.sight_masks((5., 0.), [(5., 2.)], walls, [])       # straight on
        self.assertTrue(geometric[0])

    def test_range(self):
        _, clear = CN.sight_masks((0., 0.), [(4.9, 0.), (5.1, 0.)], [], [])
        self.assertEqual(list(clear), [True, False])

    def test_robot_disc_hides_only_what_is_behind_it(self):
        geometric, clear = CN.sight_masks((0., 0.), [(4., 0.), (4., .4), (1., 0.)], [], [(2., 0.)])
        self.assertEqual(list(geometric), [True, True, True])
        self.assertEqual(list(clear), [False, True, True])         # 0.4 m off the line is outside the 0.15 m disc; in front is not behind

    def test_a_robot_on_the_eye_is_the_camera_itself(self):
        _, clear = CN.sight_masks((0., 0.), [(3., 0.)], [], [(.05, 0.)])
        self.assertTrue(clear[0])


class Shadow(unittest.TestCase):
    def room(self):
        return line(5., -2., 5., 2.) + line(-1., 2., 5., 2.) + line(-1., -2., 5., -2.)

    def test_robot_in_front_of_a_wall_leaves_a_shadow_on_it(self):
        walls = self.room()
        hidden = CN.shadowed_wall_points([(1., 0.)], walls, [(4.4, 0.)])
        self.assertGreaterEqual(len(hidden), 3)                   # 0.15 m disc 3.4 m from the eye, wall 4 m: shadow 0.35 m wide
        self.assertTrue(all(abs(p[0] - 5.) < 1e-6 and abs(p[1]) < .5 for p in hidden))

    def test_looks_from_both_sides_clear_it(self):
        walls = self.room()
        hidden = CN.shadowed_wall_points([(1., 0.), (1., 1.5), (1., -1.5)], walls, [(4.4, 0.)])
        self.assertEqual(len(hidden), 0)

    def test_no_robot_no_shadow_and_points_behind_a_wall_are_not_shadow(self):
        walls = self.room() + line(2., -2., 2., 2.)               # a closed divider: the east wall is never seen from x < 2
        self.assertEqual(len(CN.shadowed_wall_points([(0., 0.)], walls, [])), 0)
        hidden = CN.shadowed_wall_points([(0., 0.)], walls, [(4.4, 0.)])
        self.assertEqual(len(hidden), 0)                          # a robot behind the divider hides nothing the eye could see

    def test_cluster_points(self):
        groups = CN.cluster_points([(0., 0.), (.1, 0.), (.2, 0.), (3., 0.), (3.1, 0.)])
        self.assertEqual(groups, [[0, 1, 2], [3, 4]])
        self.assertEqual(CN.cluster_points([]), [])

    def test_path_gap_ignores_what_lies_at_the_start(self):
        self.assertAlmostEqual(CN.path_gap((0., 0.), (2., 0.), [(1., .3)]), .3)
        self.assertEqual(CN.path_gap((0., 0.), (2., 0.), [(0.05, .1)]), 9.)         # at the start: the robot stands there itself
        self.assertAlmostEqual(CN.path_gap((0., 0.), (2., 0.), [(2.5, 0.)]), .5)     # beyond the end: distance to the end point
        self.assertEqual(CN.path_gap((0., 0.), (2., 0.), []), 9.)


class Plan(unittest.TestCase):
    """A room 6 x 4 m east of a divider with the door at (2.2, 0.05); the robot stands at (3.3, 0) having looked from (2.6, 0) and there."""

    def setUp(self):
        self.walls = (line(5.4, -2., 5.4, 2.) + line(2.2, -2., 5.4, -2.) + line(2.2, 2., 5.4, 2.) + line(2.2, -2., 2.2, -.2) + line(2.2, .3, 2.2, 2.))
        self.pose = {'x': 3.3, 'y': 0.}
        self.eyes = [(2.6, 0.), (3.3, 0.)]

    def test_nothing_hidden_no_side_step(self):
        choice, facts = CN.plan_sidestep(self.pose, self.eyes, self.walls, [], DOOR)
        self.assertIsNone(choice)
        self.assertEqual(facts['hidden_points'], 0)

    def test_steps_across_the_line_to_the_shadow(self):
        choice, facts = CN.plan_sidestep(self.pose, self.eyes, self.walls, [(4.8, 0.)], DOOR)
        self.assertIsNotNone(choice)
        self.assertGreaterEqual(choice['revealed'], CN.SIDESTEP_MIN_REVEAL)
        self.assertAlmostEqual(abs(choice['target'][1]), math.sqrt(choice['dist_m'] ** 2 - (choice['target'][0] - 3.3) ** 2), places=2)
        self.assertLess(abs(choice['target'][0] - 3.3), .05)      # straight sideways, not toward the shadow
        self.assertIn(choice['dist_m'], CN.SIDESTEP_M)

    def test_the_shorter_one_when_it_shows_as_much(self):
        choice, facts = CN.plan_sidestep(self.pose, self.eyes, self.walls, [(4.8, 0.)], DOOR)
        shown = [c for c in facts['candidates'] if c['rejected'] is None]
        best = max(c['revealed'] for c in shown)
        ok = [c for c in shown if c['revealed'] >= CN.SIDESTEP_NEAR_BEST * best]
        self.assertEqual(choice['dist_m'], min(c['dist_m'] for c in ok))

    def test_a_wall_on_one_side_sends_it_to_the_other(self):
        pose = {'x': 3.3, 'y': 1.4}                                 # 0.6 m from the north wall
        choice, facts = CN.plan_sidestep(pose, [(2.6, 1.4), (3.3, 1.4)], self.walls, [(4.8, 1.4)], DOOR)
        self.assertIsNotNone(choice)
        self.assertLess(choice['target'][1], 1.4)
        north = [c for c in facts['candidates'] if c['target'][1] > 1.4]
        self.assertTrue(north and all(c['rejected'] in ('wall', 'wall_in_the_way') for c in north))

    def test_a_robot_on_one_side_sends_it_to_the_other(self):
        robots = [(4.8, 0.), (3.3, .9)]                             # a second robot where the north step would end
        choice, facts = CN.plan_sidestep(self.pose, self.eyes, self.walls, robots, DOOR)
        self.assertIsNotNone(choice)
        self.assertLess(choice['target'][1], 0.)
        north = [c for c in facts['candidates'] if c['target'][1] > 0.]
        self.assertTrue(north and all(c['rejected'] in ('robot', 'robot_in_the_way') for c in north))

    def test_not_into_the_doorway(self):
        pose = {'x': 2.9, 'y': 0.}
        choice, facts = CN.plan_sidestep(pose, [(2.6, 0.), (2.9, 0.)], self.walls, [(4.8, 0.)], DOOR)
        for c in facts['candidates']:
            if math.hypot(c['target'][0] - DOOR[0], c['target'][1] - DOOR[1]) < CN.SIDESTEP_DOOR_M:
                self.assertEqual(c['rejected'], 'door')
        if choice is not None:
            self.assertGreaterEqual(math.hypot(choice['target'][0] - DOOR[0], choice['target'][1] - DOOR[1]), CN.SIDESTEP_DOOR_M)

    def test_nothing_usable_returns_none_with_the_reasons(self):
        boxed = line(2.2, -2., 5.4, -2.) + line(2.2, 2., 5.4, 2.) + line(5.4, -2., 5.4, 2.)
        pose = {'x': 3.3, 'y': 0.}
        robots = [(4.8, 0.), (3.3, .8), (3.3, -.8)]                 # robots on both sides
        choice, facts = CN.plan_sidestep(pose, [(2.6, 0.), (3.3, 0.)], boxed, robots, None)
        self.assertIsNone(choice)
        self.assertTrue(facts['candidates'])
        self.assertTrue(all(c['rejected'] for c in facts['candidates']))

    def test_the_planner_takes_no_sign_place(self):
        import inspect
        names = set(inspect.signature(CN.plan_sidestep).parameters)
        self.assertEqual(names, {'pose', 'eyes', 'walls', 'robots', 'door'})


class Recorded(unittest.TestCase):
    """Zone-not-seen carries of the investigation. The sign is judged by five points across its 0.25 m width on the wall."""

    @staticmethod
    def footprint(sign):
        x, y, tangent = {11: (5.4, .40, (0, 1)), 12: (5.4, -2.10, (0, 1)), 13: (3.40, -3.15, (1, 0))}[sign]
        return [(x + k * .0625 * tangent[0], y + k * .0625 * tangent[1]) for k in (-2, -1, 0, 1, 2)]

    def check(self, pose, eyes, robots, sign):
        foot = self.footprint(sign)
        for eye in eyes:                                           # the carries really did not see it (at most two of the five points in view)
            self.assertLessEqual(int(CN.sight_masks(eye, foot, ARENA, robots)[1].sum()), 2)
        choice, facts = CN.plan_sidestep(pose, eyes, ARENA, robots, DOOR)
        self.assertIsNotNone(choice, facts)
        shown = int(CN.sight_masks(choice['target'], foot, ARENA, robots)[1].sum())
        self.assertGreaterEqual(shown, 4)                          # at least four of the five points are in view from the chosen spot
        return choice

    def test_d3m02_sign13_behind_r3(self):
        choice = self.check({'x': 3.0, 'y': -.71}, [(2.84, -.05), (2.99, -.71)], [(4.76, .34), (3.3, -2.52)], 13)
        self.assertGreater(choice['target'][0], 3.5)               # east, away from the divider

    def test_k3m03_sign12_behind_r3_with_r1_at_sign11(self):
        # the nearest other robot (r1, 1.5 m) is parked at sign 11 and hides nothing of sign 12: the shadow groups find r3 anyway
        choice = self.check({'x': 3.35, 'y': -.14}, [(2.69, .02), (3.35, -.14)], [(4.75, .29), (4.87, -1.77)], 12)
        self.assertGreaterEqual(len(CN.plan_sidestep({'x': 3.35, 'y': -.14}, [(2.69, .02), (3.35, -.14)], ARENA,
                                                     [(4.75, .29), (4.87, -1.77)], DOOR)[1]['groups']), 2)

    def test_cf3_c01_sign11_behind_r1(self):
        self.check({'x': 3.51, 'y': -.09}, [(2.15, .05), (2.81, .03)], [(4.75, .28)], 11)

    def test_the_same_pose_without_the_parked_robot_asks_for_nothing(self):
        choice, facts = CN.plan_sidestep({'x': 3.51, 'y': -.09}, [(2.15, .05), (2.81, .03)], ARENA, [], DOOR)
        self.assertIsNone(choice)


class FakePlaces:
    """Place memory stand-in: the destination is never seen (until `found` is set)."""
    obstacles, walls = {}, {}

    def __init__(self):
        self.found, self.zone_looks = False, 0

    def door(self, name):
        return {'kind': 'door', 'x': 2.2, 'y': .05, 'left': [2.2, .3], 'right': [2.2, -.2], 'width_m': .5, 'observations': 3}

    def observe(self, *a, **k):
        pass

    def observe_zone(self, *a, **k):
        self.zone_looks += 1

    def zone(self, colour, phase=None):
        return {'kind': 'zone_' + colour, 'x': 5., 'y': .4, 'points': 30} if self.found else None

    def tall_thing_beyond_door(self):
        return None


KIT = types.SimpleNamespace(
    carry_rows=REAL.carry_rows, carry_to_plan=REAL.carry_to_plan, carry_nominal_pose=REAL.carry_nominal_pose,
    carry_route=REAL.carry_route, carry_legs_spec=REAL.carry_legs_spec, carry_point_clearance=REAL.carry_point_clearance,
    carry_door_step=REAL.carry_door_step, CARRY_DOOR_STANDOFF_M=REAL.CARRY_DOOR_STANDOFF_M, CARRY_LOOK_S=REAL.CARRY_LOOK_S,
    CARRY_PASS_TRIES=REAL.CARRY_PASS_TRIES, CARRY_BOX_ROW=REAL.CARRY_BOX_ROW, CARRY_PASS_BEYOND_M=REAL.CARRY_PASS_BEYOND_M,
    CARRY_UNIT=REAL.CARRY_UNIT, CARRY_SWEEP_M=REAL.CARRY_SWEEP_M, CARRY_BODY_M=REAL.CARRY_BODY_M,
    CARRY_BACK_MAX_M=REAL.CARRY_BACK_MAX_M)


def base_module():
    """harness/carry_nav_v1.py of the base commit 676768a (None when the commit is not available)."""
    try:
        text = subprocess.run(['git', 'show', '676768a:harness/carry_nav_v1.py'], cwd=str(ROOT), capture_output=True, check=True).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        return None
    mod = types.ModuleType('carry_nav_v1_base')
    exec(compile(text, 'carry_nav_v1_base', 'exec'), mod.__dict__)
    return mod


class NavBranch(unittest.TestCase):
    POSE = {'x': 3.0, 'y': -.71, 'yaw': 0.}
    ROBOTS = [(4.76, .34), (3.3, -2.52)]

    def nav(self, mod=CN, measured=True):
        places = FakePlaces()
        nav = mod.CarryNav(KIT, places, {'x': 1., 'y': 0., 'yaw': 0.}, [], 'zone_sign13', held_kind='blue', picked=[.2, .4])
        nav.set_arena({'x': DOOR[0], 'y': DOOR[1], 'left': [2.2, .3], 'right': [2.2, -.2], 'width_m': .5}, [(p[0], p[1]) for p in ARENA])
        if measured:
            nav.pose_source = lambda: dict(self.POSE)
            nav.others_source = lambda: list(self.ROBOTS)
        nav.phase, nav.seen_close, nav.pose = 'pass', True, dict(self.POSE)     # the leg through the door is over
        return nav, places

    @staticmethod
    def drain(nav, limit=20000):
        out = []
        while len(out) < limit and (row := nav.step(b'', {})) is not None:
            out.append(row)
        return out

    def test_two_failed_scans_then_a_side_step_then_a_third_scan(self):
        nav, places = self.nav()
        rows = []
        while nav.outcome is None and not any(s.get('decision') == 'zone_not_seen_sidestep' for s in nav.steps):
            rows.append(nav.step(b'', {}))
            self.assertIsNotNone(rows[-1])
        decisions = [s['decision'] for s in nav.steps]
        self.assertEqual(decisions.count('zone_not_seen_from_door_look_again_inside'), 1)
        self.assertLess(decisions.index('zone_not_seen_from_door_look_again_inside'), decisions.index('zone_not_seen_sidestep'))
        step = next(s for s in nav.steps if s['decision'] == 'zone_not_seen_sidestep')
        self.assertEqual((nav.phase, nav.outcome), ('scan', None))
        self.assertEqual(step['try'], 1)
        self.assertIn(step['choice']['dist_m'], CN.SIDESTEP_M)
        self.assertIn('fwd:', step['spec'])
        scan_looks = [lk for lk in nav.looks if lk['phase'] == 'zone_scan']
        self.assertEqual(len(scan_looks), 36)                      # three scans of twelve stops, all named zone_scan

    def test_found_after_the_side_step_goes_to_the_zone(self):
        nav, places = self.nav()
        while not any(s.get('decision') == 'zone_not_seen_sidestep' for s in nav.steps):
            self.assertIsNotNone(nav.step(b'', {}))
        places.found = True                                       # the third scan sees the sign
        self.drain(nav)
        decisions = [s['decision'] for s in nav.steps]
        self.assertIn('go_to_zone', decisions)
        self.assertEqual(nav.outcome, 'at_zone')

    def test_not_found_ends_after_the_tries_with_the_old_outcome(self):
        nav, places = self.nav()
        self.drain(nav)
        self.assertEqual(nav.outcome, 'zone_not_seen_from_door')
        made = [s for s in nav.steps if s['decision'] == 'zone_not_seen_sidestep']
        self.assertGreaterEqual(len(made), 1)
        self.assertLessEqual(len(made), CN.SIDESTEP_TRIES)
        self.assertEqual([s['try'] for s in made], list(range(1, len(made) + 1)))

    def test_without_measured_robots_the_carry_ends_as_before(self):
        nav, places = self.nav(measured=False)
        nav.pose_source = lambda: dict(self.POSE)                  # the second scan needs the measured pose, the side-step the measured robots
        self.drain(nav)
        self.assertEqual(nav.outcome, 'zone_not_seen_from_door')
        self.assertFalse(any('sidestep' in s['decision'] for s in nav.steps))

    def test_no_parked_robot_no_side_step(self):
        nav, places = self.nav()
        nav.others_source = lambda: []
        self.drain(nav)
        self.assertEqual(nav.outcome, 'zone_not_seen_from_door')
        self.assertIn('zone_not_seen_no_sidestep', [s['decision'] for s in nav.steps])
        self.assertFalse(any(s['decision'] == 'zone_not_seen_sidestep' for s in nav.steps))

    def test_everything_before_the_failure_branch_is_the_base_commit(self):
        base = base_module()
        if base is None:
            self.skipTest('base commit 676768a not available')
        # without the measured robots the whole carry is the old one
        old, _ = self.nav(base)
        new, _ = self.nav(CN)
        old.others_source = new.others_source = None
        self.assertEqual(self.drain(new), self.drain(old))
        self.assertEqual((new.rows, new.arm, new.steps, new.looks, new.outcome), (old.rows, old.arm, old.steps, old.looks, old.outcome))
        self.assertEqual(old.outcome, 'zone_not_seen_from_door')
        # with them: the old carry stops where the new one steps aside, the rows and records before that point are the same
        old, _ = self.nav(base)
        new, _ = self.nav(CN)
        self.drain(old)
        before = len(old.rows) - old.log[-1]['rows']               # the old carry's last rows are the arm coming down (_stop)
        self.assertEqual(old.log[-1]['spec'], 'arm:hold')
        self.drain(new)
        self.assertEqual(new.rows[:before], old.rows[:before])
        self.assertEqual(new.arm[:before], old.arm[:before])
        self.assertEqual(new.looks[:len(old.looks)], old.looks)
        self.assertEqual(new.steps[:len(old.steps)], old.steps)
        self.assertEqual(new.log[:len(old.log) - 1], old.log[:-1])
        self.assertEqual(new.steps[len(old.steps)]['decision'], 'zone_not_seen_sidestep')

if __name__ == '__main__':
    unittest.main()
