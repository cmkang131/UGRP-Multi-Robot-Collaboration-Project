"""Pair-owned stop-decision contract; no scheduler, estimator or simulator edits."""

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
