"""h5 single-step DAgger target preparation, never a controller.

An oracle queried on successive STUDENT states does not supply the expert's
future trajectory from the current state. Supervise h0 only; mask the other
seven horizons unless a separately verified expert branch rollout exists.
Current frozen shadow oracle is qualified only before hover. Its phase and
all other metadata stay outside the student's observation tensor whitelist.
"""
from collections import Counter
import numpy as np

PHASES = {'start', 'fold', 'approach', 'align', 'relook'}


class OracleHoldBoundary:
    """Stop label queries after a student-issued closing command.

    The caller supplies its configured, explicitly issued OPEN startup command.
    Any lower gripper PWM is a potential close. This is a conservative data
    exclusion, not a grasp detector or an action guard; it never changes policy
    commands. Do not re-enable the oracle during this episode after reopening.
    No new hardware PWM threshold or measured joint/contact state is introduced.
    """
    def __init__(self, initial_open_command):
        self.initial_open_pwm = initial_open_command['pwm']['1']
        self.closed_issued = False

    def query(self, issued_history, callback):
        if not issued_history:
            raise ValueError('own issued history required')
        self.closed_issued |= any(c['pwm']['1'] < self.initial_open_pwm for c in issued_history)
        if self.closed_issued:
            return {'label_valid': False, 'teacher_command': None,
                    'query_blocked_by_hold_boundary': True,
                    'rejection_category': 'potential_hold_after_student_issued_close'}
        return callback()


def prepare_single_step(observations, labels, *, contract, audit):
    if (contract.CHUNK, contract.ACTION_DIM) != (8, 14):
        raise ValueError('frozen ACT chunk/action contract required')
    if any(audit.get(k) != 0 for k in ('invisible_measurements', 'held_world_reads', 'teacher_actions_executed')):
        raise ValueError('audited non-executing visible-only oracle required')
    if len(observations) != len(labels) or not observations:
        raise ValueError('nonempty one-to-one student/oracle alignment required')
    accepted, reasons, seen = [], Counter(), set()
    for index, (obs, label) in enumerate(zip(observations, labels)):
        contract.validate_observation(obs)
        sid = obs['sample_id']
        # The 1e-6 clock tolerance is the frozen dataset's raw label pairing
        # tolerance, not a newly chosen physical acceptance threshold.
        if (sid in seen or label.get('sample_id') != sid
                or abs(label['t']-obs['t']) > 1e-6):
            raise ValueError('mismatched, duplicated or time-shifted DAgger label')
        seen.add(sid)
        if label.get('query_blocked_by_hold_boundary') is True:
            reasons['potential_hold_after_student_issued_close'] += 1; continue
        if label.get('teacher_phase') not in PHASES:
            reasons['oracle_phase_outside_qualified_scope'] += 1; continue
        if label.get('phase_after') in ('failed', 'handoff', 'complete'):
            reasons['oracle_failed_or_unqualified_completion'] += 1; continue
        if label.get('label_valid') is not True or label.get('teacher_command') is None:
            reasons['oracle_no_valid_action'] += 1; continue
        if label.get('done', False):
            raise ValueError('pre-hover single-step oracle cannot supply a done target')
        target = contract.command(label['teacher_command'])
        if abs(target['t']-obs['t']) > 1e-6:
            raise ValueError('oracle command is not for the current student state')
        action = np.zeros((8, 14), np.float32)
        pad = np.ones(8, bool)
        action[0] = contract.encode_action(target, done=False)
        pad[0] = False
        accepted.append({'observation_index': index, 'sample_id': sid,
                         'action': action, 'action_is_pad': pad})
    return accepted, {
        'scope': 'pre-hover h0-only DAgger labels; not full-skill oracle',
        'funnel': [dict(gate='student_oracle_pairs', passed=len(observations), rejected=0),
                   dict(gate='qualified_oracle_action', passed=len(accepted),
                        rejected=len(observations)-len(accepted))],
        'rejections': [dict(category=k, reason=k, count=v,
                            blocking_object='not_applicable_label_admission', minimum_gap_m=None,
                            minimum_gap_status='not_applicable_non_geometric') for k,v in sorted(reasons.items())],
        'teacher_actions_executed': 0, 'valid_horizons_per_sample': 1,
        'future_student_path_borrowed_as_expert_chunk': False}
