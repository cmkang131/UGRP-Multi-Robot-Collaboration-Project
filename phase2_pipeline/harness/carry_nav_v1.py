"""carry_nav_v1: carry the held box toward the door from memory, look again, line up and drive through.

Tick-driven, DEFAULT OFF (the runner creates it only for --carry-to door / through_door). Inputs: the robot's
own camera frames, its own commanded posture, its own pose estimate at the lift and the place memory built
while it looked around. Nothing from the simulator is read.

Phases
  verify   : when the door is in memory. Arm up, turn to where it should be and look with the far-door rule.
             Seen -> approach what was just seen. Not seen -> search.
  search   : arm up, turn on the spot in 30 degree steps (one full turn), look at each stop with the far-door
             rule and note how far the floor runs ahead. Not found -> go by memory if there is one; otherwise
             move toward the most open direction (at most SEARCH_MOVES times) and search again.
  approach : in two stages, around the things remembered on the floor (one waypoint at most): first to 1.9 m
             from the door, where the close-range rule and a close look at what stands in front of the door are
             possible; then to a stopping point on the door axis (0.90 m preferred) that is clear, with a clear
             straight way through the door. No clear way -> stop there, do not drive blind.
  align    : from what was just seen, move to CARRY_PASS_STANDOFF_M in front of the door centre on the
             door axis, face the door, look again (at most CARRY_PASS_TRIES times).
  pass     : when the straight line ahead crosses the door line close enough to the centre, drive on to
             CARRY_PASS_BEYOND_M past the door line.
  scan     : in the next room, turn in 30 degree steps and note where the paint of the wanted zone colour is.
  zone     : (goal zone_<colour>) go to 0.9 m short of that paint, look again, then stop so that the release
             sets the box down on the paint. Not seen from the door -> side-step look (below), then stop there.
             With zone_confirm_close, a missed close sweep leads to a bounded search from farther back.
             Exhausting it ends the run with the box still gripped at the observation posture.
  side-step: only when both scans of the room found no destination (and the ceiling cameras measure the robots, the walls
             are known): another robot standing in front of the sign hides it (zone_not_seen_from_door, 4 of 135 carries, all
             hidden by a robot parked 0.5-0.6 m in front of the same sign). The wall that stood in the shadow of the robots in
             every look so far is worked out from the known walls and the measured robots; the robot moves 0.8-1.2 m sideways to
             where most of it can be seen and turns once round there. At most SIDESTEP_TRIES times. See plan_sidestep().
  The other outcomes lower the arm back to the hold posture.
  put_down : (planner option 'put the box I am holding down here and finish', asked again before the door is passed) the
             rows still ahead are dropped, the arm is lowered and the carry ends where the robot stands, like every other
             early outcome; the runner's release then sets the box down. The leg through the door is not cut (see put_down()).

  returning: (--multi-carry, goal through_door, nothing held) the way back from the destination room to the box room. The same phases
             as a carry to the door (the arena is known, so the door is the known one), no held check; after the pass the robot
             drives RETURN_EXIT_M further, turning toward return_face (where it remembers boxes) so that it leaves the door lane
             and the zone of the door, and stops ('through_door') instead of looking around for a zone.
  door_yield : (--multi-carry) a robot that is about to move into the zone of the door waits, at the look stop outside it, while another robot
             has the right of way there (door_right_of_way: a robot on the other side that is already in the zone, or a lower-numbered
             robot on the other side that is close to the zone).

The motion rows, the planning arithmetic and the constants are the runner's (passed in as `kit`), so that a
carry by segments and a carry by memory use the same pulses.
"""
import math

import numpy as np

EXTRA_GOALS = frozenset()     # generated map scenes (DEFAULT empty): the runner puts the 'zone_sign<n>' of the scene's own signs here
SEARCH_STEPS = 12
FAR_STOPS_M = (1.9, 1.25)     # look stops on the way: this far from the door centre, wherever the floor is free
# Stopping points on the door axis in order of preference, and whether the door is looked at again from there.
# Closer than 0.75 m both jambs do not fit in the picture, so from 0.60 and 0.50 m the robot drives through on
# the door it saw from the last look stop. Those two exist for rooms where something lies across the axis about
# 0.9 m in front of the door (a bar did in three development scenes) and the free floor is between it and the door.
STANDOFFS_M = ((.90, True), (.80, True), (.75, True), (1.05, True), (1.20, True), (.60, False), (.50, False))
TALL_HALF_M = .30             # a tall thing this close to the door axis is in the way (own half width, its half width, margin)
BEYOND_HALF_M, BEYOND_KEEP_M, BEYOND_MIN_M = .20, .45, .35   # far side of the door: corridor half width, distance kept, least pass
CORRIDOR_CLEAR_M = .18        # half the robot's width (0.12 m) plus a margin, for the straight way through the door
WALL_OPENING_M = .32           # door wall points nearer than this to the door centre are the jambs: the opening
DOOR_CLEAR_DEPTH_M = 1.30
DOOR_BUSY_M, DOOR_WAIT_S, DOOR_WAIT_TRIES = 1.5, 2.0, 20   # another robot this close to the door centre: wait and retry      # with the arena known: camera points this deep in front of the opening are not used
FRAME_DEPTH_M, FRAME_HALF_M = .20, .25   # the door frame: this deep around the door line, this far from its centre
SWEEP_DEG = 40                # at the first look stop: look this far to each side of the door
ZONE_CLOSE_SWEEP = 'left:25,pause:0.8,left:25,pause:0.8,right:75,pause:0.8,right:25,pause:0.8,left:50'
ZONE_RELOOK_TRIES, ZONE_RELOOK_BACK_M = 2, .35
# --door-lane-fix: a robot that stands in the lane beyond the door and has the lower priority (the higher number, as in door_right_of_way) backs away until it is
# this far from the door centre (BEYOND_MIN reaches 1.6 m past the line), at most LANE_BACK_TRIES times per carry
# --zone-close-fix: the first close look of a destination sign is taken this far from the floor point in front of the sign (0.9 m otherwise). Carrying, the camera is
# 0.23 m high and 18 degrees down, so the 0.25 m sign sits at the top edge of the picture and its code is cut off when the robot is nearer than about 1.25 m
# from the sign (SPD-P2_N03_S01 r2: sign 11 seen at 1.3 m, not at 1.19 m); at 1.5 m + 0.32 m + the camera offset the code lies 25 px inside the picture
ZONE_CLOSE_STOP_FIX_M = 1.5
# --zone-close-far: the code is only found reliably while the card's top border (0.255 m high) is inside the picture, i.e. from about 2.1 m on (frames of MC6-P2_N03_S02 r3: found at 2.14 m, lost at 1.7 m with the same view)
ZONE_CLOSE_STOP_FAR_M = 2.3
# ... and a robot of a lower number only has the right of way at the door when it stands within DOOR_BAND_LANE_M (2.6 m without the switch) of the door centre: the robot
# that has set its box down at sign 12 stands 2.3 m from the door on its axis, and every later robot yielded to it for the full 45 x 2 s (SPD-P2_N03_S01 NZC-S: 90 s each)
DOOR_BAND_LANE_M = 2.0
LANE_CLEAR_M, LANE_BACK_TRIES, LANE_WAIT_TRIES = 1.95, 2, 45   # ... and waits up to LANE_WAIT_TRIES x 2 s (90 s; 40 s without the switch) for a robot at / beyond the door
STOP_CLEAR_M = .20            # a stopping point must be this far from everything remembered on the floor
SEARCH_MOVES = 2
PUT_DOWN_AFTER_ROWS = ('pass', 'pass_wait')   # put_down() asked in these phases waits for the rows of the phase (the leg through the door)
HELD_TURN_MIN_DEG, HELD_AT_PICK_M, HELD_AT_PICK_FRAMES = 20., 0.30, 2   # held check, second look: turn toward the pick point
HELD_BACK_M, HELD_NEAR_X, HELD_NEAR_Y = 0.40, (0.05, 0.95), 0.45   # held check: back off, then a box of the held colour this close ahead = not held
# The back-off stops short of a known wall behind the robot (arena known): the rear edge of the base is 0.092 m behind its centre
# (base stopped at x -0.933 against the wall face at -1.025, baseline L2-07 r1), the wall boxes are 0.025 m half thick (wall points lie on
# the centre line), plus a margin. Backing the full 0.40 m into the wall pushed the base against it with the wheels still driving, and the
# held box fell out of the gripper (L2-07 r1: base 0.26 m from contact, box in the picture at tick 1030, gone at 1068).
HELD_REAR_M, HELD_WALL_HALF_M, HELD_WALL_MARGIN_M, HELD_BACK_HALF_M, HELD_BACK_SKIP_M = 0.092, 0.025, 0.03, 0.15, 0.05
# (0.20 m was too little: team-v15 D01 r2 missed the grasp and the box lay 0.26 m ahead after backing off, below the
# bottom edge of the picture with the arm at 'far', so the check read 'held' and the robot carried nothing)
NARROW_GAIN_M = 0.8          # an opening this much longer than both neighbours is treated as a likely doorway
DOOR_AGREE_M = 0.40          # with a measured pose, a new door sighting must lie this close to the known door
SEARCH_MOVE_M = (.3, 1.0)     # move 40 % of the open distance, within these limits
# --multi-carry (DEFAULT off: every attribute below is None / False and no rule changes)
RETURN_EXIT_M = 1.3           # after the pass of the way back: drive this far on, toward return_face (leaves the door lane and its zone)
RETURN_STAND_CLEAR_M = 0.5    # ... and stop at least this far from every box it remembers
DOOR_ZONE_M, DOOR_BAND_M = 1.5, 2.6   # door_right_of_way: a robot this close to the door centre is using the door; this close, a lower number goes first
YIELD_WAIT_S, YIELD_TRIES = 2.0, 45   # a yielding robot looks again every 2 s, at most 45 times (90 s), then goes on as before


def door_right_of_way(my_id, my_xy, door_xy, normal, others, zone_m=DOOR_ZONE_M, band_m=DOOR_BAND_M):
    """True when robot `my_id` at `my_xy` should wait before moving into the zone of the door because another robot has the right of way.

    Meetings at the door from opposite sides (one robot carries out while the other comes back) ended with both robots at their 0.9 m
    stopping points, each one the obstacle beyond the door of the other (_beyond_door), and both gave up after DOOR_WAIT_TRIES. The rule
    is the same for every structure (motion code, ceiling-camera positions of the robots and the door, nothing from the planner):
      * a robot that is already using the door keeps it: another robot on the OTHER side that is within `zone_m` of the door centre (or in
        the doorway itself) has the right of way, whatever its number;
      * otherwise the lower number goes first: a robot of a lower number on the OTHER side within `band_m` of the door centre has it
        (both robots stand at their look stops, neither is in the zone yet; the higher number waits).
    Robots on my own side never count (their order is the planner's door question, as before). others: {robot id: (x, y)}, positions
    measured now, in the same frame as door_xy; normal: unit vector of the door line's normal, any of the two directions."""
    nx, ny = normal
    mine = (my_xy[0] - door_xy[0]) * nx + (my_xy[1] - door_xy[1]) * ny
    for other, xy in others.items():
        if other == my_id:
            continue
        d = math.hypot(xy[0] - door_xy[0], xy[1] - door_xy[1])
        front = (xy[0] - door_xy[0]) * nx + (xy[1] - door_xy[1]) * ny
        opposite = front * mine < 0 or abs(front) < .15
        if not opposite:
            continue
        if d < zone_m or (d < band_m and other < my_id):
            return True
    return False

# Side-step look after a destination not seen from the door (see plan_sidestep). Only what the motion code may use: the own pose,
# the robots measured by the ceiling cameras and the known walls; the place of the sign is not an input.
SIDESTEP_M = (.8, 1.0, 1.2)       # distances tried, shortest first
SIDESTEP_TRIES = 3                # side-steps per carry
SIDESTEP_VIEW_M = 5.             # farthest a sign is read (the memory refuses a reading beyond 6 m; one metre of margin)
SIDESTEP_ROBOT_R_M = .15          # another robot hides what lies behind a disc of this radius (body 0.24 x 0.17 m)
SIDESTEP_WALL_BLOCK_M, SIDESTEP_WALL_SKIP_M = .07, .12   # a wall point this near the line of sight, this much in front of the target, hides it
SIDESTEP_WALL_CLEAR_M = .35       # the spot: from wall points (the turn on the spot swings the held box through 0.23 m, wall half thickness 0.025)
SIDESTEP_PATH_WALL_M = .26        # the way there: from wall points (carry_route's clearance)
SIDESTEP_ROBOT_CLEAR_M, SIDESTEP_PATH_ROBOT_M = .50, .40  # the spot / the way: from the centres of other robots
SIDESTEP_DOOR_M = 1.0             # the spot: from the door centre (the next robot passes there)
SIDESTEP_START_SKIP_M = .15       # obstacles this close to the start of the way do not count (as in carry_route)
SIDESTEP_LINK_M, SIDESTEP_MIN_CLUSTER = .35, 2   # hidden wall points closer than this belong together; fewer than this is noise (0.1 m apart)
SIDESTEP_MIN_REVEAL, SIDESTEP_NEAR_BEST = 2, .9   # a spot must show this many hidden points; shortest spot within this share of the best one


# -- side-step geometry (pure functions: plain numbers in, plain numbers out) ---------------------------------------------

def _xy(points):
    return np.array([[q[0], q[1]] for q in points], float).reshape(-1, 2)


def sight_masks(eye, points, walls, robots, view_m=SIDESTEP_VIEW_M, robot_r=SIDESTEP_ROBOT_R_M):
    """What a camera at `eye` (x, y) can see among `points` (wall points): (geometric, clear) boolean arrays.
    geometric: within view_m and no wall point in between (also a wall seen at a grazing angle is not seen: its own nearer points
    lie on the line of sight). clear: geometric and no other robot (a disc of robot_r around each (x, y) of `robots`) in between.
    Walls and robots are lists of points; a robot standing on the eye itself is the camera's own body and does not count."""
    P, W, e = _xy(points), _xy(walls), np.asarray(eye[:2], float)
    d = P - e
    dist = np.hypot(d[:, 0], d[:, 1])
    u = d / np.maximum(dist, 1e-9)[:, None]
    geometric = (dist <= view_m) & (dist > .05)
    if len(W) and len(P):
        w = W - e
        t = u[:, 0:1] * w[None, :, 0] + u[:, 1:2] * w[None, :, 1]
        perp = np.abs(u[:, 0:1] * w[None, :, 1] - u[:, 1:2] * w[None, :, 0])
        geometric &= ~((t > 0.) & (t < dist[:, None] - SIDESTEP_WALL_SKIP_M) & (perp < SIDESTEP_WALL_BLOCK_M)).any(axis=1)
    clear = geometric.copy()
    for rx, ry in robots:
        rel = np.array([rx, ry], float) - e
        if np.hypot(rel[0], rel[1]) <= robot_r + .05:
            continue
        t = u[:, 0] * rel[0] + u[:, 1] * rel[1]
        perp = np.abs(u[:, 0] * rel[1] - u[:, 1] * rel[0])
        clear &= ~((t > 0.) & (t < dist) & (perp < robot_r))
    return geometric, clear


def shadowed_wall_points(eyes, walls, robots):
    """Wall points that could be seen from at least one of the places the robot has looked from (the eyes) but, because of
    another robot in between, were seen from none of them. (n, 2) array. These are the places a sign can still be."""
    W = _xy(walls)
    geometric_any, seen_any = np.zeros(len(W), bool), np.zeros(len(W), bool)
    for eye in eyes:
        geometric, clear = sight_masks(eye, W, W, robots)
        geometric_any |= geometric
        seen_any |= clear
    return W[geometric_any & ~seen_any]


def cluster_points(points, link_m=SIDESTEP_LINK_M):
    """Single-linkage groups of points closer than link_m: a list of index lists."""
    P, left, groups = _xy(points), set(range(len(points))), []
    while left:
        todo, group = [left.pop()], []
        while todo:
            i = todo.pop()
            group.append(i)
            near = [j for j in left if np.hypot(*(P[i] - P[j])) < link_m]
            left -= set(near)
            todo += near
        groups.append(sorted(group))
    return sorted(groups, key=lambda g: g[0])


def path_gap(a, b, points, start_skip=SIDESTEP_START_SKIP_M):
    """Least distance from the segment a-b to the points whose nearest place on the segment is farther than start_skip from a."""
    P = _xy(points)
    if not len(P):
        return 9.
    a, b = np.asarray(a[:2], float), np.asarray(b[:2], float)
    ab = b - a
    length = float(np.hypot(*ab))
    u = ab / max(length, 1e-9)
    rel = P - a
    along = np.clip(rel @ u, 0., length)
    gap = np.hypot(rel[:, 0] - along * u[0], rel[:, 1] - along * u[1])
    gap = gap[along > start_skip]
    return float(gap.min()) if len(gap) else 9.


def plan_sidestep(pose, eyes, walls, robots, door=None):
    """Where to look from after the destination was not seen from the door: (choice, facts); choice None when nothing helps.

    pose: own {'x','y'}; eyes: [(x, y)] the places looked from so far; walls: known wall points; robots: [(x, y)] of the other
    robots now; door: (x, y) of the door centre. The wall in the shadow of the robots in every look so far (shadowed_wall_points)
    is where a sign can still be. Across the line from the robot to each group of such points the robot steps SIDESTEP_M metres
    to either side; a spot counts when the way and the spot are clear of walls, robots and the doorway, and it shows
    SIDESTEP_MIN_REVEAL hidden points or more. The shortest spot that shows at least SIDESTEP_NEAR_BEST of the most any spot shows
    is chosen; of equal ones the one farther from the other robots. The sign's own place is never an input."""
    p = np.array([pose['x'], pose['y']], float)
    W, R = _xy(walls), _xy(robots)
    hidden = shadowed_wall_points(eyes, walls, robots)
    groups = [g for g in cluster_points(hidden) if len(g) >= SIDESTEP_MIN_CLUSTER] if len(hidden) else []
    facts = {'hidden_points': int(len(hidden)), 'groups': [], 'candidates': []}
    angles = []
    for g in groups:
        centre = hidden[g].mean(axis=0)
        bearing = math.atan2(centre[1] - p[1], centre[0] - p[0])
        facts['groups'].append({'points': len(g), 'centre': [round(float(centre[0]), 2), round(float(centre[1]), 2)]})
        for side in (-1, 1):
            a = math.atan2(math.sin(bearing + side * math.pi / 2), math.cos(bearing + side * math.pi / 2))
            if all(abs(math.atan2(math.sin(a - b), math.cos(a - b))) > math.radians(10) for b in angles):
                angles.append(a)
    options = []
    for a in angles:
        for dist in SIDESTEP_M:
            target = p + dist * np.array([math.cos(a), math.sin(a)])
            why, robot_gap = None, float(np.hypot(*(R - target).T).min()) if len(R) else 9.
            if door is not None and math.hypot(target[0] - door[0], target[1] - door[1]) < SIDESTEP_DOOR_M:
                why = 'door'
            elif len(W) and float(np.hypot(*(W - target).T).min()) < SIDESTEP_WALL_CLEAR_M:
                why = 'wall'
            elif robot_gap < SIDESTEP_ROBOT_CLEAR_M:
                why = 'robot'
            elif path_gap(p, target, W) < SIDESTEP_PATH_WALL_M:
                why = 'wall_in_the_way'
            elif path_gap(p, target, R) < SIDESTEP_PATH_ROBOT_M:
                why = 'robot_in_the_way'
            revealed = 0 if why else int(sight_masks(target, hidden, W, [tuple(r) for r in R])[1].sum())
            option = {'dir_deg': round(math.degrees(a), 1), 'dist_m': dist, 'target': [round(float(target[0]), 3), round(float(target[1]), 3)],
                      'revealed': revealed, 'rejected': why, 'robot_gap_m': round(robot_gap, 2)}
            options.append(option)
            facts['candidates'].append(option)
    usable = [o for o in options if o['rejected'] is None and o['revealed'] >= SIDESTEP_MIN_REVEAL]
    if not usable:
        return None, facts
    best = max(o['revealed'] for o in usable)
    near_best = [o for o in usable if o['revealed'] >= SIDESTEP_NEAR_BEST * best]
    choice = min(near_best, key=lambda o: (o['dist_m'], -o['robot_gap_m'], options.index(o)))
    return choice, facts


class CarryNav:
    def __init__(self, kit, places, own, others, goal, held_kind=None, picked=None, told=None, *, zone_confirm_close=False, zone_close_fix=False, zone_close_far=False):
        if goal not in ('door', 'through_door', 'zone_orange', 'zone_blue', 'zone_purple', 'zone_sign11', 'zone_sign12', 'zone_sign13') \
                and goal not in EXTRA_GOALS:
            raise ValueError('goal must be door, through_door or zone_<orange|blue|purple>')
        self.kit, self.places, self.goal, self.held_kind = kit, places, goal, held_kind
        self.colour = goal[5:] if goal.startswith('zone_') else None
        self.zone_seen = {}
        self.zone_confirm_close, self.zone_close_fix, self.zone_close_far = zone_confirm_close, bool(zone_close_fix), bool(zone_close_far)
        self.close_look = 'zone_close' if zone_confirm_close else 'zone_look'
        if zone_confirm_close:
            # every close reading of the destination sign with its rejection reason goes to the record; --zone-close-fix accepts a card whose top border is cut off
            places.close_reads, places.close_fix, places.close_far = [], bool(zone_close_fix), bool(zone_close_far)
        self.zone_retries = 0
        self.picked = picked
        self.told = told          # {'forward_m', 'left_m'} of the wanted zone from the door, as told by another robot
        self.start = [own['x'], own['y']]
        self.open, self.moves, self.searches, self.far_stops = [], 0, 0, 0
        self.seen_close, self.blind_m, self.tall_seen, self.swept = False, None, None, False
        self.far_searched = False
        # measured own pose and other robots (ceiling cameras), DEFAULT None: callables returning the own pose
        # {'x','y','yaw'} and a list of (x, y) of the other robots, both in the list frame, or None when not measured
        self.pose_source, self.others_source = None, None
        # held check (DEFAULT off): back off a little before carrying and look whether the box still lies on the floor
        # just ahead. A box left there means the grasp failed (the colour along the picture's bottom edge could not
        # tell: a held blue box sat out of view as often as an empty gripper showed nothing)
        self.check_held, self.held_frames, self.held_result = False, [], None
        # held check, lens-edge fix (DEFAULT off; place_memory_v1.HELD_EDGE_PX): blobs that lie along the lens border are the box in the gripper
        self.held_edge_fix, self.held_edge_excluded = False, []
        # --sign-scan-early-stop (DEFAULT off): the sweep for a destination sign ends at the first look window after which the sign is in the
        # place memory (place_memory_v1.zone: 30 points = one sighting), instead of always turning the full 12 x 30 degrees
        self.sign_scan_early_stop = False
        # --door-lane-fix (DEFAULT off): see _yield_door_lane
        self.door_lane_fix, self.lane_backs = False, 0
        # arena shape given to the motion code (user decision 2026-11-15): the door and wall points in the list frame
        self.known_door, self.known_walls, self.known_zone = None, [], None
        self.pose = dict(own)                # own estimate in the list frame, updated with nominal pulse lengths
        self.others = list(others)
        self.rows, self.arm, self.segments, self.looks = [], [], [], []
        self.i = 0
        self.phase, self.outcome, self.finished = 'start', None, False
        self.put_down_requested = False
        # --multi-carry (DEFAULT off): the way back (returning), where it looks next (return_face, list frame), the door right of way
        # (right_of_way_source() -> (own id, {other id: (x, y)}) measured now, list frame) and how often the robot has waited for it
        self.returning, self.return_face, self.right_of_way_source, self.yield_tries = False, None, None, 0
        self.tries, self.reseeks, self.steps, self.log = 0, 0, [], []
        self.door = places.door('look_around')
        self.door_remembered = self.door

    # -- helpers ---------------------------------------------------------------------------------------

    def _zone(self, phase):
        """The destination: known (a wall sign given to the motion code) or as seen with the own camera."""
        if self.zone_confirm_close and phase == self.close_look:
            point = self.places.zone(self.colour, phase)
            if point and point['kind'] == self.goal and all(math.isfinite(point[k]) for k in ('x', 'y')):
                return point
            return None
        if self.known_zone is not None:
            return dict(self.known_zone)
        return self.places.zone(self.colour, phase)

    def _zone_stop_m(self):
        """How far in front of the remembered floor point the robot stops to look at the destination again."""
        if self.zone_confirm_close and self.zone_close_fix:
            return ZONE_CLOSE_STOP_FAR_M if self.zone_close_far else ZONE_CLOSE_STOP_FIX_M
        return .9

    def set_arena(self, door, walls):
        """door: {'x','y','left','right','width_m'}; walls: [(x, y)] points along the walls, both in the list frame."""
        self.known_door = dict(door, kind='door', observations=0)
        self.known_walls = [(x, y, 0.) for x, y in walls]
        self.door = self.door_remembered = dict(self.known_door)

    def set_destination(self, point):
        """The floor point in front of the chosen wall sign, list frame (a fixed fact of the arena, motion code only)."""
        self.known_zone = {'kind': 'zone_' + (self.colour or ''), 'x': point[0], 'y': point[1], 'points': 0, 'source': 'arena'}
    def _extend(self, spec, looks=()):
        """Append the rows of a segment spec. looks: (pause ordinal within the spec, phase name, near)."""
        level = self.arm[-1] if self.arm else 0.
        rows, segs, arm = self.kit.carry_rows(spec, level=level)
        base = len(self.rows)
        pauses = [n for n, g in enumerate(segs) if g['kind'] == 'pause']
        for ordinal, name, near in looks:
            n = pauses[ordinal]
            g = segs[n]
            self.looks.append({'rows': [base + g['first_row'] + 5, base + g['first_row'] + g['rows']],
                               'pose': self.kit.carry_nominal_pose(self.pose, segs[:n]), 'phase': name, 'near': near,
                               'what': 'held' if name == 'held_look' else 'zone' if name.startswith('zone') else 'door'})
        for g in segs:
            g['first_row'] += base
        self.rows += rows
        self.arm += arm
        self.segments += segs
        self.pose = self.kit.carry_nominal_pose(self.pose, segs)
        self.log.append({'phase': self.phase, 'spec': spec, 'rows': len(rows), 'pose_after': dict(self.pose)})

    def _search(self):
        self.searches += 1
        self.open = []
        self.phase = 'search'
        _, n_back = self._back_out(self._around())
        prefix = ('' if self.arm and self.arm[-1] == 1. else 'arm:far,') + ('back:%dp,' % n_back if n_back else '')
        self._extend(prefix + ','.join(['left:30,pause:0.8'] * SEARCH_STEPS),
                     looks=[(n, 'search_%d' % self.searches, False) for n in range(SEARCH_STEPS)])

    def _stop(self, outcome):
        self.phase, self.outcome = 'lower', outcome
        self._extend('arm:hold')

    def put_down(self):
        """The planner chose to set the held box down where the robot stands (re-decision before the door is passed).
        The rows still ahead are dropped (and the look windows that lay in them), then the carry stops like any other
        early outcome (_stop: arm to the hold posture, finished); the runner's release replay sets the box down. The leg
        through the door ('pass', 'pass_wait') is not cut half-way (the robot would stand in the doorway): the stop comes
        when its rows are used up. False when the carry is already ending or put_down was asked before."""
        if self.finished or self.phase in ('lower', 'done') or self.put_down_requested:
            return False
        self.put_down_requested = True
        self.steps.append({'decision': 'put_down_requested', 'phase': self.phase, 'row': self.i, 'rows_planned': len(self.rows)})
        if self.phase in PUT_DOWN_AFTER_ROWS:
            return True
        del self.rows[self.i:], self.arm[self.i:]
        self.looks = [look for look in self.looks if look['rows'][1] <= self.i]
        self._stop('put_down')
        return True

    def _reanchor(self, seen, turn_only=False, phase=None, look_yaw=None):
        """Put the own pose back in step with the memory, from a door just seen from where the robot stands.

        The things remembered on the floor are in the frame of the look-around; the own pose in that frame comes
        from the drive record and can be off by tens of degrees (one development run kept touching a bar because
        the door, seen afresh, and the bar, remembered, were 0.3-0.4 m apart in the robot's own picture). The
        remembered door is the anchor: from the pickup spot only the heading is corrected (the bearing of the
        door), closer to the door the position is shifted so that the seen door centre lies on the remembered one.
        The orientation of the door stays the one just seen. Returns the door to use, in the corrected frame.
        """
        mem = self.door_remembered
        if mem is None:
            return seen                     # found by searching: nothing to anchor to
        if self.pose_source is not None and self.pose_source() is not None:
            # the own pose is measured: the door as seen from the measured pose stands where it is
            self.steps.append({'decision': 'reanchor_not_needed', 'pose': 'measured'})
            return seen
        p = self.pose
        # look_yaw: the heading the door was seen from, when that was a sideways look and not the present heading
        seen_yaw = p['yaw'] if look_yaw is None else look_yaw
        c, s = math.cos(seen_yaw), math.sin(seen_yaw)

        def body(pt):
            dx, dy = pt[0] - p['x'], pt[1] - p['y']
            return dx * c + dy * s, -dx * s + dy * c
        left, right = body(seen['left']), body(seen['right'])
        cx, cy = .5 * (left[0] + right[0]), .5 * (left[1] + right[1])
        before = dict(p)
        if turn_only:
            turn = math.atan2(mem['y'] - p['y'], mem['x'] - p['x']) - math.atan2(cy, cx) - seen_yaw
            p['yaw'] = math.atan2(math.sin(p['yaw'] + turn), math.cos(p['yaw'] + turn))
            seen_yaw += turn
        c, s = math.cos(seen_yaw), math.sin(seen_yaw)
        if not turn_only:
            p['x'], p['y'] = mem['x'] - (c * cx - s * cy), mem['y'] - (s * cx + c * cy)

        def lst(pt):
            return [p['x'] + c * pt[0] - s * pt[1], p['y'] + s * pt[0] + c * pt[1]]
        door = dict(seen, left=lst(left), right=lst(right))
        door['x'], door['y'] = .5 * (door['left'][0] + door['right'][0]), .5 * (door['left'][1] + door['right'][1])
        if phase is not None and hasattr(self.places, 'rebase'):
            self.places.rebase(phase, before, p)    # what this look put into the memory moves with the correction
        shift = math.hypot(p['x'] - before['x'], p['y'] - before['y'])
        turn = abs(math.atan2(math.sin(p['yaw'] - before['yaw']), math.cos(p['yaw'] - before['yaw'])))
        if (shift > .30 or turn > math.radians(20)) and hasattr(self.places, 'forget_looks'):
            # The pose was far off, so everything the earlier carry looks remembered stands in the wrong place (one
            # run kept three such points 0.6 m in front of the door and found no place to stand). Keep the first
            # look-around and this look; look beside the door again.
            gone = self.places.forget_looks(('look_around', phase))
            self.swept = False
            self.steps.append({'decision': 'forgot_looks_taken_with_a_wrong_pose', 'points': gone})
        self.steps.append({'decision': 'reanchor', 'turn_only': turn_only,
                           'shift_m': math.hypot(p['x'] - before['x'], p['y'] - before['y']),
                           'turn_deg': math.degrees(math.atan2(math.sin(p['yaw'] - before['yaw']), math.cos(p['yaw'] - before['yaw'])))})
        return door

    def _consistent(self, seen):
        """With a measured own pose, a door seen far from the door already known is a false one (one run took a wall
        corner 1.2 m off for the door and drove to it). Keep the known door; return None for such a sighting."""
        if self.known_door is not None:
            return dict(self.known_door)    # the door is known: every look at it "sees" the known door
        if seen is None or self.door is None or self.pose_source is None or self.pose_source() is None:
            return seen
        gap = math.hypot(seen['x'] - self.door['x'], seen['y'] - self.door['y'])
        if gap > DOOR_AGREE_M:
            self.steps.append({'decision': 'door_sighting_rejected', 'gap_m': round(gap, 2)})
            return None
        return seen

    def _others_now(self):
        """Other robots measured now, as a ring of points around each (their body is about 0.24 x 0.17 m)."""
        if self.others_source is None:
            return []
        pts = []
        for x, y in (self.others_source() or []):
            pts += [(x + .10 * math.cos(a), y + .10 * math.sin(a), 0.) for a in [k * math.pi / 4 for k in range(8)]] + [(x, y, 0.)]
        return pts

    def _around(self):
        """Everything remembered near the robot, whichever side of the door: things, listed boxes, wall points."""
        seen = (list(self.places.obstacles.values()) + [(o[0], o[1], 0.) for o in self.others]
                + (self.known_walls if self.known_walls else list(getattr(self.places, 'walls', {}).values()))
                + self._others_now())
        return [q for q in seen if math.hypot(q[0] - self.pose['x'], q[1] - self.pose['y']) < 1.2
                and (self.picked is None or math.hypot(q[0] - self.picked[0], q[1] - self.picked[1]) > .15)]

    def _door_side(self):
        """Door normal pointing to the robot's side, and the remembered things on that side (not the carried box)."""
        door = self.door
        tx, ty = door['right'][0] - door['left'][0], door['right'][1] - door['left'][1]
        n = math.hypot(tx, ty)
        nx, ny = -ty / n, tx / n
        if nx * (self.start[0] - door['x']) + ny * (self.start[1] - door['y']) < 0:
            nx, ny = -nx, -ny
        # the listed boxes are things on the floor as well, whatever the blob rule made of them
        camera = list(self.places.obstacles.values())
        if self.known_walls:
            # The arena is known (static map) and the pose is measured: the straight way through the door is free in
            # the map, so remembered camera points inside that corridor are dropped (stale or misread marks), the way
            # a costmap's static layer plus a clearing obstacle layer does it (ROS Nav2). Other robots (ceiling
            # camera, now) and the listed boxes still count. team-v10 90721 r2: one camera point 0.34 m in front of
            # the door centre, where nothing stood, ruled out every stopping point (no_clear_way_to_door)
            def in_corridor(q):
                front = (q[0] - door['x']) * nx + (q[1] - door['y']) * ny
                return -.10 < front < DOOR_CLEAR_DEPTH_M and abs(-(q[0] - door['x']) * ny + (q[1] - door['y']) * nx) < WALL_OPENING_M
            camera = [q for q in camera if not in_corridor(q)]
        seen = camera + [(o[0], o[1], 0.) for o in self.others] + self._others_now()
        obstacles = [q for q in seen
                     if (q[0] - door['x']) * nx + (q[1] - door['y']) * ny > .10
                     and (self.picked is None or math.hypot(q[0] - self.picked[0], q[1] - self.picked[1]) > .15)]
        # the walls seen so far, as sparse points: everything on this side, and the door wall itself outside the
        # opening (WALL_OPENING_M to each side of the door centre stays free)
        # with the arena known, the known walls replace the walls read from the own camera (team-v11 90721 r2: a
        # camera wall point 0.34 m in front of the door centre still blocked the way after the camera obstacle points
        # there were dropped)
        walls = self.known_walls if self.known_walls else list(getattr(self.places, 'walls', {}).values())
        for q in walls:
            front = (q[0] - door['x']) * nx + (q[1] - door['y']) * ny
            lateral = abs(-(q[0] - door['x']) * ny + (q[1] - door['y']) * nx)
            if front > .10 or (front > -.10 and lateral > WALL_OPENING_M):
                obstacles.append(q)
        if self.seen_close:
            # The door was just seen from close by as an opening with floor behind it, so nothing stands in the
            # frame itself. A remembered point there is a jamb read a little short (one run: a single point
            # 0.13 m in front of the door line, 0.16 m from the centre, ruled out every stopping point).
            def in_frame(q):
                front = (q[0] - door['x']) * nx + (q[1] - door['y']) * ny
                lateral = abs(-(q[0] - door['x']) * ny + (q[1] - door['y']) * nx)
                return abs(front) < FRAME_DEPTH_M and lateral < FRAME_HALF_M
            obstacles = [q for q in obstacles if not in_frame(q)]
        return nx, ny, obstacles

    def _beyond_door(self):
        """How far past the door line the straight way is free: things seen standing within BEYOND_HALF_M of the
        door axis on the far side (another robot stood 0.62 m behind the door in one development scene). Zone
        paint lies farther from the axis than that in this arena."""
        door = self.door
        nx, ny, _ = self._door_side()
        fx, fy = -nx, -ny
        ahead = []
        if self.known_walls and self.others_source is not None and self.others_source() is not None:
            # arena known and robots measured now: only another robot can stand beyond the door, and its current
            # place is known; remembered camera points there are stale (LLM X01: r2 gave up at the door because of
            # points left where r1 had stood before it moved on)
            self.tall_seen, self.beyond_robot = None, False
            for x, y in self.others_source():
                forward = (x - door['x']) * fx + (y - door['y']) * fy
                lateral = abs(-(x - door['x']) * fy + (y - door['y']) * fx)
                if -.2 < forward < 1.6 and lateral < BEYOND_HALF_M + .15:
                    ahead.append(forward - .15)
                    self.beyond_robot = True
            return (min(ahead) - BEYOND_KEEP_M) if ahead else None
        for q in self.places.obstacles.values():
            forward = (q[0] - door['x']) * fx + (q[1] - door['y']) * fy
            lateral = abs(-(q[0] - door['x']) * fy + (q[1] - door['y']) * fx)
            if .05 < forward < 1.6 and lateral < BEYOND_HALF_M and q[2] < 2.5:
                ahead.append(forward)
        tall = self.places.tall_thing_beyond_door()
        self.tall_seen = tall
        if tall is not None and abs(tall['lateral_m']) < TALL_HALF_M:
            ahead.append(tall['beyond_m'])      # something as tall as the camera (another robot) on the way
        return (min(ahead) - BEYOND_KEEP_M) if ahead else None

    def _return_exit(self):
        """The way back, after the pass: leave the door lane and its zone. The robot drives RETURN_EXIT_M toward return_face (the middle of
        the boxes it remembers, list frame; along the door axis without it), or the first of a few other directions when that way is not
        clear of the boxes it remembers (self.others besides the box it set down) or ends close to one, and turns to face return_face so
        that the look-around that follows starts there. The target must lie out of the zone of the door (DOOR_ZONE_M)."""
        k, door, pose = self.kit, self.door, self.pose
        nx, ny, _ = self._door_side()
        face = self.return_face
        axis = math.atan2(-ny, -nx)                                # straight on, along the door axis into the box room
        base = math.atan2(face[1] - pose['y'], face[0] - pose['x']) if face is not None and math.hypot(face[0] - pose['x'], face[1] - pose['y']) > .3 else axis
        things = [(o[0], o[1], 0.) for o in self.others] + list(self.places.obstacles.values())
        if self.door_lane_fix:
            things += self._others_now()        # a robot that backed away from the door lane waits on the axis the way back leaves along
        chosen, tried = None, []
        for turn in (0., .52, -.52, 1.05, -1.05, 1.57, -1.57):    # 0, +-30, +-60, +-90 degrees off the first choice
            bearing = base + turn
            target = [pose['x'] + RETURN_EXIT_M * math.cos(bearing), pose['y'] + RETURN_EXIT_M * math.sin(bearing)]
            out_of_zone = math.hypot(target[0] - door['x'], target[1] - door['y']) >= DOOR_ZONE_M + .1
            way, straight = k.carry_route([pose['x'], pose['y']], target, things)
            room = k.carry_point_clearance(target, things)
            tried.append({'turn_deg': round(math.degrees(turn)), 'out_of_zone': out_of_zone, 'straight': bool(straight and not way), 'clearance_m': round(room, 2)})
            if out_of_zone and straight and not way and room >= RETURN_STAND_CLEAR_M:
                chosen = target
                break
        fallback = chosen is None
        if fallback:
            chosen = [pose['x'] + RETURN_EXIT_M * math.cos(axis), pose['y'] + RETURN_EXIT_M * math.sin(axis)]
        plan = k.carry_to_plan(pose, chosen, [], stop_m=0., face=face)
        self.phase = 'return_exit'
        self.steps.append({'decision': 'return_exit', 'target': chosen, 'face': face, 'spec': plan['spec'], 'tried': tried, 'fallback_axis': fallback})
        return self._extend(plan['spec'].replace('back:0p,', ''))

    def _door_wait_tries(self):
        return LANE_WAIT_TRIES if self.door_lane_fix else DOOR_WAIT_TRIES

    def _yield_door_lane(self):
        """--door-lane-fix: two robots met at the door, each on its stopping point 0.9 m from the centre on the axis, each the obstacle beyond the door of the
        other (the gap to the minimum pass was 3 mm: SPD-P2_N03_S01 R run, r1 out and r2 back). Both waited DOOR_WAIT_TRIES times and gave up, one of them
        for good in the lane. The robot with the higher number (the one door_right_of_way makes yield first) backs straight away from the door until it is
        LANE_CLEAR_M from the centre, where it no longer counts as beyond the door; the other passes. True when rows were planned."""
        if not self.door_lane_fix or self.lane_backs >= LANE_BACK_TRIES or self.right_of_way_source is None:
            return False
        who = self.right_of_way_source()
        if who is None:
            return False
        my_id, others = who
        door = self.door
        nx, ny, _ = self._door_side()
        fx, fy = -nx, -ny
        blockers = [r for r, (x, y) in others.items() if r != my_id
                    and -.2 < (x - door['x']) * fx + (y - door['y']) * fy < 1.6
                    and abs(-(x - door['x']) * fy + (y - door['y']) * fx) < BEYOND_HALF_M + .15]
        if not blockers or not any(r < my_id for r in blockers):
            return False                      # the robot beyond the door has the lower number: it backs away, this one waits as before
        k, p = self.kit, self.pose
        dist = math.hypot(p['x'] - door['x'], p['y'] - door['y'])
        unit = k.CARRY_UNIT['back']
        c, s_ = math.cos(p['yaw']), math.sin(p['yaw'])
        things = (list(self.places.obstacles.values()) + [(o[0], o[1], 0.) for o in self.others]
                  + (list(self.known_walls) if self.known_walls else list(getattr(self.places, 'walls', {}).values())) + self._others_now())
        things = [q for q in things if self.picked is None or math.hypot(q[0] - self.picked[0], q[1] - self.picked[1]) > .15]
        for back in (LANE_CLEAR_M - dist, .8, .6, .4):
            pulses = int(min(max(back, 0.), 1.2) / unit)
            if pulses < 10:
                continue
            xy = [p['x'] - pulses * unit * c, p['y'] - pulses * unit * s_]
            if path_gap((p['x'], p['y']), xy, things, start_skip=0.) >= k.CARRY_BODY_M and k.carry_point_clearance(xy, things) >= k.CARRY_SWEEP_M:
                self.lane_backs += 1
                self.phase, self.yield_look = 'door_yield', 'at_door_1'
                self.far_stops = len(FAR_STOPS_M)
                self.steps.append({'decision': 'door_lane_back_off', 'try': self.lane_backs, 'blockers': sorted(blockers), 'from_door_m': round(dist, 2),
                                   'pulses': pulses, 'view_xy': xy})
                self._extend('back:%dp,pause:%.1f' % (pulses, YIELD_WAIT_S))
                return True
        self.steps.append({'decision': 'door_lane_no_room', 'blockers': sorted(blockers), 'from_door_m': round(dist, 2)})
        return False

    def _pass(self, reach):
        """Drive through: reach metres to the door line, then as far beyond as is free (at most the usual)."""
        k = self.kit
        free = self._beyond_door()
        beyond = k.CARRY_PASS_BEYOND_M if free is None else min(k.CARRY_PASS_BEYOND_M, free)
        if beyond < BEYOND_MIN_M and getattr(self, 'beyond_robot', False) and self._yield_door_lane():
            return
        if beyond < BEYOND_MIN_M and getattr(self, 'beyond_robot', False) and getattr(self, 'door_waits', 0) < self._door_wait_tries():
            # the robot beyond the door is moving on: wait and look again
            self.door_waits = getattr(self, 'door_waits', 0) + 1
            self.pass_reach, self.phase = reach, 'pass_wait'
            self.steps.append({'decision': 'robot_beyond_door_wait', 'try': self.door_waits, 'free_beyond_m': free})
            return self._extend('pause:%.1f' % DOOR_WAIT_S)
        if beyond < BEYOND_MIN_M:
            self.steps.append({'decision': 'something_stands_beyond_the_door', 'free_beyond_m': free, 'tall_thing': self.tall_seen})
            return self._stop('something_stands_beyond_the_door')
        if free is not None:
            self.steps.append({'decision': 'pass_shortened', 'free_beyond_m': free, 'beyond_m': beyond})
        self.phase = 'pass'
        return self._extend('fwd:%.3f' % (reach + beyond))

    def _back_out(self, obstacles):
        """Turning on the spot swings the held box through a circle of about 0.23 m. Standing closer than that to a
        wall or a thing, back straight out first (one run turned 0.11 m in front of a wall and the box scraped it).
        Only when backing really opens the gap to CARRY_SWEEP_M, and never through something remembered.
        Returns (pose after backing, pulses)."""
        k, start = self.kit, dict(self.pose)
        near = lambda x, y: min([math.hypot(x - q[0], y - q[1]) for q in obstacles] or [9.])
        if near(start['x'], start['y']) >= k.CARRY_SWEEP_M:
            return start, 0
        unit = k.CARRY_UNIT['back']
        c, s = math.cos(start['yaw']), math.sin(start['yaw'])
        last = near(start['x'], start['y'])
        for n in range(1, int(round(k.CARRY_BACK_MAX_M / unit)) + 1):
            gap = near(start['x'] - n * unit * c, start['y'] - n * unit * s)
            if gap < last - 1e-6 and gap < k.CARRY_SWEEP_M:
                return start, 0             # backing closes in on something before the swing is free
            if gap >= k.CARRY_SWEEP_M:
                start['x'], start['y'] = start['x'] - n * unit * c, start['y'] - n * unit * s
                return start, n
            last = gap
        return start, 0                     # backing does not open the gap: stay

    def _go(self, target, obstacles, decision, look, extra=None):
        """Drive to target around the remembered things, face the door, look. False when no clear way exists."""
        k, door = self.kit, self.door
        start, n_back = self._back_out(obstacles)
        waypoints, clear = k.carry_route([start['x'], start['y']], target, obstacles)
        if not clear:
            return False
        spec = ('back:%dp,' % n_back if n_back else '') + k.carry_legs_spec(start, waypoints + [list(target)], face=[door['x'], door['y']])
        self.steps.append(dict(extra or {}, decision=decision, stop_point=list(target), waypoints=waypoints,
                               obstacle_points=len(obstacles), backed_out_pulses=n_back, spec=spec))
        prefix = '' if self.arm and self.arm[-1] == 1. else 'arm:far,'
        self._extend(prefix + spec + ',pause:%.1f' % k.CARRY_LOOK_S, looks=[(-1, look, True)])
        return True

    def _door_normal(self):
        """Unit normal of the door line, pointing to the side where the robot started this carry."""
        door = self.door
        tx, ty = door['right'][0] - door['left'][0], door['right'][1] - door['left'][1]
        n = math.hypot(tx, ty)
        nx, ny = -ty / n, tx / n
        if nx * (self.start[0] - door['x']) + ny * (self.start[1] - door['y']) < 0:
            nx, ny = -nx, -ny
        return nx, ny

    def _yield_to_door_user(self):
        """--multi-carry: True (and one 2 s pause is planned by the caller) while another robot has the right of way at the door and this robot
        is still outside the zone of the door (see door_right_of_way). Never once the robot is in the zone, never without the source."""
        if self.right_of_way_source is None or self.yield_tries >= YIELD_TRIES:
            return False
        door = self.door
        if math.hypot(self.pose['x'] - door['x'], self.pose['y'] - door['y']) <= DOOR_ZONE_M + .1:
            return False
        who = self.right_of_way_source()
        if who is None:
            return False
        my_id, others = who
        if not door_right_of_way(my_id, (self.pose['x'], self.pose['y']), (door['x'], door['y']), self._door_normal(), others,
                                 band_m=DOOR_BAND_LANE_M if self.door_lane_fix else DOOR_BAND_M):
            return False
        self.yield_tries += 1
        self.steps.append({'decision': 'yield_to_robot_at_the_door', 'try': self.yield_tries})
        return True

    def _approach(self, look='at_door_1'):
        """Toward the door in two stages: first to look stops 1.9 m and 1.25 m from it (close enough for the close-range rule and
        for a good look at what stands in front of it), then to a stopping point on the door axis."""
        if self._yield_to_door_user():
            self.phase, self.yield_look = 'door_yield', look
            return self._extend('pause:%.1f' % YIELD_WAIT_S)
        door = self.door
        nx, ny, obstacles = self._door_side()
        dist = math.hypot(self.pose['x'] - door['x'], self.pose['y'] - door['y'])
        radius = next((r for r in FAR_STOPS_M[self.far_stops:] if dist > r + .3), None)
        if radius is not None:
            self.far_stops = FAR_STOPS_M.index(radius) + 1
            # stop short on the line toward the door; if that spot or the way to it is taken, try beside it
            base = math.atan2(self.pose['y'] - door['y'], self.pose['x'] - door['x'])
            for swing in (0., .35, -.35, .7, -.7):
                target = [door['x'] + radius * math.cos(base + swing), door['y'] + radius * math.sin(base + swing)]
                if (target[0] - door['x']) * nx + (target[1] - door['y']) * ny < .5:
                    continue
                if self.kit.carry_point_clearance(target, obstacles) < STOP_CLEAR_M:
                    continue
                self.phase = 'approach_far'
                if self._go(target, obstacles, 'approach_far', 'far_stop_%d' % self.far_stops):
                    return
            self.steps.append({'decision': 'no_clear_far_stop'})
        # stopping point on the door axis: both jambs must stay in view (not closer than 0.75 m), the spot and the
        # straight way through the door must be clear of what is remembered
        tried = []

        def nearest(point):
            q = min(obstacles, key=lambda o: math.hypot(o[0] - point[0], o[1] - point[1]), default=None)
            if q is None:
                return None
            # in door coordinates: metres in front of the door line, metres along it from the centre
            return {'gap_m': round(math.hypot(q[0] - point[0], q[1] - point[1]), 3),
                    'front_m': round((q[0] - door['x']) * nx + (q[1] - door['y']) * ny, 3),
                    'along_m': round(-(q[0] - door['x']) * ny + (q[1] - door['y']) * nx, 3)}
        for standoff, look_again in STANDOFFS_M:
            if not look_again and not self.seen_close:
                tried.append({'standoff_m': standoff, 'why': 'door not seen from close by'})
                continue   # driving through without another look needs a door seen with the close-range rule
            target = [door['x'] + standoff * nx, door['y'] + standoff * ny]
            if self.kit.carry_point_clearance(target, obstacles) < STOP_CLEAR_M:
                tried.append({'standoff_m': standoff, 'why': 'stopping point taken', 'nearest': nearest(target)})
                continue
            # the straight way from that point through the door, with the robot's half width plus a margin
            detour, straight = self.kit.carry_route(target, [door['x'], door['y']], obstacles, clearance=CORRIDOR_CLEAR_M)
            if detour or not straight:
                in_way = [q for q in obstacles if 0. < (q[0] - door['x']) * nx + (q[1] - door['y']) * ny < standoff
                          and abs(-(q[0] - door['x']) * ny + (q[1] - door['y']) * nx) < CORRIDOR_CLEAR_M]
                tried.append({'standoff_m': standoff, 'why': 'straight way through the door not clear', 'points_in_way': len(in_way),
                              'first': None if not in_way else {'front_m': round((in_way[0][0] - door['x']) * nx + (in_way[0][1] - door['y']) * ny, 3),
                                                               'along_m': round(-(in_way[0][0] - door['x']) * ny + (in_way[0][1] - door['y']) * nx, 3)}})
                continue
            self.phase = 'approach' if look_again else 'approach_blind'
            self.blind_m = standoff
            if self._go(target, obstacles, self.phase, look, {'standoff_m': standoff, 'look_again': look_again}):
                return
            tried.append({'standoff_m': standoff, 'why': 'no clear way to the stopping point'})
        self.steps.append({'decision': 'no_clear_stopping_point', 'door_width_m': door.get('width_m'), 'tried': tried})
        # another robot (measured now) at the door: it is passing, so wait and try again instead of giving up
        # (LLM T1 C01: r2 looked while r1 went through the door; r1's points filled the way and r2 set its box down)
        robots_at_door = [q for q in self._others_now() if math.hypot(q[0] - door['x'], q[1] - door['y']) < DOOR_BUSY_M]
        if robots_at_door and getattr(self, 'door_waits', 0) < self._door_wait_tries():
            self.door_waits = getattr(self, 'door_waits', 0) + 1
            self.door_wait_look = look
            self.phase = 'door_wait'
            self.steps.append({'decision': 'door_busy_wait', 'try': self.door_waits})
            return self._extend('pause:%.1f' % DOOR_WAIT_S)
        self._stop('no_clear_way_to_door')

    def _held_back_m(self):
        """How far the held check backs off: HELD_BACK_M, or less when a known wall stands behind the robot (within the body width,
        along its reverse heading) closer than that. Only with the arena known (known_walls); otherwise unchanged."""
        if not self.known_walls:
            return HELD_BACK_M
        p = self.pose_source() if self.pose_source is not None else None
        p = p if p is not None else self.pose
        c, s = math.cos(p['yaw']), math.sin(p['yaw'])
        free = None
        for q in self.known_walls:
            dx, dy = q[0] - p['x'], q[1] - p['y']
            behind, side = -(dx * c + dy * s), -dx * s + dy * c
            if behind > 0. and abs(side) < HELD_BACK_HALF_M and (free is None or behind < free):
                free = behind
        if free is None:
            return HELD_BACK_M
        return max(0., min(HELD_BACK_M, free - HELD_WALL_HALF_M - HELD_REAR_M - HELD_WALL_MARGIN_M))

    def _sidestep_look(self):
        """The destination was not seen from the door, not even after the second look inside: move sideways and look again (see
        plan_sidestep). True when rows were added (the phase stays 'scan', the looks are 'zone_scan', so what was seen adds up with
        the earlier looks); False when this carry may not or cannot do it, and the carry ends as before. Needs the measured pose and
        the measured other robots (ceiling cameras) and the known walls and door."""
        tries = getattr(self, 'sidesteps', 0)
        if (tries >= SIDESTEP_TRIES or not self.colour or self.pose_source is None or self.others_source is None
                or not self.known_walls or self.known_door is None):
            return False
        robots = self.others_source()
        if robots is None:
            return False
        pose = self.pose_source() or dict(self.pose)     # a stale ceiling reading: the pose of the start of this tick (measured)
        eyes = []
        for look in self.looks:
            if look['phase'] == 'zone_scan' and all(math.hypot(look['pose']['x'] - e[0], look['pose']['y'] - e[1]) > .15 for e in eyes):
                eyes.append((look['pose']['x'], look['pose']['y']))
        if not eyes:
            return False
        choice, facts = plan_sidestep(pose, eyes, self.known_walls, [tuple(r[:2]) for r in robots],
                                      door=(self.known_door['x'], self.known_door['y']))
        if choice is None:
            self.steps.append({'decision': 'zone_not_seen_no_sidestep', 'try': tries + 1, 'hidden_points': facts['hidden_points'],
                               'groups': facts['groups'], 'candidates': facts['candidates']})
            return False
        self.sidesteps = tries + 1
        legs = self.kit.carry_legs_spec(pose, [choice['target']])
        self.pose = dict(pose)
        self.steps.append({'decision': 'zone_not_seen_sidestep', 'try': self.sidesteps, 'choice': choice, 'hidden_points': facts['hidden_points'],
                           'groups': facts['groups'], 'candidates': facts['candidates'], 'spec': legs})
        self._extend(legs + ',' + ','.join(['right:30,pause:0.8'] * 12), looks=[(n, 'zone_scan', False) for n in range(12)])
        return True

    def _retry_zone_look(self):
        """Back away with the gripper closed, then aim the sweep at the last hint. Only the new view can confirm it."""
        reason = 'retry_limit'
        if self.zone_retries < ZONE_RELOOK_TRIES:
            k, p = self.kit, self.pose
            unit = k.CARRY_UNIT['back']
            pulses = int(min(ZONE_RELOOK_BACK_M, self._held_back_m()) / unit)
            view = dict(p, x=p['x'] - pulses * unit * math.cos(p['yaw']),
                        y=p['y'] - pulses * unit * math.sin(p['yaw']))
            obstacles = self._around()
            xy = [view['x'], view['y']]
            if (pulses and path_gap((p['x'], p['y']), xy, obstacles, start_skip=0.) >= k.CARRY_BODY_M
                    and k.carry_point_clearance(xy, obstacles) >= k.CARRY_SWEEP_M):
                self.zone_retries += 1
                self.close_look = 'zone_close_%d' % self.zone_retries
                hint = self.zone_seen['from_door']
                aim = k.carry_legs_spec(view, [], face=[hint['x'], hint['y']])
                spec = 'back:%dp,%s,pause:%.1f,%s' % (pulses, aim, k.CARRY_LOOK_S, ZONE_CLOSE_SWEEP)
                self.steps.append({'decision': 'back_off_and_reobserve_zone', 'try': self.zone_retries, 'view_xy': xy})
                return self._extend(spec, looks=[(n, self.close_look, True) for n in range(5)])
            reason = 'backoff_blocked'
        self.steps.append({'decision': 'zone_unconfirmed', 'reason': reason, 'retries': self.zone_retries})
        self.phase, self.outcome, self.finished = 'done', 'zone_unconfirmed', True

    # -- phase machine ---------------------------------------------------------------------------------
    def _next(self):
        k = self.kit
        if self.put_down_requested and self.phase not in ('lower', 'done'):
            return self._stop('put_down')       # asked during the leg through the door: its rows are used up now
        if self.phase == 'pass_wait':
            return self._pass(self.pass_reach)
        if self.returning and self.phase == 'pass':
            return self._return_exit()           # the way back is over at the door; no zone is looked for in the box room
        if self.returning and self.phase == 'return_exit':
            return self._stop('through_door')
        if self.phase == 'door_yield':
            return self._approach(look=getattr(self, 'yield_look', 'at_door_1'))
        if self.phase == 'door_wait':
            self.far_stops = len(FAR_STOPS_M)          # already near the door: go straight for the stopping point
            return self._approach(look=getattr(self, 'door_wait_look', 'at_door_1'))
        if self.phase == 'start' and self.check_held and self.held_result is None:
            self.held_result = 'looking'
            self.phase = 'held_look'
            back = self._held_back_m()
            self.steps.append({'decision': 'held_back_off', 'back_m': round(back, 3), 'full_m': HELD_BACK_M})
            return self._extend('arm:far,%spause:1.0' % ('back:%.2f,' % back if back >= HELD_BACK_SKIP_M else ''), looks=[(0, 'held_look', False)])
        if self.phase == 'held_look' and self.picked is not None and self.pose_source is not None \
                and self.pose_source() is not None and not getattr(self, 'held_turned', False):
            # also look where the box was picked from (measured pose): a missed box is not always straight ahead
            # (team-llm17 T1 X01: both robots missed, the boxes lay off to the side, the check read 'held')
            self.held_turned = True
            q = self.pose_source()
            turn = math.atan2(self.picked[1] - q['y'], self.picked[0] - q['x']) - q['yaw']
            turn = math.degrees(math.atan2(math.sin(turn), math.cos(turn)))
            if abs(turn) > HELD_TURN_MIN_DEG:
                return self._extend('%s:%.1f,pause:1.0' % ('left' if turn > 0 else 'right', abs(turn)), looks=[(0, 'held_look', False)])
        if self.phase == 'held_look':
            near, at_pick = [], []
            for pts, q in self.held_frames:
                near.append(any(HELD_NEAR_X[0] < x < HELD_NEAR_X[1] and abs(y) < HELD_NEAR_Y for x, y in pts))
                if self.picked is not None and self.pose_source is not None:
                    c, s_ = math.cos(q['yaw']), math.sin(q['yaw'])
                    at_pick.append(any(math.hypot(q['x'] + c * x - s_ * y - self.picked[0], q['y'] + s_ * x + c * y - self.picked[1])
                                       < HELD_AT_PICK_M for x, y in pts))
            left = sum(near) * 2 >= max(1, len(near)) or sum(at_pick) >= HELD_AT_PICK_FRAMES
            self.held_result = 'not_held' if left else 'held'
            self.steps.append({'decision': 'held_check', 'box_left_on_floor': left, 'frames': len(near), 'frames_with_box': sum(near),
                               'frames_box_at_pick_point': sum(at_pick)})
            if self.held_edge_fix:
                self.steps[-1]['edge_excluded_blobs'] = [b for frame in self.held_edge_excluded for b in frame]
                self.steps[-1]['edge_excluded_frames'] = sum(1 for frame in self.held_edge_excluded if frame)
            if left:
                return self._stop('box_not_held')
            self.phase = 'start'
        if self.phase == 'start':
            if self.door is None:
                return self._search()
            start, n_back = self._back_out(self._around())
            turn = math.atan2(self.door['y'] - start['y'], self.door['x'] - start['x']) - start['yaw']
            turn = math.atan2(math.sin(turn), math.cos(turn))
            self.phase = 'verify'
            return self._extend('arm:far,%s%s:%.2f,pause:1.0' % ('back:%dp,' % n_back if n_back else '',
                                'left' if turn >= 0 else 'right', math.degrees(abs(turn))), looks=[(-1, 'verify', False)])
        if self.phase == 'verify':
            seen = self._consistent(self.places.door('verify'))
            self.steps.append({'decision': 'verify', 'seen': seen is not None})
            if seen is None:
                return self._search()
            self.door = self._reanchor(seen, turn_only=True, phase='verify')
            return self._approach()
        if self.phase == 'search':
            name = 'search_%d' % self.searches
            found = self._consistent(self.places.door(name))
            if found is not None:
                # The door just found is where the robot really stands relative to it; the remembered door says where
                # that is in the frame of the memory. The heading from the drive record can be far off after circling
                # a box (two runs: 50 and 150 degrees), so the own pose is put back on the remembered door: heading
                # only from far away, position as well from close by.
                mem = self.door_remembered
                close = mem is not None and math.hypot(self.pose['x'] - found['x'], self.pose['y'] - found['y']) < 2.3
                self.door = self._reanchor(found, turn_only=not close, phase=name)
                return self._approach()
            if self.door is not None and self.moves == 0:
                # not visible from here, but remembered from the look-around: go by memory, look closely there
                self.steps.append({'decision': 'go_by_memory', 'after': name})
                return self._approach()
            if self.moves >= SEARCH_MOVES or not self.open:
                return self._stop('door_not_found_by_search')
            # move toward the most open direction that does not pass close to a listed box, then search again
            self.moves += 1
            # A doorway shows as a direction that is open much farther than its neighbours on both sides (one run went
            # 1 m toward the long open end of the room twice and never saw the door 2.7 m behind it). Try such narrow
            # openings first, then the most open directions.
            ring = sorted(self.open, key=lambda v: v[0])
            def narrowness(i):
                return ring[i][1] - max(ring[i - 1][1], ring[(i + 1) % len(ring)][1])
            order = sorted(range(len(ring)), key=lambda i: (-(narrowness(i) > NARROW_GAIN_M), -ring[i][1]))
            for yaw, reach in [ring[i] for i in order]:
                dist = max(SEARCH_MOVE_M[0], min(SEARCH_MOVE_M[1], .4 * reach))
                target = [self.pose['x'] + dist * math.cos(yaw), self.pose['y'] + dist * math.sin(yaw)]
                plan = k.carry_to_plan(self.pose, target, self.others, stop_m=0.)
                if plan['path_clear'] and reach >= 1.0:
                    break
            else:
                return self._stop('door_not_found_no_open_direction')
            self.steps.append({'decision': 'move_to_look_elsewhere', 'toward_yaw_deg': math.degrees(yaw), 'open_m': reach,
                               'spec': plan['spec']})
            self.phase = 'search_move'
            return self._extend(plan['spec'].replace('back:0p,', ''))
        if self.phase == 'search_move':
            return self._search()
        if self.phase == 'approach_far':
            name = self.looks[-1]['phase']
            seen = self._consistent(self.places.door(name))
            self.steps.append({'decision': 'looked_from_far_stop', 'seen': seen is not None})
            if seen is not None:
                self.door, self.seen_close = self._reanchor(seen, phase=name), True
            elif not self.far_searched:
                # Not where the memory put it: the own heading is probably off. Turn on the spot and look for it
                # from here (it is within the close-range rule now) before going any farther on a wrong heading.
                self.far_searched = True
                self.steps.append({'decision': 'search_from_far_stop'})
                return self._search()
            if not self.swept:
                # From the first look stop the floor in front of the door is about a metre ahead: look to both sides
                # of the door for things standing there (a bar beside the door axis was seen with one point from
                # the start and brushed twice). Closer in, the held box hides that floor.
                self.swept = True
                self.phase = 'sweep'
                return self._extend('left:%d,pause:0.6,right:%d,pause:0.6,left:%d' % (SWEEP_DEG, 2 * SWEEP_DEG, SWEEP_DEG),
                                    looks=[(0, 'area_left', False), (1, 'area_right', False)])
            return self._approach()
        if self.phase == 'sweep':
            self.steps.append({'decision': 'looked_beside_the_door', 'things_remembered': len(self.places.obstacles)})
            if not self.seen_close:
                # the door was not where the robot faced, but one of the sideways looks may have caught it: the
                # heading was off (one run faced 20 degrees past the door and drove on by memory alone)
                for look in self.looks[-2:]:
                    seen = self._consistent(self.places.door(look['phase']))
                    if seen is not None:
                        self.door = self._reanchor(seen, turn_only=True, phase=look['phase'], look_yaw=look['pose']['yaw'])
                        self.steps.append({'decision': 'door_seen_in_a_sideways_look', 'phase': look['phase']})
                        break
            return self._approach()
        if self.phase == 'approach_blind':
            # too close to see both jambs: straight through, on the door seen from the last look stop
            if self.goal == 'door':
                return self._stop('in_front_of_door')
            if self.door_lane_fix and self.known_door is not None and self.pose_source is not None and self.pose_source() is not None:
                # --door-lane-fix: the door is known and the own pose measured, so the lining up needs no picture. The open-loop way to the 0.6 m stop had
                # left the heading 22 degrees off the door axis (MC5-P2_N03_S04 r3) and the straight pass wedged the robot at the jamb: check it like any look stop
                self.phase = 'approach'
            else:
                self.steps.append({'decision': 'pass_without_another_look', 'from_m': self.blind_m})
                return self._pass(self.blind_m)
        if self.phase in ('approach', 'align'):
            name = self.looks[-1]['phase']
            seen = self._consistent(self.places.door(name))
            if seen is None and self.reseeks < 1:
                # too close or turned away: look again. Back up first only when nothing remembered stands behind
                # (one run backed into a bar 0.2 m behind it); otherwise look a little to each side on the spot.
                self.reseeks += 1
                c, s = math.cos(self.pose['yaw']), math.sin(self.pose['yaw'])
                behind = [q for q in list(self.places.obstacles.values()) + [(o[0], o[1], 0.) for o in self.others]
                          if -.60 < (q[0] - self.pose['x']) * c + (q[1] - self.pose['y']) * s < 0
                          and abs(-(q[0] - self.pose['x']) * s + (q[1] - self.pose['y']) * c) < .30]
                if behind:
                    self.steps.append({'decision': 'look_to_each_side_again', 'seen_from': name, 'things_behind': len(behind)})
                    return self._extend('left:12,pause:1.0,right:24,pause:1.0,left:12',
                                        looks=[(0, name + '_again', True), (1, name + '_again', True)])
                self.steps.append({'decision': 'back_up_and_look_again', 'seen_from': name, 'spec': 'back:0.25'})
                return self._extend('back:0.25,pause:%.1f' % k.CARRY_LOOK_S, looks=[(-1, name + '_again', True)])
            if seen is None:
                return self._stop('door_not_seen_from_%s' % name)
            self.door, self.seen_close = self._reanchor(seen, phase=name), True
            kind, move, facts = k.carry_door_step(self.door, self.pose)
            self.steps.append(dict(facts, seen_from=name, decision=kind, spec=move))
            if self.goal == 'door':
                return self._stop('in_front_of_door')
            if kind == 'pass':
                return self._pass(facts['straight_distance_m'])
            if self.tries >= k.CARRY_PASS_TRIES:
                return self._stop('not_lined_up_after_%d_tries' % self.tries)
            # line up again: a stopping point on the axis of the door as just seen, chosen and reached around the
            # remembered things like the first one (a run that simply backed onto the axis touched a bar behind it)
            self.tries += 1
            return self._approach(look='at_door_%d' % (self.tries + 1))
        if self.phase == 'pass' and self.colour and self.told:
            # told where the zone is relative to the door: go there without looking around first
            point = self.places.place_from_description(self.told, self.door, self.start)
            zone = {'kind': 'zone_' + self.colour, 'x': point[0], 'y': point[1], 'source': 'told'}
            self.zone_seen['told'] = zone
            plan = k.carry_to_plan(self.pose, point, [], stop_m=self._zone_stop_m())
            self.steps.append({'decision': 'go_to_told_zone', 'zone': zone, 'spec': plan['spec']})
            self.phase = 'zone_told'
            return self._extend(plan['spec'].replace('back:0p,', '') + ',pause:%.1f' % k.CARRY_LOOK_S,
                                looks=[(-1, self.close_look, self.zone_confirm_close)])
        if self.phase == 'zone_told':
            if self._zone(self.close_look) is None:
                # not there: look around after all
                self.steps.append({'decision': 'told_zone_not_seen_look_around'})
                self.phase = 'scan'
                return self._extend(','.join(['right:30,pause:0.8'] * 12), looks=[(n, 'zone_scan', False) for n in range(12)])
            self.zone_seen['from_door'] = self.zone_seen['told']
            self.phase = 'zone_near'
            return self._next()
        if self.phase == 'pass' and self.known_zone is not None:
            self.phase = 'scan'             # the destination is known: no need to look around for it
            return self._next()
        if self.phase == 'pass':
            self.phase = 'scan'
            return self._extend(','.join(['right:30,pause:0.8'] * 12),
                                looks=[(n, 'zone_scan', False) for n in range(12)] if self.colour else ())
        if self.phase == 'scan':
            if self.colour is None:
                return self._stop('through_door')
            zone = self._zone('zone_scan')
            self.zone_seen['from_door'] = zone
            if zone is None and self.pose_source is not None and not getattr(self, 'room_scanned', False):
                # not seen from the door: drive 1.0 m further into the room and look around once more
                self.room_scanned = True
                c, s = math.cos(self.pose['yaw']), math.sin(self.pose['yaw'])
                plan = k.carry_to_plan(self.pose, [self.pose['x'] + 1.0 * c, self.pose['y'] + 1.0 * s], [])
                self.steps.append({'decision': 'zone_not_seen_from_door_look_again_inside', 'spec': plan['spec']})
                return self._extend(plan['spec'].replace('back:0p,', '') + ',' + ','.join(['right:30,pause:0.8'] * 12),
                                    looks=[(n, 'zone_scan', False) for n in range(12)])
            if zone is None and self._sidestep_look():
                return
            if zone is None:
                return self._stop('zone_not_seen_from_door')
            # go to 0.9 m short of the remembered paint, facing it, and look again
            plan = k.carry_to_plan(self.pose, [zone['x'], zone['y']], [], stop_m=self._zone_stop_m())
            self.steps.append({'decision': 'go_to_zone', 'zone': zone, 'spec': plan['spec']})
            self.phase = 'zone_near'
            return self._extend(plan['spec'].replace('back:0p,', '') + ',pause:%.1f' % k.CARRY_LOOK_S,
                                looks=[(-1, self.close_look, self.zone_confirm_close)])
        if self.phase == 'zone_near':
            close = self._zone(self.close_look)
            if close is None and not getattr(self, 'zone_swept', False):
                # At 0.7 m the 25 cm sign spans about 20 degrees. A coarser sweep clipped it at the edge in X04 r1.
                self.zone_swept = True
                self.steps.append({'decision': 'zone_not_seen_close_sweep'})
                return self._extend(ZONE_CLOSE_SWEEP, looks=[(n, self.close_look, self.zone_confirm_close) for n in range(4)])
            self.zone_seen['close'] = close
            if close is None and self.zone_confirm_close:
                return self._retry_zone_look()
            zone = close or self.zone_seen['from_door']
            plan = k.carry_to_plan(self.pose, [zone['x'], zone['y']], [])   # the box is set down on that point
            self.steps.append({'decision': 'set_down_in_zone', 'zone': zone, 'spec': plan['spec']})
            self.phase = 'zone_final'
            return self._extend(plan['spec'].replace('back:0p,', ''))
        if self.phase == 'zone_final':
            return self._stop('at_zone')
        if self.phase == 'lower':
            self.phase, self.finished = 'done', True

    def step(self, jpeg, posture):
        """One control tick -> (wheels, pulse seconds, arm level 0..1), or None when the carry is over."""
        if self.i >= len(self.rows) and self.pose_source is not None:
            measured = self.pose_source()
            if measured is not None:
                self.pose = dict(measured)  # plan the next part from where the robot really is
        while self.i >= len(self.rows) and not self.finished:
            self._next()
        if self.finished:
            return None
        for look in self.looks:
            if look['rows'][0] <= self.i < look['rows'][1]:
                p = look['pose']
                if self.pose_source is not None and self.pose_source() is not None:
                    p = self.pose_source()      # where the robot really stood for this frame
                if look['what'] == 'held':
                    # body-frame boxes of the held colour, with the pose they were seen from (list frame)
                    if self.held_edge_fix:
                        self.held_frames.append((self.places.box_on_floor(jpeg, posture, self.held_kind, edge_fix=True), dict(p)))
                        self.held_edge_excluded.append(list(self.places.last_edge_excluded))
                    else:
                        self.held_frames.append((self.places.box_on_floor(jpeg, posture, self.held_kind), dict(p)))
                    continue
                if look['what'] == 'zone':
                    self.places.observe_zone(jpeg, posture, self.colour, pose=(p['x'], p['y'], p['yaw']),
                                             phase=look['phase'], held_kind=self.held_kind, **({'close': True} if look['near'] else {}))
                else:
                    # while searching, the door may be far or close: both rules look at every frame
                    for near in ((False, True) if look['phase'].startswith(('search_', 'verify')) else (look['near'],)):
                        self.places.observe(jpeg, posture, pose=(p['x'], p['y'], p['yaw']), phase=look['phase'],
                                            ignore_below_row=self.kit.CARRY_BOX_ROW, near=near,
                                            held_kind=self.held_kind)
                    if look['phase'].startswith('search_') and self.i == look['rows'][0]:
                        self.open.append((p['yaw'], self.places.open_distance(jpeg, posture, self.kit.CARRY_BOX_ROW)))
        if self.sign_scan_early_stop:
            self._stop_scan_early()
        wheels, seconds = self.rows[self.i]
        level = self.arm[self.i]
        self.i += 1
        return wheels, seconds, level

    def _stop_scan_early(self):
        """At the last row of a destination-sign look window of the sweep: when the sign is already in the memory, drop the rows of the rest of the
        sweep. The row being issued now (the last tick of the pause) stays; the next tick plans the way to the zone from where the robot stands
        (the measured pose, or the nominal pose of this pause). The sweep is only cut at a pause, so the robot always stands still."""
        if self.phase != 'scan' or not (self.colour or '').startswith('sign'):
            return
        for look in self.looks:
            if look['phase'] == 'zone_scan' and look['rows'][1] - 1 == self.i and self.i + 1 < len(self.rows):
                break
        else:
            return
        zone = self._zone('zone_scan')
        if zone is None:
            return
        cut = self.i + 1
        self.steps.append({'decision': 'zone_scan_early_stop', 'row': self.i, 'rows_dropped': len(self.rows) - cut,
                           'points': zone.get('points')})
        del self.rows[cut:], self.arm[cut:]
        self.segments = [g for g in self.segments if g['first_row'] < cut]
        self.looks = [l for l in self.looks if l['rows'][0] < cut]
        self.pose = dict(look['pose'])      # the nominal pose of this pause: the rotations before it, none after

    def record(self):
        return {'goal': self.goal, 'told': self.told, 'held_kind': self.held_kind, 'zone_seen': self.zone_seen, 'outcome': self.outcome, 'phase': self.phase, 'tries': self.tries,
                'door_remembered': self.door_remembered, 'door_last_seen': self.door,
                'searches': self.searches, 'search_moves': self.moves, 'steps': self.steps, 'log': self.log, 'looks': self.looks, 'segments': self.segments,
                'rows_issued': self.i, 'rows_planned': len(self.rows), 'pose_estimate': dict(self.pose),
                **({'close_reads': list(self.places.close_reads)} if getattr(self.places, 'close_reads', None) is not None and self.zone_confirm_close else {})}
