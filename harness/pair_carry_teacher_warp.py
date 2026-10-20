"""GT pair-carry teacher (P2): hold -> carry -> wide door -> zone B -> set down -> retreat.

Demonstration-only exception (pair-act-carry-plan P2): this teacher reads the
simulator truth snapshot (``scripts/run_grasp_act_teacher.snapshot``) and is
never a student input. It starts from the state in which the frozen beamact5
grasp teacher reached ``joint_held`` (both bilateral finger contacts >= 0.5,
beam min_z >= 0.012 m, tilt <= 10 deg for 3 SIM s) and drives BOTH robots from
one central GT state machine, so the two robots are synchronised by
construction (no peer messages are modelled here).

Default OFF: nothing imports this module unless the runner is called with
``pair_carry='pair_carry_gt_v1'``. All numbers in ``Params`` are new P2
candidate constants (see experiments/2026-10-21-pairact-p2/DESIGN.md), not
measured values; the smoke run is what measures them.

Pure Python: no mujoco / warp / sim imports at module import time, so the
geometry and the state machine are unit-testable on a machine without the
simulator. The wheel conversion (``sim.grasp_act_port.duty_wheels``) is
injected or lazily imported.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

MODE = 'pair_carry_gt_v1'
MODES = ('off', MODE)
# Set-down target (default: the frozen P2 behaviour, IK back to the grasp height).
# 'floor_contact_v1' keeps lowering past the grasp height until the GT beam
# lowest point is within ``floor_margin_m`` of the floor, bounded by
# ``lower_max_s`` (DESIGN §2-1). Opt-in only.
LOWER_MODES = ('grasp_height', 'floor_contact_v1')
SCHEMA = 'ugrp.pairact.carry_teacher.v1'
ROLES = ('teal', 'blue')
SERVOS = (1, 3, 4, 5, 6)
GRIPPER_OPEN = 2000
BEAM_HALF = (.30, .02)          # sim/zone_cargo.py long_beam landing_half_extents_m
ROBOT_RADIUS_M = .17            # existing teacher planning disc (grasp_act_teacher_v3 default)
HOLD_MIN_Z_M = .012             # same joint-hold criterion as the frozen runner
HOLD_MIN_FORCE = .5

# Phase order (one central machine). Every phase has a cap and a failure code.
PHASES = ('carry_hold', 'to_west_staging', 'rotate_door', 'to_door_entry', 'door_pass',
          'to_east_staging', 'rotate_zone', 'to_zone', 'zone_settle', 'lower', 'open',
          'raise', 'retreat', 'done')
FAIL = {
    'carry_hold': 'carry_hold_lost',
    'to_west_staging': 'west_staging_timeout',
    'rotate_door': 'rotate_door_timeout',
    'to_door_entry': 'door_entry_timeout',
    'door_pass': 'door_pass_timeout',
    'to_east_staging': 'east_staging_timeout',
    'rotate_zone': 'rotate_zone_timeout',
    'to_zone': 'zone_approach_timeout',
    'zone_settle': 'zone_align_timeout',
    'lower': 'lower_timeout',
    'open': 'open_timeout',
    'raise': 'raise_timeout',
    'retreat': 'retreat_timeout',
}
LOWER_NO_CONTACT = 'lower_no_floor_contact'   # floor_contact_v1 only
# Additional teacher-side abort codes (GT, teacher only; the evaluator recounts
# drops independently from eval-only rows).
ABORTS = ('carry_hold_lost', 'formation_stretch', 'formation_tracking_lost',
          'door_clearance_insufficient', 'staging_unclear', 'route_blocked',
          'zone_unreachable', 'carry_total_timeout', 'arm_targets_missing', LOWER_NO_CONTACT)


@dataclass(frozen=True)
class Params:
    dt: float = .1
    v_max: float = .08            # virtual beam-centre speed, m/s (candidate)
    w_max: float = .25            # virtual beam yaw rate, rad/s (candidate)
    k_xy: float = 1.5             # per-robot pose P gain, 1/s
    k_yaw: float = 1.2
    robot_v_cap: float = .10      # per-robot body speed cap, m/s
    robot_w_cap: float = .35      # per-robot yaw-rate cap, rad/s
    effort_xy: float = 3.         # same scaling as VisibleOnlyGraspTeacher._continuous
    effort_yaw: float = .65
    deadband_xy: float = .006
    deadband_yaw: float = math.radians(1.)
    track_tol_xy: float = .04     # virtual target advances only inside these
    track_tol_yaw: float = math.radians(6.)
    stretch_pause_m: float = .03  # |d12 - d12(handover)| pauses the virtual target
    stretch_fail_m: float = .08
    stretch_fail_s: float = 1.
    track_fail_m: float = .15
    track_fail_s: float = 3.
    hold_lost_s: float = .5
    hold_settle_s: float = 1.     # carry_hold: keep lift height before moving
    stage_dx: float = .95         # staging distance from the door plane (m)
    door_entry_dx: float = .75    # beam centre this far before/after the door plane
    door_margin_m: float = .05    # lateral clearance per side inside the door
    clear_margin_m: float = .05   # in-place rotation circle margin to walls
    zone_tol_xy: float = .03
    zone_tol_yaw: float = math.radians(4.)
    zone_inner_margin_m: float = .02
    lower_s: float = 1.6
    lower_mode: str = 'grasp_height'
    floor_margin_m: float = .004  # floor_contact_v1: stop when beam min_z <= this (< eval rest .006)
    lower_max_s: float = 4.       # floor_contact_v1: lift -> place_deep cap; no touch -> lower_no_floor_contact
    floor_touch_hold_s: float = .2  # min_z must stay within the margin this long before freezing
    place_deep_m: float = .025    # place_deep = IK at grasp_z - place_deep_m (arm_targets_from_teacher)
    open_s: float = .8
    raise_s: float = 1.
    settle_after_s: float = .3
    retreat_m: float = .15
    retreat_speed: float = .06
    retreat_cap_s: float = 4.
    carry_cap_s: float = 110.
    phase_caps_s: dict = field(default_factory=lambda: {
        'carry_hold': 4., 'to_west_staging': 40., 'rotate_door': 20., 'to_door_entry': 25.,
        'door_pass': 30., 'to_east_staging': 30., 'rotate_zone': 20., 'to_zone': 30.,
        'zone_settle': 8., 'lower': 4., 'open': 2., 'raise': 3., 'retreat': 5.})


# ---------------------------------------------------------------- SE(2) helpers

def wrap(a):
    return (a + math.pi) % (2*math.pi) - math.pi


def compose(a, b):
    """World pose of b expressed in frame a."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c*b[0] - s*b[1], a[1] + s*b[0] + c*b[1], wrap(a[2] + b[2]))


def inverse(a):
    c, s = math.cos(a[2]), math.sin(a[2])
    return (-c*a[0] - s*a[1], s*a[0] - c*a[1], wrap(-a[2]))


def relative(a, b):
    """Pose of b in the frame of a."""
    return compose(inverse(a), b)


def to_local(pose, xy):
    dx, dy = xy[0]-pose[0], xy[1]-pose[1]
    c, s = math.cos(pose[2]), math.sin(pose[2])
    return (c*dx + s*dy, -s*dx + c*dy)


def clip(v, cap):
    return max(-cap, min(cap, v))


# ------------------------------------------------------------ map geometry

def door_of(static_map, door_id='door_wide'):
    d = next(p for p in static_map['passages'] if p['id'] == door_id)
    if d.get('axis') != 'x':
        raise NotImplementedError('TODO(P2): only x-axis doors (vertical divider) are handled')
    return {'id': d['id'], 'x': float(d['center_m'][0]), 'cy': float(d['center_m'][1]),
            'half_y': float(d['half_extents_m'][1]), 'width': float(d['width_m'])}


def zone_of(static_map, zone='zone_B'):
    z = static_map['regions'][zone]
    return {'id': zone, 'cx': float(z['center_m'][0]), 'cy': float(z['center_m'][1]),
            'hx': float(z['half_extents_m'][0]), 'hy': float(z['half_extents_m'][1])}


def wall_rects(static_map):
    """Every fixed obstacle incl. perimeter walls, as (cx, cy, hx, hy, yaw)."""
    return tuple((float(o['center_m'][0]), float(o['center_m'][1]), float(o['half_extents_m'][0]),
                  float(o['half_extents_m'][1]), float(o.get('yaw_rad', 0.)))
                 for o in static_map.get('obstacles', ()))


def rect_distance(point, rect):
    cx, cy, hx, hy, yaw = rect
    dx, dy = point[0]-cx, point[1]-cy
    if yaw:
        c, s = math.cos(yaw), math.sin(yaw)
        dx, dy = c*dx + s*dy, -s*dx + c*dy
    return math.hypot(max(abs(dx)-hx, 0.), max(abs(dy)-hy, 0.))


def beam_corners(pose, half=BEAM_HALF):
    return [compose(pose, (sx*half[0], sy*half[1], 0.))[:2] for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]


def formation_points(beam_pose, offsets):
    """Key world points of the rigid formation: robot centres + beam corners."""
    robots = {rid: compose(beam_pose, off) for rid, off in offsets.items()}
    return robots, beam_corners(beam_pose)


def formation_radius(offsets, *, robot_radius=ROBOT_RADIUS_M):
    """Radius of the circle swept by an in-place rotation about the beam centre."""
    r = max(math.hypot(o[0], o[1]) + robot_radius for o in offsets.values())
    return max(r, math.hypot(*BEAM_HALF))


def lateral_extent(offsets, yaw_rel, *, robot_radius=ROBOT_RADIUS_M):
    """Half-width of the formation perpendicular to the door axis.

    ``yaw_rel`` is the beam yaw minus the door axis yaw. Returns (min, max) of
    the lateral coordinate relative to the beam centre (robots as discs, beam
    as its rectangle).
    """
    c, s = math.cos(yaw_rel), math.sin(yaw_rel)
    lat = []
    for o in offsets.values():
        y = s*o[0] + c*o[1]
        lat += [y - robot_radius, y + robot_radius]
    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        x, y = sx*BEAM_HALF[0], sy*BEAM_HALF[1]
        lat.append(s*x + c*y)
    return min(lat), max(lat)


def door_passage(door, offsets, yaw_rel, *, margin):
    """Lateral offset of the beam centre inside the door, or None if too wide.

    Returns dict(width_needed, width_available, centre_y) where centre_y is the
    beam-centre y that centres the formation in the door opening.
    """
    lo, hi = lateral_extent(offsets, yaw_rel)
    need = (hi - lo) + 2*margin
    out = {'width_needed_m': need, 'width_available_m': door['width'], 'lateral_lo_m': lo, 'lateral_hi_m': hi}
    out['centre_y'] = door['cy'] - (hi + lo)/2 if need <= door['width'] + 1e-9 else None
    return out


def circle_clear(centre, radius, rects, *, margin):
    return min((rect_distance(centre, r) for r in rects), default=math.inf) >= radius + margin


def staging_point(door, side, radius, rects, *, dx, margin, step=.05, max_shift=2.):
    """First point at distance dx from the door plane (west: side=-1, east: +1)
    whose in-place rotation circle is wall-free, scanning away from the door
    centre line in both lateral directions. None if nothing fits."""
    x = door['x'] + side*dx
    for k in range(int(max_shift/step) + 1):
        for sgn in ((1,) if k == 0 else (1, -1)):
            y = door['cy'] + sgn*k*step
            if circle_clear((x, y), radius, rects, margin=margin):
                return (x, y)
    return None


def nearest_axis_yaw(current, axis_yaw):
    """Beam is 180-deg symmetric for placement: pick axis_yaw or axis_yaw+pi."""
    a, b = wrap(axis_yaw), wrap(axis_yaw + math.pi)
    return a if abs(wrap(a - current)) <= abs(wrap(b - current)) else b


def beam_in_zone(beam_pose, zone, *, margin=0.):
    return all(abs(x - zone['cx']) <= zone['hx'] - margin + 1e-9 and abs(y - zone['cy']) <= zone['hy'] - margin + 1e-9
               for x, y in beam_corners(beam_pose))


def carry_route(beam_pose, offsets, static_map, *, params=Params(), door_id='door_wide', zone='zone_B'):
    """Waypoint list of virtual beam-centre poses (x, y, yaw) with segment tags.

    west staging (keep yaw) -> rotate to door axis -> door entry -> through door
    -> east staging -> rotate to the zone long axis -> zone centre.
    Raises ValueError(code) with an ABORTS code when the geometry cannot work.
    """
    door, z, rects = door_of(static_map, door_id), zone_of(static_map, zone), wall_rects(static_map)
    radius = formation_radius(offsets)
    west = staging_point(door, -1, radius, rects, dx=params.stage_dx, margin=params.clear_margin_m)
    east = staging_point(door, +1, radius, rects, dx=params.stage_dx, margin=params.clear_margin_m)
    if west is None or east is None:
        raise ValueError('staging_unclear')
    door_yaw = nearest_axis_yaw(beam_pose[2], 0.)          # door axis is world x
    passage = door_passage(door, offsets, wrap(door_yaw - 0.), margin=params.door_margin_m)
    if passage['centre_y'] is None:
        raise ValueError('door_clearance_insufficient')
    zone_axis = math.pi/2 if z['hy'] >= z['hx'] else 0.    # beam long axis along the zone long axis
    zone_yaw = nearest_axis_yaw(door_yaw, zone_axis)
    if not beam_in_zone((z['cx'], z['cy'], zone_yaw), z, margin=params.zone_inner_margin_m):
        raise ValueError('zone_unreachable')
    cy = passage['centre_y']
    route = [('to_west_staging', (west[0], west[1], beam_pose[2])),
             ('rotate_door', (west[0], west[1], door_yaw)),
             ('to_door_entry', (door['x'] - params.door_entry_dx, cy, door_yaw)),
             ('door_pass', (door['x'] + params.door_entry_dx, cy, door_yaw)),
             ('to_east_staging', (east[0], east[1], door_yaw)),
             ('rotate_zone', (east[0], east[1], zone_yaw)),
             ('to_zone', (z['cx'], z['cy'], zone_yaw))]
    return route, {'door': door, 'zone': z, 'passage': passage, 'formation_radius_m': radius,
                   'west_staging': west, 'east_staging': east}


def segment_clear(a, b, offsets, rects, obstacles=(), *, step=.05, robot_radius=ROBOT_RADIUS_M, margin=.0):
    """GT check of the rigid formation swept along a straight (pose-interpolated)
    segment: robot discs and beam corners vs walls and object discs."""
    n = max(1, int(math.ceil(max(math.dist(a[:2], b[:2]), abs(wrap(b[2]-a[2]))*formation_radius(offsets))/step)))
    for i in range(n + 1):
        u = i/n
        p = (a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u, wrap(a[2]+wrap(b[2]-a[2])*u))
        robots, corners = formation_points(p, offsets)
        for r in robots.values():
            if min((rect_distance(r[:2], w) for w in rects), default=math.inf) < robot_radius + margin:
                return False, ('wall', i/n)
            for o in obstacles:
                if math.dist(r[:2], o['xy']) < robot_radius + o['radius'] + margin:
                    return False, ('object', i/n)
        for c in corners:
            if min((rect_distance(c, w) for w in rects), default=math.inf) < margin:
                return False, ('wall_beam', i/n)
    return True, None


def route_clear(start, route, offsets, rects, obstacles):
    """Every straight segment of ``route`` against walls AND GT object discs."""
    prev = start
    for tag, target in route:
        ok, why = segment_clear(prev, target, offsets, rects, obstacles)
        if not ok:
            return False, {'segment': tag, 'hit': why}
        prev = target
    return True, None


def check_route(start, route, offsets, rects, obstacles):
    """Return (route, blocked). The nominal order translates to the west staging
    point with the handover yaw and then rotates. If that is blocked (e.g. a
    beam held across the room would sweep the south wall), the only alternative
    is to rotate in place at the handover point first, then translate. No other
    detour exists. blocked=None: nominal ok; (True, info): rotate-first used;
    (False, info): both blocked (info of the nominal order)."""
    ok, why = route_clear(start, route, offsets, rects, obstacles)
    if ok:
        return route, None
    (_, west), (_, rot) = route[0], route[1]
    alt = [('rotate_door', (start[0], start[1], rot[2])), ('to_west_staging', (west[0], west[1], rot[2]))] + route[2:]
    ok_alt, _ = route_clear(start, alt, offsets, rects, obstacles)
    return (alt, (True, why)) if ok_alt else (route, (False, why))


# --------------------------------------------------------- control helpers

def body_command(pose, target, ff=(0., 0., 0.), *, params=Params()):
    """P control in the robot frame with world-frame feed-forward; capped.

    Returns (forward m/s, left m/s, turn rad/s).
    """
    ex, ey = target[0]-pose[0], target[1]-pose[1]
    vx, vy = ff[0] + params.k_xy*ex, ff[1] + params.k_xy*ey
    c, s = math.cos(pose[2]), math.sin(pose[2])
    fwd, left = c*vx + s*vy, -s*vx + c*vy
    turn = ff[2] + params.k_yaw*wrap(target[2]-pose[2])
    speed = math.hypot(fwd, left)
    if speed > params.robot_v_cap:
        fwd, left = fwd*params.robot_v_cap/speed, left*params.robot_v_cap/speed
    turn = clip(turn, params.robot_w_cap)
    if math.hypot(ex, ey) < params.deadband_xy and not any(ff[:2]):
        fwd = left = 0.
    if abs(wrap(target[2]-pose[2])) < params.deadband_yaw and not ff[2]:
        turn = 0.
    return fwd, left, turn


def default_wheel_fn(effort):
    from sim.grasp_act_port import duty_wheels   # lazy: simulator package
    return duty_wheels(effort)


def make_command(now, pwm, drive, *, params=Params(), wheel_fn=None):
    """Same 14-dim issued command format as the student contract v5."""
    fwd, left, turn = drive
    if fwd == 0. and left == 0. and turn == 0.:
        wheels, widths = [0.]*4, [0.]*4
    else:
        wheels, widths = (wheel_fn or default_wheel_fn)([params.effort_xy*fwd, params.effort_xy*left,
                                                          params.effort_yaw*turn])
    return {'t': float(now), 'wheels': [float(w) for w in wheels], 'duration_s': [float(d) for d in widths],
            'pwm': {str(s): int(pwm[s]) for s in SERVOS}}


def interpolate_pwm(start, end, u):
    u = max(0., min(1., u)); e = u*u*(3-2*u)
    return {s: int(round(start[s] + e*(end[s]-start[s]))) for s in SERVOS}


def hold_ok(truth, roles):
    beam = truth['beam']
    return (beam['min_z'] >= HOLD_MIN_Z_M and
            all(min(truth['contacts'][rid]) >= HOLD_MIN_FORCE for rid in roles))


# ------------------------------------------------------------- state machine

class PairCarryTeacherWarp:
    """One GT supervisor for both robots after a verified joint hold.

    ``arm_targets[rid]`` must hold integer PWM dicts keyed by servo id:
    ``place`` (gripper still closed, grip site back at the grasp height) and
    ``hover`` (gripper open, grip site at the pre-grasp hover height). The
    lift pose is the robot's current issued PWM at handover. See
    ``arm_targets_from_teacher`` for the runner-side IK glue.
    """

    def __init__(self, roles, truth, now, static_map, arm_targets, pwm, *, params=Params(),
                 wheel_fn=None, door_id='door_wide', zone='zone_B', obstacles=None):
        if sorted(roles.values()) != sorted(ROLES):
            raise ValueError('one robot per beam end required')
        if params.lower_mode not in LOWER_MODES:
            raise ValueError(f'unknown lower mode {params.lower_mode!r}')
        if params.lower_mode == 'floor_contact_v1' and params.phase_caps_s['lower'] < params.lower_max_s + params.settle_after_s:
            raise ValueError('lower phase cap must cover lower_max_s + settle')
        self.roles, self.p, self.wheel_fn = dict(roles), params, wheel_fn
        self.rids = tuple(roles)
        self.static_map = static_map
        self.t0 = float(now)
        self.pwm = {rid: {int(s): int(v) for s, v in pwm[rid].items()} for rid in self.rids}
        self.lift_pwm = {rid: dict(self.pwm[rid]) for rid in self.rids}
        need = {'place', 'hover'} | ({'place_deep'} if params.lower_mode == 'floor_contact_v1' else set())
        missing = [rid for rid in self.rids if not arm_targets or rid not in arm_targets
                   or not need <= set(arm_targets[rid])]
        self.touch_pwm, self.touch_since = None, None
        self.arm_targets = arm_targets
        beam = tuple(truth['beam']['pose'])
        robots = {rid: tuple(truth['robots'][rid]['pose']) for rid in self.rids}
        self.offsets = {rid: relative(beam, robots[rid]) for rid in self.rids}
        self.d12_0 = math.dist(robots[self.rids[0]][:2], robots[self.rids[1]][:2])
        self.virtual = beam
        self.phase, self.phase_t, self.outcome = 'carry_hold', self.t0, None
        self.log, self.events = [], [{'t': now, 'event': 'handover', 'beam': beam, 'offsets': self.offsets,
                                      'd12_m': self.d12_0}]
        self.hold_lost_since = self.stretch_since = self.track_since = None
        self.max_stretch = self.max_track = 0.
        self.retreat_start = {}
        self.route, self.route_info, self.seg = [], {}, 0
        if missing:
            self._fail('arm_targets_missing', now, detail=missing)
            return
        try:
            self.route, self.route_info = carry_route(beam, self.offsets, static_map, params=params,
                                                      door_id=door_id, zone=zone)
        except ValueError as error:
            self._fail(str(error), now)
            return
        self.route, blocked = check_route(beam, self.route, self.offsets, wall_rects(static_map),
                                          list(obstacles or ()))
        self.route_info['variant'] = 'translate_first' if blocked is None or blocked[0] else 'rotate_first'
        if blocked is not None and not blocked[0]:
            # TODO(P2): no formation-space planner yet; a blocked straight
            # segment is an explicit failure code, never a silent detour.
            self._fail('route_blocked', now, detail=blocked[1])
            return

    # ---- bookkeeping
    def _fail(self, code, now, detail=None):
        self.outcome = code
        self.events.append({'t': now, 'event': 'fail', 'code': code, 'phase': self.phase, 'detail': detail})
        self.phase = 'done'

    def _set(self, phase, now):
        self.events.append({'t': now, 'event': 'phase', 'from': self.phase, 'to': phase})
        self.phase, self.phase_t = phase, now

    def _hold_cmds(self, now):
        return {rid: make_command(now, self.pwm[rid], (0., 0., 0.), params=self.p, wheel_fn=self.wheel_fn)
                for rid in self.rids}

    @property
    def done(self):
        return self.phase == 'done'

    # ---- main tick
    def step(self, truth, now):
        """Return {rid: (command, done)} for this 0.1 s tick."""
        now = float(now)
        if self.phase == 'done':
            return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
        if now - self.t0 >= self.p.carry_cap_s - 1e-8:
            self._fail('carry_total_timeout', now)
            return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
        cap = self.p.phase_caps_s.get(self.phase)
        if cap is not None and now - self.phase_t >= cap - 1e-8:
            self._fail(FAIL[self.phase], now)
            return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
        robots = {rid: tuple(truth['robots'][rid]['pose']) for rid in self.rids}
        carrying = self.phase in PHASES[:PHASES.index('lower')]
        if carrying:
            if not hold_ok(truth, self.rids):
                self.hold_lost_since = now if self.hold_lost_since is None else self.hold_lost_since
                if now - self.hold_lost_since >= self.p.hold_lost_s - 1e-8:
                    self._fail('carry_hold_lost', now)
                    return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
            else:
                self.hold_lost_since = None
            stretch = abs(math.dist(robots[self.rids[0]][:2], robots[self.rids[1]][:2]) - self.d12_0)
            self.max_stretch = max(self.max_stretch, stretch)
            if stretch > self.p.stretch_fail_m:
                self.stretch_since = now if self.stretch_since is None else self.stretch_since
                if now - self.stretch_since >= self.p.stretch_fail_s - 1e-8:
                    self._fail('formation_stretch', now, detail={'stretch_m': stretch})
                    return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
            else:
                self.stretch_since = None
        else:
            stretch = 0.
        issue_phase = self.phase
        handler = getattr(self, '_' + self.phase)
        drive = handler(truth, robots, now, stretch)
        out = {}
        for rid in self.rids:
            out[rid] = (make_command(now, self.pwm[rid], drive.get(rid, (0., 0., 0.)), params=self.p,
                                     wheel_fn=self.wheel_fn), self.phase == 'done')
        # 'issue_phase' = phase whose handler produced this tick's command (eval-only
        # drive response pairs it with the GT motion over the next tick).
        self.log.append({'t': now, 'phase': self.phase, 'issue_phase': issue_phase, 'virtual': list(self.virtual),
                         'stretch_m': stretch,
                         'drive': {rid: list(drive.get(rid, (0., 0., 0.))) for rid in self.rids},
                         'wheels': {rid: list(out[rid][0]['wheels']) for rid in self.rids},
                         'duration_s': {rid: list(out[rid][0]['duration_s']) for rid in self.rids}})
        return out

    # ---- phases
    def _carry_hold(self, truth, robots, now, stretch):
        if now - self.phase_t >= self.p.hold_settle_s - 1e-8 and self.hold_lost_since is None:
            self.seg = 0
            self._set(self.route[0][0], now)
        return {}

    def _track(self, robots, now, stretch, target):
        """Advance the virtual beam pose toward ``target`` only while both robots
        track it; return per-robot drive commands and whether the segment is done."""
        p = self.p
        errs = {}
        for rid in self.rids:
            want = compose(self.virtual, self.offsets[rid])
            errs[rid] = (math.dist(robots[rid][:2], want[:2]), abs(wrap(want[2] - robots[rid][2])))
        worst = max(e[0] for e in errs.values()); worst_yaw = max(e[1] for e in errs.values())
        self.max_track = max(self.max_track, worst)
        if worst > p.track_fail_m:
            self.track_since = now if self.track_since is None else self.track_since
            if now - self.track_since >= p.track_fail_s - 1e-8:
                self._fail('formation_tracking_lost', now, detail={'err_m': worst})
                return {}, False
        else:
            self.track_since = None
        tracking = worst <= p.track_tol_xy and worst_yaw <= p.track_tol_yaw and stretch <= p.stretch_pause_m
        vel = (0., 0., 0.)
        if tracking:
            dx, dy = target[0]-self.virtual[0], target[1]-self.virtual[1]
            dyaw = wrap(target[2]-self.virtual[2])
            dist = math.hypot(dx, dy)
            step_xy = min(dist, p.v_max*p.dt); step_yaw = clip(dyaw, p.w_max*p.dt)
            if dist > 1e-9 and step_xy < dist:
                # keep translation and rotation finishing together
                frac = step_xy/dist
                if abs(dyaw) > 1e-9:
                    step_yaw = clip(dyaw*frac, p.w_max*p.dt) if abs(dyaw*frac) < abs(step_yaw) else step_yaw
            elif abs(dyaw) > 1e-9 and abs(step_yaw) < abs(dyaw):
                frac = abs(step_yaw/dyaw); step_xy = dist*frac
            ux, uy = (dx/dist, dy/dist) if dist > 1e-9 else (0., 0.)
            self.virtual = (self.virtual[0]+ux*step_xy, self.virtual[1]+uy*step_xy, wrap(self.virtual[2]+step_yaw))
            vel = (ux*step_xy/p.dt, uy*step_xy/p.dt, step_yaw/p.dt)
        drive = {}
        for rid in self.rids:
            want = compose(self.virtual, self.offsets[rid])
            # feed-forward: rigid-body velocity of the robot point
            o = compose((0., 0., self.virtual[2]), self.offsets[rid])
            ff = (vel[0] - vel[2]*o[1], vel[1] + vel[2]*o[0], vel[2])
            drive[rid] = body_command(robots[rid], want, ff, params=p)
        arrived = (math.dist(self.virtual[:2], target[:2]) < 1e-6 and abs(wrap(self.virtual[2]-target[2])) < 1e-6
                   and all(e[0] <= p.track_tol_xy and e[1] <= p.track_tol_yaw for e in errs.values()))
        return drive, arrived

    def _route_phase(self, truth, robots, now, stretch):
        tag, target = self.route[self.seg]
        drive, arrived = self._track(robots, now, stretch, target)
        if self.phase == 'done':
            return {}
        if arrived:
            self.seg += 1
            self._set(self.route[self.seg][0] if self.seg < len(self.route) else 'zone_settle', now)
        return drive

    _to_west_staging = _rotate_door = _to_door_entry = _door_pass = _route_phase
    _to_east_staging = _rotate_zone = _to_zone = _route_phase

    def _zone_settle(self, truth, robots, now, stretch):
        """Final GT check on the TRUE beam pose (not the virtual one)."""
        z = self.route_info['zone']
        target = self.route[-1][1]
        beam = tuple(truth['beam']['pose'])
        err_xy = math.dist(beam[:2], target[:2])
        err_yaw = abs(wrap(nearest_axis_yaw(beam[2], target[2]) - beam[2]))
        if (err_xy <= self.p.zone_tol_xy and err_yaw <= self.p.zone_tol_yaw
                and beam_in_zone(beam, z, margin=self.p.zone_inner_margin_m)):
            self.events.append({'t': now, 'event': 'zone_aligned', 'beam': beam})
            self._set('lower', now)
            return {}
        # correct the virtual target by the true beam residual (GT feedback)
        corr = (self.virtual[0] + (target[0]-beam[0]), self.virtual[1] + (target[1]-beam[1]),
                wrap(self.virtual[2] + wrap(target[2]-beam[2])))
        drive, _ = self._track(robots, now, stretch, corr)
        return drive

    def _arm_phase(self, now, start_key, end_key, duration, nxt):
        u = (now - self.phase_t)/duration
        for rid in self.rids:
            start = self.lift_pwm[rid] if start_key == 'lift' else self._arm(rid, start_key)
            end = self._arm(rid, end_key)
            self.pwm[rid] = interpolate_pwm(start, end, u)
        if u >= 1. + self.p.settle_after_s/duration - 1e-9:
            self._set(nxt, now)
        return {}

    def _arm(self, rid, key):
        t = self.arm_targets[rid]
        if key in ('place', 'open') and self.touch_pwm is not None:
            # floor_contact_v1: the set-down pose is where the floor was touched
            base = self.touch_pwm[rid]
        else:
            base = t['place' if key == 'open' else key]
        base = {int(s): int(v) for s, v in base.items()}
        return {**base, 1: GRIPPER_OPEN} if key == 'open' else base

    def _lower(self, truth, robots, now, stretch):
        # Both arms follow the same clock: simultaneous lowering by construction.
        if self.p.lower_mode == 'floor_contact_v1':
            return self._lower_to_floor(truth, now)
        return self._arm_phase(now, 'lift', 'place', self.p.lower_s, 'open')

    def _lower_to_floor(self, truth, now):
        """Lower lift -> place_deep on one clock over lower_max_s and freeze both
        arms as soon as the GT beam lowest point stays within floor_margin_m of
        the floor for floor_touch_hold_s. No touch by lower_max_s -> explicit
        failure (never opens in the air)."""
        p, el = self.p, now - self.phase_t
        if self.touch_pwm is not None:
            if now - self.touch_t >= p.settle_after_s - 1e-8:
                self._set('open', now)
            return {}
        if truth['beam']['min_z'] <= p.floor_margin_m:
            self.touch_since = now if self.touch_since is None else self.touch_since
            if now - self.touch_since >= p.floor_touch_hold_s - 1e-8:
                self.touch_pwm = {rid: dict(self.pwm[rid]) for rid in self.rids}
                self.touch_t = now
                self.events.append({'t': now, 'event': 'floor_touch', 'min_z': truth['beam']['min_z'],
                                    'lower_elapsed_s': el})
                return {}
        else:
            self.touch_since = None
        if el >= p.lower_max_s - 1e-8 and self.touch_since is None:
            self._fail(LOWER_NO_CONTACT, now, detail={'min_z': truth['beam']['min_z']})
            return {}
        # same smoothstep as grasp_height, but toward the deeper target and
        # held still while the touch dwell is being confirmed
        if self.touch_since is None:
            u = el/p.lower_max_s
            for rid in self.rids:
                self.pwm[rid] = interpolate_pwm(self.lift_pwm[rid], self._arm(rid, 'place_deep'), u)
        return {}

    def _open(self, truth, robots, now, stretch):
        return self._arm_phase(now, 'place', 'open', self.p.open_s, 'raise')

    def _raise(self, truth, robots, now, stretch):
        drive = self._arm_phase(now, 'open', 'hover', self.p.raise_s, 'retreat')
        if self.phase == 'retreat':
            self.retreat_start = {rid: robots[rid] for rid in self.rids}
        return drive

    def _retreat(self, truth, robots, now, stretch):
        """Back straight away from the beam end (robot -x) up to retreat_m;
        bounded by GT wall clearance. Ends as 'retreat_bounded' when blocked."""
        rects = wall_rects(self.static_map)
        drive, moved, blocked = {}, {}, False
        for rid in self.rids:
            pose, start = robots[rid], self.retreat_start[rid]
            moved[rid] = math.dist(pose[:2], start[:2])
            ahead = compose(pose, (-.03, 0., 0.))
            if min((rect_distance(ahead[:2], w) for w in rects), default=math.inf) < ROBOT_RADIUS_M:
                blocked = True
            drive[rid] = (-self.p.retreat_speed, 0., 0.) if moved[rid] < self.p.retreat_m else (0., 0., 0.)
        if all(m >= self.p.retreat_m for m in moved.values()) or blocked or now - self.phase_t >= self.p.retreat_cap_s - 1e-8:
            kind = 'retreat_complete' if all(m >= self.p.retreat_m for m in moved.values()) else 'retreat_bounded'
            self.events.append({'t': now, 'event': kind, 'moved_m': moved})
            self.retreat_kind = kind
            self._set('done', now)
            self.outcome = 'command_sequence_complete'
            return {}
        if blocked:
            return {}
        return drive

    def diagnostic(self):
        return {'schema': SCHEMA, 'mode': MODE, 'params': asdict(self.p), 'outcome': self.outcome,
                'phase': self.phase, 'route': [[t, list(p)] for t, p in self.route],
                'route_info': self.route_info, 'offsets': {k: list(v) for k, v in self.offsets.items()},
                'd12_0_m': self.d12_0, 'max_stretch_m': self.max_stretch, 'max_track_err_m': self.max_track,
                'lower_mode': self.p.lower_mode,
                'floor_touch_pwm': ({k: {str(s): v for s, v in d.items()} for k, d in self.touch_pwm.items()}
                                    if self.touch_pwm is not None else None),
                'retreat': getattr(self, 'retreat_kind', None), 'events': self.events}


def arm_targets_from_teacher(teacher, *, hover_z=.095, place_deep_m=None):
    """Runner glue (needs the simulator arm model). Reuses the grasp teacher's
    own recorded grasp point and the same IK the pick used
    (``sim/grasp_act_teacher.py::_queue_pick``): place = grip site back at the
    grasp height (gripper closed 1500), hover = gripper open at hover_z.
    ``place_deep_m`` (floor_contact_v1 only) adds place_deep = grip site
    place_deep_m below the grasp height; the IK may clamp it [확인 필요 on gcp6]."""
    from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
    xyz = getattr(teacher, 'grasp_xyz', None)
    if xyz is None:
        return None
    grip = solve_grip_site_ik(xyz)
    pitch = tool_pose(grip).pitch_deg
    place = {**solve_grip_site_ik(xyz, preferred_pitch_deg=pitch), 1: 1500}
    hover = {**solve_grip_site_ik((xyz[0], xyz[1], hover_z), preferred_pitch_deg=pitch), 1: GRIPPER_OPEN}
    pan = int(teacher.sink.pwm[6])
    out = {'place': {**{int(k): int(v) for k, v in place.items()}, 6: pan},
           'hover': {**{int(k): int(v) for k, v in hover.items()}, 6: pan}}
    if place_deep_m is not None:
        deep = {**solve_grip_site_ik((xyz[0], xyz[1], xyz[2] - place_deep_m), preferred_pitch_deg=pitch), 1: 1500}
        out['place_deep'] = {**{int(k): int(v) for k, v in deep.items()}, 6: pan}
    return out


def static_map_for(scene_config, *, door_id='door_wide', zone='zone_B'):
    """The scene's own static map must carry the door and zone definitions."""
    static = scene_config.get('static_map') or {}
    if not any(p.get('id') == door_id for p in static.get('passages', ())) or zone not in static.get('regions', {}):
        # TODO(P2): confirm on gcp6 that the r13 v7 scenario map is
        # zone_wide_two_doors_final_v3 and exposes passages/regions in
        # scene.config['static_map']; otherwise resolve it via
        # harness.zone_final_environment.resolve(map_id) with its hash checks.
        raise NotImplementedError(f'scene static map {static.get("map_id")!r} lacks {door_id}/{zone}')
    return static


def carry_obstacles(truth, roles):
    """GT discs for the first (free-room) segment: other cargo/objects and idle robots."""
    out = [{'id': k, 'xy': list(v['xy']), 'radius': float(v['radius'])}
           for k, v in truth.get('objects', {}).items() if k != 'beam_1']
    out += [{'id': rid, 'xy': list(v['pose'][:2]), 'radius': ROBOT_RADIUS_M}
            for rid, v in truth['robots'].items() if rid not in roles]
    return out


def start_from_runner(plan, truth, now, scene, teachers, previous, carry_cap_s, lower_mode='grasp_height'):
    """Runner glue called once at the joint-hold handover (scripts/run_grasp_act_teacher.py)."""
    if lower_mode not in LOWER_MODES:
        raise ValueError(f'unknown lower mode {lower_mode!r}')
    params = Params(carry_cap_s=float(carry_cap_s), lower_mode=lower_mode)
    if lower_mode == 'floor_contact_v1':
        params = Params(carry_cap_s=float(carry_cap_s), lower_mode=lower_mode,
                        phase_caps_s={**params.phase_caps_s, 'lower': params.lower_max_s + 1.})
    static = static_map_for(scene.config)
    deep = params.place_deep_m if lower_mode == 'floor_contact_v1' else None
    targets = {rid: arm_targets_from_teacher(t, place_deep_m=deep) for rid, t in teachers.items()}
    targets = {rid: v for rid, v in targets.items() if v is not None}
    pwm = {rid: {int(k): int(v) for k, v in previous[rid]['pwm'].items()} for rid in teachers}
    return PairCarryTeacherWarp(plan['roles'], truth, now, static, targets, pwm, params=params,
                                obstacles=carry_obstacles(truth, plan['roles']))
