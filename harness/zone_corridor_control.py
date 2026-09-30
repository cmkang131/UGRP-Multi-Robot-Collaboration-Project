"""T10b own-RGB corridor decision and bounded command loop (offline candidate).

The only read port is observe(own_frame, static_geometry, own_issued_commands).
The write port issue(command) has no return-state contract. Delivered messages
are the existing fixed M2 status wire, identical in all communication modes.
There is no world, peer executor, top camera, setup, referee or GT port.

A real RGB observer and calibrated actuator are deliberately NOT registered by
this module. The legacy study corridor admission remains closed pending their
review, a new execution bundle, and the eight physical acceptance cells.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import math

from harness.zone_corridor_control_plan import (ControlConfig, CorridorPlan, MEMORY_PROFILE,
                                               PROFILE, angle, digest)
from harness.zone_pair_status import (PROFILE as STATUS_PROFILE, PairStatusChannel,
                                      PairStatusEndpoint, finite)

VISIBILITY = frozenset(('clear', 'blocked', 'unknown'))


@dataclass(frozen=True)
class OwnFrame:
    robot_id: str
    sequence: int
    captured_at_s: float
    rgb: bytes


@dataclass(frozen=True)
class OwnView:
    """Observer output, NEVER a host-supplied control input.

    reference_pose is the held item's reference inferred from this actor's own
    RGB; base_yaw_rad is the same actor's own heading. Error bounds include
    localization AND held-item relative-pose uncertainty. Clear means the whole
    short commanded swept volume is visibly free, including stopping distance;
    missing coverage is unknown. Holding is this actor's own grip only.
    """
    reference_pose: tuple
    base_yaw_rad: float
    position_error_m: float
    yaw_error_rad: float
    holding: str
    travel: str
    refuge: str
    source_frame_sequence: int
    source_captured_at_s: float
    source_rgb_sha256: str


@dataclass(frozen=True)
class Command:
    robot_id: str
    issued_at_s: float
    duration_s: float
    forward_m_s: float = 0.
    left_m_s: float = 0.
    yaw_rad_s: float = 0.

    @property
    def moving(self):
        return any((self.forward_m_s, self.left_m_s, self.yaw_rad_s))


@dataclass(frozen=True)
class Decision:
    state: str
    reason: str
    command: Command
    status_messages: tuple
    issued: bool
    passage_observed: bool = False
    delivery_complete: bool = False


class CorridorController:
    """One independently owned actor; instantiate the SAME class/config in all modes.

    Construction snapshots the public plan. No condition argument exists.
    task_id must be a fresh jointly accepted job nonce; roles are supplied by
    the high-level plan, never selected from host/partner state. Pair initial
    entry and each station use the frozen status barrier. Mid-leg pair traffic
    or readiness loss terminates safely; autonomous pair pivot/bay retreat is
    unsupported, so a capable solo actor yields using its own refuge check.
    """
    def __init__(self, robot_id, plan: CorridorPlan, *, task_id, observe, issue,
                 config=ControlConfig()):
        if not isinstance(plan, CorridorPlan):
            raise TypeError('T10a-admitted CorridorPlan required')
        if robot_id not in plan.formation.robots:
            raise ValueError('actor not assigned to formation')
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            raise ValueError('fresh nonempty job nonce required')
        if not callable(observe) or not callable(issue) or not isinstance(config, ControlConfig):
            raise TypeError('own observer, command port and ControlConfig required')
        self.robot_id, self.plan, self.config = robot_id, copy.deepcopy(plan), config
        self.observe, self.issue = observe, issue
        # Role mapping is separate in records, but also binds the pair wire.
        self.task_id = task_id + ':' + digest([plan.route_sha256, plan.assignment_sha256])
        self.bus = PairStatusChannel(self.task_id, participants=plan.formation.robots)
        self.endpoint = PairStatusEndpoint(self.bus, robot_id)
        self.state, self.reason = 'ENTER', 'await_own_rgb'
        self.history, self.audit, self.deliveries = [], [], []
        self.started = self.last_now = None
        self.last_sequence = -1
        self.last_capture = -math.inf
        self.station, self.active = 0, False
        self.wait_started = self.clear_since = None
        self.clear_count = self.exit_count = self.standoffs = 0
        self.wait_resume = None
        self.branch_path, self.branch_index = (), 0
        self.progress_key = self.progress_best = self.progress_at = None
        self.barrier_station = self.barrier_started = None
        self._frame = None

    def record(self):
        return {'profile': PROFILE, 'memory_profile': MEMORY_PROFILE,
                'status_profile': STATUS_PROFILE, 'config': asdict(self.config),
                'config_sha256': digest(asdict(self.config)), **self.plan.record(),
                'robot_id': self.robot_id, 'task_id': self.task_id}

    def _fail(self, reason):
        self.state, self.reason = 'ABORTED', reason

    def _hold(self):
        return Command(self.robot_id, self.last_now, self.config.tick_s)

    def _near(self, pose, target):
        return (math.dist(pose[:2], target[:2]) <= self.config.position_tolerance_m
                and abs(angle(pose[2] - target[2])) <= self.config.yaw_tolerance_rad)

    def _valid_view(self, view):
        if not isinstance(view, OwnView):
            return False
        if (type(view.source_frame_sequence) is not int
                or view.source_frame_sequence != self._frame.sequence
                or not finite(view.source_captured_at_s)
                or view.source_captured_at_s != self._frame.captured_at_s
                or view.source_rgb_sha256 != hashlib.sha256(self._frame.rgb).hexdigest()):
            return False
        p = view.reference_pose
        if not isinstance(p, tuple) or len(p) != 3 or not all(finite(x) for x in p):
            return False
        if not all(finite(x) for x in (view.base_yaw_rad, view.position_error_m, view.yaw_error_rad)):
            return False
        if (not isinstance(view.travel, str) or not isinstance(view.refuge, str)
                or view.travel not in VISIBILITY or view.refuge not in VISIBILITY
                or view.holding not in ('yes', 'no', 'unknown')):
            return False
        radius = max(math.hypot(x, y) for part in self.plan.formation.parts for x, y in part)
        return (0 <= view.position_error_m <= self.config.max_position_error_m
                and 0 <= view.yaw_error_rad <= self.config.max_yaw_error_rad
                and view.position_error_m + radius * view.yaw_error_rad < self.plan.formation.margin_m
                and abs(angle(view.base_yaw_rad - p[2] - self.plan.stations[self.robot_id][2]))
                <= self.config.yaw_tolerance_rad + self.config.max_yaw_error_rad)

    def _receive(self, delivered):
        if not isinstance(delivered, (tuple, list)):
            self._fail('INVALID_DELIVERY')
            return
        for row in delivered:
            if (not isinstance(row, dict) or row.get('robot_id') == self.robot_id
                    or not self.bus.publish(row, self.last_now)):
                self._fail('INVALID_DELIVERY')
                return
            self.deliveries.append({'received_at_s': self.last_now, 'message': dict(row)})

    def _peer_guard(self):
        if not self.plan.pair:
            return True
        peer = next(r for r in self.plan.formation.robots if r != self.robot_id)
        latest = self.bus.latest.get(peer)
        if latest is None:
            if self.last_now - self.started >= self.config.pair_start_timeout_s:
                self._fail('HEARTBEAT_MISSING')
            return False
        if not self.bus.partner_view(self.robot_id, self.last_now)[peer]['alive']:
            self._fail('HEARTBEAT_EXPIRED')
            return False
        if latest['state'] in ('abort', 'stopped', 'invalid_image', 'incompatible', 'uncertain'):
            self._fail('PAIR_MEMBER_FAILED')
            return False
        if latest['state'] == 'done' and self.station < len(self.plan.path) - 1:
            self._fail('PAIR_PROGRESS_DIVERGED')
            return False
        active_states = ('carry', f'carry_go_{self.station}', f'carry_ready_{self.station + 1}')
        if self.active and latest['state'] not in active_states:
            self._fail('PAIR_READINESS_LOST')
            return False
        return True

    def _sync(self, station):
        if not self.plan.pair:
            return True
        if self.barrier_station != station:
            self.barrier_station, self.barrier_started = station, self.last_now
        if self.last_now - self.barrier_started >= self.config.wait_timeout_s:
            self._fail('PAIR_WAIT_TIMEOUT')
            return False
        barrier = self.endpoint.sync_for('carry@' + str(station))
        frame = self._frame
        fid = f'{self.robot_id}-{frame.sequence}-' + hashlib.sha256(frame.rgb).hexdigest()[:12]
        if not barrier.report(self.robot_id, ready=True, observed_at_s=frame.captured_at_s,
                              received_at_s=self.last_now, frame_id=fid):
            self._fail('PAIR_EVIDENCE_REJECTED')
            return False
        decision = barrier.authorize(self.last_now)
        if decision['phase'] == 'ABORT':
            self._fail('PAIR_BARRIER_EXPIRED')
        elif decision['phase'] == 'GO':
            self.barrier_station = self.barrier_started = None
            return True
        return False

    def _clear_streak(self, clear):
        if not clear:
            self.clear_count, self.clear_since = 0, None
            return False
        if self.clear_since is None:
            self.clear_since = self.last_now
        self.clear_count += 1
        return (self.clear_count >= self.config.clear_frames
                and self.last_now - self.clear_since >= self.config.clear_hold_s - 1e-9)

    def _begin_wait(self, resume):
        self.standoffs += 1
        if self.standoffs > self.config.max_standoffs:
            self._fail('REPEATED_STANDOFF')
            return
        self.state, self.reason = 'WAIT_LANE', 'own_rgb_lane_blocked_or_unknown'
        self.wait_started, self.wait_resume = self.last_now, resume
        self.clear_count, self.clear_since = 0, None

    def _choose_yield(self, view):
        """Only SELF feasibility is used; no host grant or peer position is read."""
        p = self.plan
        if p.refuge_path is None or self.station < p.refuge_index:
            self._begin_wait('FOLLOW')
            return
        if view.refuge != 'clear':
            self._fail('REFUGE_UNOBSERVED_OR_BLOCKED')
            return
        self.standoffs += 1
        if self.standoffs > self.config.max_standoffs:
            self._fail('REPEATED_STANDOFF')
            return
        # Reverse ONLY the already observed route prefix to the authored bay
        # junction. Commands issued on a failed leg do not advance station.
        back = (view.reference_pose,) + tuple(reversed(p.path[p.refuge_index:self.station + 1]))
        if not p.contract._lane_sweep(back, p.formation.parts):
            self._fail('RETREAT_SWEEP_REFUSED')
            return
        route = back + p.refuge_path[1:]
        self.branch_path = tuple(v for i, v in enumerate(route) if i == 0 or v != route[i - 1])
        self.branch_index = 1
        self.state, self.reason = 'RETREAT', 'self_feasible_refuge'
        self.active = False
        self.progress_key = None

    def _navigate(self, view, target, key, *, lane):
        pose, p, c = view.reference_pose, self.plan, self.config
        distance = math.dist(pose[:2], target[:2])
        yaw_error = angle(target[2] - pose[2])
        metric = distance + abs(yaw_error) * .2
        if self.progress_key != key:
            self.progress_key, self.progress_best, self.progress_at = key, metric, self.last_now
        elif metric < self.progress_best - c.progress_epsilon_m:
            self.progress_best, self.progress_at = metric, self.last_now
        elif self.last_now - self.progress_at >= c.progress_timeout_s:
            self._fail('OWN_RGB_NO_PROGRESS')
            return self._hold()
        # Check the actual connector from this RGB pose, not just plan vertices.
        sweep = p.contract._lane_sweep if lane else p.contract._sweep
        if not sweep((pose, target), p.formation.parts):
            self._fail('NAVIGATION_SWEEP_REFUSED')
            return self._hold()
        vx = vy = 0.
        if distance > c.position_tolerance_m:
            speed = min(c.speed_m_s, distance / c.tick_s)
            vx, vy = ((target[k] - pose[k]) / distance * speed for k in (0, 1))
        omega = 0. if abs(yaw_error) <= c.yaw_tolerance_rad else math.copysign(
            min(c.yaw_rate_rad_s, abs(yaw_error) / c.tick_s), yaw_error)
        # Solo rotation uses the catalogue grip offset. Pair pivot is refused
        # at plan admission. Opposite carrier headings get opposite body axes.
        sx, sy, _ = p.stations[self.robot_id]
        co, si = math.cos(pose[2]), math.sin(pose[2])
        rx, ry = co * sx - si * sy, si * sx + co * sy
        bx, by = vx - omega * ry, vy + omega * rx
        scale = max(1., math.hypot(bx, by) / c.base_speed_m_s)
        vx, vy, omega, bx, by = (x / scale for x in (vx, vy, omega, bx, by))
        predicted = (pose[0] + vx * c.tick_s, pose[1] + vy * c.tick_s, pose[2] + omega * c.tick_s)
        # Translation + yaw pursuit may differ from T10a's interpolated line.
        # Its actual short commanded sweep must ALSO pass.
        if not sweep((pose, predicted), p.formation.parts):
            self._fail('COMMAND_SWEEP_REFUSED')
            return self._hold()
        co, si = math.cos(view.base_yaw_rad), math.sin(view.base_yaw_rad)
        return Command(self.robot_id, self.last_now, c.tick_s,
                       co * bx + si * by, -si * bx + co * by, omega)

    def _full_exit(self, pose):
        lo, hi, _, _ = self.plan.contract._extent(pose, self.plan.formation.parts)
        cx, _, hx, _, _ = self.plan.geometry.corridor
        return lo > cx + hx if self.plan.direction == 'west_to_east' else hi < cx - hx

    def _advance(self, view):
        p, now = self.plan, self.last_now
        if self.state == 'ENTER':
            if not self._near(view.reference_pose, p.path[0]):
                self._fail('ENTRY_POSE_MISMATCH')
                return self._hold()
            self.state, self.reason = 'FOLLOW', 'entry_observed'
        if self.state in ('WAIT_LANE', 'WAIT_BAY'):
            if (self.state == 'WAIT_BAY'
                    and p.contract.bay_stop(p.formation, view.reference_pose)['static_ok'] is not True):
                self._fail('BAY_NOT_OCCUPIED_BY_SELF')
                return self._hold()
            if now - self.wait_started >= self.config.wait_timeout_s:
                self._fail('WAIT_TIMEOUT')
            elif self._clear_streak(view.travel == 'clear'):
                if self.state == 'WAIT_BAY':
                    if view.refuge != 'clear':
                        self._fail('REENTRY_UNOBSERVED_OR_BLOCKED')
                    else:
                        self.branch_path, self.branch_index = p.refuge_path[::-1], 1
                        self.state, self.reason = 'REENTER', 'own_rgb_lane_cleared'
                        self.progress_key = None
                else:
                    self.state, self.reason = self.wait_resume, 'own_rgb_lane_cleared'
            return self._hold()
        if self.state in ('RETREAT', 'REENTER'):
            if view.refuge != 'clear' or self.state == 'REENTER' and view.travel != 'clear':
                self._fail('REFUGE_TRAFFIC_CONFLICT')
                return self._hold()
            target = self.branch_path[self.branch_index]
            if self._near(view.reference_pose, target):
                self.branch_index += 1
                if self.branch_index == len(self.branch_path):
                    if self.state == 'RETREAT':
                        if p.contract.bay_stop(p.formation, view.reference_pose)['static_ok'] is not True:
                            self._fail('BAY_NOT_OCCUPIED_BY_SELF')
                        else:
                            self.state, self.reason = 'WAIT_BAY', 'own_rgb_refuge_reached'
                            self.wait_started = now
                            self.clear_count, self.clear_since = 0, None
                    else:
                        self.station, self.active = p.refuge_index, False
                        self.state, self.reason = 'FOLLOW', 'own_rgb_reentered'
                return self._hold()
            return self._navigate(view, target, (self.state, self.branch_index), lane=False)
        if self.station == len(p.path) - 1:
            self.state, self.reason = 'VERIFY_EXIT', 'waypoint_is_not_completion'
            if not self._near(view.reference_pose, p.path[-1]) or not self._full_exit(view.reference_pose):
                self._fail('EXIT_NOT_CONFIRMED')
                return self._hold()
            self.exit_count += 1
            if self.exit_count >= self.config.exit_frames and self._sync(self.station):
                self.state, self.reason = 'PASSED', 'own_rgb_full_formation_exit'
            return self._hold()
        target = p.path[self.station + 1]
        if self.active and self._near(view.reference_pose, target):
            if p.pair and view.travel != 'clear':
                self._fail('PAIR_TRAFFIC_STOP')
            else:
                self.station, self.active = self.station + 1, False
                self.progress_key = None
                self.reason = 'waypoint_observed_not_complete'
            return self._hold()
        if view.travel != 'clear':
            if p.pair and (self.active or self.endpoint.latched):
                self._fail('PAIR_TRAFFIC_STOP')
            else:
                self._choose_yield(view)
            return self._hold()
        if p.pair and self.active:
            peer = next(r for r in p.formation.robots if r != self.robot_id)
            if self.bus.latest[peer]['state'] == f'carry_ready_{self.station + 1}':
                self._fail('PAIR_PROGRESS_DIVERGED')
                return self._hold()
        if not self.active:
            if p.pair and not self._near(view.reference_pose, p.path[self.station]):
                self._fail('PAIR_STATION_DIVERGED')
                return self._hold()
            if not self._sync(self.station):
                return self._hold()
            self.active = True
        return self._navigate(view, target, ('FOLLOW', self.station), lane=True)

    def tick(self, frame: OwnFrame, *, now_s, delivered=()):
        """Consume one fresh own frame, issue one bounded command, return own status.

        now_s is this actor's monotonic clock. The coordinator may log SIM time
        separately; this function never queries a simulator. Each accepted frame
        and actual issued command is retained for provenance/progress auditing.
        """
        outgoing_start = len(self.bus.log)
        valid_clock = finite(now_s) and now_s >= 0 and (self.last_now is None or now_s > self.last_now)
        if not valid_clock:
            self._fail('INVALID_CLOCK')
            # A stale/invalid clock cannot extend the last command's lease.
            now_s = self.last_now if self.last_now is not None else 0.
        self.last_now = now_s
        if self.started is None:
            self.started = now_s
        command = self._hold()
        if self.state not in ('ABORTED', 'PASSED'):
            fresh = (isinstance(frame, OwnFrame) and frame.robot_id == self.robot_id
                     and type(frame.sequence) is int and frame.sequence > self.last_sequence
                     and finite(frame.captured_at_s) and 0 <= frame.captured_at_s <= now_s
                     and frame.captured_at_s > self.last_capture
                     and now_s - frame.captured_at_s < self.config.frame_ttl_s
                     and isinstance(frame.rgb, bytes) and bool(frame.rgb))
            if not fresh:
                self._fail('OWN_IMAGE_INVALID')
            elif now_s - self.started >= self.config.passage_timeout_s:
                self._fail('PASSAGE_TIMEOUT')
            else:
                self._frame, self.last_sequence = frame, frame.sequence
                self.last_capture = frame.captured_at_s
                self._receive(delivered)
                peers_ready = self._peer_guard() if self.state != 'ABORTED' else False
                try:
                    view = self.observe(frame, self.plan.geometry, tuple(self.history))
                except Exception:
                    view = None
                if self.state != 'ABORTED':
                    if not self._valid_view(view):
                        self._fail('OWN_VIEW_INVALID_OR_UNCERTAIN')
                    elif view.holding != 'yes':
                        self._fail('OWN_GRIP_NOT_CONFIRMED')
                    elif not self.plan.contract._clear(view.reference_pose, self.plan.formation.parts):
                        self._fail('OWN_POSE_STATIC_CONFLICT')
                    elif peers_ready:
                        command = self._advance(view)
                self.audit.append({'frame_sequence': frame.sequence, 'captured_at_s': frame.captured_at_s,
                                   'rgb_sha256': hashlib.sha256(frame.rgb).hexdigest(),
                                   'state': self.state, 'reason': self.reason})
        if self.state == 'ABORTED':
            command = self._hold()
            self.endpoint.fail(self.reason, now_s)
        elif self.state == 'PASSED':
            self.endpoint.tick('done', now_s)
        elif self.state in ('WAIT_LANE', 'WAIT_BAY'):
            self.endpoint.tick('not_ready', now_s)
        else:
            self.endpoint.tick('carry', now_s)
        issued = False
        try:
            self.issue(command)
            self.history.append(command)
            issued = True
        except Exception:
            self._fail('ACTUATOR_ISSUE_FAILED')
            self.endpoint.fail(self.reason, now_s)
            command = self._hold()
            try:
                self.issue(command)
                self.history.append(command)
                issued = True
            except Exception:
                pass  # failed hold is exposed; never claim an actual stop
        outgoing = tuple(dict(row) for row in self.bus.log[outgoing_start:] if row['robot_id'] == self.robot_id)
        return Decision(self.state, self.reason, command, outgoing, issued, self.state == 'PASSED')
