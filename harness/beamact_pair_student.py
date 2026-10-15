"""Student command barrier; no teacher, perception, simulator or geometry API."""
from copy import deepcopy

MODE = 'beamact2_student_v1'


class StudentBarrier:
    """A close proposal emits READY; existing GO/ACK releases that proposal.

    Closing means a decrease from the last issued gripper PWM: the pinned
    teacher's OPEN=2000/CLOSED=1500 establishes that direction. Even a one-PWM
    close proposal must await GO/ACK; there is no learned/tuned PWM threshold.
    Only the pending ACT proposal and actually issued history are used. Waiting
    holds the last PWM and stops wheels; it never supplies grasp motion.
    """
    def __init__(self):
        self.pending = None
        self.started = False
        self.done = False
        self.events = []

    @property
    def ready(self):
        return self.pending is not None or self.started

    def propose(self, value, done, previous):
        if self.pending is not None:
            raise ValueError('pending ACT proposal must be released before inference')
        if not self.started and value['pwm']['1'] < previous['pwm']['1']:
            self.pending = (deepcopy(value), bool(done))
            self.events.append(dict(t=value['t'], event='READY', source='own_ACT_close_proposal'))
            return True
        return False

    def issue(self, now, previous, proposal, done, permit):
        if self.pending is not None:
            if permit:
                proposal, done = self.pending
                self.pending = None
                self.started = True
                self.events.append(dict(t=now, event='close_released_after_GO_ACK'))
            else:
                # The mechanical hold is the unchanged protocol WAIT action.
                return dict(deepcopy(previous), t=now, wheels=[0.] * 4,
                            duration_s=[0.] * 4), False
        if proposal is None:
            raise ValueError('missing student command; no fallback')
        value = dict(deepcopy(proposal), t=now)
        self.done = bool(done)
        return value, self.done


STAGES = ('approach', 'alignment', 'READY', 'grasp', 'lift_3s')


class Funnel:
    """Evaluation only: stages accumulate in order; counts remain recountable."""
    def __init__(self):
        self.first = {}
        self.frames = {s: 0 for s in STAGES}
        self.rejected = {s: 0 for s in STAGES}

    def add(self, now, passed):
        for i, stage in enumerate(STAGES):
            eligible = i == 0 or STAGES[i-1] in self.first
            if eligible and passed[stage]:
                self.first.setdefault(stage, now)
                self.frames[stage] += 1
            elif eligible:
                self.rejected[stage] += 1

    def record(self):
        return dict(first_pass_sim_t=self.first,
                    cumulative_run_pass={s: int(s in self.first) for s in STAGES},
                    frames_pass=self.frames, frames_rejected=self.rejected,
                    failure_stage=next((s for s in STAGES if s not in self.first), None))
