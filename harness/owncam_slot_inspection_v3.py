"""Bounded own-camera empty-slot inspection while keeping the cargo closed."""
from harness.m1_owncam_delivery import M1OwnCamDelivery
from harness.owncam_drive import CARRY_POSTURE, SEARCH_POSE, SETTLE_S
from harness.owncam_memory_v3 import SLOT_CLEAR_MAX_AGE_S

SLOT_VIEW_STANDOFFS_M = (.95, 1.05)
MAX_SLOT_VIEWS = len(SLOT_VIEW_STANDOFFS_M)
SLOT_INSPECTION_TIMEOUT_S = 120.


class SlotInspectionV3:
    def _slot_state(self, now):
        gate = self.verification['place']
        self.slot_record = self.memory.slot_state(now, self.slot_xy, self._slot_half(),
                         exclude=[self.target_track_id], since=gate['since'], max_age_s=SLOT_CLEAR_MAX_AGE_S)
        return self.slot_record['state']

    def _slot_fail(self, now, reason):
        self.outcome = 'SLOT_OCCUPIED_IN_MEMORY' if reason == 'occupied' else 'SLOT_UNVERIFIED'
        self.slot_handoff = {'requires_upper_level_decision': True, 'reason': reason,
                             'slot_id': self.slot_id, 'slot_state': self.slot_record,
                             'attempts': self.verification['place'].get('slot_attempts', 0),
                             'cargo_held': bool(self.skill is not None and self.skill.box.held),
                             'release_started': False}
        self._event(now, 'slot_verification_handoff', **self.slot_handoff)
        self.slot_inspection = None
        self.leg, self.sweep = None, None
        return {'mode': 'done', 'outcome': self.outcome, 'handoff': self.slot_handoff}

    def _begin_slot_inspection(self, now):
        gate = self.verification['place']
        gate.setdefault('slot_deadline', now + SLOT_INSPECTION_TIMEOUT_S)
        if now >= gate['slot_deadline']:
            return self._slot_fail(now, 'inspection_timeout')
        self.slot_inspection = {'stage': 'outbound'}
        return self._next_slot_view(now)

    def _next_slot_view(self, now):
        gate = self.verification['place']
        attempt = gate.get('slot_attempts', 0)
        if attempt >= MAX_SLOT_VIEWS:
            return self._slot_fail(now, 'unknown_after_views')
        gate['slot_attempts'] = attempt + 1
        goal = (self.slot_xy[0] - SLOT_VIEW_STANDOFFS_M[attempt], self.slot_xy[1])
        self.slot_inspection.update(stage='outbound', goal=list(goal))
        self._event(now, 'slot_inspection_viewpoint', attempt=attempt+1, goal=list(goal),
                    posture={**SEARCH_POSE, 1: 1500}, loaded=True)
        self._start_leg(goal, loaded=True)  # same static-map planner/own-pose/keep-outs
        return self._hold()

    def decide(self, now):
        if self.outcome and self.slot_handoff is not None:
            return {'mode': 'done', 'outcome': self.outcome, 'handoff': self.slot_handoff}
        if self.slot_inspection is not None:
            return self._tick_slot_inspection(now)
        return super().decide(now)

    def _tick_slot_inspection(self, now):
        gate, inspection = self.verification['place'], self.slot_inspection
        if now >= gate['slot_deadline']:
            return self._slot_fail(now, 'inspection_timeout')
        stage = inspection['stage']
        if stage in ('outbound', 'return'):
            cmds, outcome = self._drive_leg(now)
            if outcome is None:
                return {'mode': 'tick', 'commands': cmds}
            if outcome != 'arrived':
                return self._slot_fail(now, stage + '_leg_' + outcome)
            self.leg = None
            if stage == 'outbound':
                inspection['stage'] = 'inspect'
                # Fresh, spaced frames at a visible stand-off. Never open grip.
                self._start_sweep(now, 'slot_inspection', {**SEARCH_POSE, 1: 1500},
                                  [1500]*4, CARRY_POSTURE, 'empty_slot_v3')
                return self._hold()
            inspection.update(stage='restore', since=now)
        if inspection['stage'] == 'inspect':
            commands = self._tick_sweep(now)
            if commands is not None:
                return {'mode': 'tick', 'commands': commands}
            inspection['stage'] = 'checked_view'
            self.reanchor_needed = True
        if inspection['stage'] == 'checked_view':
            if self.probe is not None or self.reanchor_needed:
                return self._inspection_reanchor(now)
            state = self._slot_state(now)
            if state == 'occupied':
                return self._slot_fail(now, 'occupied')
            if state != 'free':
                return self._next_slot_view(now)
            mask = self.memory.slot_cells(self.slot_xy, self._slot_half())
            gate['empty_slot_evidence'] = {
                'observed_at': float(self.memory.free_observed_at[mask].min()),
                'frame_ids': sorted(set(self.memory.free_frame_ids[mask].tolist())),
                'viewpoint': inspection['goal'], 'source': 'own_rgb_uncertainty_checked_floor'}
            self._event(now, 'slot_empty_verified', **gate['empty_slot_evidence'])
            inspection['stage'] = 'return'
            self._start_leg(self.skill._preplace_goal(), loaded=True)
            return self._hold()
        if inspection['stage'] == 'restore':
            steps = self._arm_steps(self.skill.box.lift_top_pose())
            if steps:
                inspection['since'] = now
                return {'mode': 'tick', 'commands': [{'kind': 'hold'}] + steps}
            if now - inspection['since'] < SETTLE_S:
                return self._hold()
            self.slot_inspection = None
            self.reanchor_needed = True
            # The normal gate rechecks current occupancy, certificate age,
            # fresh pose and attachment before any skill/release dispatch.
            return self._hold()
        return self._hold()

    def _inspection_reanchor(self, now):
        obs = self.last_obs
        if (obs is None or not -1e-8 <= now-float(obs['sim_time']) <= .25+1e-8
                or obs['frame_id'] == self.last_skill_frame):
            return self._hold()  # advance SIM; bounded even without new frames
        result = M1OwnCamDelivery._skill(self, now)  # reanchor/probe branch returns before release
        if self.outcome:
            return self._slot_fail(now, 'cargo_reanchor_' + self.outcome)
        return result
