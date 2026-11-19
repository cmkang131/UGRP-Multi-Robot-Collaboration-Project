"""Two robots meet at the door: the real CarryNav on both, kinematic bodies that move by the nominal pulse lengths, measured poses and measured other robots.
Reproduces the NZC-R deadlock of 2026-11-19 (r1 out with its box, r2 back, each the obstacle beyond the door of the other: both gave up after 20 waits) and
checks that --door-lane-fix resolves it in both number orders and from different arrival times, without the robots coming nearer than a body length."""
import math
import unittest

from harness import carry_nav_v1 as NM
from scripts import run_grasp_act_student as solo

U = solo.CARRY_UNIT


class FakePlaces:
    def __init__(self):
        self.obstacles, self.walls = {}, {}
    def door(self, phase): return None
    def observe(self, *a, **k): pass
    def observe_zone(self, *a, **k): pass
    def open_distance(self, *a, **k): return 5.
    def tall_thing_beyond_door(self): return None
    def box_on_floor(self, *a, **k): return []


def arena_walls():
    pts = []
    n = lambda a, b: [a + (b - a) * i / int(abs(b - a) / .05) for i in range(int(abs(b - a) / .05) + 1)]
    for y in n(-2.5, -.25): pts.append((0., y))
    for y in n(.25, 2.5): pts.append((0., y))
    for x in n(-4., 4.): pts += [(x, 2.5), (x, -2.5)]
    for y in n(-2.5, 2.5): pts += [(-4., y), (4., y)]
    return pts


class Robot:
    def __init__(self, rid, x, y, yaw, returning, fix, world):
        self.rid, self.world = rid, world
        self.x, self.y, self.yaw = x, y, yaw
        self.nav = NM.CarryNav(solo, FakePlaces(), {'x': x, 'y': y, 'yaw': yaw}, [], 'through_door')
        self.nav.set_arena({'x': 0., 'y': 0., 'left': [0., .25], 'right': [0., -.25], 'width_m': .5}, arena_walls())
        self.nav.returning = returning
        self.nav.return_face = [-2.2, 0.] if returning and x > 0 else None
        self.nav.door_lane_fix = fix
        self.nav.pose_source = lambda: {'x': self.x, 'y': self.y, 'yaw': self.yaw}
        self.nav.others_source = lambda: [(r.x, r.y) for r in world if r is not self]
        self.nav.right_of_way_source = lambda: (self.rid, {r.rid: (r.x, r.y) for r in world if r is not self})
        self.done = False
        self.rows = 0

    def tick(self):
        if self.done:
            # an outgoing robot scans 25 s beside the door line and then drives off toward its zone (1 m per 10 s)
            if not self.nav.returning:
                self.after = getattr(self, 'after', 0) + 1
                if self.after > 250:
                    ang = math.atan2(-1.7 - self.y, 3.5 - self.x)
                    self.x += .01 * math.cos(ang); self.y += .01 * math.sin(ang)
            return
        row = self.nav.step(b'', {})
        if row is None:
            self.done = True
            return
        wheels, seconds, level = row
        self.rows += 1
        if not any(wheels):
            return
        w = [1 if v > 0 else -1 if v < 0 else 0 for v in wheels]
        if w == [1, 1, 1, 1]: d = U['fwd']; self.x += d * math.cos(self.yaw); self.y += d * math.sin(self.yaw)
        elif w == [-1, -1, -1, -1]: d = U['back']; self.x -= d * math.cos(self.yaw); self.y -= d * math.sin(self.yaw)
        elif w == [-1, 1, -1, 1]: self.yaw += U['left']
        elif w == [1, -1, 1, -1]: self.yaw -= U['left']
        else: raise ValueError(w)


def run(fix, ticks=6000, x_start=2.6, y_start=2.4):
    world = []
    X = Robot('r1', -x_start, 0., 0., False, fix, world)       # outgoing, lower number
    Y = Robot('r2', y_start, 0., math.pi, True, fix, world)     # returning, higher number
    world += [X, Y]
    mind = 9.
    for t in range(ticks):
        X.tick(); Y.tick()
        mind = min(mind, math.hypot(X.x - Y.x, X.y - Y.y))
        if Y.done and (X.done and getattr(X, 'after', 0) > 900):
            break
    return X, Y, mind, t




def meet(fix, out_id, back_id, x_start, y_start):
    world = []
    out = Robot(out_id, -x_start, 0., 0., False, fix, world)            # leaves the box room (x < 0), box in hand
    back = Robot(back_id, y_start, 0., math.pi, True, fix, world)       # comes back from the destination room
    world += [out, back]
    nearest = 9.
    for tick in range(6000):
        out.tick()
        back.tick()
        nearest = min(nearest, math.hypot(out.x - back.x, out.y - back.y))
        if back.done and out.done and getattr(out, 'after', 0) > 900:
            break
    return out, back, nearest


class DoorMeeting(unittest.TestCase):
    def test_both_give_up_without_the_switch(self):
        out, back, _ = meet(False, 'r1', 'r2', 1.5, 1.5)
        self.assertEqual((out.nav.outcome, back.nav.outcome), ('something_stands_beyond_the_door',) * 2)

    def test_the_switch_lets_both_through_in_either_number_order_and_arrival(self):
        for out_id, back_id in (('r1', 'r2'), ('r2', 'r1')):
            for x_start, y_start in ((1.5, 1.5), (2.6, 2.4), (1.5, 2.4), (2.4, 1.5)):
                with self.subTest(out=out_id, back=back_id, start=(x_start, y_start)):
                    out, back, nearest = meet(True, out_id, back_id, x_start, y_start)
                    self.assertEqual((out.nav.outcome, back.nav.outcome), ('through_door', 'through_door'))
                    self.assertGreater(nearest, .30)

    def test_a_parked_lower_number_robot_2_3_m_out_no_longer_holds_the_door_for_90_s(self):
        for fix, yields in ((False, 45), (True, 0)):
            world = []
            mover = Robot('r3', -2.6, 0., 0., False, fix, world)
            parked = Robot('r1', 2.3, 0., 0., False, fix, world)
            parked.done, parked.after = True, -10 ** 9
            world += [mover, parked]
            for tick in range(4000):
                mover.tick()
                if mover.done:
                    break
            self.assertEqual(mover.nav.outcome, 'through_door')
            self.assertEqual(sum(1 for s in mover.nav.steps if s.get('decision') == 'yield_to_robot_at_the_door'), yields, fix)


if __name__ == '__main__':
    unittest.main()
