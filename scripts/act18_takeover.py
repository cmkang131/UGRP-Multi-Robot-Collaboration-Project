"""C1 executable teacher takeover from the student's own current state.

Default-off.  The existing label-only oracle path is untouched: these helpers
are constructed only when the private DAgger owner is launched with
``--takeover``.  No simulator, torch, GPU or MuJoCo import happens at import
time; the frozen ``SoloTeacher`` (or a test double) is injected by the caller.

What this module owns:

* ``TakeoverTrigger`` - the preregistered C1 start condition (elapsed >= 6 s
  and 20 consecutive issued ticks moving OR stopped).  It reads the student's
  own issued wheel command, never measured truth.
* ``TeacherTakeover`` - a fresh teacher seeded with the student's last issued
  pwm, its phase clock reset through the teacher's own ``_set(now)`` path, and
  the existing hard-coded 3 s hold shortened/lengthened from one parameter by
  shifting only that phase's clock (the phase machine and command queues stay
  frozen).
* ``TakeoverRgb`` - the same own-RGB holding channel as
  ``scripts/warp_act_episode.py``: ``LookbackObserver`` for
  ``solo_lift_lookback_v1`` and ``lift_answer`` otherwise.
"""
from __future__ import annotations

from copy import deepcopy

NOMINAL_HOLD_S = 3.0
MAX_HOLD_S = 60.0
DEFAULT_AFTER_S = 6.0
DEFAULT_STREAK_TICKS = 20
TAKEOVER_PROFILE = 'solo_visible_only_v1'
TAKEOVER_STABILITY = 'align_relook_v1'
TAKEOVER_REACH = 'pad_window_v2'
TAKEOVER_RGB_MODE = 'solo_lift_lookback_v1'
SERVOS = (1, 3, 4, 5, 6)


class TakeoverTrigger:
    """Preregistered C1 trigger: elapsed >= after_s and a 20-tick motion streak.

    "moving" is the student's own issued wheel command (any non-zero wheel),
    not measured base motion; a truth read would violate the actor input audit.
    Once fired it stays fired for this episode.
    """

    def __init__(self, *, after_s=DEFAULT_AFTER_S, streak_ticks=DEFAULT_STREAK_TICKS):
        if not isinstance(after_s, (int, float)) or after_s < 0:
            raise ValueError('nonnegative takeover delay required')
        if type(streak_ticks) is not int or streak_ticks < 1:
            raise ValueError('positive integer takeover streak required')
        self.after_s, self.streak_ticks = float(after_s), streak_ticks
        self.streak = 0
        self.streak_moving = None
        self.fired = False
        self.fired_elapsed_s = None

    def observe(self, elapsed_s, command):
        if not isinstance(elapsed_s, (int, float)) or elapsed_s < 0:
            raise ValueError('nonnegative episode elapsed time required')
        if self.fired:
            return True
        moving = any(abs(float(w)) > 1e-9 for w in command['wheels'])
        if self.streak_moving is None or moving == self.streak_moving:
            self.streak += 1
        else:
            self.streak = 1
        self.streak_moving = moving
        if elapsed_s+1e-9 >= self.after_s and self.streak >= self.streak_ticks:
            self.fired, self.fired_elapsed_s = True, float(elapsed_s)
        return self.fired

    def record(self):
        return {'after_s': self.after_s, 'streak_ticks': self.streak_ticks,
                'streak': self.streak, 'streak_moving': self.streak_moving,
                'fired': self.fired, 'fired_elapsed_s': self.fired_elapsed_s,
                'motion_source': 'own issued wheel command; no measured truth'}


def issued_pwm(command):
    """Exact last-issued servo snapshot, rejecting partial/foreign commands."""
    pwm = command.get('pwm') if isinstance(command, dict) else None
    if not isinstance(pwm, dict) or not pwm:
        raise ValueError('student last-issued pwm required')
    out = {int(k): int(v) for k, v in pwm.items()}
    if set(out) != set(SERVOS):
        raise ValueError('student last-issued pwm must cover exactly servos 1,3,4,5,6')
    return out


class TeacherTakeover:
    """One fresh teacher, seeded by the student and clock-reset at the trigger.

    ``hold_s`` changes only the teacher's existing 3 s hold phase.  The teacher
    gate is ``now - phase_t >= 3``; on entry we move ``phase_t`` by
    ``NOMINAL_HOLD_S - hold_s`` so the frozen phase machine advances after
    exactly ``hold_s`` seconds.  No teacher command or branch is edited.
    """

    def __init__(self, teacher, *, now, hold_s=NOMINAL_HOLD_S):
        if not isinstance(hold_s, (int, float)) or not 0 < float(hold_s) <= MAX_HOLD_S:
            raise ValueError('hold_s must be in (0, 60] seconds')
        self.teacher = teacher
        self.hold_s = float(hold_s)
        self.started_t = float(now)
        self.hold_ticks = 0
        self.phase_t_shift_s = 0.
        self.phases = []
        # The fresh teacher has no clock; stamp it through the teacher's own
        # phase transition path so every later timeout is measured from here.
        teacher._set('start', now)

    def step(self, now, *, measurement=None, rgb_holding='unknown', own_rgb=None):
        before = self.teacher.phase
        value, done = self.teacher.step(now, measurement=measurement,
                                        rgb_holding=rgb_holding, own_rgb=own_rgb)
        after = self.teacher.phase
        if before != 'hold' and after == 'hold':
            shift = NOMINAL_HOLD_S-self.hold_s
            self.teacher.phase_t -= shift
            self.phase_t_shift_s += shift
        if after == 'hold':
            self.hold_ticks += 1
        self.phases.append(after)
        return value, done

    def record(self):
        return {'started_t': self.started_t, 'hold_s': self.hold_s,
                'hold_ticks': self.hold_ticks, 'phase_t_shift_s': self.phase_t_shift_s,
                'phases': list(self.phases), 'teacher_result': self.teacher.result,
                'scope': 'executed takeover; commands are applied through owner.step'}


def takeover_teacher(plan, command, *, now, hold_s=NOMINAL_HOLD_S, ops=None, route=None,
                     teacher_factory=None):
    """Construct the fresh frozen teacher seeded with the student's last pwm."""
    pwm = issued_pwm(command)
    if teacher_factory is None:
        from sim.grasp_act_solo_teacher import SoloTeacher

        def teacher_factory(pwm):
            return SoloTeacher(plan['kind'], plan['role'], pwm, profile=TAKEOVER_PROFILE,
                               held_object_hidden_v1=True,
                               teacher_stability=TAKEOVER_STABILITY,
                               reach_mode=TAKEOVER_REACH, ops=ops, route=route,
                               rgb_lift_mode=TAKEOVER_RGB_MODE,
                               solo_lift_lookback_margin_v1=True)
    teacher = teacher_factory(pwm)
    return TeacherTakeover(teacher, now=now, hold_s=hold_s)


class TakeoverRgb:
    """Own-RGB holding evidence on the same channel as the current pipeline.

    ``solo_lift_lookback_v1`` uses the existing ``LookbackObserver``; every
    other RGB mode falls back to the existing ``lift_answer``.  Both are
    injected lazily so this module stays importable without cv2/torch.
    """

    def __init__(self, kind, *, mode=TAKEOVER_RGB_MODE, save=None,
                 observer_factory=None, lift_answer=None):
        if kind not in ('cyan', 'red', 'green', 'yellow', 'can', 'tile'):
            raise ValueError('solo cargo kind required')
        if mode not in ('off', 'solo_rgb_lift_v2', 'solo_rgb_lift_v3', 'solo_lift_lookback_v1'):
            raise ValueError('unknown solo RGB lift mode')
        if mode != 'off' and not callable(save):
            raise ValueError('RGB lift evidence saver required')
        self.kind, self.mode, self.save = kind, mode, save
        self._observer_factory, self._lift_answer = observer_factory, lift_answer
        self.observer = None
        self.last = None
        self.answers = []

    def _observer(self):
        if self.observer is None:
            factory = self._observer_factory
            if factory is None:
                from sim.grasp_act_solo_lookback import LookbackObserver
                factory = LookbackObserver
            self.observer = factory(self.kind)
        return self.observer

    def _judge(self, frame, teacher):
        judge = self._lift_answer
        if judge is None:
            from sim.grasp_act_solo_rgb import lift_answer
            judge = lift_answer
        if teacher.low is None or teacher.grasp_xyz is None:
            return 'unknown', {'answer': 'unknown', 'reason': 'grasp_not_frozen'}
        return judge(frame, teacher.sink.pwm, self.kind, teacher.low, teacher.grasp_xyz[:2])

    def before_step(self, frame, *, now, previous, phase, teacher):
        """Answer for this tick, mirroring warp_act_episode.py order exactly."""
        answer = 'unknown'
        if self.mode == 'off':
            return answer
        if phase in ('verify_lift', 'hold'):
            command = {**deepcopy(previous), 't': now}
            if self.mode == 'solo_lift_lookback_v1':
                self.last = self._observer().observe(frame, command, complete=True,
                                                     save=self.save)
            else:
                answer, record = self._judge(frame, teacher)
                self.last = {**record, 'answer': answer}
            answer = self.last.get('answer', 'unknown')
            if answer not in ('yes', 'no', 'unknown'):
                raise ValueError('own RGB holding answer must be yes/no/unknown')
            self.answers.append(answer)
        elif phase == 'lift' and self.mode == 'solo_lift_lookback_v1':
            self.last = self._observer().observe(frame, {**deepcopy(previous), 't': now},
                                                 complete=False, save=self.save)
        return answer

    def after_step(self, frame, *, now, previous, command, phase_before, phase_after):
        """Start/issue the observer after the teacher step, as the episode does."""
        if self.mode != 'solo_lift_lookback_v1':
            return
        observer = self._observer()
        if phase_before in ('align', 'approach') and phase_after == 'hover':
            observer.start(frame, {**deepcopy(previous), 't': now}, self.save)
        observer.issue(command, phase_after)

    def record(self):
        return {'mode': self.mode, 'answers': list(self.answers),
                'last': self.last, 'observer': getattr(self.observer, 'record', lambda: None)()}
