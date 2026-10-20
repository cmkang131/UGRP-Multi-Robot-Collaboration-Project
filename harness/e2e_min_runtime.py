"""E2E-min runtime glue: executor protocol, nav carry adapter, per-tick router.

Executor protocol (one object per robot and source):

    propose(frame, now) -> {'command': cmd, 'done': bool}            # grasp / release
    propose(frame, now) -> {'command': cmd, 'arrived': bool,
                            'no_claim': bool}                         # nav carry
    record_issued(cmd)   (optional) the command actually issued this tick

``route_tick`` queries only the source each robot's RobotHandoff asks for
(``E2EMinEpisode.sources``), so an executor that is not active never sees a
frame and never has a command attributed to it.  Any executor exception is
turned into an invalid proposal, which the state machine fails closed with the
phase's executor error code.  No GT, map or simulator state passes through here.
"""
from __future__ import annotations

from harness.e2e_min_handoff import DEFAULT_HOLD_RULE

#: carry-pose render verdict (harness/e2e_min_carry_pose.verdict ``adopted``) ->
#: hold rule this adapter may run.  Only the pose reached without moving the arm
#: after grasp done is runnable; the others need an arm transition while holding.
VERDICT_HOLD_RULE = {'act_lift_end': DEFAULT_HOLD_RULE}


class NavCarryAdapter:
    """Wrap a nav-mode NavRobot for NAV_CARRY.

    The wrapped task must already be in its NAVIGATE phase (L1-lite order
    selected at tick 0).  ``observe`` and ``command`` are called only on ticks
    the handoff routes to nav, so the adapter's own issued-pulse odometry
    (``e2ewarp_selfnav.py:1020-1108``) starts at the carry start pose.
    """

    def __init__(self, task, *, carry_pose_verdict):
        for name in ('observe', 'command'):
            if not callable(getattr(task, name, None)):
                raise ValueError('nav task lacks ' + name)
        if not hasattr(task, 'component') or not hasattr(task, 'command_history'):
            raise ValueError('nav task lacks component/command_history')
        adopted = (carry_pose_verdict or {}).get('adopted')
        if adopted not in VERDICT_HOLD_RULE:
            # TODO(E2E_MIN_TODO:carry_pose_transition): teacher_hold_max_pitch /
            # carry_look_v1 / gripper_hold_arm_search_v1 need the arm to move
            # while the cube is held; that transition is unmeasured.
            raise NotImplementedError('E2E_MIN_TODO:carry_pose_transition:' + str(adopted))
        self.task = task
        self.hold_rule = VERDICT_HOLD_RULE[adopted]
        self.verdict = dict(carry_pose_verdict)
        self.started = False

    def propose(self, frame, now):
        phase = getattr(self.task.component, 'phase', None)
        if not self.started:
            if phase != 'NAVIGATE':
                raise ValueError('nav carry requires a selected NAVIGATE task, got ' + str(phase))
            self.started = True
        report = self.task.observe(frame)
        command = self.task.command(now)
        own = (report or {}).get('own_navigation') or {}
        return dict(command=command,
                    arrived=getattr(self.task.component, 'phase', None) == 'ARRIVED',
                    no_claim=own.get('arrival_no_claim') is True)

    def record_issued(self, command):
        # Keep the runner's issued history truthful (held PWM, not SEARCH).
        if self.task.command_history:
            self.task.command_history[-1] = dict(command)


def route_tick(episode, now, frames, executors):
    """One control tick for both robots; returns ``{robot: command|None}``.

    ``executors[robot][source]`` with source in {'grasp','nav','release'}.
    """
    sources = episode.sources(now)
    proposals, used = {}, {}
    for robot, source in sources.items():
        if source is None:
            continue
        executor = (executors.get(robot) or {}).get(source)
        if executor is None:
            proposals[robot] = None
            continue
        try:
            proposals[robot] = executor.propose(frames[robot], now)
            used[robot] = executor
        except Exception as exc:  # fail closed through the state machine
            proposals[robot] = dict(error=f'{type(exc).__name__}: {exc}')
    commands = episode.tick(now, proposals)
    for robot, executor in used.items():
        record = getattr(executor, 'record_issued', None)
        if callable(record) and commands.get(robot) is not None:
            record(commands[robot])
    return commands
