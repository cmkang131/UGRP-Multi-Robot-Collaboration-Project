"""Multi-carry repairs of 2026-11-19 (all DEFAULT off): --zone-close-fix, --return-pose-fallback, --door-lane-fix.
No world, actor or planner service."""
import argparse
import math
import unittest
from types import SimpleNamespace

try:
    import cv2
except ImportError:                     # the work VMs have OpenCV; the local test run skips the pixel tests
    cv2 = None

from harness import carry_nav_v1 as nav_module, exec_opt
from scripts import run_grasp_act_student as solo


def parsed(*argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--overhead', action='store_true')
    exec_opt.add_arguments(parser)
    args = parser.parse_args(list(argv))
    return exec_opt.from_args(parser, args)


class Switches(unittest.TestCase):
    def test_all_default_off_and_absent_from_the_settings(self):
        self.assertIsNone(parsed())
        for field in ('zone_close_fix', 'zone_close_far', 'return_pose_fallback', 'door_lane_fix', 'look_turn', 'oracle_return_face', 'oracle_wide_pick'):
            self.assertFalse(getattr(exec_opt.Options(), field))
            self.assertNotIn(field, exec_opt.Options().settings())

    def test_each_flag_sets_only_its_field(self):
        for flag, field in (('--zone-close-fix', 'zone_close_fix'), ('--zone-close-far', 'zone_close_far'), ('--return-pose-fallback', 'return_pose_fallback'), ('--door-lane-fix', 'door_lane_fix'), ('--look-turn', 'look_turn'), ('--oracle-return-face', 'oracle_return_face'), ('--oracle-wide-pick', 'oracle_wide_pick')):
            self.assertEqual(parsed(flag), exec_opt.Options(**{field: True}))
            self.assertEqual(parsed(flag).settings(), {field: True})


class OracleReturnFace(unittest.TestCase):
    def test_the_plan_names_the_next_box_place_once_the_robot_is_sent_back(self):
        from scripts import run_team_carry as team
        itinerary = {'r3': [dict(box='a', order='o5', xy=(0.3, -1.86), door='door_1'), dict(box='d', order='o2', xy=(1.16, 0.43), door='door_1')]}
        plan = team.MultiFixedPlan({'r3': [('red', 'sign13'), ('blue', 'sign11')]}, ['r3'], {'r3': 'door_1'}, itinerary=itinerary,
                                   starts={'r3': (0.57, -1.25, -2.16)})
        self.assertEqual(plan.return_hint('r3'), [0.3, -1.86])           # the first box, before the robot has finished its first carry
        answer = plan.decide('r3', 225., 'next', [{'key': 'back', 'text': 'back'}, {'key': 'finish', 'text': 'finish'}])
        self.assertEqual(answer['option'], 'back')
        self.assertEqual(plan.return_hint('r3'), [1.16, 0.43])
        self.assertIsNone(plan.return_hint('r9'))


class OracleWidePick(unittest.TestCase):
    def plan(self, wide):
        from scripts import run_team_carry as team
        itinerary = {'r3': [dict(box='a', order='o1', xy=(0.69, -1.92), door='door_1'), dict(box='e', order='o2', xy=(0.78, -1.19), door='door_1')],
                     'r1': [dict(box='c', order='o3', xy=(-0.05, -1.4), door='door_1')]}
        plan = team.MultiFixedPlan({'r3': [('red', 'sign11'), ('blue', 'sign12')], 'r1': [('red', 'sign13')]}, ['r1', 'r3'], {'r3': 'door_1', 'r1': 'door_1'},
                                   itinerary=itinerary, starts={})
        plan.wide_second_pick = wide
        plan.pose_source = lambda rid: (1.5, -0.2, -2.7)                  # the robot's place in the world frame at the second look-around
        return plan

    def options(self, plan, distance):
        # a blue box listed `distance` m from the plan's place, 2.2 m from the robot
        import math
        x, y, yaw = 1.5, -0.2, -2.7
        bx, by = 0.78 + distance, -1.19
        d, a = math.hypot(bx - x, by - y), math.atan2(by - y, bx - x) - yaw
        side = 'left' if a > 0 else 'right'
        return [{'key': 'box:0', 'text': '<blue box> in the box room, %.1f m away, %d\u00b0 %s of me' % (d, round(abs(math.degrees(a))), side)},
                {'key': 'look_around', 'text': 'look around'}, {'key': 'finish', 'text': 'finish'}]

    def test_second_carry_takes_a_box_listed_half_a_metre_off_only_with_the_switch(self):
        for wide, expected in ((False, 'look_around'), (True, 'box:0')):
            plan = self.plan(wide)
            plan.trip['r3'] = 1                                               # second carry (the 'next' answer has counted it)
            plan.targets['r3'] = plan.itinerary['r3'][1]
            self.assertEqual(plan.pick_option('r3', 'blue', self.options(plan, .5), 480.), expected, wide)

    def test_first_carry_keeps_the_narrow_tolerance(self):
        plan = self.plan(True)
        plan.trip['r3'] = 0
        plan.targets['r3'] = plan.itinerary['r3'][1]
        self.assertEqual(plan.pick_option('r3', 'blue', self.options(plan, .5), 480.), 'look_around')


class LookTurn(unittest.TestCase):
    def test_the_turns_alternate_and_add_up_to_a_sweep_of_both_sides(self):
        degrees = []
        for spec in solo.LOOK_TURN_SPECS:
            rows = solo.carry_rows(spec)[0]
            pulses = [w for w, _ in rows if any(w)]
            kind = 'right' if pulses[0] == [v * solo.CARRY_PULSE[0] for v in solo.CARRY_WHEELS['right']] else 'left'
            turned = len(pulses) * math.degrees(solo.CARRY_UNIT[kind])
            degrees.append(turned if kind == 'left' else -turned)
        self.assertEqual([round(d / 5) * 5 for d in degrees], [-40, 80, -120])
        cumulative = [sum(degrees[:i + 1]) for i in range(3)]
        self.assertEqual([round(d / 5) * 5 for d in cumulative], [-40, 40, -80])        # a box 67 degrees to the right is 27 degrees off the heading after the first turn


class ReturnStart(unittest.TestCase):
    NOMINAL = {'x': 1., 'y': 2., 'yaw': .5}

    def test_fresh_pose_is_used_with_or_without_the_switch(self):
        for fallback in (False, True):
            self.assertEqual(solo.return_start_pose((3., 4., 1.), self.NOMINAL, fallback), ({'x': 3., 'y': 4., 'yaw': 1.}, False))

    def test_lost_robot_ends_the_run_unless_the_switch_is_on(self):
        self.assertIsNone(solo.return_start_pose(None, self.NOMINAL, False))
        self.assertEqual(solo.return_start_pose(None, self.NOMINAL, True), (self.NOMINAL, True))
        self.assertIsNone(solo.return_start_pose(None, None, True))
        start, _ = solo.return_start_pose(None, self.NOMINAL, True)
        start['x'] = 9.
        self.assertEqual(self.NOMINAL['x'], 1.)       # a copy


class NoPlaces:
    obstacles, walls = {}, {}

    def door(self, phase):
        return None


def lane_nav(my_id, blocker_id, *, flag=True, walls=((9., 9.),)):
    """Door at the origin, line along y; robot at x +0.95 facing the door (it started at +3); the other stands at x -0.93 on the axis (the NZC-R meeting)."""
    nav = nav_module.CarryNav(solo, NoPlaces(), {'x': 3., 'y': 0., 'yaw': 3.14159}, [], 'through_door')
    nav.set_arena({'x': 0., 'y': 0., 'left': (0., .25), 'right': (0., -.25), 'width_m': .5}, list(walls))
    nav.pose = {'x': .95, 'y': 0., 'yaw': 3.14159}
    nav.door_lane_fix = flag
    other = (-.93, 0.)
    nav.others_source = lambda: [other]
    nav.right_of_way_source = lambda: (my_id, {blocker_id: other})
    nav.beyond_robot = False
    return nav


class DoorLane(unittest.TestCase):
    def test_the_meeting_is_a_3_mm_miss(self):
        nav = lane_nav('r2', 'r1', flag=False)
        nav._pass(.9)
        self.assertEqual(nav.steps[-1]['decision'], 'robot_beyond_door_wait')
        self.assertAlmostEqual(nav.steps[-1]['free_beyond_m'], .33, places=2)

    def test_higher_number_backs_out_of_the_lane(self):
        nav = lane_nav('r2', 'r1')
        nav._pass(.9)
        step = nav.steps[-1]
        self.assertEqual(step['decision'], 'door_lane_back_off')
        self.assertEqual(step['blockers'], ['r1'])
        self.assertEqual(nav.phase, 'door_yield')
        pulses = step['pulses']
        self.assertGreaterEqual(pulses * solo.CARRY_UNIT['back'] + .95, nav_module.LANE_CLEAR_M - .02)
        wheels = [row[0] for row in nav.rows if any(row[0])]
        self.assertEqual(len(wheels), pulses)
        self.assertTrue(all(w == [-1., -1., -1., -1.] or all(v < 0 for v in w) for w in wheels))
        self.assertGreater(nav.pose['x'], 1.8)          # the nominal pose moved away from the door
        self.assertEqual(nav.lane_backs, 1)

    def test_lower_number_waits_for_the_other_to_back_off(self):
        nav = lane_nav('r1', 'r2')
        nav._pass(.9)
        self.assertEqual(nav.steps[-1]['decision'], 'robot_beyond_door_wait')
        self.assertEqual(nav.lane_backs, 0)

    def test_two_backs_at_most_then_the_old_wait(self):
        nav = lane_nav('r2', 'r1')
        nav._pass(.9)
        nav.pose = {'x': .95, 'y': 0., 'yaw': 3.14159}
        nav._pass(.9)
        self.assertEqual(nav.lane_backs, 2)
        nav.pose = {'x': .95, 'y': 0., 'yaw': 3.14159}
        nav._pass(.9)
        self.assertEqual(nav.steps[-1]['decision'], 'robot_beyond_door_wait')

    def test_no_room_behind_keeps_the_old_wait(self):
        wall = [(1.4, y / 10.) for y in range(-10, 11)] + [(9., 9.)]
        nav = lane_nav('r2', 'r1', walls=wall)
        nav._pass(.9)
        decisions = [s['decision'] for s in nav.steps]
        self.assertIn('door_lane_no_room', decisions)
        self.assertEqual(decisions[-1], 'robot_beyond_door_wait')

    def test_a_parked_lower_number_robot_2_3_m_out_stops_holding_the_door_only_with_the_switch(self):
        # robot r1 stands at its sign 2.3 m beyond the door centre (set down, run over); r3 comes from the box room, 2.4 m out
        for flag, yields in ((False, True), (True, False)):
            nav = lane_nav('r3', 'r1', flag=flag)
            nav.pose = {'x': -2.4, 'y': 0., 'yaw': 0.}
            nav.start = [-2.4, 0.]
            nav.right_of_way_source = lambda: ('r3', {'r1': (2.3, 0.)})
            self.assertEqual(nav._yield_to_door_user(), yields, flag)

    def blind_nav(self, flag, heading_error_deg):
        # the robot stands 0.6 m in front of the door (door at the origin, axis along x) after an open-loop approach, off the axis by heading_error_deg
        nav = lane_nav('r3', 'r1', flag=flag)
        nav.known_door = dict(nav.door)
        nav.pose = {'x': .6, 'y': 0., 'yaw': math.pi + math.radians(heading_error_deg)}
        nav.pose_source = lambda: dict(nav.pose)
        nav.looks.append({'rows': [0, 1], 'pose': dict(nav.pose), 'phase': 'approach_blind_look', 'near': True, 'what': 'door'})
        nav.phase, nav.blind_m = 'approach_blind', .6
        nav.others_source = lambda: []
        nav.right_of_way_source = lambda: ('r3', {})
        nav._next()
        return nav

    def test_blind_pass_checks_the_heading_only_with_the_switch(self):
        old = self.blind_nav(False, 22.)
        self.assertEqual(old.steps[-1]['decision'], 'pass_without_another_look')      # drives straight: 0.24 m off the axis at the door line
        new = self.blind_nav(True, 22.)
        self.assertNotIn('pass_without_another_look', [s['decision'] for s in new.steps])
        step = next(s for s in new.steps if 'turn_to_face_deg' in s)
        self.assertEqual(step['decision'], 'align')
        self.assertGreater(abs(step['turn_to_face_deg']), 12.)
        straight = self.blind_nav(True, 2.)
        self.assertEqual(next(s for s in straight.steps if 'turn_to_face_deg' in s)['decision'], 'pass')      # a lined-up robot still drives straight through

    def test_far_robot_is_not_a_blocker(self):
        nav = lane_nav('r2', 'r1')
        far = (-1.8, 0.)
        nav.others_source = lambda: [far]
        nav.right_of_way_source = lambda: ('r2', {'r1': far})
        nav._pass(.9)
        self.assertEqual(nav.phase, 'pass')


def square(x0, y0, side):
    return [[x0, y0], [x0 + side, y0], [x0 + side, y0 + side], [x0, y0 + side]]


@unittest.skipIf(cv2 is None, 'the card projection needs OpenCV')
class TopClip(unittest.TestCase):
    def setUp(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / 'harness' / 'robot_tags_v1.py'
        spec = importlib.util.spec_from_file_location('robot_tags_v1_mc_test', str(path))
        self.tags = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tags)

    def test_card_top_off_the_picture_is_not_whole_but_is_accepted_by_the_fix(self):
        reading = {'sign': 11, 'corners_px': square(200., 10., 100.)}      # the card's top border lies 6.7 px above the picture
        self.assertFalse(self.tags.whole_sign_in_frame(reading))
        self.assertTrue(self.tags.sign_in_frame_top_clipped(reading))
        reading = {'sign': 11, 'corners_px': square(200., 30., 100.)}      # fully inside: both rules agree
        self.assertTrue(self.tags.whole_sign_in_frame(reading))
        self.assertTrue(self.tags.sign_in_frame_top_clipped(reading))

    def test_the_fix_still_refuses_a_code_at_the_edge_or_a_clipped_side(self):
        for corners in (square(200., 2., 100.),            # code corner within 3 px of the top edge
                        square(1., 100., 100.),            # code corner at the left edge
                        square(300., 380., 100.),          # card bottom border off the picture
                        square(560., 100., 78.)):          # card's right border off the picture
            reading = {'sign': 11, 'corners_px': corners}
            self.assertFalse(self.tags.sign_in_frame_top_clipped(reading), corners)


class FakeTags:
    """Stand-in for robot_tags_v1 so that PlaceMemory._sign_points runs without pixels."""
    def __init__(self, whole, top_clipped, floor):
        self.whole, self.top_clipped, self.floor = whole, top_clipped, floor

    def card_corners(self, reading):
        import numpy as np
        return np.array([[190., -5.], [310., -5.], [310., 130.], [190., 130.]])

    def whole_sign_in_frame(self, reading):
        return self.whole

    def sign_in_frame_top_clipped(self, reading):
        return self.top_clipped

    def sign_on_floor(self, reading, posture, extrinsics, K):
        return None if self.floor is None else {'x': self.floor[0], 'y': self.floor[1], 'normal': [-1., 0.]}


@unittest.skipIf(cv2 is None, 'place_memory_v1 needs OpenCV')
class CloseReads(unittest.TestCase):
    def memory(self, reading_sign=11, **tags):
        from harness import place_memory_v1 as pm
        memory = pm.PlaceMemory(SimpleNamespace(K=None, D=None, camera_extrinsics=None))
        memory._tags = FakeTags(**tags)
        memory._tag_reader = SimpleNamespace(read=lambda jpeg: [{'sign': reading_sign, 'side_px': 100., 'corners_px': square(200., 10., 100.)}])
        return memory

    def test_default_close_look_keeps_the_whole_border_rule_and_the_2_m_limit(self):
        memory = self.memory(whole=False, top_clipped=True, floor=(1.3, 0.))
        self.assertEqual(memory._sign_points(b'', {}, 11, close=True, phase='zone_close'), [])
        memory = self.memory(whole=True, top_clipped=True, floor=(2.1, 0.))
        self.assertEqual(memory._sign_points(b'', {}, 11, close=True, phase='zone_close'), [])
        memory = self.memory(whole=True, top_clipped=False, floor=(1.3, 0.))
        self.assertEqual(len(memory._sign_points(b'', {}, 11, close=True, phase='zone_close')), 30)

    def test_fix_takes_a_top_clipped_card_and_reads_to_2_6_m(self):
        memory = self.memory(whole=False, top_clipped=True, floor=(2.3, 0.))
        memory.close_fix = True
        points = memory._sign_points(b'', {}, 11, close=True, phase='zone_close')
        self.assertEqual(len(points), 30)
        self.assertAlmostEqual(points[0][0], 2.3 - .32)          # the box goes SIGN_BOX_M in front of the sign (normal -x)
        memory = self.memory(whole=False, top_clipped=True, floor=(2.7, 0.))
        memory.close_fix = True
        self.assertEqual(memory._sign_points(b'', {}, 11, close=True, phase='zone_close'), [])

    def test_close_far_reads_to_3_3_m(self):
        memory = self.memory(whole=False, top_clipped=True, floor=(3.0, 0.))
        memory.close_fix = True
        self.assertEqual(memory._sign_points(b'', {}, 11, close=True, phase='zone_close'), [])      # 2.6 m with --zone-close-fix alone
        memory.close_far = True
        self.assertEqual(len(memory._sign_points(b'', {}, 11, close=True, phase='zone_close')), 30)
        memory = self.memory(whole=False, top_clipped=True, floor=(3.4, 0.))
        memory.close_fix = memory.close_far = True
        self.assertEqual(memory._sign_points(b'', {}, 11, close=True, phase='zone_close'), [])

    def test_far_reading_is_not_changed_by_the_fix(self):
        memory = self.memory(whole=False, top_clipped=False, floor=(4.0, 0.))
        memory.close_fix = True
        self.assertEqual(len(memory._sign_points(b'', {}, 11, close=False)), 30)     # the door scan: no frame rule, 6 m

    def test_every_close_reading_is_logged_with_its_reason(self):
        memory = self.memory(whole=False, top_clipped=False, floor=(1.3, 0.))
        memory.close_reads = []
        memory._sign_points(b'', {}, 11, close=True, phase='zone_close_1')
        memory._tag_reader = SimpleNamespace(read=lambda jpeg: [{'sign': 12, 'side_px': 50., 'corners_px': square(200., 10., 50.)}])
        memory._sign_points(b'', {}, 11, close=True, phase='zone_close_1')
        self.assertEqual([(r['phase'], r['sign'], r['accepted'], r['why']) for r in memory.close_reads],
                         [('zone_close_1', 11, False, 'not_in_frame'), ('zone_close_1', 12, False, 'other_id')])
        self.assertEqual(memory.close_reads[0]['card_y'], [-5., 130.])
        self.assertFalse(memory.close_reads[0]['whole'])


class NavRecord(unittest.TestCase):
    def test_close_reads_reach_the_record_only_with_zone_confirm_close(self):
        places = SimpleNamespace(door=lambda phase: None)
        plain = nav_module.CarryNav(solo, places, {'x': 0., 'y': 0., 'yaw': 0.}, [], 'zone_sign11')
        self.assertNotIn('close_reads', plain.record())
        self.assertFalse(hasattr(places, 'close_reads'))
        confirm = nav_module.CarryNav(solo, places, {'x': 0., 'y': 0., 'yaw': 0.}, [], 'zone_sign11', zone_confirm_close=True, zone_close_fix=True)
        self.assertEqual(confirm.record()['close_reads'], [])
        self.assertTrue(places.close_fix)


if __name__ == '__main__':
    unittest.main()
