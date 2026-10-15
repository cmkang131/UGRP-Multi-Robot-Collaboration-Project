"""Opt-in release19: reuse a completed identical-command lookaround dwell.

No move/settle constant is reduced. In the global panorama the first capture
reissues arm_to_look's exact command after 1 s, then waits another 0.8 s.
Only already elapsed, unchanged own-command time may satisfy that wait.
Fresh capture, all three views, both sweeps and acceptance tests remain.
"""
from __future__ import annotations

from sim import release18
from sim.lookaround_localization import ScriptRunner as LegacyScriptRunner

PROFILE = 'release19_v1'
PROFILES = (*release18.PROFILES, PROFILE)


def validate(profile, record_training, options, plan):
    release18.validate(release18.PROFILE if profile == PROFILE else profile,
                       record_training, options, plan)


class ScriptRunner(LegacyScriptRunner):
    """The old runner except for a capture immediately after the same servo step.

    Require the complete requested snapshot, fresh command history, no held
    cargo and no wheel/pending servo activity. Unknown history keeps the full
    old wait. A new command never borrows the old command's elapsed time.
    """
    def __init__(self, steps, start, *, teacher, command_history, idle):
        super().__init__(steps, start)
        self.teacher = teacher
        self.command_history = command_history
        self.idle = idle
        self.reused_waits = []

    def tick(self, now, *, set_servo, set_wheels, wheels_idle, capture):
        def enter(step):
            pose = step.get('servo')
            if not pose or not step.get('capture') or self.i==0:
                return False
            previous=self.steps[self.i-1]
            if previous.get('servo')!=pose or previous.get('wheels'):
                return False
            if step.get('wheels') or self.teacher.holding or not self.idle() or not wheels_idle():
                return False
            history = self.command_history
            if history is None or history.pwm != self.teacher.pwm:
                return False
            ages = [history.servo_age(sid, value, now) for sid, value in pose.items()]
            if any(age is None or age < step['wait']-1e-9 for age in ages):
                return False
            # Do not skip the command, view or original stability requirement.
            set_servo(pose, now)
            self.log.append(dict(label=step['label'], t=float(now)))
            self.reused_waits.append(dict(t=now,label=step['label'],
                omitted_wait_s=step['wait'],command_age_s=min(ages),
                source='own issued PWM history',capture=bool(step.get('capture'))))
            self.t_step = now
            self.waiting_from = now-step['wait']
            return True

        # Legacy tick can finish one step and enter another in the same call.
        # Intercept each such entry without changing its clock or command order.
        while not self.done:
            if self.t_step is None and enter(self.steps[self.i]):
                step = self.steps[self.i]
                if step.get('capture'):
                    capture(now)
                self.i += 1
                self.t_step = None
                if self.i >= len(self.steps):
                    self.done = True
                    self.end = now
                continue
            # Stop legacy tick at the next entry, then reconsider that entry.
            if self.t_step is not None:
                step = self.steps[self.i]
                if step.get('wheels') and not wheels_idle():
                    return
                if self.waiting_from is None:
                    self.waiting_from = now
                if now-self.waiting_from < step['wait']-1e-9:
                    return
                if step.get('capture'):
                    capture(now)
                self.i += 1
                self.t_step = None
                if self.i >= len(self.steps):
                    self.done = True
                    self.end = now
                continue
            return super().tick(now,set_servo=set_servo,set_wheels=set_wheels,
                                wheels_idle=wheels_idle,capture=capture)


class TopCameraAudit:
    """Guard the runner's public top-JPEG entry; eval gets an explicit permit.

    Counts attempted control reads before raising. No evaluation image is
    returned to a teacher. Private renderer APIs are outside this counter.
    """
    def __init__(self):
        self.control_reads = 0
        self.evaluation_reads = 0
        self._evaluation = False

    def install(self, world):
        original = world.render_team_jpeg
        def guarded(*args, **kwargs):
            if not self._evaluation:
                self.control_reads += 1
                raise RuntimeError('CONTROL_TOP_CAMERA_FORBIDDEN')
            self.evaluation_reads += 1
            return original(*args, **kwargs)
        world.render_team_jpeg = guarded

    def evaluation_jpeg(self, world, **kwargs):
        self._evaluation = True
        try:
            return world.render_team_jpeg(**kwargs)
        finally:
            self._evaluation = False

    def record(self):
        return dict(control_top_camera_reads=self.control_reads,
                    evaluation_top_camera_reads=self.evaluation_reads,
                    top_camera_counter_scope='guarded world.render_team_jpeg, from world creation through cleanup; private renderer APIs excluded')
