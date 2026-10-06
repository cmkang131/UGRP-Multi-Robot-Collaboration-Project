"""Pair-owned stop-decision contract; no scheduler, estimator or simulator edits."""

from harness import pair_llm_clock as clock

from harness.zone_study_contract import ContractViolation

DECISION_WINDOW_S = 10.
LOOK_AGAIN_PER_STOP = 1
LOOK_AGAIN_PER_CASE = 1
CALLS_PER_ACTOR = 36
CALLS_TOTAL = 72
UTTERANCES_PER_ACTOR = 6
UTTERANCES_TOTAL = 12
COHORT_TOKEN_CAP = 1_100_000
LLM_INERT_THRESHOLD = .5
CARRY_CHOICES = ('continue', 'set_down')
POST_LOOK_CHOICES = ('regrasp', 'look_again')
HOOK_ACTIONS = {'carry_decision': CARRY_CHOICES, 'post_look_decision': POST_LOOK_CHOICES}
HOOK_EVENTS = ('carry_leg_started', 'carry_stop_reached', 'setdown_started', 'setdown_completed',
               'relook_result', 'regrasp_result', 'carry_resumed')


class DecisionWindow:
    """One robot's window on the harness clock. No controller/evaluation fields are copied."""

    def __init__(self):
        self.current = None
        self.serial = 0

    def on_event(self, event, *, origin_s):
        if event['event'] in ('job_done', 'job_failed'):
            self.current = None
            return False
        if event['event'] != 'pair_progress':
            return False
        detail = event.get('detail') or {}
        kind = detail.get('kind')
        if kind == 'carry_stop_reached':
            command, end = 'carry_decision', detail.get('decide_at_s')
            cutoff = detail.get('latch_until_s')
        elif kind == 'relook_result' and 'window_until_s' in detail:
            command, end = 'post_look_decision', detail['window_until_s']
            cutoff = end
        else:
            return False
        start = event.get('sim_s')
        start, end, cutoff = (clock.ticks(t) for t in (start, end, cutoff))
        origin = clock.ticks(origin_s)
        if not (start <= cutoff <= end and 0 < end-start <= clock.WINDOW):
            raise ContractViolation('invalid decision window interval')
        self.serial += 1
        self.current = {'kind': command, 'opened_at_sim_s': clock.seconds(start-origin),
                        'decide_at_sim_s': clock.seconds(end-origin),
                        'latch_until_sim_s': clock.seconds(cutoff-origin)}
        return True

    def is_open(self, now):
        w = self.current
        return w is not None and clock.ticks(w['opened_at_sim_s']) <= clock.ticks(now) < clock.ticks(w['decide_at_sim_s'])

    def snapshot(self, now):
        return dict(self.current) if self.is_open(now) else None

    def reference(self, now):
        return self.serial if self.is_open(now) else None


def record():
    return {'decision_window_s': DECISION_WINDOW_S, 'post_look_window_s': DECISION_WINDOW_S,
            'same_in_all_conditions': True, 'carry_choices': list(CARRY_CHOICES),
            'post_look_choices': list(POST_LOOK_CHOICES),
            'look_again_caps': {'per_stop': LOOK_AGAIN_PER_STOP, 'per_robot_per_case': LOOK_AGAIN_PER_CASE},
            'llm_inert_threshold': LLM_INERT_THRESHOLD, 'llm_inert_comparison': 'strictly_greater',
            'token_method': 'M2', 'cohort_token_cap': COHORT_TOKEN_CAP,
            'message_wake_scope': 'stop_window',
            'deviation': 'Coordinator e7: received text can wake the owning robot inside a decision window '
                         'while its pair job remains active; sealed scheduler sources stay unchanged.'}
