"""llm_moves_v1: the small moves a planner may choose (--llm-moves, DEFAULT OFF): back off a little, step aside, look around here.

The planner only names the move; the motion is code. This module is pure (no simulator, no camera): it plans a move from the robot's own
pose estimate (the ceiling-camera pose of the runner), the walls and the door the motion code already knows and the boxes the robot
remembers, turns it into wheel rows of the same pulses as the carry (CARRY_PULSE, CARRY_UNIT of the runner, passed in as `kit`) and drives
them one row per tick with a stop in the rows when another robot (measured by the ceiling cameras, as in the yield rules of the runner) is
in the way of the next row. Nothing here is told to the planner except the plain outcome (done / stopped early / no room).

Moves (BACK_M, ASIDE_M are the nominal lengths):
  back  : straight back BACK_M (the 'back' segment of the carry).
  aside : a sideways step of ASIDE_M. mode 'strafe': one mecanum sideways leg (wheel pattern -++- = left, +--+ = right, wheel level 0.35 as every
          carry pulse). The simulated robot has physical 45-degree rollers (sim/masterpi_drive_friction*.py) and the code already strafes in
          it: the approach servo's lateral pulses (harness/approach_survey_v1_parts/approach_core.py:49,58,449; face_align.py:181) are measured
          at 0.35: 10.2 mm per single 0.10 s pulse against 11.1 mm forward; the drive table (harness/drive_table_v1.json) has 422 + 193
          development ticks of -++- / +--+ with +-6 mm per tick sideways, forward 0 and a yaw drift of about 3 mrad per tick against the step.
          mode 'detour': turn 90 degrees, forward ASIDE_M, turn back (units measured with the box held).
  look  : no motion; the runner starts a new look-around where the robot stands.

SIDE_UNIT_M is an ESTIMATE for 39 continuous pulses: the measured 10.2 mm is for single pulses with rest ticks, the carry's measured forward unit
is 13.94 mm in a row against 11.1 mm single, so the same ratio (0.92) gives 12.8 mm. Between the two the step is 0.40-0.50 m; the room check
looks PATH_TOL times farther. Measure it with the box held and not held on the work VM before trusting 'strafe' at the nominal length (MOVES.md).
"""
import math

BACK_M, ASIDE_M = 0.40, 0.50
SIDE_UNIT_M = 0.0128                                   # ESTIMATE, see above
SIDE_WHEELS = {'left': [-1., 1., 1., -1.], 'right': [1., -1., -1., 1.]}
PATH_TOL = 1.3                                         # the clearance is checked along this much more than the nominal length (unit uncertainty)
CLEAR_M, HELD_CLEAR_M, HELD_AHEAD_M = 0.30, 0.22, 0.20  # robot centre to a wall point / remembered box; the held box (0.20 m ahead of the centre) to the same
DOOR_KEEP_M = 0.65                                     # a move does not come nearer to the door centre than this (it would park in the doorway mouth); the door lane and its right of way stay the carry's
STOP_AHEAD_M, STOP_HALF_M, STOP_SPIN_M = 0.55, 0.32, 0.50   # runtime stop: another robot this far ahead in the direction of the next row (half width), or this close to the centre while turning
KINDS = ('back', 'aside', 'look')
MODES = ('strafe', 'detour')
MOTION = {'back': (-1., 0.), 'fwd': (1., 0.), 'side_left': (0., 1.), 'side_right': (0., -1.)}


def _samples(pose, heading, length, step=0.05):
    n = max(1, int(math.ceil(length / step)))
    return [(pose['x'] + length * i / n * math.cos(heading), pose['y'] + length * i / n * math.sin(heading)) for i in range(n + 1)]


def _room(points, foot_heading, obstacles, holding, door_xy):
    """Smallest (clearance - needed) over the path and the footprint (the centre, and the held box 0.20 m ahead of it along `foot_heading`
    when holding); negative = not free. Only a thing the path comes closer to than it started counts (a robot that already stands close
    to a box and moves away from it is not stopped by that box). door_xy: the path may not come nearer to the door centre than DOOR_KEEP_M."""
    foot = [(0., CLEAR_M)] + ([(HELD_AHEAD_M, HELD_CLEAR_M)] if holding else [])
    c, s = math.cos(foot_heading), math.sin(foot_heading)
    room = 9.
    for ahead, need in foot:
        pts = [(x + ahead * c, y + ahead * s) for x, y in points]
        for ox, oy in obstacles:
            d0 = math.hypot(pts[0][0] - ox, pts[0][1] - oy)
            for px, py in pts[1:]:
                d = math.hypot(px - ox, py - oy)
                if d < need and d < d0 - 1e-9:
                    room = min(room, d - need)
    if door_xy is not None:
        d0 = math.hypot(points[0][0] - door_xy[0], points[0][1] - door_xy[1])
        for x, y in points[1:]:
            d = math.hypot(x - door_xy[0], y - door_xy[1])
            if d < DOOR_KEEP_M and d < d0 - 1e-9:
                room = min(room, d - DOOR_KEEP_M)
    return room


def refused(why):
    return {'ok': False, 'why': why}


def plan_move(kind, pose, obstacles, door_xy, kit, *, holding=False, mode='strafe', robots=()):
    """-> {'ok': True, 'kind', 'mode', 'side', 'legs', 'nominal_m', 'slack_m'} or {'ok': False, 'why'}.

    pose {'x','y','yaw'}: the robot's own estimate in the list frame (None: not measured -> refused). obstacles: [(x, y)] wall points and
    remembered boxes in the same frame (the arena the motion code knows and the robot's own look-around list). door_xy: the door centre or None.
    robots: [(x, y)] other robots measured now, used ONLY to pick the side (away from the nearest one) in code; the plan's room check
    never reads them (their positions are not told to the planner either way). holding: the robot holds a box (the box is part of the
    footprint and a turn on the spot needs CARRY_SWEEP_M)."""
    if kind not in ('back', 'aside'):
        raise ValueError('a motion move is back or aside')
    if pose is None:
        return refused('no_measured_pose')
    yaw = pose['yaw']
    if kind == 'back':
        pts = _samples(pose, yaw + math.pi, BACK_M * PATH_TOL)
        room = _room(pts, yaw, obstacles, holding, door_xy)
        if room < 0:
            return refused('no_room_behind')
        return {'ok': True, 'kind': 'back', 'mode': 'back', 'side': None, 'legs': [('back', BACK_M)], 'nominal_m': BACK_M, 'slack_m': round(room, 3)}
    if mode not in MODES:
        raise ValueError('aside mode must be strafe or detour')
    options = []
    for side, turn in (('left', math.pi / 2), ('right', -math.pi / 2)):
        heading = yaw + turn
        pts = _samples(pose, heading, ASIDE_M * PATH_TOL)
        room = _room(pts, heading if mode == 'detour' else yaw, obstacles, holding, door_xy)
        if mode == 'detour':
            # turning on the spot at the start and at the end swings the box (and the body) through a circle: nothing remembered inside CARRY_SWEEP_M
            for cx, cy in (pts[0], pts[-1]):
                room = min(room, min([math.hypot(cx - ox, cy - oy) for ox, oy in obstacles] or [9.]) - kit.CARRY_SWEEP_M)
        if room >= 0:
            options.append((room, side, pts[-1]))
    if not options:
        return refused('no_room_beside')
    best = max(o[0] for o in options)
    near = [o for o in options if best - o[0] < 0.05]
    if len(near) > 1 and robots:
        # a tie in room: step to the side that ends farther from the nearest other robot
        rx, ry = min(robots, key=lambda r: math.hypot(r[0] - pose['x'], r[1] - pose['y']))
        chosen = max(near, key=lambda o: math.hypot(o[2][0] - rx, o[2][1] - ry))
    else:
        chosen = max(near, key=lambda o: (o[0], o[1] == 'left'))
    room, side, _ = chosen
    if mode == 'strafe':
        legs = [('side', side, ASIDE_M)]
    else:
        legs = [(side, 90.), ('fwd', ASIDE_M), ('right' if side == 'left' else 'left', 90.)]
    return {'ok': True, 'kind': 'aside', 'mode': mode, 'side': side, 'legs': legs, 'nominal_m': ASIDE_M, 'slack_m': round(room, 3)}


def build_rows(plan, kit):
    """-> (rows [(wheels, pulse seconds)], tags). Pulses of the carry (kit.CARRY_PULSE) and its gap rows; tags name what a row does."""
    legs = plan['legs']
    gap = kit.CARRY_GAP_ROWS
    if legs[0][0] == 'side':
        n = int(round(legs[0][2] / SIDE_UNIT_M))
        wheels = [kit.CARRY_PULSE[0] * w for w in SIDE_WHEELS[legs[0][1]]]
        return [(wheels, kit.CARRY_PULSE[1])] * n + [([0.] * 4, 0.)] * (2 * gap), ['side_' + legs[0][1]] * n + ['gap'] * (2 * gap)
    rows, segments, _ = kit.carry_rows(','.join('%s:%s' % (k, v) for k, v in legs))
    tags = ['gap'] * len(rows)
    for seg in segments:
        if seg['kind'] in ('fwd', 'back', 'left', 'right'):
            for i in range(seg['first_row'], seg['first_row'] + seg['pulses']):
                tags[i] = seg['kind']
    return rows, tags


def blocked(tag, robots_body):
    """True when another robot (body frame of this robot: +x ahead, +y left) is in the way of a row tagged `tag`."""
    if tag == 'gap':
        return False
    if tag in ('left', 'right'):
        return any(math.hypot(x, y) < STOP_SPIN_M for _, (x, y) in robots_body)
    dx, dy = MOTION[tag]
    return any(-0.05 < x * dx + y * dy < STOP_AHEAD_M and abs(-x * dy + y * dx) < STOP_HALF_M for _, (x, y) in robots_body)


class MoveRun:
    """One move, driven one row per control tick. step() -> (wheels, pulse seconds), or None when the move is over (status set)."""

    def __init__(self, request, plan, rows, tags, at_s):
        self.request, self.plan, self.rows, self.tags, self.at_s = dict(request), plan, rows, tags, at_s
        self.i, self.status, self.reason = 0, None, None

    @classmethod
    def look(cls, request, at_s):
        run = cls(request, {'ok': True, 'kind': 'look', 'mode': 'look', 'side': None, 'legs': [], 'nominal_m': 0., 'slack_m': None}, [], [], at_s)
        return run

    @classmethod
    def refuse(cls, request, why, at_s):
        run = cls(request, {'ok': False, 'why': why}, [], [], at_s)
        run.status, run.reason = 'refused', why
        return run

    def step(self, robots_body=()):
        if self.status is not None:
            return None
        if self.i >= len(self.rows):
            self.status = 'done'
            return None
        tag = self.tags[self.i]
        if blocked(tag, robots_body):
            self.status, self.reason = 'stopped', 'robot_in_the_way'
            return None
        row = self.rows[self.i]
        self.i += 1
        return row

    def record(self):
        plan = self.plan
        out = {'kind': self.request['kind'], 'where': self.request.get('where'), 'status': self.status or 'running', 'reason': self.reason,
               'at_s': round(self.at_s, 1), 'rows_planned': len(self.rows), 'rows_done': self.i, 'motion_rows_planned': sum(1 for t in self.tags if t != 'gap'),
               'motion_rows_done': sum(1 for t in self.tags[:self.i] if t != 'gap')}
        if plan.get('ok'):
            out.update(mode=plan['mode'], side=plan['side'], legs=[list(leg) for leg in plan['legs']], nominal_m=plan['nominal_m'], slack_m=plan['slack_m'])
        return out
