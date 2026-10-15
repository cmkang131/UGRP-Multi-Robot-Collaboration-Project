"""Heavy-crate grasp teacher: the visible_only beam grasp teacher plus a lift barrier.

Differences from the beam (docs: experiments/2026-10-14-crate-teacher/README.md):
- the grasp markers are the crate lugs (sim/cargo_teacher_profile.CRATE);
- the start skew (0..1.5 s, GraspStartSync) only delays the descent and close;
- after the close the robot reports its own READY-TO-LIFT (own issued close sequence
  complete + settle, no contact, no object height) and waits for a second code
  READY/GO/ACK barrier; only then the lift is queued. The 0.25 kg scene keeps
  the same two-robot barrier; historical 0.66-0.68 kg solo limits predate the
  current servo limits and are not applicable.
The default reuses ``VisibleOnlyGraspTeacher``; opt-in crate modes add the
pre-grasp checks and command-space lift described in crate8.md / crate9.md.
"""
from __future__ import annotations
import math
from harness.visual_arm_v3 import solve_grip_site_ik, tool_pose
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_teacher import local
from sim.cargo_teacher_profile import CRATE
from sim.crate_lift_pose import MODES as LIFT_POSE_MODES, CARTESIAN_MODES, ANTIPODAL_OPTION, select_lift_prefix

LIFT_WAIT_LIMIT_S = 20.


class CrateGraspTeacher(VisibleOnlyGraspTeacher):
    def __init__(self, *args, profile=CRATE, crate_lift_pose='off', crate_approach_recovery='off',
                 crate_wall_footprint='off', crate_stances='off', crate_pulse_safety='off', crate_candidate_recovery='off',
                 crate_alignment='off', crate_motion='off', **kwargs):
        from sim.crate_alignment_v14 import MODE as ALIGNMENT
        if crate_alignment not in ('off', ALIGNMENT):
            raise ValueError('unknown crate alignment')
        if crate_alignment != 'off' and (crate_candidate_recovery == 'off' or crate_stances == 'off'):
            raise ValueError('crate14 alignment requires crate13 staging and stances')
        from sim.crate_motion_v15 import MODE as MOTION
        from sim.crate_motion_v16 import MODE as MOTION16
        from sim.crate_motion_v17 import MODES as MOTION17
        if crate_motion not in ('off', MOTION, MOTION16, *MOTION17):raise ValueError('unknown crate motion')
        if crate_motion != 'off' and crate_alignment == 'off':raise ValueError('crate15 requires crate14 alignment')
        self.crate_motion = crate_motion
        self.navigation_cache = {}
        self.navigation_t = None
        self.navigation_budget = None
        self.motion_blocked_since = None
        self.motion_recovery_at = None
        self.motion_blocked_origin = None
        self.motion17 = crate_motion in MOTION17
        self.motion16 = crate_motion == MOTION16 or self.motion17
        self.escape_last = None
        self.escape_no_move_ticks = 0
        self.escape_flip_ticks = 0
        self.escape_no_move_since = None
        self.escape_flip_since = None
        self.motion_clear_since = None
        self.motion_clear_origin = None
        self.teacher_compute_s = 0.
        self.teacher_compute_total_s = 0.
        self.crate15_errors = None
        self.search_view_origin = None
        self.search_view_key = None
        self.search_view_visited = set()
        self.search_view_progress = None
        self.search_view_repeat = 0
        self.crate_alignment = crate_alignment
        self.staging_elapsed_s = 0.
        self.staging_clock_t = None
        self.staging_peer_blocked = False
        self.staging_paused_s = 0.
        self.peer_clock_t = None
        self.peer_clock_blocked = False
        self.peer_elapsed_s = 0.
        from sim.crate_navigation_v12 import WALL_MODE, STANCE_MODE
        from sim.crate_approach_recovery import PULSE_MODES
        if crate_wall_footprint not in ('off',WALL_MODE) or crate_stances not in ('off',STANCE_MODE):
            raise ValueError('unknown crate navigation mode')
        if crate_pulse_safety not in PULSE_MODES:raise ValueError('unknown crate pulse safety')
        if any(v!='off' for v in (crate_wall_footprint,crate_stances,crate_pulse_safety)):
            if crate_approach_recovery=='off' or crate_lift_pose!=ANTIPODAL_OPTION:
                raise ValueError('crate12 navigation requires recovery and antipodal grasp')
        if crate_wall_footprint!='off' and crate_pulse_safety=='off':
            raise ValueError('wall footprint requires swept pulse checks')
        from sim.crate_candidate_recovery import MODE
        if crate_candidate_recovery not in ('off', MODE):
            raise ValueError('unknown crate candidate recovery')
        if crate_candidate_recovery != 'off' and crate_wall_footprint == 'off':
            raise ValueError('staging recovery requires the swept footprint profile')
        self.crate_candidate_recovery = crate_candidate_recovery
        self.staging_since = None
        self.staging_excluded = set()
        self.staging_last = None
        self.staging_repeat = 0
        self.staging_scan_at = -math.inf
        self.crate_wall_footprint=crate_wall_footprint
        self.crate_stances=crate_stances
        self.crate_pulse_safety=crate_pulse_safety
        from sim.crate_approach_recovery import MODES, OPTION
        if crate_approach_recovery not in MODES:
            raise ValueError(f'crate_approach_recovery: {crate_approach_recovery}')
        if crate_approach_recovery == OPTION:
            if crate_lift_pose != ANTIPODAL_OPTION:
                raise ValueError('crate approach recovery requires antipodal grasp')
            kwargs.update(approach_progress='approach_progress_v1', approach_recovery='approach_recovery_v1')
        if crate_lift_pose not in LIFT_POSE_MODES:
            raise ValueError(f'crate_lift_pose: {crate_lift_pose}')
        super().__init__(*args, **kwargs)
        self.cargo_profile = profile
        self.lift_done = False
        self.lift_pose = None
        self.closed_at = None
        self.crate_lift_pose = crate_lift_pose
        self.lift_selection = None
        self.lift_prefix = None
        self.approach_excluded = set()
        # Separate from the common parent's approach_progress mode string.
        self.crate_visible_progress = None
        self.crate_last_visible_t = None
        self.crate_approach_recovery = crate_approach_recovery
        self.crate_recovery_log = []
        if crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            self.approach_grasp_filter = lambda world, pose: visible_grasp(
                world, self.rid, self.end, pose=pose)['valid']
        if crate_lift_pose in CARTESIAN_MODES:
            if self.teacher_stability == 'off' or self.approach_goal_set == 'off':
                raise ValueError('Cartesian crate lift requires alignment and approach goal set')
            from sim.crate_cartesian_lift import STATION_M
            self.staging_distance = STATION_M
            self.approach_choice = (0., STATION_M)
            self.approach_distances = (STATION_M,)
        if crate_stances!='off':
            from sim.crate_navigation_v12 import ANGLES_DEG,DISTANCES_M,stance_grasp_valid
            self.approach_angles=ANGLES_DEG
            self.approach_distances=tuple(dict.fromkeys((self.staging_distance,*DISTANCES_M)))
            self.approach_grasp_filter=lambda world,pose:stance_grasp_valid(world,self.rid,self.end,pose)
        if crate_alignment != 'off':
            from sim.crate_alignment_v14 import STATION_M, DISTANCES_M, stance_valid
            self.staging_distance = STATION_M
            self.approach_choice = (0., STATION_M)
            self.approach_distances = DISTANCES_M
            self.approach_grasp_filter = lambda world, pose: stance_valid(world, self.rid, self.end, pose)

    def _alignment_bands(self):
        if self.crate_alignment == 'off':
            return super()._alignment_bands()
        from sim.crate_alignment_v14 import INNER, OUTER
        return INNER, OUTER

    def _alignment_settled(self, truth, errors):
        if self.crate_alignment == 'off':
            return super()._alignment_settled(truth, errors)
        self.crate15_errors = tuple(errors)
        inner, _ = self._alignment_bands()
        return self.ready_geometry(truth) and all(abs(e) <= b for e, b in zip(errors, inner))

    def _resume_alignment(self, errors):
        if self.crate_alignment != 'off' and not any(self.align_active):
            inner, _ = self._alignment_bands()
            axis = max(range(3), key=lambda i: abs(errors[i])/inner[i])
            if abs(errors[axis]) > 1e-9:
                self.align_active[axis] = True

    def _wait_ready(self, truth, now):
        if self.crate_alignment != 'off':
            return self._approach(truth, now)
        return super()._wait_ready(truth, now)

    def _continuous(self, now, forward, left, turn):
        if self.crate_motion != 'off' and self.phase in ('align', 'ready') and self.crate15_errors is not None:
            from sim.crate_motion_v15 import alignment_pulse
            return alignment_pulse(self._hold(now), (forward,left,turn), self.crate15_errors)
        value = super()._continuous(now, forward, left, turn)
        if self.crate_alignment != 'off' and self.phase in ('align', 'ready'):
            from harness.grasp_act_contract import wheel_mix, command
            desired = wheel_mix([3.*forward, 3.*left, .65*turn])
            # Reactivating an axis must survive the duty encoder's 1 ms
            # truncation. Retain the existing alignment 40 ms pulse floor,
            # including READY waiting. The normal swept safety check follows.
            for i, effort in enumerate(desired):
                if effort:
                    value['wheels'][i] = math.copysign(.35, effort)
                    value['duration_s'][i] = max(.04, value['duration_s'][i])
            return command(value)
        return value

    def _observe_stable(self, world, now):
        value = super()._observe_stable(world, now)
        if self.crate_motion == 'off' or value is None or self.phase != 'search' or not self.folded_ready:
            return value
        # View acquisition around a CURRENTLY visible body, never the inferred
        # hidden assigned lug. Ordinary pan/body scan remains when no body is seen.
        obj=world['objects'].get(self.cargo_profile.item_id)
        if obj is None or self.cargo_profile.item_id not in world['visibility'][self.rid]['objects']:
            return value
        from sim.grasp_act_visible_route import drive
        pose=world['robots'][self.rid]['pose'];centre=obj['xy'];nav=self._navigation(world)
        if self.search_view_progress is not None:
            key,at,before=self.search_view_progress
            if now-at>=1.-1e-8:
                self.search_view_repeat=self.search_view_repeat+1 if math.dist(pose[:2],before)<.01 else 0
                self.search_view_progress=(key,now,tuple(pose[:2]))
                if self.search_view_repeat>=3:
                    self.search_view_visited.add(key);self.search_view_key=None
                    self.search_view_progress=None;self.search_view_repeat=0
        if self.search_view_origin is None:
            self.search_view_origin=math.atan2(pose[1]-centre[1],pose[0]-centre[0])
        choices=([self.search_view_key] if self.search_view_key is not None else [])
        choices += [k for k in (60,-60,90,-90,120,-120,180) if k not in self.search_view_visited and k not in choices]
        for key in choices:
            angle=self.search_view_origin+math.radians(key)
            goal=(centre[0]+.45*math.cos(angle),centre[1]+.45*math.sin(angle))
            if math.dist(pose[:2],goal)<.04:
                self.search_view_visited.add(key);self.search_view_key=None
                continue
            heading=math.atan2(centre[1]-goal[1],centre[0]-goal[0])
            if not nav.free(goal,heading):continue
            path=nav.path(pose[:2],goal,heading)
            target=nav.waypoint(pose[:2],path,centre)
            if target is None:continue
            self.search_view_key=key
            if self.search_view_progress is None or self.search_view_progress[0]!=key:
                self.search_view_progress=(key,now,tuple(pose[:2]));self.search_view_repeat=0
            self.crate_recovery_log.append({'t':now,'recovery':'visible_body_side_view',
                'body_source':'current_visible_cargo','hidden_lug_read':False,'view_deg':key,'goal':goal})
            return self._continuous(now,**drive(pose,goal,target,centre))
        return value

    def _peer_wait_expired(self, now, blocked):
        if self.crate_alignment == 'off':
            return super()._peer_wait_expired(now, blocked)
        if self.peer_clock_t is not None and not self.peer_clock_blocked:
            self.peer_elapsed_s += max(0., now-self.peer_clock_t)
        self.peer_clock_t = now
        self.peer_clock_blocked = blocked
        return self.peer_elapsed_s >= 12.-1e-8

    def _peer_route(self, world, goal, now):
        if self.motion16:
            nav = self._navigation(world)
            pose = world['robots'][self.rid]['pose']
            target = nav.waypoint(pose[:2], self.path, nav.focus or goal)
            if not nav.free(goal, nav.heading_at(goal, pose[2])) or target is None:
                self._motion_blocked(world, now)
                return self._hold(now)
            return None
        if self.crate_motion != 'off':
            # Peer footprints already constrain every goal, route and pulse.
            # Do not reintroduce the old circular peer-wait gate here.
            return None
        value = super()._peer_route(world, goal, now)
        if self.crate_alignment != 'off' and self.peer_wait_since is None:
            self.peer_clock_t = None
            self.peer_elapsed_s = 0.
            self.peer_clock_blocked = False
        return value

    def _staging_clock(self, now):
        if self.staging_since is None:
            return
        if self.staging_clock_t is not None:
            dt = max(0., now-self.staging_clock_t)
            if self.staging_peer_blocked:
                self.staging_paused_s += dt
            else:
                self.staging_elapsed_s += dt
        self.staging_clock_t = now

    def _staging_expired(self, now):
        if self.motion16:
            # Wall time in SIM seconds includes all peer pauses. At 12 s the
            # step-level recovery retreats/relooks; at 24 s it hands off.
            return self.motion_blocked_since is not None and now-self.motion_blocked_since >= 24.-1e-8
        if self.crate_alignment == 'off':
            return self.staging_since is not None and now-self.staging_since >= 12.-1e-8
        self._staging_clock(now)
        return self.staging_elapsed_s >= 12.-1e-8

    def _navigation(self, world):
        if self.motion16:
            from sim.crate_motion_v16 import Navigation, MAX_TICK_EXPANSIONS
            if self.motion17:
                from sim.crate_motion_v17 import Navigation
            if self.navigation_t != world['t']:
                self.navigation_cache = {}
                self.navigation_t = world['t']
                self.navigation_budget = {'remaining': MAX_TICK_EXPANSIONS}
            snapshot = {k: world[k] for k in ('t', 'robots', 'beam', 'visibility', 'objects', 'walls')}
            search = self.phase in ('search', 'relook')
            key = (self.folded_ready, search, repr(snapshot))
            if key not in self.navigation_cache:
                self.navigation_cache[key] = Navigation(snapshot, self.rid, self.folded_ready,
                    self.cargo_profile, self.bounds, end=self.end, search=search, budget=self.navigation_budget)
            return self.navigation_cache[key]
        if self.crate_motion != 'off':
            from sim.crate_motion_v15 import Navigation
            return Navigation(world,self.rid,self.folded_ready,self.cargo_profile,self.bounds,end=self.end)
        if self.crate_wall_footprint=='off':return None
        from sim.crate_navigation_v12 import WallFootprint
        return WallFootprint(world,self.rid,self.folded_ready,self.cargo_profile,self.bounds)

    def _motion_blocked(self, world, now):
        if self.motion17:
            self.motion_clear_since = None
            self.motion_clear_origin = None
        if self.motion_blocked_since is None:
            self.motion_blocked_since = now
            self.motion_blocked_origin = tuple(world['robots'][self.rid]['pose'][:2])

    def _motion17_progress(self, world, now, value, *, escape):
        """Only admitted issued pose/bearing, never measured simulator motion."""
        from harness.grasp_act_visible_world import command_delta
        pose = tuple(world['robots'][self.rid]['pose'])
        dx, dy, da = command_delta(value, .1)
        sign = 0 if abs(da) < 1e-8 else (1 if da > 0 else -1)
        if escape:
            self.motion_clear_since = None; self.motion_clear_origin = None
            previous = self.escape_last
            no_move = (math.hypot(dx, dy) < .0005 or
                       previous is not None and math.dist(pose[:2], previous[0][:2]) < .0005)
            flipped = previous is not None and sign*previous[1] < 0
            self.escape_no_move_ticks = self.escape_no_move_ticks+1 if no_move else 0
            self.escape_flip_ticks = self.escape_flip_ticks+1 if flipped else (1 if sign else 0)
            self.escape_no_move_since = ((now if self.escape_no_move_since is None else self.escape_no_move_since)
                                         if no_move else None)
            self.escape_flip_since = self.escape_flip_since if flipped else (now if sign else None)
            self.escape_last = (pose, sign)
            if self.escape_no_move_ticks >= 10:
                self._motion_blocked(world, self.escape_no_move_since)
            if self.escape_flip_ticks >= 10:
                self._motion_blocked(world, self.escape_flip_since)
            return
        self.escape_last = None; self.escape_no_move_since = None; self.escape_flip_since = None
        self.escape_no_move_ticks = 0; self.escape_flip_ticks = 0
        # A recovered usable route with sustained >5mm net progress retires an
        # old deadline; a <5cm recovery must not inherit a stale blocked timer.
        if self.motion_blocked_since is not None and self.approach_plan_valid and math.hypot(dx, dy) >= .0005:
            if self.motion_clear_since is None:
                self.motion_clear_since = now; self.motion_clear_origin = pose[:2]
            if now-self.motion_clear_since >= .5-1e-8 and math.dist(pose[:2], self.motion_clear_origin) >= .005:
                self.motion_blocked_since = None; self.motion_blocked_origin = None
                self.motion_recovery_at = None; self.motion_clear_since = None; self.motion_clear_origin = None
        else:
            self.motion_clear_since = None; self.motion_clear_origin = None

    def navigation_stats(self):
        values = [n.stats for n in self.navigation_cache.values()]
        return {'expansions': sum(v['expansions'] for v in values),
                'budget_exhausted': sum(v['budget_exhausted'] for v in values),
                'remaining_expansions': (self.navigation_budget or {}).get('remaining'),
                'path_pads_m': [p for v in values for p in v['path_pads_m']],
                'attempted_pads_m': [p for v in values for p in v.get('attempted_pads_m', [])],
                'segment_calls': sum(v['segment_calls'] for v in values),
                'segment_cache_hits': sum(v['segment_cache_hits'] for v in values)}

    def _motion_timeout(self, world, now):
        if self.motion_blocked_since is None:
            return None
        elapsed = now-self.motion_blocked_since
        if elapsed >= 24.-1e-8:
            self.outcome = 'approach_blocked_handoff'
            self.crate_recovery_log.append({'t': now, 'recovery': 'crate16_blocked_24s_handoff'})
            return self._hold(now)
        if elapsed >= 12.-1e-8 and self.motion_recovery_at is None:
            self.motion_recovery_at = now
            if self.search_view_key is not None:
                self.search_view_visited.add(self.search_view_key)
            self.search_view_key = None; self.search_view_progress = None
            self.staging_since = None; self.staging_peer_blocked = False
            self.path = []; self.path_goal = None; self.next_plan = now
            self._begin_relook(now, 'crate16_blocked_12s_backoff_relook')
            self.crate_recovery_log.append({'t': now, 'recovery': 'crate16_blocked_12s_backoff_relook',
                                            'next_action': 'checked_backoff_then_other_view', 'elapsed_s': elapsed})
        if self.motion_recovery_at is not None and now-self.motion_recovery_at < 1.-1e-8:
            # This proposal still passes the ordinary SE(2) pulse check. If
            # retreat is obstructed, the arm/body scan supplies reobservation.
            self.arm.tick(now)
            return self._continuous(now, -.05, 0., 0.)
        return None

    def _uses_goal_set(self, world):
        if self.crate_wall_footprint!='off' or self.crate_stances!='off':return True
        return super()._uses_goal_set(world)

    def _begin_relook(self, now, reason):
        if self.crate_lift_pose in CARTESIAN_MODES:
            # Finite recovery: retain the failed stance, re-observe, then use
            # the existing collision-checked alternative-goal planner.
            self.approach_excluded.add(self.approach_choice)
            self.approach_plan_valid = False
            self.crate_visible_progress = None
            self.next_plan = now
        return super()._begin_relook(now, reason)

    def _approach(self, truth, now):
        if (self.crate_candidate_recovery != 'off' and self.phase == 'approach'
                and truth['beam'] is not None and truth['visibility'][self.rid]['visible_probes'] >= 5):
            if not self._plan_approach(truth, now):
                return self._staging_recovery(truth, now), False
            if self.staging_since is not None:
                self.crate_visible_progress = None
            self.staging_since = None
            self.staging_elapsed_s = 0.
            self.staging_clock_t = None
            self.staging_peer_blocked = False
            self.staging_last = None
        if (self.crate_lift_pose in CARTESIAN_MODES and self.phase == 'approach'
                and truth['beam'] is not None and truth['visibility'][self.rid]['visible_probes'] >= 5):
            pose, _, _, goal = self._geometry(truth)
            error = math.dist(pose[:2], goal)
            if (self.crate_approach_recovery != 'off'
                    and (self.crate_last_visible_t is None or now-self.crate_last_visible_t > .15)):
                self.crate_visible_progress = None
            self.crate_last_visible_t = now
            if self.crate_visible_progress is None or error < self.crate_visible_progress[0]-.005:
                self.crate_visible_progress = (error, now)
            elif now-self.crate_visible_progress[1] >= 3.:
                return self._begin_relook(now, 'crate_approach_no_visible_progress_3s')
        return super()._approach(truth, now)

    def _plan_approach(self, world, now):
        old_path, old_goal, old_choice = list(self.path), self.path_goal, self.approach_choice
        valid = super()._plan_approach(world, now)
        if self.motion16:
            if not valid:
                self._motion_blocked(world, now)
            elif (not self.motion17 and self.motion_blocked_origin is not None and
                  math.dist(world['robots'][self.rid]['pose'][:2], self.motion_blocked_origin) >= .05):
                self.motion_blocked_since = None; self.motion_recovery_at = None
                self.motion_blocked_origin = None
        if self.crate_motion != 'off' and not valid and old_path and old_choice not in self.approach_excluded:
            nav=self._navigation(world);pose,g,heading,goal=self._geometry(world)
            nearest=min(range(len(old_path)),key=lambda i:math.dist(pose[:2],old_path[i]))
            remaining=[tuple(pose[:2]),*old_path[nearest:],tuple(goal)]
            if (old_goal is not None and math.dist(goal,old_goal)<=.025
                    and self.approach_grasp_filter(world,(*goal,heading)) and nav.free(goal,heading)
                    and all(nav.segment(a,b,pose[2] if i==0 else nav.heading_at(a,heading),nav.heading_at(b,heading))
                            for i,(a,b) in enumerate(zip(remaining,remaining[1:])))
                    and nav.waypoint(pose[:2],remaining,g) is not None):
                self.path=remaining;self.path_goal=tuple(goal);self.approach_plan_valid=True
                self.approach_blocked_since=None;valid=True
                self.crate_recovery_log.append({'t':now,'recovery':'revalidated_previous_path'})
        if self.crate_candidate_recovery != 'off':
            # This finite staging controller owns the deadline while no grasp
            # pose is reachable; the legacy 3 s deadline must not fire first.
            self.approach_blocked_since = None
            if self.crate_alignment != 'off':
                from sim.crate_alignment_v14 import peer_blocks_stances
                self._staging_clock(now)
                blocked = not valid and peer_blocks_stances(world, self)
                if blocked != self.staging_peer_blocked:
                    self.crate_recovery_log.append({'t': now, 'recovery': 'staging_peer_clock',
                        'paused': blocked, 'elapsed_s': self.staging_elapsed_s,
                        'reason': 'visible_peer_disc' if blocked else 'peer_clear_or_other_cause'})
                self.staging_peer_blocked = blocked
        if (self.crate_approach_recovery != 'off' and not valid and self.goal_set_log
                and self.goal_set_log[-1]['t'] == now):
            candidates = self.goal_set_log[-1]['candidates']
            # Every geometrically legal stance is statically occupied: give
            # navigation an explicit handoff, rather than scanning for 30 s.
            # Never call a peer, path/grid failure or excluded stance static.
            from sim.grasp_act_visible_route import constraints, free
            from scripts.zone_teacher import PeerDisc
            radius, discs, rects = constraints(world, self.rid, self.folded_ready, self.cargo_profile)
            fixed = [d for d in discs if not isinstance(d, PeerDisc)]
            legal = [c for c in candidates if c['reason'] != 'grasp_geometry']
            if self.crate_wall_footprint=='off' and legal and all(c['reason'] == 'blocked_goal' and not free(c['goal'], fixed, rects, radius)
                             for c in legal):
                self._approach_handoff(now)
                self.crate_recovery_log.append({'t': now, 'recovery': 'static_stances_blocked_handoff'})
        return valid

    def _staging_recovery(self, world, now):
        from sim.crate_candidate_recovery import staging_view
        from sim.grasp_act_visible_route import drive
        self.staging_since = now if self.staging_since is None else self.staging_since
        if self._staging_expired(now):
            self.outcome = 'approach_blocked_handoff'
            self.crate_recovery_log.append({'t': now, 'recovery': 'staging_exhausted_handoff'})
            return self._hold(now)
        pose = world['robots'][self.rid]['pose']
        if self.staging_last is not None:
            key, at, before = self.staging_last
            if now-at >= 1.-1e-8:
                self.staging_repeat = self.staging_repeat+1 if math.dist(pose[:2], before) < .01 else 0
                self.staging_last = (key, now, tuple(pose[:2]))
                if self.staging_repeat >= 3:
                    self.staging_excluded.add(key)
                    self.staging_last = None
                    self.staging_repeat = 0
        view = staging_view(world, self, self.staging_excluded)
        if view is None:
            # A blocked footprint is never overridden. Re-observe with the
            # existing compact arm scan; the finite deadline still applies.
            if self.arm.until <= now and now-self.staging_scan_at >= 1.-1e-8:
                offset = 250 if int(now-self.staging_since) % 2 == 0 else -250
                target = max(500, min(2500, self.initial_search_pan+offset))
                self.arm.queue({**self.sink.pwm, 6: target}, now, duration=.4)
                self.staging_scan_at = now
            self.crate_recovery_log.append({'t': now, 'recovery': 'staging_no_safe_route_reobserve'})
            return self._hold(now)
        if self.staging_last is None or self.staging_last[0] != view['key']:
            self.staging_last = (view['key'], now, tuple(pose[:2]))
            self.staging_repeat = 0
        self.path = view['path']
        self.crate_recovery_log.append({'t': now, 'recovery': 'collision_checked_staging_view',
            'key': view['key'], 'goal': view['goal'], 'target': view['target'], 'ready': False})
        return self._continuous(now, **drive(pose, view['goal'], view['target'], world['beam']['ends'][self.end]))

    def _check_navigation_pulse(self, truth, value, now):
        if self.crate_motion != 'off' and self.phase in ('approach','align','ready','search','relook'):
            nav=self._navigation(truth)
            if self.motion17:
                safe = nav.pulse_safe(value)
                if any(value['wheels']) and self.crate_motion == 'crate_motion_v17':
                    preferred = nav.preferred_escape(value)
                    if preferred is not None:
                        kind, candidate = preferred
                        self._motion17_progress(truth, now, candidate, escape=True)
                        self.crate_recovery_log.append({'t': now, 'recovery': 'crate17_escape', 'kind': kind})
                        return candidate
                if safe:
                    self._motion17_progress(truth, now, value, escape=False)
                    return value
                for kind, candidate in nav.escape_candidates(value):
                    if any(candidate['wheels']) and nav.pulse_safe(candidate):
                        self._motion17_progress(truth, now, candidate, escape=True)
                        self.crate_recovery_log.append({'t': now, 'recovery': 'crate17_escape', 'kind': kind})
                        return candidate
                self._motion_blocked(truth, now)
                self._motion17_progress(truth, now, self._hold(now), escape=True)
                self.next_plan = now
                self.crate_recovery_log.append({'t': now, 'recovery': 'crate17_blocked_hold'})
                return self._hold(now)
            if nav.pulse_safe(value):return value
            if self.crate_motion == 'crate_motion_v16':
                # Preserve search yaw or escape from an admitted margin; never
                # bypass collision checks when a combined pulse is rejected.
                from harness.grasp_act_visible_world import command_delta
                turn = command_delta(value, .1)[2]
                attempts = (self._continuous(now, 0., 0., math.copysign(.15, turn)),
                            self._continuous(now, -.05, 0., 0.))
                for candidate in attempts:
                    if any(candidate['wheels']) and nav.pulse_safe(candidate):
                        self.crate_recovery_log.append({'t': now, 'recovery': 'crate16_safe_escape_pulse'})
                        return candidate
            self.crate_recovery_log.append({'t':now,'recovery':'crate15_unsafe_pulse_hold_replan'})
            self.next_plan=now
            return self._hold(now)
        # A held or invisible assigned lug is never read by this correction.
        if self.crate_approach_recovery == 'off' or self.phase not in ('approach','align','ready','search','relook'):
            return value
        from sim.crate_approach_recovery import safe_pulse
        if (self.phase in ('search','relook') or truth['visibility'][self.rid]['visible_probes'] < 5
                or truth['beam'] is None):
            # Losing the lug must not revoke an already known static wall.
            # Only own issued pose and retained walls are needed for this check.
            if (self.crate_wall_footprint!='off' and any(value['wheels'])
                    and not safe_pulse(value,truth['robots'][self.rid]['pose'],[],truth.get('walls',[]),.13,
                                       mode=self.crate_pulse_safety,wall_footprint=True)):
                self.crate_recovery_log.append({'t':now,'recovery':'persistent_wall_search_hold'})
                return self._hold(now)
            return value
        from sim.grasp_act_visible_route import constraints, waypoint, drive
        pose, g, _, goal = self._geometry(truth)
        radius, discs, rects = constraints(truth, self.rid, self.folded_ready, self.cargo_profile)
        footprint=self.crate_wall_footprint!='off'
        if footprint:rects=truth.get('walls',[])
        safe=lambda c:safe_pulse(c,pose,discs,rects,radius,mode=self.crate_pulse_safety,wall_footprint=footprint)
        if safe(value):
            return value
        # Use the same collision-checked route with yaw decoupled. Recheck
        # the quantized wheel pulse too; no untested fallback can be issued.
        target = waypoint(pose[:2], self.path, discs, rects, radius)
        if target is not None:
            effort = drive(pose, goal, target, g)
            effort['turn'] = 0.
            candidate = self._continuous(now, **effort)
            if any(candidate['wheels']) and safe(candidate):
                self.crate_recovery_log.append({'t': now, 'recovery': 'safe_translation_without_yaw'})
                return candidate
        if self.crate_pulse_safety!='off':
            # Translation into an inflated crate remains rejected. Pure yaw
            # leaves circular cargo clearance unchanged; walls still sweep the
            # oriented chassis. No arbitrary mm tolerance is granted.
            error=math.atan2(g[1]-pose[1],g[0]-pose[0])-pose[2]
            error=math.atan2(math.sin(error),math.cos(error))
            candidate=self._continuous(now,0.,0.,max(-.15,min(.15,.6*error)))
            if any(candidate['wheels']) and safe(candidate):
                self.crate_recovery_log.append({'t':now,'recovery':'no_closer_yaw'})
                return candidate
        self.crate_recovery_log.append({'t': now, 'recovery': 'unsafe_pulse_hold_replan'})
        self.path = []; self.path_goal = None; self.next_plan = now
        return self._hold(now)

    def ready_geometry(self, truth):
        if not super().ready_geometry(truth):
            return False
        if self.crate_lift_pose not in CARTESIAN_MODES:
            return True
        if self.crate_alignment != 'off':
            from sim.crate_alignment_v14 import grasp_valid, OUTER
            from sim.grasp_act_teacher import wrap
            pose, g, heading, _ = self._geometry(truth)
            x, y = local(pose, g)
            errors = (x-self.staging_distance, y, wrap(heading-pose[2]))
            return (all(abs(e) <= b for e, b in zip(errors, OUTER))
                    and grasp_valid(truth, self.rid, self.end, pose))
        if self.crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            if not visible_grasp(truth, self.rid, self.end)['valid']:
                return False
        # This runs only before the pick, on the currently visible assigned lug.
        from sim.crate_cartesian_lift import plan_lift
        pose, g, _, _ = self._geometry(truth)
        x, y = local(pose, g)
        grip = {1: 1500, **solve_grip_site_ik((x, y, g[2]))}
        best, _ = plan_lift(grip)
        return best is not None

    # --- phase bookkeeping ---
    def _set(self, phase, now):
        # The beam teacher ends at 'complete' right after its lift; here the close ends at
        # 'closed' and only the lift (after the barrier) ends at 'complete'.
        if phase == 'complete' and not self.lift_done:
            phase = 'closed'
            self.closed_at = now
            if self.crate_lift_pose != 'off':
                if self.crate_lift_pose in CARTESIAN_MODES:
                    from sim.crate_cartesian_lift import plan_lift
                    self.lift_prefix, self.lift_selection = plan_lift(self.sink.pwm)
                else:
                    self.lift_prefix, self.lift_selection = select_lift_prefix(self.sink.pwm, self.lift_pose)
                if self.lift_prefix is None:
                    self.outcome = 'crate_lift_pose_no_candidate'
        super()._set(phase, now)

    def lift_ready(self):
        """Own READY-TO-LIFT: the issued close sequence has completed (own command history only)."""
        return self.phase == 'closed' and self.outcome is None

    # --- picking: hover, descent, close (no lift yet) ---
    def _queue_pick(self, truth, now):
        if self.crate_alignment != 'off' and not self.ready_geometry(truth):
            self._begin_relook(now, 'crate14_pick_geometry_changed')
            return
        if self.crate_lift_pose == ANTIPODAL_OPTION:
            from sim.crate_antipodal import visible_grasp
            if not visible_grasp(truth, self.rid, self.end)['valid']:
                # READY can become stale during the asynchronous start delay.
                # Replan from current visible inputs before any grasp command.
                self._begin_relook(now, 'crate_grasp_geometry_changed')
                return
        pose = truth['robots'][self.rid]['pose']
        g = truth['beam']['ends'][self.end]
        x, y = local(pose, g)
        self.grasp_xyz = (x, y, g[2])
        self.initial_end_z = g[2]
        grip = solve_grip_site_ik(self.grasp_xyz)
        pitch = tool_pose(grip).pitch_deg
        hover = solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch)
        self.arm.queue({**hover, 1: 2000}, now, duration=1.)
        for i in range(1, 9):
            z = .095+(g[2]-.095)*i/8
            self.arm.queue(solve_grip_site_ik((x, y, z), preferred_pitch_deg=pitch), now, duration=.15, settle=.04)
        self.arm.queue({1: 1500}, now, duration=.8, settle=.5)
        self.lift_pose = solve_grip_site_ik((x, y, .095), preferred_pitch_deg=pitch)
        self._set('pick', now)

    def _queue_lift(self, now):
        if self.crate_lift_pose == 'off':
            self.arm.queue(self.lift_pose, now, duration=1.2, settle=.5)
        else:
            if self.lift_prefix is None:
                self.outcome = 'crate_lift_pose_no_candidate'
                return
            # Issue the already checked command samples at their planned times.
            # v1 is a legacy prefix; Cartesian v1 shares the same rise/time law.
            start = max(now, self.arm.until)
            self.arm.events.extend((start+t, sid, pulse) for t, sid, pulse in self.lift_prefix['events'])
            self.arm.commanded.update(self.lift_prefix['issued_pwm'])
            self.arm.until = start+self.lift_prefix['prefix_duration_s']+.5
        self._set('lift', now)

    # --- stepping ---
    def step(self, truth, now, *, permit_pick=False, permit_lift=False):
        # Same own-command propagation as the parent, but with the extra permit.
        from sim.grasp_act_teacher_v3 import propagate_owned
        from copy import deepcopy
        import time
        at = time.perf_counter()
        if self.motion17 and self.navigation_t != truth['t']:
            # Preserve prepare_signal work within this tick, expire it even on
            # holding ticks that do not call navigation at all.
            self.navigation_t = None; self.navigation_cache = {}; self.navigation_budget = None
        if self.crate_motion == 'crate_motion_v16':
            # No cached visible cargo survives across ticks or into holding.
            self.navigation_t = None; self.navigation_cache = {}
        if self.local_seen is not None and self.last_command is not None and self.last_tick is not None:
            self.local_seen = propagate_owned(self.local_seen, self.last_command, min(.1, now-self.last_tick))
        value, done = self._step(truth, now, permit_pick=permit_pick, permit_lift=permit_lift)
        value = self._check_navigation_pulse(truth, value, now)
        if self.phase in ('align', 'ready', 'pick', 'closed', 'lift', 'complete'):
            self.progress.reset()
        self.last_command = deepcopy(value)
        self.last_tick = now
        self.teacher_compute_s = time.perf_counter()-at
        self.teacher_compute_total_s += self.teacher_compute_s
        return value, done

    def _step(self, truth, now, *, permit_pick, permit_lift=False):
        if self.outcome is not None:
            return self._hold(now), False
        if self.motion16 and self.phase in ('approach', 'align', 'ready', 'search', 'relook'):
            recovery = self._motion_timeout(truth, now)
            if recovery is not None:
                return recovery, False
        if (self.crate_candidate_recovery != 'off' and self.staging_since is not None
                and self.phase in ('approach', 'search', 'relook') and self._staging_expired(now)):
            self.outcome = 'approach_blocked_handoff'
            self.crate_recovery_log.append({'t': now, 'recovery': 'staging_exhausted_handoff'})
            return self._hold(now), False
        if self.phase in ('closed', 'lift'):
            arms_done = self.arm.tick(now)
            if self.phase == 'closed':
                if permit_lift:
                    self._queue_lift(now)
                elif now-self.phase_t > LIFT_WAIT_LIMIT_S:
                    self.outcome = 'lift_barrier_timeout'
                return self._hold(now), False
            if arms_done:
                self.lift_done = True
                self.command_complete = True
                self._set('complete', now)
                return self._hold(now), True
            return self._hold(now), False
        value, done = super()._step(truth, now, permit_pick=permit_pick)
        if self.phase == 'closed':
            # the parent flagged completion at the end of the close; here that is not the end
            self.command_complete = False
            return value, False
        return value, done

    def diagnostic(self):
        return {**super().diagnostic(), 'profile': 'visible_only_crate', 'lift_barrier': True,
                'crate_approach_recovery': self.crate_approach_recovery,
                'crate_wall_footprint': self.crate_wall_footprint,
                'crate_stances': self.crate_stances, 'crate_pulse_safety': self.crate_pulse_safety,
                'crate_candidate_recovery': self.crate_candidate_recovery, 'crate_recovery_log': self.crate_recovery_log,
                'crate_alignment': self.crate_alignment, 'crate_motion': self.crate_motion,
                'teacher_compute_s': self.teacher_compute_s, 'teacher_compute_total_s': self.teacher_compute_total_s,
                'navigation_stats': self.navigation_stats(),
                'staging_clock': {'elapsed_s': self.staging_elapsed_s, 'peer_paused_s': self.staging_paused_s,
                                  'peer_blocked': self.staging_peer_blocked},
                'closed_at': self.closed_at, 'lift_done': self.lift_done,
                'crate_lift_pose': self.crate_lift_pose, 'lift_pose_selection': self.lift_selection,
                **({'excluded_stalled_stances': sorted(self.approach_excluded)}
                   if self.crate_lift_pose in CARTESIAN_MODES else {}),
                'done_semantics': 'own issued close+lift sequence complete after the lift barrier; physical evaluation separate'}
