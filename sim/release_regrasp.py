"""Default-off release teacher barrier: own wrist RGB + issued PWM only.

The shared visual comparison is reused byte-for-byte from solo branch
6f057f7e97c1a3aec9e8c398b8d9068e27b25df8. Its pickup-site-empty fallback
is deliberately unavailable: a partner can remove a beam from that site.
One robot at a time makes a 20 mm command-space lift challenge; the partner
keeps its commands fixed. Visual confirmation is a hypothesis, not contact
or measured height. Thresholds require separate physical positive/negative
validation before promotion. This module never imports a simulator.
"""
from __future__ import annotations

from collections import Counter
import copy
import numpy as np

from sim.rgb_lift_evidence import confirm_parts_v3, shape

OPTION = 'own_rgb_lift_v1'
MODES = ('off', OPTION)
MAX_ATTEMPTS = 3                         # original attempt + two own retries
LIFT_M = .020
MOVE_S = 1.4
SETTLE_S = 3.
VERIFY_CAP_S = 5.


def beam_mask(frame):
    """Existing long-beam hue, without using a partner's image or end pose."""
    import cv2
    from harness.zone_own_perception import hue_mask, _usable_region
    return ((hue_mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), 'long_beam') > 0)
            & _usable_region(frame.shape[1], frame.shape[0]))


def near_grip(frame):
    """Reject the distant/edge shaft seen by the empty r1 wrist in release10.

    A central shaft is necessary, never sufficient: a sequential lift challenge
    and a fresh sustained comparison are also mandatory. No camera/FOV change.
    """
    mask = beam_mask(frame)
    h, w = mask.shape
    fraction = float(mask[h//5:4*h//5, w//4:3*w//4].mean())
    return dict(qualified=fraction >= .60, central_fraction=fraction,
                threshold=.60, scope='provisional own wrist near-field shaft')


def lift_evidence(before, after, settled, commands):
    record = confirm_parts_v3(before, after, commands=commands,
        masks=lambda frame: (beam_mask(frame),), names=('beam',),
        settled=settled, rule=OPTION)
    proximity = [near_grip(f) for f in (before, after, settled)]
    record['near_grip'] = proximity
    if not all(p['qualified'] for p in proximity):
        record.update(verdict='not_confirmed', reason='own_grip_shaft_not_framed')
    record['answer'] = {'confirmed':'yes', 'not_confirmed':'no', 'undetermined':'unknown'}[record['verdict']]
    return record


def continuity(reference, frame):
    """Fresh retention check, usable only AFTER that robot's own challenge."""
    b, a = shape(beam_mask(reference)), shape(beam_mask(frame))
    ok = (near_grip(frame)['qualified'] and a is not None and b is not None
          and .70 <= a['fraction']/b['fraction'] <= 1.40
          and max(abs(x-y) for x,y in zip(a['center'], b['center'])) <= .06
          and max(abs(x-y) for x,y in zip(a['extent'], b['extent'])) <= .10)
    return dict(answer='yes' if ok else 'no', reason='own_rgb_retained' if ok else 'own_rgb_hold_lost')


class RegraspBarrier:
    """Bounded sequential challenge/retry; only scalar receipts leave it.

    capture(rid, now, label) returns the fresh own BGR frame and saves its hash.
    schedule(rid, sequence, now) issues only that robot's arm commands. Loaded
    shared motion waits for both code ACKs. An opt-in failed-grip recovery may
    move only the opened robot, with peer commands fixed and confirmations reset.
    """
    def __init__(self, teachers, epoch, now, *, wheel_commands, recovery_factory=None):
        self.teachers = teachers
        self.robots = tuple(teachers)
        self.epoch = epoch
        self.wheel_commands = wheel_commands
        self.peer_commands = {}
        self.attempts = {r:1 for r in teachers}
        self.confirmed = {r:False for r in teachers}
        self.references = {}
        self.expected = {}
        self.records = []
        self.samples = []
        self.rejections = Counter()
        self.answers = Counter()
        self.state = 'start'
        self.rid = self.robots[0]
        self.until = now
        self.failure = None
        self.recovery_factory = recovery_factory
        self.recovery = None
        self.recoveries = []

    def command(self, rid, now):
        return dict(t=now, pwm=dict(self.teachers[rid].pwm), wheels=list(self.wheel_commands(rid)))

    def _reject(self, rid, reason, now):
        self.confirmed[rid] = False
        self.teachers[rid].holding = False
        self.rejections[reason] += 1
        self.records.append(dict(t=now, robot=rid, epoch=self.epoch,
            attempt=self.attempts[rid], event='rejected', reason=reason))

    def fresh(self, now, capture):
        """No old-epoch, command-changed or one-sided confirmation can pass."""
        for rid in self.robots:
            if any(self.wheel_commands(rid)):
                return rid, 'base_command_during_verification'
            if not self.confirmed[rid]:
                return rid, 'own_rgb_unconfirmed'
            if dict(self.teachers[rid].pwm) != self.expected[rid]:
                return rid, 'confirmed_command_changed'
            rec = continuity(self.references[rid], capture(rid, now, 'barrier'))
            self.samples.append(dict(t=now, robot=rid, epoch=self.epoch, **rec))
            if rec['answer'] != 'yes':
                return rid, rec['reason']
        return None, None

    def retry(self, rid, reason, now, schedule):
        self._reject(rid, reason, now)
        self.rid = rid
        if self.attempts[rid] >= MAX_ATTEMPTS:
            self.failure = f'regrasp_attempt_cap:{rid}:{reason}'
            self.state = 'failed'
            return
        self.attempts[rid] += 1
        if self.recovery_factory is not None:
            # Individual open-grip recovery is distinct from shared loaded
            # transport. Any previous peer confirmation must be tested afresh.
            self.confirmed = {r:False for r in self.robots}
            for t in self.teachers.values():t.holding = False
            self.peer_commands = {r:dict(t.pwm) for r,t in self.teachers.items() if r!=rid}
            try:
                self.recovery = self.recovery_factory(self.teachers[rid], now)
            except ValueError as error:
                self.failure = f'regrasp_realign_unreachable:{rid}:{error}'
                self.state = 'failed'
                return
            self.recoveries.append(self.recovery)
            self.records.append(dict(t=now,robot=rid,epoch=self.epoch,
                attempt=self.attempts[rid],event='retry_realign',reason=reason))
            self.state = 'realign'
            return
        try:
            seq, duration = self.teachers[rid].pick_schedule(now)
        except ValueError:
            self.failure = f'regrasp_retry_unreachable:{rid}'
            self.state = 'failed'
            return
        schedule(rid, seq, now)
        self.records.append(dict(t=now, robot=rid, epoch=self.epoch,
            attempt=self.attempts[rid], event='retry', reason=reason))
        self.state, self.until = 'retry_wait', now+duration

    def tick(self, now, capture, schedule):
        rid = self.rid
        if self.state == 'failed':
            return 'failed'
        if self.state == 'ready':
            return 'ready'
        if self.state == 'realign':
            if any(any(self.wheel_commands(r)) or self.teachers[r].pwm!=p
                   for r,p in self.peer_commands.items()):
                self.failure = 'regrasp_partner_command_during_realign'
                self.state = 'failed'
                return 'failed'
            status = self.recovery.tick(now,capture,schedule)
            if status == 'failed':
                self.failure = self.recovery.failure+':'+rid
                self.state = 'failed'
                return 'failed'
            if status == 'ready':
                if any(any(self.wheel_commands(r)) for r in self.robots):
                    self.failure = 'regrasp_base_command_before_retry'
                    self.state = 'failed'
                    return 'failed'
                try:seq,duration = self.teachers[rid].pick_schedule(now,xy=self.recovery.xy)
                except ValueError:
                    self.failure = f'regrasp_retry_unreachable:{rid}'
                    self.state = 'failed'
                    return 'failed'
                schedule(rid,seq,now)
                self.state,self.until = 'retry_wait',now+duration
            return 'pending'
        if any(any(self.wheel_commands(r)) for r in self.robots):
            self.failure = 'regrasp_base_command_during_verification'
            self.state = 'failed'
            return 'failed'
        if self.state in ('lift','verify','restore') and any(
                self.teachers[r].pwm != p for r,p in self.peer_commands.items()):
            self.failure = 'regrasp_partner_command_during_test'
            self.state = 'failed'
            return 'failed'
        if self.state == 'lift':
            self.commands.append(self.command(rid, now))
        if now < self.until-1e-8:
            return 'pending'
        if self.state == 'retry_wait':
            self.state = 'start'
        if self.state == 'start':
            from harness.visual_arm_v3 import forward_grip
            teacher = self.teachers[rid]
            self.base = dict(teacher.pwm)
            self.peer_commands = {r:dict(t.pwm) for r,t in self.teachers.items() if r!=rid}
            self.before = capture(rid, now, 'before_test')
            self.commands = [self.command(rid, now)]
            self.yes_since = None
            self.records.append(dict(t=now, robot=rid, epoch=self.epoch,
                attempt=self.attempts[rid], event='test_start', commanded_lift_m=LIFT_M))
            try:
                z = forward_grip(self.base)[2]
                seq = [(0., teacher.arm_waypoints(z+LIFT_M, 1)[0])]
            except ValueError:
                self.failure = f'regrasp_test_unreachable:{rid}'
                self.state = 'failed'
                return 'failed'
            schedule(rid, seq, now)
            self.state, self.until = 'lift', now+MOVE_S
        elif self.state == 'lift':
            self.after = capture(rid, now, 'lift_complete')
            self.completed = now
            self.state, self.until = 'verify', now+SETTLE_S
        elif self.state == 'verify':
            frame = capture(rid, now, 'settled_test')
            rec = lift_evidence(self.before, self.after, frame, self.commands)
            if dict(self.teachers[rid].pwm) != self.commands[-1]['pwm']:
                rec.update(answer='unknown', reason='test_command_changed')
            self.samples.append(dict(t=now, robot=rid, epoch=self.epoch,
                                     attempt=self.attempts[rid], **rec))
            self.answers[rec['answer']] += 1
            self.yes_since = (now if self.yes_since is None else self.yes_since) if rec['answer']=='yes' else None
            passed = self.yes_since is not None and now-self.yes_since >= 1.-1e-8
            if passed or now-self.completed >= VERIFY_CAP_S-1e-8:
                self.verdict = dict(answer='yes' if passed else rec['answer'], reason=rec['reason'])
                schedule(rid, [(0., self.base)], now)
                self.state, self.until = 'restore', now+MOVE_S
        elif self.state == 'restore':
            frame = capture(rid, now, 'restored_test')
            retained = continuity(self.before, frame)
            if self.verdict['answer']=='yes' and retained['answer']=='yes':
                self.confirmed[rid] = True
                self.references[rid] = frame.copy()
                self.expected[rid] = dict(self.teachers[rid].pwm)
                self.records.append(dict(t=now, robot=rid, epoch=self.epoch,
                    attempt=self.attempts[rid], event='confirmed', reason='own_sequential_rgb_lift'))
                pending = [r for r in self.robots if not self.confirmed[r]]
                if pending:
                    self.rid = pending[0]
                    self.state, self.until = 'start', now
                else:
                    bad, reason = self.fresh(now, capture)
                    if bad is None:
                        self.state = 'ready'
                        return 'ready'
                    self.retry(bad, reason, now, schedule)
            else:
                reason = self.verdict['reason'] if self.verdict['answer']!='yes' else retained['reason']
                self.retry(rid, reason, now, schedule)
        return 'failed' if self.failure else 'pending'

    def record(self):
        return dict(epoch=self.epoch, attempts=dict(self.attempts), confirmed=dict(self.confirmed),
            failure=self.failure, events=copy.deepcopy(self.records), samples=copy.deepcopy(self.samples),
            answer_counts=dict(self.answers), rejection_reasons=dict(self.rejections),
            **({'realign_recoveries':[r.record() for r in self.recoveries]} if self.recovery_factory else {}),
            physical_validation='unverified; own RGB hypothesis only')
