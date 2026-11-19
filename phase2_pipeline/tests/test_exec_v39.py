"""Tests of the execution-layer experiment switches v39 (all default off): held-check lens-edge fix, "look around again" pick option, body stop of a
failed robot. No simulator, no network.

  * place_memory_v1: last_bright_rows / lens_edge_share on small made-up masks (a sliver along the border, a box in the middle, a tall box clipped
    at one side only, a box clipped by the bottom border), and PlaceMemory.box_on_floor on a synthetic lens picture (needs cv2);
  * run_grasp_act_student.look_back_m;
  * run_team_carry: the pick point with and without look_around (option list, counting, empty list, re-listing), FixedPlan, and run_team with a
    failed robot (fake world and fake robot generators: the failed body gets zero wheels, the others go on, the fixed plan's door order skips it);
  * scripts/held_edge_offline: look_ticks / verdict on made-up command rows.
Run:  python3 -B -m unittest discover -s tests -p 'test_exec_v39.py' -v   (in the worktree root)"""
import sys
sys.dont_write_bytecode = True

import importlib.util
import json
import math
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.run_grasp_act_student as SOLO  # noqa: E402
import scripts.run_team_carry as TEAM  # noqa: E402

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


PM = load(ROOT / 'harness' / 'place_memory_v1.py', 'place_memory_v1_v39_test') if cv2 is not None else None
OFF = load(ROOT / 'scripts' / 'held_edge_offline.py', 'held_edge_offline_v39_test')


def lens_picture():
    """A 480x640 'lens': bright floor inside a rounded border, black outside; the bottom border curves up towards the sides (row 462 in the middle)."""
    value = np.zeros((480, 640), np.uint8)
    for x in range(22, 602):
        bottom = int(462 - 18 * ((x - 312) / 290.) ** 2)
        value[10:bottom, x] = 120
    return value


class LensEdge(unittest.TestCase):
    def setUp(self):
        self.value = lens_picture()
        self.last = PM.last_bright_rows(self.value) if PM else None

    def blob(self, x0, x1, y0, y1):
        mask = np.zeros((480, 640), bool)
        mask[y0:y1, x0:x1] = True
        return mask

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_last_bright_row_follows_the_border(self):
        self.assertEqual(int(self.last[312]), 461)
        self.assertGreater(int(self.last[312]), int(self.last[40]))      # the border curves up towards the sides
        self.assertEqual(int(self.last[5]), -1)                         # black column

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_sliver_along_the_border_is_edge_hugging(self):
        x0, x1 = 530, 590
        top = [int(self.last[x]) for x in range(x0, x1)]
        mask = np.zeros((480, 640), bool)
        for x, last in zip(range(x0, x1), top):
            mask[last - 12:last - 1, x] = True                          # 11 px high, ends 1 px above the border everywhere
        self.assertEqual(PM.lens_edge_share(mask, self.last), 1.0)

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_box_in_the_middle_is_not(self):
        self.assertEqual(PM.lens_edge_share(self.blob(250, 300, 250, 300), self.last), 0.0)

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_tall_box_clipped_at_one_side_only_is_not(self):
        # a real box whose lower left corner touches the border (the columns near the left border end at its row) but whose bottom edge is far above it
        # over most columns: not the held box
        mask = self.blob(40, 160, 300, 400)
        self.assertLess(PM.lens_edge_share(mask, self.last), PM.HELD_EDGE_COLUMNS)
        mask2 = mask.copy()
        mask2[400:int(self.last[40]) + 1, 40:46] = True                 # the first 6 columns reach the border
        self.assertLess(PM.lens_edge_share(mask2, self.last), PM.HELD_EDGE_COLUMNS)

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_box_cut_by_the_border_is_hugging(self):
        mask = self.blob(200, 420, 380, 460)                            # its lower edge lies along the border over most columns
        for x in range(200, 420):
            mask[int(self.last[x]) - 2:, x] = False
            mask[int(self.last[x]) - 3:int(self.last[x]) - 1, x] = True
        self.assertGreaterEqual(PM.lens_edge_share(mask, self.last), PM.HELD_EDGE_COLUMNS)

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_edge_distance_limit(self):
        mask = self.blob(250, 300, 300, 300 + 1)
        for x in range(250, 300):
            last = int(self.last[x])
            mask[:, x] = False
            mask[last - PM.HELD_EDGE_PX, x] = True                      # exactly HELD_EDGE_PX above the border: still hugging
        self.assertEqual(PM.lens_edge_share(mask, self.last), 1.0)
        shifted = np.roll(mask, -1, axis=0)                             # one row higher: not
        self.assertEqual(PM.lens_edge_share(shifted, self.last), 0.0)

    @unittest.skipIf(cv2 is None, 'needs cv2')
    def test_empty_blob(self):
        self.assertEqual(PM.lens_edge_share(np.zeros((480, 640), bool), self.last), 0.)


@unittest.skipIf(cv2 is None, 'needs cv2')
class BoxOnFloor(unittest.TestCase):
    """PlaceMemory.box_on_floor on a synthetic picture: a red sliver along the lens border and a red box mid-picture."""
    POSTURE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}

    @classmethod
    def setUpClass(cls):
        gp = load(ROOT / 'harness' / 'approach_survey_v1_parts' / 'ground_projection.py', 'ground_projection')
        cls.places = PM.PlaceMemory(gp)

    def picture(self, sliver, box):
        value = lens_picture()
        bgr = np.zeros((480, 640, 3), np.uint8)
        bgr[value > 0] = (150, 120, 110)                                # bluish floor (low saturation)
        last = PM.last_bright_rows(value)
        if sliver:
            for x in range(530, 590):
                bgr[int(last[x]) - 12:int(last[x]) - 1, x] = (0, 0, 200)
        if box:
            bgr[250:300, 250:300] = (0, 0, 200)
        return cv2.imencode('.jpg', bgr)[1].tobytes()

    def test_sliver_alone(self):
        jpeg = self.picture(True, False)
        self.assertEqual(len(self.places.box_on_floor(jpeg, self.POSTURE, 'red')), 1)          # the old rule reads it as a box on the floor
        self.assertEqual(self.places.box_on_floor(jpeg, self.POSTURE, 'red', edge_fix=True), [])
        self.assertEqual(len(self.places.last_edge_excluded), 1)
        self.assertGreaterEqual(self.places.last_edge_excluded[0]['edge_share'], 0.99)

    def test_box_alone_is_kept_either_way(self):
        jpeg = self.picture(False, True)
        old = self.places.box_on_floor(jpeg, self.POSTURE, 'red')
        self.assertEqual(len(old), 1)
        self.assertEqual(self.places.box_on_floor(jpeg, self.POSTURE, 'red', edge_fix=True), old)
        self.assertEqual(self.places.last_edge_excluded, [])

    def test_both(self):
        jpeg = self.picture(True, True)
        self.assertEqual(len(self.places.box_on_floor(jpeg, self.POSTURE, 'red')), 2)
        kept = self.places.box_on_floor(jpeg, self.POSTURE, 'red', edge_fix=True)
        self.assertEqual(len(kept), 1)
        self.assertTrue(0.05 < kept[0][0] < 0.95)

    def test_default_call_signature_unchanged(self):
        jpeg = self.picture(True, True)
        self.assertEqual(self.places.box_on_floor(jpeg, self.POSTURE, 'red'), self.places.box_on_floor(jpeg, self.POSTURE, 'red', edge_fix=False))


class LookBack(unittest.TestCase):
    def test_free_space_behind(self):
        self.assertEqual(SOLO.look_back_m((0., 0., 0.), []), SOLO.LOOK_BACK_M)
        self.assertEqual(SOLO.look_back_m((0., 0., 0.), [(-2., 0.)]), SOLO.LOOK_BACK_M)

    def test_wall_behind_shortens(self):
        back = SOLO.look_back_m((0., 0., 0.), [(-0.35, 0.), (-0.35, 0.05)])
        self.assertAlmostEqual(back, 0.35 - SOLO.LOOK_WALL_HALF_M - SOLO.LOOK_REAR_M - SOLO.LOOK_WALL_MARGIN_M)

    def test_wall_too_close_gives_zero(self):
        self.assertEqual(SOLO.look_back_m((0., 0., 0.), [(-0.18, 0.)]), 0.)

    def test_wall_beside_or_ahead_is_ignored(self):
        self.assertEqual(SOLO.look_back_m((0., 0., 0.), [(0.2, 0.), (-0.2, 0.5)]), SOLO.LOOK_BACK_M)

    def test_heading_matters(self):
        self.assertEqual(SOLO.look_back_m((0., 0., math.pi), [(-0.18, 0.)]), SOLO.LOOK_BACK_M)      # facing the wall: behind is free
        self.assertEqual(SOLO.look_back_m((0., 0., math.pi), [(0.18, 0.)]), 0.)


class FakeBrain:
    """decide() answers scripted keys; records every option list."""
    def __init__(self, answers):
        self.answers, self.asked, self.told = list(answers), [], []

    def tell(self, rid, facts):
        self.told.append(facts)

    def decide(self, rid, now_s, point, options):
        self.asked.append((point, [o['key'] for o in options], [o['text'] for o in options]))
        return {'option': self.answers.pop(0) if self.answers else 'wait', 'wait_s': 2.0, 'sent': [], 'calls': 1}

    def poll(self, rid, now_s):
        return False


def entry(kind, x, y):
    return {'kind': kind, 'x': x, 'y': y, 'distance_m': math.hypot(x, y), 'bearing_rad': math.atan2(y, x)}


class PickPoint(unittest.TestCase):
    ENTRIES = [entry('red', 1., 0.), entry('cyan', 1.2, 0.4)]

    def make(self, answers, **kw):
        brain, clock = FakeBrain(answers), [0.]
        choose, _destination, _gate, state = TEAM.hooks('r1', brain, lambda: clock[0], [], **kw)
        return brain, choose, state, clock

    def test_default_options_unchanged(self):
        brain, choose, state, _ = self.make(['box:0'])
        self.assertEqual(choose(self.ENTRIES), 0)
        self.assertEqual(brain.asked[0][1], ['box:0', 'box:1', 'wait', 'finish'])

    def test_option_offered_after_the_boxes_with_the_agreed_key_and_text(self):
        brain, choose, state, _ = self.make(['box:1'], look_around=True)
        self.assertEqual(choose(self.ENTRIES), 1)
        self.assertEqual(brain.asked[0][1], ['box:0', 'box:1', TEAM.LOOK_AROUND_KEY, 'wait', 'finish'])
        self.assertEqual(TEAM.LOOK_AROUND_KEY, 'look_around')
        self.assertEqual(brain.asked[0][2][2], 'look around again (turn in place and refresh my box list)')

    def test_chosen_look_around_relists_and_counts(self):
        brain, choose, state, clock = self.make([TEAM.LOOK_AROUND_KEY, 'box:0'], look_around=True)
        clock[0] = 12.
        self.assertEqual(choose(self.ENTRIES), 'look_around')
        self.assertEqual(state['looks'], 1)
        self.assertEqual(state['look_log'], [12.0])
        self.assertFalse(state['listed'])
        self.assertEqual(sum('seen_boxes' in f for f in brain.told), 1)
        self.assertEqual(choose(self.ENTRIES), 0)                       # asked again with the new list, which is told again
        self.assertEqual(sum('seen_boxes' in f for f in brain.told), 2)

    def test_option_disappears_after_the_maximum(self):
        brain, choose, state, _ = self.make([TEAM.LOOK_AROUND_KEY] * 5, look_around=True)
        results = [choose(self.ENTRIES) for _ in range(TEAM.LOOK_AROUND_MAX + 1)]
        self.assertEqual(results[:TEAM.LOOK_AROUND_MAX], ['look_around'] * TEAM.LOOK_AROUND_MAX)
        self.assertNotIn(TEAM.LOOK_AROUND_KEY, brain.asked[-1][1])
        self.assertEqual(results[-1], 'wait')                            # an answer that is not an offered key waits

    def test_empty_list_asks_the_planner_only_with_the_switch(self):
        brain, choose, state, _ = self.make([TEAM.LOOK_AROUND_KEY], look_around=True)
        self.assertEqual(choose([]), 'look_around')
        self.assertEqual(brain.asked[0][1], [TEAM.LOOK_AROUND_KEY, 'wait', 'finish'])
        brain, choose, state, _ = self.make([])
        self.assertIsNone(choose([]))                                    # unchanged: nothing it can grasp, its run ends, the planner is not asked
        self.assertEqual(brain.asked, [])

    def test_empty_list_ends_the_run_when_no_look_is_left(self):
        brain, choose, state, _ = self.make([], look_around=True)
        state['looks'] = TEAM.LOOK_AROUND_MAX
        self.assertIsNone(choose([]))
        self.assertEqual(brain.asked, [])

    def test_capability_limit_still_applies(self):
        brain, choose, state, _ = self.make(['box:0'], look_around=True, can_grasp=('red',))
        self.assertEqual(choose(self.ENTRIES), 0)
        self.assertEqual(brain.asked[0][1], ['box:0', TEAM.LOOK_AROUND_KEY, 'wait', 'finish'])


class FixedPlanLook(unittest.TestCase):
    PICK = [{'key': 'box:0', 'text': 'go grasp target object <red box> in the box room, 1.0 m away, straight ahead of me (my label r1-box0)'},
            {'key': 'wait', 'text': 'wait here for now'}, {'key': 'finish', 'text': 'finish'}]
    LOOK = {'key': 'look_around', 'text': TEAM.LOOK_AROUND_TEXT}

    def test_colour_missing_looks_around_when_offered(self):
        plan = TEAM.FixedPlan({'r1': ('blue', 'sign11')}, ['r1'])
        self.assertEqual(plan.decide('r1', 12., 'pick', self.PICK[:1] + [self.LOOK] + self.PICK[1:])['option'], 'look_around')

    def test_colour_missing_waits_without_the_option(self):
        plan = TEAM.FixedPlan({'r1': ('blue', 'sign11')}, ['r1'])
        self.assertEqual(plan.decide('r1', 12., 'pick', self.PICK)['option'], 'wait')

    def test_colour_present_picks_it(self):
        plan = TEAM.FixedPlan({'r1': ('red', 'sign11')}, ['r1'])
        self.assertEqual(plan.decide('r1', 12., 'pick', self.PICK[:1] + [self.LOOK] + self.PICK[1:])['option'], 'box:0')


class FixedPlanTargetReLook(unittest.TestCase):
    """Phase-2 gate P2G-N09-S01 (a work record), robot r2, target box b at (-0.45, -6.92): grasped, lifted, dropped (drop_detected at
    138.4 s); at the re-look (150.5 s) the robot stood at (-0.875, -6.894, yaw 0.612) and box b lay at (-0.484, -6.911), 0.39 m away, 37.6 deg right: inside the
    survey camera's blind zone, so the list held one entry, a blue box 2.66 m away, 35 deg right (approach_survey_v1 of out-r2/summary.json). The pick option texts
    are rebuilt with box_where from those numbers (the run did not log them). FixedPlan answered 'finish' (assigned_box_not_listed, residual None)."""
    TARGET = {'r2': {'box': 'b', 'xy': (-0.45, -6.92)}}
    FIRST_POSE = (-0.2006324624280872, -7.749085098436693, 2.05880388702608)      # r2 when it first looked around (12.0 s)
    RELOOK_POSE = (-0.8751959033199598, -6.893809236817768, 0.6115124564397834)    # r2 at the re-look (150.5 s)
    RED_FIRST = {'key': 'box:0', 'text': 'go grasp target object <red box> in the box room, 0.9 m away, 11° right of me (my label r2-box0)'}
    BLUE_RELOOK = {'key': 'box:0', 'text': 'go grasp target object <blue box> in the box room, 2.7 m away, 35° right of me (my label r2-box0)'}
    LOOK = {'key': 'look_around', 'text': TEAM.LOOK_AROUND_TEXT}
    TAIL = [{'key': 'wait', 'text': 'wait here for now'}, {'key': 'finish', 'text': 'finish'}]

    def plan(self, pose):
        plan = TEAM.FixedPlan({'r2': ('red', 'sign19')}, ['r2'], targets=self.TARGET)
        plan.pose_source = lambda rid: pose
        return plan

    def test_decode_reproduces_the_logged_first_pick(self):
        plan = self.plan(self.FIRST_POSE)
        self.assertEqual(plan.decide('r2', 12., 'pick', [self.RED_FIRST] + self.TAIL)['option'], 'box:0')
        got = plan.pick_log[-1]
        self.assertEqual((got['resolved_xy'], got['reason']), ([-0.463, -6.888], 'assigned_box'))                          # as in team.json picks[0]
        self.assertAlmostEqual(got['residual_m'], 0.035, delta=0.002)       # the logged 0.035 used the pose of the very tick (the eval row here is the nearest)

    def test_relook_list_decodes_to_the_blue_box_not_to_b(self):
        colour, xy = TEAM.option_world_xy(self.BLUE_RELOOK['text'], self.RELOOK_POSE)
        self.assertEqual(colour, 'blue')
        self.assertAlmostEqual(xy[0], 1.825, delta=0.01)
        self.assertAlmostEqual(xy[1], -6.892, delta=0.01)
        self.assertGreater(math.hypot(xy[0] + 0.45, xy[1] + 6.92), 2.2)      # 2.28 m from the target: no tolerance (0.30 / 1.0 m) could take it

    def test_listed_box_matches_with_the_live_pose(self):
        """If the camera had listed box b (0.4 m away, 38 deg right) the plan would have taken it: the matching is not the failure."""
        plan = self.plan(self.RELOOK_POSE)
        plan.pick_log.append({'rid': 'r2', 'option': 'box:0'})                  # not the first look
        red = {'key': 'box:0', 'text': 'go grasp target object <red box> in the box room, 0.4 m away, 38° right of me (my label r2-box0)'}
        self.assertEqual(plan.decide('r2', 150.5, 'pick', [red] + self.TAIL)['option'], 'box:0')
        self.assertLess(plan.pick_log[-1]['residual_m'], 0.05)

    def test_relook_without_the_option_finishes_as_before(self):
        plan = self.plan(self.RELOOK_POSE)
        plan.pick_log.append({'rid': 'r2', 'option': 'box:0'})
        self.assertEqual(plan.decide('r2', 150.5, 'pick', [self.BLUE_RELOOK] + self.TAIL)['option'], 'finish')
        self.assertEqual((plan.pick_log[-1]['reason'], plan.pick_log[-1]['residual_m']), ('assigned_box_not_listed', None))

    def test_relook_with_the_option_looks_around_and_finishes_when_it_is_gone(self):
        plan = self.plan(self.RELOOK_POSE)
        plan.pick_log.append({'rid': 'r2', 'option': 'box:0'})
        for _ in range(TEAM.LOOK_AROUND_MAX):
            self.assertEqual(plan.decide('r2', 150.5, 'pick', [self.BLUE_RELOOK, self.LOOK] + self.TAIL)['option'], 'look_around')
        self.assertEqual((plan.pick_log[-1]['option'], plan.pick_log[-1]['reason']), ('look_around', 'assigned_box_not_listed'))
        # the hooks stop offering it after LOOK_AROUND_MAX looks: the plan finishes as before
        self.assertEqual(plan.decide('r2', 190., 'pick', [self.BLUE_RELOOK] + self.TAIL)['option'], 'finish')

    def test_a_look_around_at_the_first_look_keeps_the_first_tolerance(self):
        plan = self.plan(self.FIRST_POSE)
        far = {'key': 'box:0', 'text': 'go grasp target object <red box> in the box room, 1.5 m away, straight ahead of me (my label r2-box0)'}
        self.assertEqual(plan.decide('r2', 12., 'pick', [far, self.LOOK] + self.TAIL)['option'], 'look_around')
        self.assertEqual(plan.decide('r2', 25., 'pick', [far, self.LOOK] + self.TAIL)['option'], 'look_around')     # still the 0.30 m tolerance, not 1.0 m
        self.assertEqual([e['first'] for e in plan.pick_log], [True, True])
        self.assertEqual(plan.decide('r2', 40., 'pick', [self.RED_FIRST, self.LOOK] + self.TAIL)['option'], 'box:0')

    def test_no_pose_still_finishes(self):
        plan = TEAM.FixedPlan({'r2': ('red', 'sign19')}, ['r2'], targets=self.TARGET)    # no pose source, no start pose
        self.assertEqual(plan.decide('r2', 12., 'pick', [self.RED_FIRST, self.LOOK] + self.TAIL)['option'], 'finish')
        self.assertEqual(plan.pick_log[-1]['reason'], 'no_pose')

    def test_look_back_m_is_zero_at_the_relook_pose(self):
        """The v39 back-off cannot help this record: the west wall (x = -1.05, wall points every 0.1 m from y = -13.7) stands 0.147 m behind the body, so a
        look-around from there lists the same blind-zone picture (open: a move along the wall or a tilted-down near look)."""
        wall = [(-1.05, -13.7 + 0.1 * k) for k in range(152)]
        self.assertEqual(SOLO.look_back_m(self.RELOOK_POSE, wall), 0.)
        self.assertGreater(SOLO.look_back_m((-0.655, -6.911, -0.014), wall), 0.2)      # where it grasped: 0.25 m of room


class FakeWorld:
    def __init__(self):
        self.data = types.SimpleNamespace(time=0.)
        self.closed = False

    def robot(self, rid):
        return types.SimpleNamespace(base_xyz=lambda: np.array([1., 2., .03]))

    def close(self):
        self.closed = True


class FakePort:
    def __init__(self, rid):
        self.rid = rid


class BodyStop(unittest.TestCase):
    """run_team with fake robot generators and a fake physics: the body of the failed robot gets zero wheels from the failure time on."""

    def run_team(self, brain=None, ask_pick_at=None, **switches):
        sim = types.ModuleType('sim.zone_scenario_scene')
        sim.ScenarioFinalV3Scene = types.SimpleNamespace(
            from_scenario=lambda sid, seed: types.SimpleNamespace(config={'setup_only': {'objects': {}}}))
        calls, stopped = [], []

        def run_steps(plan, protocol, model, output, **kw):
            shared = kw['shared']
            if 'world' not in shared:
                shared['world'] = FakeWorld()
            world, rid = shared['world'], plan['robot_id']
            port = FakePort(rid)
            yield {'world': world, 'robot': rid, 'port': port, 'wheels': None, 'deadlines': None, 'until': 1.0}
            for k in range(40):
                if ask_pick_at is not None and rid == 'r1' and k == ask_pick_at:
                    kw['choose_box'](PickPoint.ENTRIES)        # the robot's pick decision: the planner may answer robot_failed here
                signal = yield {'world': world, 'robot': rid, 'port': port, 'wheels': [.35] * 4, 'deadlines': [world.data.time + .1] * 4,
                                'until': 1.0 + .1 * (k + 1)}
                if signal == 'body_stopped':
                    stopped.append(rid)
                    return {'status': 'complete', 'rid': rid, 'termination': 'body_stopped'}      # as run_steps does: report written normally
            return {'status': 'complete', 'rid': rid}

        def advance(world, requests, until):
            calls.append((round(until, 3), {r['port'].rid: tuple(r['wheels']) if r['wheels'] is not None else None for r in requests}))
            world.data.time = until

        scene = {'id': 'T', 'boxes': [{'colour': 'red', 'x': 1., 'y': 1., 'id': 'b1'}],
                 'robots': [{'rid': 'r1', 'x': 0., 'y': 0., 'yaw': 0.}, {'rid': 'r2', 'x': 0., 'y': 1., 'yaw': 0.}, {'rid': 'r3', 'x': 0., 'y': 2., 'yaw': 0.}],
                 'orders': [{'id': 'o1', 'colour': 'red', 'count': 1, 'sign': 11}], 'knows': {'r1': ['o1'], 'r2': ['o1'], 'r3': ['o1']}}
        plan = {'scenario_id': 'x', 'seed': 1, 'robot_id': 'r1', 'spawns': {'r1': [0., 0., .03, 0.]}}
        brain = brain or TEAM.FixedPlan({r: ('red', 'sign11') for r in ('r1', 'r2', 'r3')}, ['r1', 'r2', 'r3'])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(sys.modules, {'sim.zone_scenario_scene': sim}), \
                mock.patch.object(TEAM.solo, 'run_steps', run_steps), mock.patch.object(TEAM.solo, 'advance_physics', advance):
            record = TEAM.run_team(plan, {}, 'model', Path(tmp) / 'out', brain=brain, orders={}, knows={}, scene=scene, **switches)
        self.stopped = stopped
        return record, calls, brain

    def test_default_has_no_failure_keys(self):
        record, calls, brain = self.run_team()
        self.assertNotIn('failed', record)
        self.assertNotIn('conditions', record)
        self.assertEqual(self.stopped, [])
        self.assertEqual(sorted(record['finished']), ['r1', 'r2', 'r3'])
        self.assertTrue(all(len(c[1]) == 3 for c in calls))

    def test_failed_robot_body_stops_at_the_time(self):
        record, calls, brain = self.run_team(fail_robot='r1', fail_at_s=1.5)
        self.assertEqual(record['failed']['r1']['by'], 'time')
        self.assertGreaterEqual(record['failed']['r1']['t'], 1.5)
        self.assertEqual(sorted(record['finished']), ['r2', 'r3'])                      # r1's generator was never finished
        before = [c for c in calls if c[0] <= 2.5 and c[0] > 1.05]
        after = [c for c in calls if c[0] > 2.7]
        self.assertTrue(all(c[1]['r1'] == (.35,) * 4 for c in before))
        self.assertTrue(after and all(c[1]['r1'] == (0.,) * 4 and c[1]['r2'] == (.35,) * 4 for c in after))   # frozen request: wheels 0, still ticked
        self.assertIn('r1', brain.ended)
        self.assertEqual(self.stopped, ['r1'])                                           # only the failed robot's generator is told to end (its report is written normally)
        self.assertEqual((record['failed']['r1']['xy_at_stop'], record['failed']['r1']['xy_at_end']), ([1., 2.], [1., 2.]))     # evaluation side
        self.assertEqual(record['conditions']['body_stop'], {'fail_robot': 'r1', 'fail_at_s': 1.5, 'stop_failed_body': False})

    def test_all_others_finish_and_run_ends(self):
        record, calls, brain = self.run_team(fail_robot='r2', fail_at_s=0.5)
        self.assertEqual(sorted(record['finished']), ['r1', 'r3'])
        self.assertEqual(record['failed']['r2']['by'], 'time')

    @staticmethod
    def failing_planner():
        """The fixed plan, except that robot r1 is answered 'robot_failed' (halted) at its pick decisions: what the planner host does for a robot of --fail-robot."""
        class Failing(TEAM.FixedPlan):
            def decide(self, rid, now_s, point, options):
                if rid == 'r1' and point == 'pick':
                    return {'option': 'wait', 'wait_s': 2., 'sent': [], 'calls': 0, 'halted': True, 'reason': 'robot_failed'}
                return super().decide(rid, now_s, point, options)
        return Failing({r: ('red', 'sign11') for r in ('r1', 'r2', 'r3')}, ['r1', 'r2', 'r3'])

    def test_planner_answer_stops_the_body_only_when_asked(self):
        record, calls, brain = self.run_team(brain=self.failing_planner(), ask_pick_at=5, stop_failed_body=True)
        self.assertEqual(record['failed']['r1']['by'], 'planner')                         # --stop-failed-body: stopped at the planner's answer
        self.assertEqual(self.stopped, ['r1'])
        self.assertTrue(any(c[1]['r1'] == (0.,) * 4 for c in calls[-5:]))
        self.assertEqual(record['conditions']['body_stop'], {'fail_robot': None, 'fail_at_s': None, 'stop_failed_body': True})
        record, calls, brain = self.run_team(brain=self.failing_planner(), ask_pick_at=5)
        self.assertNotIn('failed', record)                                                 # without the switch the answer changes nothing in the body
        self.assertEqual(sorted(record['finished']), ['r1', 'r2', 'r3'])

    def test_planner_answer_also_counts_with_a_runner_failure_time(self):
        record, calls, brain = self.run_team(brain=self.failing_planner(), ask_pick_at=5, fail_robot='r1', fail_at_s=30.)
        self.assertEqual(record['failed']['r1']['by'], 'planner')                         # earlier than the time

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            self.run_team(fail_robot='r1')
        with self.assertRaises(ValueError):
            self.run_team(fail_robot='r9', fail_at_s=3.)


class Hooks(unittest.TestCase):
    def test_robot_failed_answer_marks_the_state(self):
        class Failing(FakeBrain):
            def decide(self, rid, now_s, point, options):
                return {'option': 'wait', 'wait_s': 0., 'sent': [], 'calls': 0, 'halted': True, 'reason': 'robot_failed'}
        brain = Failing([])
        choose, _d, _g, state = TEAM.hooks('r1', brain, lambda: 12., [])
        self.assertEqual(choose(PickPoint.ENTRIES), 'wait')
        self.assertTrue(state['failed'] and state['halted'])

    def test_other_halts_do_not_mark_failed(self):
        class Halting(FakeBrain):
            def decide(self, rid, now_s, point, options):
                return {'option': 'wait', 'wait_s': 0., 'sent': [], 'calls': 0, 'halted': True, 'reason': 'Robot call cap reached'}
        choose, _d, _g, state = TEAM.hooks('r1', Halting([]), lambda: 12., [])
        choose(PickPoint.ENTRIES)
        self.assertNotIn('failed', state)


class OfflineHelpers(unittest.TestCase):
    @staticmethod
    def rows(spec):
        out = []
        for source, wheels in spec:
            out.append({'command': {'t': 0., 'wheels': [wheels] * 4, 'pwm': {}}, 'source': source})
        return out

    def test_look_ticks_without_turn(self):
        spec = [('act', 0.)] * 3 + [('carry_code', 0.)] * 20 + [('carry_code', -.35)] * 29 + [('carry_code', 0.)] * 5 + [('carry_code', 0.)] * 10 \
            + [('carry_code', 0.)] * 5 + [('carry_code', 0.)] + [('held_check', 0.)]
        rows = self.rows(spec)
        k = len(rows) - 1
        ticks = OFF.look_ticks(rows, k)
        first = 3 + 20 + 29 + 5
        self.assertEqual(ticks, [first + 5 + i for i in range(5)])

    def test_verdict(self):
        pose = (0., 0., 0.)
        box_ahead = [([(0.6, 0.0)], pose)] * 5
        nothing = [([], pose)] * 5
        self.assertTrue(OFF.verdict(box_ahead, None))
        self.assertFalse(OFF.verdict(nothing, (0.6, 0.0)))
        self.assertTrue(OFF.verdict([([(0.6, 0.0)], pose)] * 3 + [([], pose)] * 2, None))      # 3 of 5 frames: more than half
        self.assertFalse(OFF.verdict([([(0.6, 0.0)], pose)] * 2 + [([], pose)] * 3, None))
        far = [([(1.5, 0.0)], pose)] * 5
        self.assertFalse(OFF.verdict(far, None))
        self.assertTrue(OFF.verdict([([(0.2, 0.9)], pose)] * 2 + [([], pose)] * 3, (0.2, 0.9)))   # two frames with a box at the pick point


if __name__ == '__main__':
    unittest.main()
