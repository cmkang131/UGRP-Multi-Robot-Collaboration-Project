"""Opt-in nav-only, two-robot execution mode for scripts/run_e2e_warp.

Contract (2026-10-18, first slice):
- Explicit ``--mode nav`` only. The default ``--mode smoke`` and the existing
  ``--mode mission`` paths are unchanged; nothing here is reachable by default.
- Exactly two robots ``('r1', 'r2')``; the leader rotates ``seed % 2``.
- Admission requires only the ``navigation`` component. ACT, loaded camera FK,
  static-map registration, own/static-map correction and release relocalization
  are neither required nor loaded.
- No static map: only order/condition metadata reaches the navigation adapter
  and the LLM prompt. Map-geometry keys are rejected, never silently stripped.
- Fail closed: nav mode has no evaluator, so a result can never claim E2E or
  physical success, even after an adapter reports ``destination_arrived``.

The real selfnav adapter and own-command odometry are intentionally NOT wired
in this slice; the owner supplies a navigation factory through the manifest.
"""
from __future__ import annotations

import copy

from harness.e2e_warp_components import NAV_REQUIRED, factory

MODE = 'nav'
ROBOTS = ('r1', 'r2')
REQUIRED = NAV_REQUIRED
#: Order-sheet / condition metadata only. Any other key (e.g. static_map,
#: map, geometry, scene) is rejected so a map cannot leak into the prompt or
#: the navigation component.
STATIC_KEYS = ('orders', 'condition', 'goal', 'mission', 'robot_count',
               'destination_zone', 'leader_id', 'role', 'slots')
DEPENDENCY_STATUS = ('nav-only own-input navigation adapter pending; '
                     'selfnav wiring and own-command odometry not injected')


def leader_for_seed(seed):
    """Two-robot rotation: even seed -> r1, odd seed -> r2 (never r3)."""
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError('seed must be an int')
    return ROBOTS[seed % len(ROBOTS)]


#: Map/GT geometry names rejected at *any* nesting depth (independent verifier
#: finding 2026-10-18: top-level checks alone let {'mission': {'static_map': ...}}
#: through to the adapter and the LLM prompt).
FORBIDDEN_KEYS = ('static_map', 'map_geometry', 'wall_map', 'geometry', 'walls',
                  'doors', 'ground_truth', 'groundtruth', 'gt', 'truth', 'pose',
                  'coordinates', 'bounds_m')


def _reject_geometry(value, path='static'):
    """Recursively reject map/GT-like keys; never silently strip them."""
    if isinstance(value, dict):
        for key, item in value.items():
            low = str(key).lower()
            where = path + '.' + low
            if low in FORBIDDEN_KEYS or (low.startswith('static_map') and not isinstance(item, bool)):
                raise ValueError('static map/GT input is forbidden by contract v1 at ' + where)
            _reject_geometry(item, where)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_geometry(item, path + f'[{index}]')
    return value


def nav_static(static):
    """Return only order/condition metadata; reject any map input.

    A missing static is allowed (no map is required), but a mapping is copied
    through an explicit allowlist so the LLM and the navigation adapter can
    never receive static-map geometry by accident.
    """
    if static is None:
        return {}
    if not isinstance(static, dict):
        raise TypeError('static must be a mapping or None')
    unknown = sorted(set(static) - set(STATIC_KEYS))
    if unknown:
        raise ValueError('nav mode accepts order/condition metadata only; rejected keys: '
                         + ','.join(unknown))
    value = {k: copy.deepcopy(static[k]) for k in STATIC_KEYS if k in static}
    return _reject_geometry(value)


def queue_fields(seed, robots=ROBOTS):
    """Explicit queue markers written only by ``--prepare --mode nav``."""
    robots = tuple(robots)
    if not robots or not set(robots) <= set(ROBOTS):
        raise ValueError('invalid execution robot set')
    return dict(nav_only=True, robots=list(robots), leader_id=robots[seed % len(robots)],
                component_requirements=list(REQUIRED), static_map_input=False,
                dependency_status=DEPENDENCY_STATUS)


def validate_queue(queue, seed, robots=ROBOTS):
    """Re-check the prepared nav queue before any physics import.

    This is deliberately fail-closed: a tampered or stale queue cannot turn a
    three-robot (or static-map) run into nav mode.  ``robots`` is the pair, or
    the single robot of the r4 solo diagnostic (validated again in the gate
    queue: the solo marker is r4-only).
    """
    robots = tuple(robots)
    if not robots or not set(robots) <= set(ROBOTS):
        raise ValueError('NAV_ROBOTS_REQUIRED')
    if queue.get('nav_only') is not True:
        raise ValueError('NAV_ONLY_QUEUE_REQUIRED')
    if tuple(queue.get('robots') or ()) != robots:
        raise ValueError('NAV_ROBOTS_REQUIRED')
    if queue.get('leader_id') != robots[seed % len(robots)]:
        raise ValueError('NAV_LEADER_MISMATCH')
    if queue.get('static_map_input') is not False:
        raise ValueError('NAV_STATIC_MAP_INPUT_FORBIDDEN')
    if tuple(queue.get('component_requirements') or ()) != REQUIRED:
        raise ValueError('NAV_COMPONENT_REQUIREMENTS_MISMATCH')
    # A tampered queue cannot smuggle map/GT geometry into the run.
    _reject_geometry(queue, path='queue')
    return queue


def fail_closed_result_fields(robots=ROBOTS):
    """Result markers: nav mode never claims physical or E2E success."""
    robots = tuple(robots)
    return dict(nav_only=True, robots=list(robots),
                component_requirements=list(REQUIRED), static_map_input=False,
                student_execution=False, physical_success_available=False,
                success_claim='not_available', success_evidence=None,
                E2E_success=False, research_result=False)


def all_arrived(tasks):
    """True only when every nav controller reports its own ARRIVED phase.

    Arrival is an unverified own-input claim; it stops the run but is not a
    success claim and is never written to physical-evaluation.json.
    """
    components = [getattr(task, 'component', None) for task in tasks]
    return bool(components) and all(getattr(c, 'phase', None) == 'ARRIVED' for c in components)


class NavigationOnlyController:
    """Navigation-only composition: no ACT, no release, no static map.

    The owner navigation adapter follows the ABI documented by the mission
    composition: ``observe(OwnFrame) -> report``, ``task_candidates(completed)``,
    ``start(instruction, phase)``, ``command(sim_s)`` and ``on_messages(rows)``.
    Wheel commands are issued by the adapter; no odometry is injected here.
    """

    def __init__(self, robot, static, navigation):
        if robot not in ROBOTS:
            raise ValueError('nav mode is two-robot only (r1/r2): ' + str(robot))
        if not (callable(getattr(navigation, 'observe', None))
                and callable(getattr(navigation, 'task_candidates', None))
                and callable(getattr(navigation, 'start', None))
                and callable(getattr(navigation, 'command', None))):
            raise ValueError('navigation adapter does not implement the nav ABI')
        self.robot = robot
        self.static = nav_static(static)
        self.navigation = navigation
        self.phase, self.instruction = 'TASK', None
        self.events, self.completed = [], []
        # r3 fail-safe record: a NO_CLAIM stop is recorded once, next to the
        # ARRIVED events, so the raw run shows why the wheels held.
        self._no_claim_recorded = False

    @property
    def needs_decision(self):
        return self.phase == 'TASK'

    @property
    def complete(self):
        # No evaluator in nav mode: a completion claim would be unfalsifiable.
        return False

    def observe(self, frame):
        if frame.robot_id != self.robot:
            raise ValueError('cross-robot navigation input rejected')
        report = self.navigation.observe(frame)
        if not isinstance(report, dict):
            raise ValueError('navigation report must be a mapping')
        if self.phase == 'NAVIGATE' and report.get('destination_arrived') is True:
            self.events.append(dict(sim_s=frame.sim_s, before=self.phase, after='ARRIVED',
                                    reason='own-input destination_arrived (unverified)'))
            self.phase = 'ARRIVED'
        if (self.phase == 'NAVIGATE' and report.get('arrival_no_claim') is True
                and not self._no_claim_recorded):
            # r3 fail-safe: the path cap was spent without reaching the projection
            # claim.  Recorded once; the wheels hold and no arrival is claimed.
            self._no_claim_recorded = True
            self.events.append(dict(sim_s=frame.sim_s, before=self.phase, after=self.phase,
                                    reason='NO_CLAIM: path cap reached with d_proj below the claim'))
        return dict(phase=self.phase, own_navigation=report,
                    physical_success_available=False, arrival_claim_verified=False)

    def candidates(self):
        candidates = self.navigation.task_candidates(list(self.completed))
        if not isinstance(candidates, list):
            raise ValueError('navigation candidates must be a list')
        return candidates

    def select(self, candidate, now, *, reason=None):
        if not isinstance(candidate, dict):
            raise ValueError('navigation candidate must be a mapping')
        self.instruction = copy.deepcopy(candidate)
        self.navigation.start(copy.deepcopy(candidate), 'navigate')
        self.events.append(dict(sim_s=float(now), before=self.phase, after='NAVIGATE',
                                reason=(reason or 'LLM selected a navigation candidate')))
        self.phase = 'NAVIGATE'

    def receive(self, rows):
        if rows:
            self.navigation.on_messages(copy.deepcopy(rows))

    def command(self, now):
        return self.navigation.command(now)


class NavRobot:
    """Runner task for nav mode, mirroring the MissionRobot protocol."""
    def __init__(self, robot, static, components, *, navigation_factory=None):
        if robot not in ROBOTS:
            raise ValueError('nav mode is two-robot only (r1/r2): ' + str(robot))
        static = nav_static(static)
        if 'navigation_factory' not in components:
            raise ValueError('DEPENDENCY_WAIT:hash-bound navigation_factory')
        build = navigation_factory or factory(components['navigation_factory'])
        navigation = build(robot_id=robot, static=static)
        self.component = NavigationOnlyController(robot, static, navigation)
        self.command_history = []
        self.pending_inbox = []

    def observe(self, frame):
        return self.component.observe(frame)

    def candidates(self):
        return self.component.candidates()

    def receive(self, rows):
        self.pending_inbox.extend(copy.deepcopy(rows))
        return self.component.receive(copy.deepcopy(rows))

    def take_inbox(self):
        rows, self.pending_inbox = self.pending_inbox, []
        return rows

    def select(self, candidate, now, *, reason=None):
        return self.component.select(candidate, now, reason=reason)

    def command(self, now):
        from harness.grasp_act_contract import command
        result = command(self.component.command(now))
        self.command_history.append(result)
        return result

    @property
    def complete(self):
        return self.component.complete is True
