"""Student command barrier; no teacher, perception, simulator or geometry API."""
from copy import deepcopy

MODE = 'beamact2_student_v1'
STAGE_MODE = 'beamact4_stage_v1'
RECOVERY_MODE = 'beamact4_done_recovery_v1'
# Semantic labels, not geometry inputs. See beamact4 teacher-spec.md for the
# offline targets; categorical argmax adds no confidence/geometry threshold.
LEARNED_STAGES = ('approach', 'alignment', 'ready', 'execute', 'recover', 'complete')


class StudentBarrier:
    """Legacy close READY, or an explicitly enabled learned stage declaration.

    Closing means a decrease from the last issued gripper PWM: the pinned
    teacher's OPEN=2000/CLOSED=1500 establishes that direction. Even a one-PWM
    close proposal must await GO/ACK; there is no learned/tuned PWM threshold.
    Only the pending ACT proposal and actually issued history are used. Waiting
    holds the last PWM and stops wheels; it never supplies grasp motion.
    """
    def __init__(self, *, stage_mode='off'):
        if stage_mode not in ('off', STAGE_MODE):
            raise ValueError('unknown student stage mode')
        self.stage_mode, self.stage, self.blocked = stage_mode, None, False
        self.pending = None
        self.started = False
        self.done = False
        self.events = []

    @property
    def ready(self):
        if self.stage_mode == STAGE_MODE:
            return self.stage == 'ready' or (self.started and self.stage in ('execute', 'complete'))
        return self.pending is not None or self.started

    def propose(self, value, done, previous, *, stage=None):
        if self.stage_mode == STAGE_MODE:
            if stage not in LEARNED_STAGES:
                raise ValueError('learned stage required; no PWM readiness fallback')
            self.stage, self.blocked, self.pending = stage, False, None
            if stage in ('approach', 'alignment', 'recover'):
                self.started = False
                # Existing protocol hold only. A premature close cannot grant
                # READY or leak through before GO/ACK. Re-infer after rejection.
                self.blocked = value['pwm']['1'] < previous['pwm']['1']
            elif stage == 'ready':
                self.pending = (deepcopy(value), bool(done))
                self.events.append(dict(t=value['t'], event='READY', source='own_ACT_stage_head'))
            elif not self.started:
                self.blocked = True
            if self.blocked:
                self.events.append(dict(t=value['t'], event='proposal_rejected',
                    reason_category='close_before_learned_ready' if stage in ('approach', 'alignment', 'recover')
                    else 'execution_without_GO_ACK', blocked_object='UNKNOWN:not_observed', min_gap_m=None,
                    gap_scope='not available in own-command protocol adapter'))
            return self.pending is not None
        if self.pending is not None:
            raise ValueError('pending ACT proposal must be released before inference')
        if not self.started and value['pwm']['1'] < previous['pwm']['1']:
            self.pending = (deepcopy(value), bool(done))
            self.events.append(dict(t=value['t'], event='READY', source='own_ACT_close_proposal'))
            return True
        return False

    def issue(self, now, previous, proposal, done, permit):
        if self.stage_mode == STAGE_MODE and self.stage not in LEARNED_STAGES:
            raise ValueError('propose a learned stage before issuing')
        if self.stage_mode == STAGE_MODE and (self.blocked or
                (self.stage in ('execute', 'complete') and not permit)):
            self.done = False
            return dict(deepcopy(previous), t=now, wheels=[0.] * 4, duration_s=[0.] * 4), False
        if self.pending is not None:
            if permit:
                proposal, done = self.pending
                self.pending = None
                self.started = True
                self.events.append(dict(t=now, event='stage_proposal_released_after_GO_ACK'
                    if self.stage_mode == STAGE_MODE else 'close_released_after_GO_ACK'))
            else:
                # The mechanical hold is the unchanged protocol WAIT action.
                if self.stage_mode == STAGE_MODE:
                    self.done = False
                return dict(deepcopy(previous), t=now, wheels=[0.] * 4,
                            duration_s=[0.] * 4), False
        if proposal is None:
            raise ValueError('missing student command; no fallback')
        value = dict(deepcopy(proposal), t=now)
        self.done = bool(done)
        return value, self.done


class RearmingStartSync:
    """Reuse the pinned GO/ACK protocol after withdrawal of a READY message.

    No phase, peer pose or teacher label crosses the protocol: only its existing
    boolean READY channel. A prior START must not keep a withdrawn message true.
    The factory retains the pinned message format, deadlines and start delays.
    """
    def __init__(self, participants, delays, factory):
        self.participants, self.delays, self.factory = tuple(participants), dict(delays), factory
        self.sync = factory(self.participants, self.delays)
        self.previous = {r: False for r in self.participants}
        self.events, self.offset, self.cycle = [], 0, 0

    def tick(self, ready, now):
        if set(ready) != set(self.participants) or any(type(v) is not bool for v in ready.values()):
            raise ValueError('READY messages only')
        if self.sync.go_at is not None and any(self.previous[r] and not ready[r] for r in ready):
            self.cycle += 1
            self.events.append(dict(t=now, event='READY_withdrawn_rearm', cycle=self.cycle))
            self.sync = self.factory(self.participants, self.delays)
            self.offset = 0
        permits = self.sync.tick(ready, now)
        self.events.extend(dict(e, cycle=self.cycle) for e in self.sync.events[self.offset:])
        self.offset = len(self.sync.events)
        self.previous = dict(ready)
        return permits


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
