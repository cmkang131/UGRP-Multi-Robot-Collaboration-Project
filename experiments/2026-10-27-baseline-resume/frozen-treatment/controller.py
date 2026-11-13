"""External, default-off supervision treatment; never imports a simulator.

Anchors: S/harness/pairact_r1_student.py 3e12d2f5..., pairact_r1.py
8a986924..., beamact_pair_student.py 9650e085... (baseline-reference.json).
All thresholds, action decoding, roles and own-input construction stay pinned.
"""
from collections import Counter
from copy import deepcopy

from harness import pairact_r1 as pair
from harness import pairact_r1_student as student

ORIGINAL_CONTROLLER = student.PairStudentController
MODES = ('none', 'arm_c', 'arm_s')


class TreatmentBarrier(pair.PairActBarrier):
    """C: proposals pass; S: only pre-READY close rejection is removed."""

    def __init__(self, *, mode='none', place_sync='off'):
        if mode not in MODES:
            raise ValueError('unknown treatment mode')
        super().__init__(place_sync=place_sync)
        self.mode = mode
        if mode != 'none' and place_sync != 'off':
            raise ValueError('registered treatment requires original place_sync=off')

    @property
    def ready(self):
        # C has no actionable G5 READY producer. The controller separately
        # sends policy-stage READY to the unchanged protocol for DIAGNOSTICS.
        return False if self.mode == 'arm_c' else super().ready

    def propose(self, value, done, previous, *, stage=None):
        if self.mode == 'none':
            return super().propose(value, done, previous, stage=stage)
        if stage not in pair.STAGES:
            raise ValueError('learned pair stage required; no PWM readiness fallback')
        if self.mode == 'arm_s' and stage not in pair.WITHDRAW_STAGES:
            return super().propose(value, done, previous, stage=stage)
        self.pair_stage = stage
        self.stage = pair.BEAMACT4_EQUIVALENT[stage]
        self.blocked = False
        self.pending = self.place_pending = None
        self.started = self.place_started = False
        if stage in pair.WITHDRAW_STAGES and value['pwm']['1'] < previous['pwm']['1']:
            self.events.append(dict(t=value['t'], event='treatment_close_gate_bypassed',
                reason_category='close_before_learned_ready_suppressed',
                blocked_object='UNKNOWN:not_observed', min_gap_m=None,
                gap_scope='not measured: own-command software gate', treatment=self.mode))
        return False

    def issue(self, now, previous, proposal, done, permit, place_permit=False):
        if self.mode != 'arm_c':
            return super().issue(now, previous, proposal, done, permit, place_permit)
        if self.pair_stage not in pair.STAGES or proposal is None:
            raise ValueError('current learned proposal required; no fallback')
        # G3/G6/G7/G8: no permit, pending or started value selects an action.
        self.done = bool(done)
        return dict(deepcopy(proposal), t=now), self.done


class TickExecutor(pair.PairActChunkExecutor):
    """One actual discard and one fresh prediction per registered robot-tick."""

    def __init__(self, predict, **kwargs):
        self.discard_calls = self.prediction_calls = self.tick_count = 0

        def counted(observation, jpegs):
            self.prediction_calls += 1
            return predict(observation, jpegs)

        super().__init__(counted, **kwargs)

    def discard_pending(self):
        self.discard_calls += 1
        return super().discard_pending()

    def step(self, observation, jpegs, *, interrupt=False):
        # Original pairact_r1.py:252-254 resets done_requested then discards
        # for done recovery. Coalesce that SAME reset with the forced G9 clear
        # so done ticks and segment switches cannot add a second discard.
        if self.done_recovery == pair.RECOVERY_MODE and self.core.done_requested:
            self.core.done_requested = False
        self.tick_count += 1
        self.discard_pending()
        return super().step(observation, jpegs, interrupt=interrupt)


class TreatmentController(ORIGINAL_CONTROLLER):
    """Pinned own inputs/executor semantics, external barrier and sequencing."""

    def __init__(self, predict, roles, episode_id, initial, *, mode='none', **kwargs):
        if mode not in MODES:
            raise ValueError('unknown treatment mode')
        self.treatment_mode = mode
        super().__init__(predict, roles, episode_id, initial, **kwargs)
        if mode == 'none':
            return
        recovery = kwargs.get('done_recovery', pair.RECOVERY_MODE)
        if recovery != pair.RECOVERY_MODE:
            raise ValueError('treatment supports the frozen r2 done_recovery only')
        self.executors = {r: TickExecutor(predict, done_recovery=recovery) for r in roles}
        self.barriers = {r: TreatmentBarrier(mode=mode, place_sync=kwargs.get('place_sync', 'off')) for r in roles}
        self.segments = {r: 'grasp' for r in roles}
        self.release_t = {r: None for r in roles}
        self.robot_finish_t = {r: None for r in roles}
        self.episode_origin_t = min(initial[r]['t'] for r in roles)
        self.metrics = {r: dict(skills=Counter(), stages=Counter(), state225_nonzero=0,
                               software_hold_ticks=0, nonzero_wheel_ticks=0, issued_ticks=0) for r in roles}

    def _token(self, rid):
        if self.treatment_mode == 'none':
            return super()._token(rid)
        segment = self.segments[rid] if self.treatment_mode == 'arm_c' else self.segment
        # Literal user HOLD: grasp on EVERY tick, including release segment.
        # Preserve original destination transition ('none' -> 'B'); no wait.
        return 'grasp', student.DESTINATION if segment == 'release' else 'none'

    def propose(self, now, robots):
        if self.treatment_mode == 'none':
            return super().propose(now, robots)
        if set(robots) != set(self.roles) or any(set(v) != student.REQUEST_KEYS for v in robots.values()):
            raise ValueError('own camera + own issued command only')
        if self.proposals:
            raise ValueError('one issue required after each treatment propose')
        out = {}
        for rid, req in robots.items():
            skill, destination = self._token(rid)
            obs, jpegs, path = self.inputs[rid].observe(now, req['jpeg'], skill=skill,
                role=self.roles[rid], destination_zone=destination)
            ex, barrier = self.executors[rid], self.barriers[rid]
            proposal, done = ex.step(obs, jpegs)
            barrier.propose(proposal, done, req['issued'], stage=ex.stage)
            self.proposals[rid] = proposal, done, req['issued']
            m = self.metrics[rid]
            m['skills'][skill] += 1
            m['stages'][ex.stage] += 1
            m['state225_nonzero'] += int(student.c.context(obs)[225] != 0)
            ready = ex.stage == 'ready' if self.treatment_mode == 'arm_c' else bool(barrier.ready)
            out[rid] = dict(ready=ready, observation=obs, rgb_path=path, stage=ex.stage,
                treatment=self.treatment_mode,
                ready_scope='diagnostic_policy_stage_only' if self.treatment_mode == 'arm_c' else 'original_protocol')
        return out

    def issue(self, now, permits):
        if self.treatment_mode == 'none':
            return super().issue(now, permits)
        if set(permits) != set(self.roles) or any(type(v) is not bool for v in permits.values()):
            raise ValueError('protocol permits only')
        if set(self.proposals) != set(self.roles):
            raise ValueError('one current proposal per robot required')
        self.permits = dict(permits)  # diagnostic in C; actionable in S
        out = {}
        for rid, (proposal, done, previous) in self.proposals.items():
            barrier, ex = self.barriers[rid], self.executors[rid]
            hold = self.treatment_mode == 'arm_s' and (barrier.blocked or
                (barrier.stage in ('execute', 'complete') and not permits[rid]) or
                (barrier.pending is not None and not permits[rid]))
            value, done = barrier.issue(now, previous, proposal, done, permits[rid])
            self.inputs[rid].issue(value)
            self.done[rid] = bool(done)
            self.done_since[rid] = (now if self.done_since[rid] is None else self.done_since[rid]) if done else None
            m = self.metrics[rid]
            m['software_hold_ticks'] += int(hold)
            m['nonzero_wheel_ticks'] += int(any(w != 0 for w in value['wheels']))
            m['issued_ticks'] += 1
            segment = self.segments[rid] if self.treatment_mode == 'arm_c' else self.segment
            out[rid] = dict(command=value, done=bool(done), stage=ex.stage, segment=segment,
                permit=permits[rid], blocked=bool(barrier.blocked),
                permit_affects_action=self.treatment_mode == 'arm_s', software_hold=bool(hold),
                inference_calls=ex.prediction_calls, discard_calls=ex.discard_calls)
        self.proposals = {}
        self._sequence(now)
        return out

    def _sequence(self, now):
        if self.treatment_mode == 'none':
            return super()._sequence(now)
        if self.treatment_mode == 'arm_s':
            # Original joint timing/AND/events. Pending chunks are cleared on
            # the NEXT tick by G9, before any step, with no second discard.
            if self.segment == 'grasp' and self._held(now, student.RELEASE_AFTER_S):
                self.segment, self.switch_t = 'release', now
                self.done_since = {r: None for r in self.roles}
                self.release_t = {r: now for r in self.roles}
                self.events.append(dict(t=now, event='release_instruction', source='both_own_done_flags'))
            elif self.segment == 'release' and self.finish_t is None and self._held(now, student.FINISH_AFTER_S):
                self.finish_t = now
                self.robot_finish_t = {r: now for r in self.roles}
                self.events.append(dict(t=now, event='finished', source='both_own_release_done_flags'))
            return
        for rid in self.roles:
            since = self.done_since[rid]
            # Same original _held tolerance (1e-8), same 3 s / 1.5 s constants;
            # only the peer AND is removed. Neither threshold is retuned.
            if self.segments[rid] == 'grasp':
                if since is not None and now - since >= student.RELEASE_AFTER_S - 1e-8:
                    self.segments[rid], self.release_t[rid] = 'release', now
                    self.done_since[rid] = None
                    self.events.append(dict(t=now, event='release_instruction', robot_id=rid, source='own_done_flag'))
            elif self.robot_finish_t[rid] is None and since is not None and now - since >= student.FINISH_AFTER_S - 1e-8:
                self.robot_finish_t[rid] = now
                self.events.append(dict(t=now, event='robot_finished', robot_id=rid, source='own_release_done_flag'))
        unique = set(self.segments.values())
        self.segment = next(iter(unique)) if len(unique) == 1 else 'mixed'
        times = [t for t in self.release_t.values() if t is not None]
        self.switch_t = min(times) if times else None
        # Lane bookkeeping only: never gates another robot's transition/action.
        if self.finish_t is None and all(t is not None for t in self.robot_finish_t.values()):
            self.finish_t = max(self.robot_finish_t.values())
            self.events.append(dict(t=now, event='finished', source='all_independently_finished'))

    def summary(self):
        out = super().summary()
        if self.treatment_mode == 'none':
            return out
        metrics = {}
        for r, m in self.metrics.items():
            ex = self.executors[r]
            metrics[r] = dict(ticks=ex.tick_count, inference_calls=ex.prediction_calls,
                discard_calls=ex.discard_calls, issued_ticks=m['issued_ticks'],
                skill_counts=dict(m['skills']), stage_counts=dict(m['stages']),
                state225_nonzero=m['state225_nonzero'], software_hold_ticks=m['software_hold_ticks'],
                nonzero_wheel_ticks=m['nonzero_wheel_ticks'])
        out['treatment'] = dict(mode=self.treatment_mode, metrics=metrics,
            episode_origin_t=self.episode_origin_t, timestamp_basis='absolute_SIM',
            segments=dict(self.segments) if self.treatment_mode == 'arm_c' else {r: self.segment for r in self.roles},
            release_t=dict(self.release_t), robot_finish_t=dict(self.robot_finish_t),
            release_instruction_t_scope='first_robot' if self.treatment_mode == 'arm_c' else 'joint',
            skill_rule='grasp_all_ticks_including_release',
            READY_funnel_rule='all_robot_policy_stage_ready_same_tick_after_geometry',
            protocol_scope='diagnostic_only' if self.treatment_mode == 'arm_c' else 'original_action_barrier')
        return out
