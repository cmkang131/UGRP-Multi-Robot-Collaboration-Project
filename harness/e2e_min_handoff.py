"""Minimal E2E (N2) handoff: allocate -> grasp -> carry (nav) -> release.

Default OFF (env ``E2E_MIN_HANDOFF=on_v1``).  This module is the *controller-side*
phase state machine only.  It never reads GT, the static map or simulator
state; it sees only what each executor proposes (own command + own done/arrival
flags) and the L1-lite allocation record.

Phases per robot (see experiments/2026-10-21-e2e-min/DESIGN.md §3)::

    ALLOCATE -> {ACT_GRASP | TEACHER_GRASP} -> NAV_CARRY
             -> {ACT_RELEASE | TEACHER_RELEASE} -> DONE
    any phase -> FAIL(code)           (fail-closed, terminal)

Which grasp/release executor runs is fixed by the level (E2E-0/1/2) before the
run; every teacher-substituted step is written to the queue field
``e2e_substitutions`` and to the handoff log (never to a video overlay).

Command hold rules (DESIGN.md §3.3):

* H1 phase-entry tick: wheels 0, PWM = held PWM.  No executor output is issued
  on the tick a transition happens.
* H2 grasp done -> settle: for ``settle_s`` after the grasp done tick the robot
  holds (wheels 0, held PWM) and the nav adapter is NOT queried, so its own
  issued-pulse odometry never integrates a command that was not issued.
* H3 NAV_CARRY: wheels and pulse widths come unchanged from nav; all five PWM
  channels are replaced by the held PWM (``last_hold_all_servos_v1``).
* H4 release entry: the release executor starts from the held PWM.
* H5 DONE: wheels 0, last issued PWM.  FAIL: wheels 0, last issued PWM (the
  gripper is never opened by a failure).

Connection points to the scene/physics owner and to the ACT/teacher/nav
executors that are NOT verified yet raise ``NotImplementedError`` with an
``E2E_MIN_TODO:<id>`` tag; see ``INTEGRATION_POINTS`` and DESIGN.md §6.
"""
from __future__ import annotations

import copy
import os

ENV = 'E2E_MIN_HANDOFF'
MODE = 'on_v1'
SCHEMA = 'ugrp.e2e_min.handoff.v1'
ROBOTS = ('r1', 'r2')
SLOTS = ('left', 'right')
SERVOS = ('1', '3', '4', '5', '6')

ALLOCATE = 'ALLOCATE'
ACT_GRASP = 'ACT_GRASP'
TEACHER_GRASP = 'TEACHER_GRASP'
NAV_CARRY = 'NAV_CARRY'
ACT_RELEASE = 'ACT_RELEASE'
TEACHER_RELEASE = 'TEACHER_RELEASE'
DONE = 'DONE'
FAIL = 'FAIL'
PHASES = (ALLOCATE, ACT_GRASP, TEACHER_GRASP, NAV_CARRY, ACT_RELEASE, TEACHER_RELEASE, DONE, FAIL)
GRASP_PHASES = (ACT_GRASP, TEACHER_GRASP)
RELEASE_PHASES = (ACT_RELEASE, TEACHER_RELEASE)
TERMINAL = (DONE, FAIL)
#: Stage names used by the evaluator's per-stage reach table.
STAGE_OF = {ALLOCATE: 'allocate', ACT_GRASP: 'grasp', TEACHER_GRASP: 'grasp',
            NAV_CARRY: 'carry', ACT_RELEASE: 'release', TEACHER_RELEASE: 'release',
            DONE: 'done', FAIL: 'fail'}

LEVELS = {
    'E2E-0': dict(grasp='teacher', release='teacher', label='배관 확인, 연구 결과 아님'),
    'E2E-1': dict(grasp='act', release='teacher', label='혼합 E2E(내려놓기 teacher)'),
    'E2E-2': dict(grasp='act', release='act', label='순수 E2E'),
}
HOLD_RULES = ('last_hold_all_servos_v1', 'gripper_hold_arm_search_v1')
DEFAULT_HOLD_RULE = 'last_hold_all_servos_v1'

#: Phase SIM-second budgets.  grasp 90 s = the ACT full-evaluation cap
#: (warp_act_api.py:410, 900 ticks); settle 3.1 s = SoloSequence SETTLE_S
#: (grasp_act_rollout.py:92-106); carry 60 s = nav SIM_BUDGET_S
#: (e2ewarp_nav_gate.py:67).  release 45 s is a placeholder [확인 필요] that the
#: prereg must freeze before any run.
DEFAULT_TIMEOUTS = dict(grasp=90.0, settle=3.1, carry=60.0, release=45.0)

ERRORS = {
    'E2E_ALLOC_FAILED': 'allocation record missing, fatal or not success-eligible',
    'E2E_ALLOC_SLOTS_INVALID': 'decided slots are not one distinct left/right per robot',
    'E2E_GRASP_TIMEOUT': 'no grasp done within the grasp budget',
    'E2E_GRASP_EXECUTOR_ERROR': 'grasp executor raised or returned an invalid proposal',
    'E2E_HOLD_MISSING': 'grasp done without a valid issued PWM to hold',
    'E2E_NAV_NO_CLAIM': 'nav latched NO_CLAIM (projection path cap) while carrying',
    'E2E_NAV_TIMEOUT': 'no arrival claim within the carry budget',
    'E2E_NAV_EXECUTOR_ERROR': 'nav adapter raised or returned an invalid command',
    'E2E_RELEASE_TIMEOUT': 'no release done within the release budget',
    'E2E_RELEASE_EXECUTOR_ERROR': 'release executor raised or returned an invalid proposal',
    'E2E_EVENT_OUT_OF_ORDER': 'tick time went backwards or a phase was driven twice',
}

#: Unverified connection points (DESIGN.md §6).  Each raises NotImplementedError.
INTEGRATION_POINTS = (
    'world_builder',        # v6 two-robot world WITH cubes + finger/cargo contact pairs
    'act_skill_client',     # ACT actor RPC on the nav runner's own frames (r1 and r2)
    'teacher_skill',        # scripted SoloTeacher grasp/release inside the nav runner
    'nav_carry_adapter',    # nav adapter started from the post-grasp pose with held arm
    'runner_loop',          # run_e2e_warp tick loop routing + no early NAV_ARRIVAL stop
    'eval_cube_geometry',   # cube qpos address / half size written to eval-geometry.json
    'gripper_hold_arm_search_v1',  # alternative hold rule (arm back to SEARCH)
)


class E2EMinError(ValueError):
    def __init__(self, code, detail=''):
        if code not in ERRORS:
            raise ValueError('unknown E2E error code: ' + str(code))
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code, self.detail = code, detail


def enabled(environ=None):
    """True only for the exact opt-in; any other non-empty value fails closed."""
    value = (os.environ if environ is None else environ).get(ENV, '')
    if value == '':
        return False
    if value != MODE:
        raise ValueError(f'{ENV} must be unset or {MODE!r}, got {value!r}')
    return True


def substitutions(level):
    """Teacher-substituted steps for a level, e.g. ['release:teacher']."""
    spec = _level(level)
    return [f'{step}:teacher' for step in ('grasp', 'release') if spec[step] == 'teacher']


def queue_fields(level, hold_rule=DEFAULT_HOLD_RULE):
    _level(level)
    if hold_rule not in HOLD_RULES:
        raise ValueError('unknown hold rule: ' + str(hold_rule))
    return dict(e2e_min=MODE, e2e_level=level, e2e_substitutions=substitutions(level),
                e2e_overlay_text=False, e2e_hold_rule=hold_rule,
                e2e_label=LEVELS[level]['label'])


def validate_queue(queue):
    """Fail closed unless the queue's E2E markers are exactly consistent."""
    if not isinstance(queue, dict) or queue.get('e2e_min') != MODE:
        raise ValueError('E2E_QUEUE: e2e_min=on_v1 required')
    level = queue.get('e2e_level')
    expected = queue_fields(level, queue.get('e2e_hold_rule', DEFAULT_HOLD_RULE))
    for key, value in expected.items():
        if queue.get(key) != value:
            raise ValueError(f'E2E_QUEUE: {key}={queue.get(key)!r} != {value!r}')
    return expected


def _level(level):
    if level not in LEVELS:
        raise ValueError('unknown E2E level: ' + str(level))
    return LEVELS[level]


def check_command(row):
    """Own-command whitelist (same ranges as grasp_act_contract.command)."""
    from harness.grasp_act_contract import command
    return command(row)


def hold_command(now, pwm):
    return dict(t=float(now), wheels=[0.0] * 4, duration_s=[0.0] * 4, pwm=dict(pwm))


def held_pwm(last_pwm, rule=DEFAULT_HOLD_RULE):
    """PWM to hold while carrying.  Only the directive's rule is implemented."""
    if rule == 'last_hold_all_servos_v1':
        pwm = {str(k): v for k, v in dict(last_pwm or {}).items()}
        if set(pwm) != set(SERVOS) or any(type(v) is not int or not 500 <= v <= 2500
                                          for v in pwm.values()):
            raise E2EMinError('E2E_HOLD_MISSING', repr(last_pwm))
        return pwm
    if rule == 'gripper_hold_arm_search_v1':
        # TODO(E2E_MIN_TODO:gripper_hold_arm_search_v1): moving the arm back to
        # SEARCH while the gripper holds the cube would restore the nav camera
        # mount (selfnav GATE_GROUND_PROJECTION fit at SEARCH), but whether the
        # cube stays held through that arm motion is unmeasured.
        raise NotImplementedError('E2E_MIN_TODO:gripper_hold_arm_search_v1')
    raise ValueError('unknown hold rule: ' + str(rule))


class RobotHandoff:
    """One robot's phase machine.  Pure: no I/O, no simulator, no GT."""

    def __init__(self, robot, level, *, hold_rule=DEFAULT_HOLD_RULE, timeouts=None,
                 initial_pwm=None):
        if robot not in ROBOTS:
            raise ValueError('unknown robot: ' + str(robot))
        self.robot, self.level, self.spec = robot, level, _level(level)
        if hold_rule not in HOLD_RULES:
            raise ValueError('unknown hold rule: ' + str(hold_rule))
        self.hold_rule = hold_rule
        self.timeouts = {**DEFAULT_TIMEOUTS, **(timeouts or {})}
        self.phase, self.slot = ALLOCATE, None
        self.fail_code = self.fail_detail = None
        self.entered_at = 0.0
        self.last_t = None
        self.hold_pwm = None
        self.settle_until = None
        self.last_pwm = dict(initial_pwm) if initial_pwm else None
        self.transitions = []
        self.reach = {ALLOCATE: 0.0}
        self.commands = 0

    # -- transitions -----------------------------------------------------
    def _go(self, now, phase, reason, code=None):
        self.transitions.append(dict(robot=self.robot, sim_s=round(float(now), 3),
                                     **{'from': self.phase}, to=phase, reason=reason,
                                     code=code))
        self.phase, self.entered_at = phase, float(now)
        self.reach.setdefault(phase, round(float(now), 3))

    def fail(self, now, code, detail=''):
        if code not in ERRORS:
            raise ValueError('unknown E2E error code: ' + str(code))
        if self.phase in TERMINAL:
            return
        self.fail_code, self.fail_detail = code, str(detail)
        self._go(now, FAIL, 'fail-closed', code=code)

    def allocated(self, now, slot):
        if self.phase != ALLOCATE:
            raise E2EMinError('E2E_EVENT_OUT_OF_ORDER', f'{self.robot} allocated in {self.phase}')
        if slot not in SLOTS:
            return self.fail(now, 'E2E_ALLOC_SLOTS_INVALID', repr(slot))
        self.slot = slot
        grasp = ACT_GRASP if self.spec['grasp'] == 'act' else TEACHER_GRASP
        self._go(now, grasp, f'slot {slot} allocated by LLM')

    # -- per tick --------------------------------------------------------
    def source(self, now):
        """Which executor to query this tick: 'grasp'|'nav'|'release'|None (hold)."""
        if self.phase in GRASP_PHASES:
            return 'grasp'
        if self.phase == NAV_CARRY:
            return None if (self.settle_until is not None and now < self.settle_until - 1e-9
                            or now == self.entered_at) else 'nav'
        if self.phase in RELEASE_PHASES:
            return None if now == self.entered_at else 'release'
        return None

    def tick(self, now, proposal=None):
        """Advance one control tick and return the command to issue.

        ``proposal`` is what the queried executor returned for this tick:
        grasp/release ``{'command': cmd, 'done': bool}``; nav
        ``{'command': cmd, 'arrived': bool, 'no_claim': bool}``.  ``None`` when
        :meth:`source` said hold.  A missing or invalid proposal for a queried
        source fails closed.
        """
        now = float(now)
        if self.last_t is not None and now < self.last_t - 1e-9:
            self.fail(now, 'E2E_EVENT_OUT_OF_ORDER', f'{now} < {self.last_t}')
            return self._final(now)
        self.last_t = now
        if self.phase == ALLOCATE or self.phase in TERMINAL:
            return self._final(now)
        src = self.source(now)
        if self.phase in GRASP_PHASES:
            return self._grasp(now, proposal)
        if self.phase == NAV_CARRY:
            return self._carry(now, proposal, src)
        return self._release(now, proposal, src)

    def _issue(self, cmd):
        self.commands += 1
        self.last_pwm = dict(cmd['pwm'])
        return cmd

    def _final(self, now):
        if self.last_pwm is None:
            return None
        return hold_command(now, self.last_pwm)

    def _valid(self, proposal, code):
        try:
            if not isinstance(proposal, dict) or 'command' not in proposal:
                raise ValueError('proposal with command required')
            return check_command(proposal['command'])
        except (ValueError, TypeError) as exc:
            raise E2EMinError(code, str(exc)) from None

    def _grasp(self, now, proposal):
        if now - self.entered_at > self.timeouts['grasp'] + 1e-9:
            self.fail(now, 'E2E_GRASP_TIMEOUT', f'{now - self.entered_at:.1f}s')
            return self._final(now)
        try:
            cmd = self._valid(proposal, 'E2E_GRASP_EXECUTOR_ERROR')
        except E2EMinError as exc:
            self.fail(now, exc.code, exc.detail)
            return self._final(now)
        if proposal.get('done') is True:
            try:
                self.hold_pwm = held_pwm(cmd['pwm'], self.hold_rule)
            except E2EMinError as exc:
                self.fail(now, exc.code, exc.detail)
                return self._final(now)
            self._issue(hold_command(now, self.hold_pwm))
            self.settle_until = now + self.timeouts['settle']
            self._go(now, NAV_CARRY, f'{self.spec["grasp"]} grasp done; hold '
                     f'{self.hold_rule}; settle {self.timeouts["settle"]}s')
            return hold_command(now, self.hold_pwm)
        return self._issue(cmd)

    def _carry(self, now, proposal, src):
        start = self.settle_until if self.settle_until is not None else self.entered_at
        if now - start > self.timeouts['carry'] + 1e-9:
            self.fail(now, 'E2E_NAV_TIMEOUT', f'{now - start:.1f}s')
            return self._final(now)
        if src is None:
            return self._issue(hold_command(now, self.hold_pwm))
        try:
            cmd = self._valid(proposal, 'E2E_NAV_EXECUTOR_ERROR')
        except E2EMinError as exc:
            self.fail(now, exc.code, exc.detail)
            return self._final(now)
        if proposal.get('no_claim') is True:
            self.fail(now, 'E2E_NAV_NO_CLAIM', 'nav NO_CLAIM latched')
            return self._final(now)
        if proposal.get('arrived') is True:
            release = ACT_RELEASE if self.spec['release'] == 'act' else TEACHER_RELEASE
            self._go(now, release, 'own arrival claim (unverified); release starts next tick')
            return self._issue(hold_command(now, self.hold_pwm))
        # H3: nav wheels/pulses unchanged, all PWM channels held.
        return self._issue(dict(t=now, wheels=list(cmd['wheels']),
                                duration_s=list(cmd['duration_s']), pwm=dict(self.hold_pwm)))

    def _release(self, now, proposal, src):
        if now - self.entered_at > self.timeouts['release'] + 1e-9:
            self.fail(now, 'E2E_RELEASE_TIMEOUT', f'{now - self.entered_at:.1f}s')
            return self._final(now)
        if src is None:
            return self._issue(hold_command(now, self.hold_pwm))
        try:
            cmd = self._valid(proposal, 'E2E_RELEASE_EXECUTOR_ERROR')
        except E2EMinError as exc:
            self.fail(now, exc.code, exc.detail)
            return self._final(now)
        self._issue(cmd)
        if proposal.get('done') is True:
            self._go(now, DONE, f'{self.spec["release"]} release done')
            return hold_command(now, self.last_pwm)
        return cmd

    def export(self):
        return dict(robot=self.robot, level=self.level, phase=self.phase, slot=self.slot,
                    fail_code=self.fail_code, fail_detail=self.fail_detail,
                    hold_rule=self.hold_rule, hold_pwm=copy.deepcopy(self.hold_pwm),
                    reach=dict(self.reach), transitions=copy.deepcopy(self.transitions),
                    commands=self.commands)


class E2EMinEpisode:
    """Two robots + the shared ALLOCATE step."""

    def __init__(self, level, *, robots=ROBOTS, hold_rule=DEFAULT_HOLD_RULE, timeouts=None,
                 initial_pwm=None):
        _level(level)
        if tuple(robots) != ROBOTS:
            raise ValueError('minimal E2E is exactly r1+r2')
        self.level = level
        self.robots = {r: RobotHandoff(r, level, hold_rule=hold_rule, timeouts=timeouts,
                                       initial_pwm=(initial_pwm or {}).get(r))
                       for r in robots}
        self.allocation = None

    def allocate(self, now, record):
        """Bind the L1-lite allocation record (``allocate_slots`` output)."""
        self.allocation = copy.deepcopy(record) if isinstance(record, dict) else None
        rec = record if isinstance(record, dict) else {}
        decisions = rec.get('decisions') or {}
        if not rec or rec.get('fatal') is True or rec.get('success_eligible') is not True:
            for r in self.robots.values():
                r.fail(now, 'E2E_ALLOC_FAILED', ','.join(map(str, rec.get('errors') or ())))
            return False
        if (set(decisions) != set(ROBOTS) or sorted(decisions.values()) != sorted(SLOTS)):
            for r in self.robots.values():
                r.fail(now, 'E2E_ALLOC_SLOTS_INVALID', repr(decisions))
            return False
        for robot, handoff in self.robots.items():
            handoff.allocated(now, decisions[robot])
        return True

    def tick(self, now, proposals):
        return {r: h.tick(now, (proposals or {}).get(r)) for r, h in self.robots.items()}

    def sources(self, now):
        return {r: h.source(now) for r, h in self.robots.items()}

    @property
    def finished(self):
        return all(h.phase in TERMINAL for h in self.robots.values())

    def export(self):
        return dict(schema=SCHEMA, level=self.level, label=LEVELS[self.level]['label'],
                    e2e_substitutions=substitutions(self.level), overlay_text=False,
                    allocation_success_eligible=bool((self.allocation or {}).get('success_eligible')),
                    slots={r: h.slot for r, h in self.robots.items()},
                    robots={r: h.export() for r, h in self.robots.items()},
                    integration_points_open=list(INTEGRATION_POINTS))


# -- unverified connection points (DESIGN.md §6) ---------------------------
def build_world(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:world_builder): the nav builder strips every cube
    # (scripts/e2e_warp_physics.py:77-80) and the ACT owner builds solo-r1 worlds
    # with C312 compiled references bound to the exact XML
    # (warp_act_api.py:148-157, simalt_compiled_compat.py:85-89).  A v6
    # two-robot world with one cube per robot inside the ACT start distribution
    # and the cargo finger contact pairs does not exist yet.
    raise NotImplementedError('E2E_MIN_TODO:world_builder')


def act_skill_client(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:act_skill_client): the ACT actor runs in the torch env
    # behind the owner RPC (act16w_eval_owner.py:48-60); the owner and History
    # are r1-only (warp_act_api.py:60,67,149-157).  Feeding r2 frames and
    # driving the actor from the nav runner process is unverified.
    raise NotImplementedError('E2E_MIN_TODO:act_skill_client')


def teacher_skill(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:teacher_skill): SoloTeacher (frozen 6f057f7e
    # sim/grasp_act_solo_teacher.py) is constructed only by the teacher runner;
    # its inputs inside the nav runner and its release-away-from-pickup
    # behaviour are unverified.
    raise NotImplementedError('E2E_MIN_TODO:teacher_skill')


def nav_carry_adapter(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:nav_carry_adapter): SelfCentricNavigation always sends
    # SEARCH PWM (e2ewarp_selfnav.py:1030-1031) and its ground projection is fit
    # at the SEARCH camera mount (e2ewarp_selfnav.py:280-289); starting it from
    # the post-grasp pose with the arm held elsewhere is unverified.
    raise NotImplementedError('E2E_MIN_TODO:nav_carry_adapter')


def runner_loop(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:runner_loop): run_e2e_warp issues task.command(now)
    # (scripts/run_e2e_warp.py:500-506) and stops on nav_all_arrived
    # (:524-528); the E2E loop must route through E2EMinEpisode.tick and must
    # not stop at arrival.
    raise NotImplementedError('E2E_MIN_TODO:runner_loop')


def eval_cube_geometry(*_args, **_kwargs):
    # TODO(E2E_MIN_TODO:eval_cube_geometry): eval_geometry
    # (e2ewarp_nav_gate.py:722-733) records robot qpos addresses only; the cube
    # free-joint qpos address and half size per robot are needed by
    # harness/e2e_min_eval.recount_run.
    raise NotImplementedError('E2E_MIN_TODO:eval_cube_geometry')
