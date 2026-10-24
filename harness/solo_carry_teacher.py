"""GT single-robot carry teacher: hold -> carry -> door -> zone B slot -> set down -> back off.

DERIVED / UNVERIFIED (solo-e2e/20261024): never exercised by a physics run.
Every number is inherited from ``Params`` of the pair carry teacher (itself a
candidate set, see harness/pair_carry_teacher_warp.py); no new physics
parameter, port or primitive is introduced.

Demonstration-only exception, same status as the pair carry teacher: it reads
the simulator truth snapshot and is never a student input. It starts from the
state where the unchanged ``VisibleOnlyGraspTeacher`` finished its grasp and
the runner measured a stable single-robot lift (finger forces >= 0.5 N,
cargo min_z >= 0.012 m, tilt <= 10 deg for 3 SIM s), then drives ONE robot.

Reuse of the pair executor (no pair sync logic): the phase machine, the
virtual-pose tracker (``_track``), the arm phases (lower / open / raise), the
retreat, the route builder ``carry_route`` (door_wide staging, door passage,
zone B), ``check_route`` (rotate-first alternative) and the command builders
are the pair teacher's, run with a one-robot "formation": the robot plus the
can it holds, rigid in a frame whose yaw is the robot's own heading at the
handover (a can has no heading). Deviations from pair carry:

* last waypoint = the plan-provided zone-B SLOT centre instead of the zone
  centre; the slot rectangle must lie inside zone B and the robot's standing
  pose at the slot must clear the walls;
* ``zone_settle`` checks the true can against the slot rectangle (a disc of
  the can's radius fully inside) instead of the beam footprint;
* no stretch / second robot; obstacles = every other cargo disc (the parked
  pair beam INCLUDED) and the idle robots;
* lower mode is ``grasp_height`` only (floor_contact_v1 is not wired for solo);
  route mode is straight only (no detour search): a blocked route fails
  explicitly as ``route_blocked``.

``VisibleOnlyGraspTeacher._route`` is deliberately not used here: it plans in
the visible-world odometry frame against visible walls, while the slot is a
world-frame plan pose; mixing them would need an unverified frame anchor.
"""
from __future__ import annotations

import math

from harness import solo_carry_contract as sc
from harness.pair_carry_teacher_warp import (
    PHASES, FAIL, HOLD_MIN_FORCE, HOLD_MIN_Z_M, ROBOT_RADIUS_M, Params, PairCarryTeacherWarp,
    arm_targets_from_teacher, carry_route, check_route, compose, make_command, relative,
    rect_distance, static_map_for, wall_rects, zone_of)

SCHEMA = 'ugrp.solo.carry_teacher.v1'
CARGO_RADIUS_M = .019                 # sim/zone_cargo.py CATALOGUE['can'] landing_half_extents_m


def hold_ok(truth, rid):
    return (truth['beam']['min_z'] >= HOLD_MIN_Z_M and min(truth['contacts'][rid]) >= HOLD_MIN_FORCE)


def obstacles_for(truth, rid, cargo_id=sc.CARGO_ITEM_ID):
    """GT discs: every other cargo (the parked beam too) and the idle robots."""
    out = [{'id': k, 'xy': list(v['xy']), 'radius': float(v['radius'])}
           for k, v in truth.get('objects', {}).items() if k != cargo_id]
    out += [{'id': r, 'xy': list(v['pose'][:2]), 'radius': ROBOT_RADIUS_M}
            for r, v in truth['robots'].items() if r != rid]
    return out


class SoloCarryTeacher(PairCarryTeacherWarp):
    def __init__(self, rid, truth, now, static_map, arm_targets, pwm, slot, *, params=Params(),
                 wheel_fn=None, door_id='door_wide', zone=sc.ZONE, obstacles=()):
        if rid != sc.ROBOT_ID:
            raise ValueError('solo carry drives robot r1 only')
        if params.lower_mode != 'grasp_height':
            raise ValueError('solo carry supports lower mode grasp_height only')
        self.rid, self.rids, self.roles = rid, (rid,), {rid: sc.TEACHER_END}
        self.p, self.wheel_fn, self.static_map, self.slot = params, wheel_fn, static_map, slot
        self.t0 = float(now)
        self.pwm = {rid: {int(s): int(v) for s, v in pwm[rid].items()}}
        self.lift_pwm = {rid: dict(self.pwm[rid])}
        self.touch_pwm, self.touch_since = None, None
        self.arm_targets = arm_targets
        cargo = tuple(truth['beam']['pose'])         # key name from the pair snapshot; holds the can
        robot = tuple(truth['robots'][rid]['pose'])
        frame = (cargo[0], cargo[1], robot[2])       # a can has no heading: use the robot's own
        self.offsets = {rid: relative(frame, robot)}
        self.d12_0 = 0.
        self.virtual = frame
        self.phase, self.phase_t, self.outcome = 'carry_hold', self.t0, None
        self.log, self.events = [], [{'t': now, 'event': 'handover', 'cargo': cargo, 'offsets': self.offsets,
                                      'slot': {k: list(v) if isinstance(v, (list, tuple)) else v
                                               for k, v in slot.items()}}]
        self.hold_lost_since = self.stretch_since = self.track_since = None
        self.max_stretch = self.max_track = 0.
        self.retreat_start = {}
        self.route, self.route_info, self.seg = [], {}, 0
        self.route_plans = self.detour_searches = 0
        if not arm_targets or rid not in arm_targets or not {'place', 'hover'} <= set(arm_targets[rid]):
            self._fail('arm_targets_missing', now, detail=[rid])
            return
        self.route_plans += 1
        try:
            route, info = carry_route(frame, self.offsets, static_map, params=params, door_id=door_id, zone=zone)
        except ValueError as error:
            self._fail(str(error), now)
            return
        z = zone_of(static_map, zone)
        slot_pose = tuple(slot['pose'])
        zone_rect = {'pose': (z['cx'], z['cy'], 0.), 'half_extents_m': (z['hx'], z['hy'])}
        corners = [compose(slot_pose, (sx*slot['half_extents_m'][0], sy*slot['half_extents_m'][1], 0.))[:2]
                   for sx in (-1, 1) for sy in (-1, 1)]
        if not all(sc.slot_contains(zone_rect, c, 0., margin=params.zone_inner_margin_m) for c in corners):
            self._fail('zone_unreachable', now, detail='slot rectangle not inside zone B')
            return
        zone_yaw = route[-1][1][2]
        route[-1] = ('to_zone', (slot_pose[0], slot_pose[1], zone_yaw))
        standing = compose(route[-1][1], self.offsets[rid])
        if min((rect_distance(standing[:2], w) for w in wall_rects(static_map)), default=math.inf) < ROBOT_RADIUS_M:
            self._fail('zone_unreachable', now, detail='robot standing pose at the slot touches a wall')
            return
        self.route_info = {**info, 'slot': list(slot_pose)}
        self.route, blocked = check_route(frame, route, self.offsets, wall_rects(static_map), list(obstacles))
        self.route_info['variant'] = 'translate_first' if blocked is None or blocked[0] else 'rotate_first'
        if blocked is not None and not blocked[0]:
            self._fail('route_blocked', now, detail=blocked[1])

    def step(self, truth, now):
        """Return {rid: (command, done)} for this 0.1 s tick."""
        now, rid = float(now), self.rid
        def idle():
            return {rid: (c, True) for rid, c in self._hold_cmds(now).items()}
        if self.phase == 'done':
            return idle()
        if now - self.t0 >= self.p.carry_cap_s - 1e-8:
            self._fail('carry_total_timeout', now)
            return idle()
        cap = self.p.phase_caps_s.get(self.phase)
        if cap is not None and now - self.phase_t >= cap - 1e-8:
            self._fail(FAIL[self.phase], now)
            return idle()
        robots = {rid: tuple(truth['robots'][rid]['pose'])}
        if self.phase in PHASES[:PHASES.index('lower')]:
            if not hold_ok(truth, rid):
                self.hold_lost_since = now if self.hold_lost_since is None else self.hold_lost_since
                if now - self.hold_lost_since >= self.p.hold_lost_s - 1e-8:
                    self._fail('carry_hold_lost', now)
                    return idle()
            else:
                self.hold_lost_since = None
        issue_phase = self.phase
        drive = getattr(self, '_' + self.phase)(truth, robots, now, 0.)
        out = {rid: (make_command(now, self.pwm[rid], drive.get(rid, (0., 0., 0.)), params=self.p,
                                  wheel_fn=self.wheel_fn), self.phase == 'done')}
        self.log.append({'t': now, 'phase': self.phase, 'issue_phase': issue_phase, 'virtual': list(self.virtual),
                         'stretch_m': 0., 'drive': {rid: list(drive.get(rid, (0., 0., 0.)))},
                         'wheels': {rid: list(out[rid][0]['wheels'])},
                         'duration_s': {rid: list(out[rid][0]['duration_s'])}})
        return out

    def _zone_settle(self, truth, robots, now, stretch):
        """Final GT check of the TRUE can against the slot rectangle (not the virtual pose)."""
        target = self.route[-1][1]
        cargo = tuple(truth['beam']['pose'])
        if (math.dist(cargo[:2], target[:2]) <= self.p.zone_tol_xy
                and sc.slot_contains(self.slot, cargo[:2], CARGO_RADIUS_M, margin=self.p.zone_inner_margin_m)):
            self.events.append({'t': now, 'event': 'zone_aligned', 'cargo': cargo})
            self._set('lower', now)
            return {}
        corr = (self.virtual[0] + (target[0]-cargo[0]), self.virtual[1] + (target[1]-cargo[1]), target[2])
        drive, _ = self._track(robots, now, stretch, corr)
        return drive

    def diagnostic(self):
        return {**super().diagnostic(), 'schema': SCHEMA, 'mode': sc.MODE, 'status': sc.STATUS,
                'slot': {k: list(v) if isinstance(v, (list, tuple)) else v for k, v in self.slot.items()}}


def start_from_runner(plan, truth, now, scene, teachers, previous, carry_cap_s):
    """Runner glue, called once at the stable-lift handover (scripts/run_grasp_act_teacher.py)."""
    params = Params(carry_cap_s=float(carry_cap_s))
    rid = sc.ROBOT_ID
    arm = arm_targets_from_teacher(teachers[rid])
    targets = {rid: arm} if arm is not None else {}
    pwm = {rid: {int(k): int(v) for k, v in previous[rid]['pwm'].items()}}
    return SoloCarryTeacher(rid, truth, now, static_map_for(scene.config), targets, pwm, plan['solo_slot'],
                            params=params, obstacles=obstacles_for(truth, rid))
