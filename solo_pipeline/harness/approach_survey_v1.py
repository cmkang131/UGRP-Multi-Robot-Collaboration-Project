"""approach_survey_v1: look around, approach, then square up to the box. Own RGB and own commands only.

Drop-in for the runner's approach slot (same step/arrived/reason/trace/record surface as
approach_servo_v1.ApproachServo), DEFAULT OFF. It replaces the start hint that used to be derived
from the real box position:

  1. survey   : stationary base, 13 camera pan poses, every whole red/cyan blob is projected to the
                floor and merged into an observed list (survey_observe.Survey).
  2. select   : the task names one entry of that list by index. The index comes from the caller
                (in simulation the evaluator matches the designated box to an entry; later a
                planner picks from the list). Nothing but the integer reaches this module.
  3. approach : the pinned c7232b9 servo, started from the selected entry's bearing and range
                (survey_observe.Approach, variant "baseline").
  4. align    : read the box face tilt from the lower blob contour and orbit to the nearest face
                (face_align.FaceAligner). Skipped when the approach did not arrive.

Inputs are JPEG bytes, the caller's command clock and the integer index. No plan, seed, pose,
contact or simulator value is accepted. The component modules live in approach_survey_v1_parts/.
"""
import importlib.util
import sys
from pathlib import Path

PARTS = Path(__file__).resolve().parent / 'approach_survey_v1_parts'
FAR_POSTURE = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
PAN_SEQUENCE = (1500, 1250, 1000, 750, 500, 1000, 1500, 1750, 2000, 2250, 2500, 2000, 1500)
INIT_TICKS = 10        # explicit fixed posture, then 1.0 s
POSE_SETTLE_TICKS = 5  # 0.5 s after each pan command
POSE_FRAMES = 3        # three own images per pan pose
RESTORE_TICKS = 7      # back to the far posture, 0.7 s
ALIGN_LIMIT = 1600


def _load(name):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(PARTS / (name + '.py')))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SurveyApproach:
    """Tick-driven: call step(jpeg, now) once per 0.1 s control tick until arrived is True."""

    def __init__(self, contract, select_index):
        if not callable(select_index):
            raise ValueError('select_index must be a callable taking the observed list')
        self.c = contract
        self._select = select_index
        _load('ground_projection')
        self.baseline = _load('approach_core')
        self.student = _load('survey_observe')
        self.align_mod = _load('face_align')
        self.D_STOP_M = self.baseline.D_STOP_M
        self.survey = self.student.Survey(self.baseline)
        self.stage = 'init'
        self.arrived = False
        self.reason = None
        self.trace = []           # approach-stage rows (same shape the runner already reads)
        self.stage_log = []
        self.entries = None
        self.index = None
        self.servo = None
        self.aligner = None
        self.align_reason = None
        self.approach_reason = None
        self._issued = dict(FAR_POSTURE)
        self._count = 0
        self._pose = 0
        self._ticks = {'init': 0, 'survey': 0, 'restore': 0, 'approach': 0, 'align': 0}

    def _hold(self, now, posture):
        self._issued = {int(k): int(v) for k, v in posture.items()}
        return self.c.command({'t': now, 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                               'pwm': {str(s): int(self._issued[s]) for s in self.c.SERVOS}})

    def _track(self, value):
        self._issued = {int(k): int(v) for k, v in value['pwm'].items()}
        return value

    def step(self, jpeg, now):
        if type(jpeg) is not bytes or type(now) not in (int, float):
            raise ValueError('step accepts only JPEG bytes and the command clock')
        if self.arrived:
            return None
        self._ticks[self.stage] += 1
        if self.stage == 'init':
            self._count += 1
            if self._count >= INIT_TICKS:
                self.stage, self._count, self._pose = 'survey', 0, 0
            return self._hold(now, FAR_POSTURE)
        if self.stage == 'survey':
            posture = {**FAR_POSTURE, 6: PAN_SEQUENCE[self._pose]}
            # Frames taken after the settle wait were captured under this pan command.
            if self._count >= POSE_SETTLE_TICKS:
                self.survey.observe(jpeg, dict(posture))
            self._count += 1
            if self._count >= POSE_SETTLE_TICKS + POSE_FRAMES:
                self._pose, self._count = self._pose + 1, 0
                if self._pose >= len(PAN_SEQUENCE):
                    self.stage = 'restore'
                    return self._hold(now, FAR_POSTURE)
                posture = {**FAR_POSTURE, 6: PAN_SEQUENCE[self._pose]}
            return self._hold(now, posture)
        if self.stage == 'restore':
            self._count += 1
            if self._count >= RESTORE_TICKS:
                self.entries = [dict(e) for e in self.survey.entries()]
                index = self._select([dict(e) for e in self.entries])
                if type(index) is not int or not 0 <= index < len(self.entries):
                    self.index, self.arrived, self.reason = None, True, 'not_found'
                    self.stage_log.append({'stage': 'select', 'result': 'not_found', 'entries': len(self.entries)})
                    return self._hold(now, FAR_POSTURE)
                self.index = index
                self.servo = self.student.Approach(self.baseline, self.c, [dict(e) for e in self.entries], index)
                self.stage = 'approach'
                self.stage_log.append({'stage': 'select', 'result': 'selected', 'index': index,
                                       'entries': len(self.entries)})
            return self._hold(now, FAR_POSTURE)
        if self.stage == 'approach':
            value = self.servo.step(jpeg, now)
            self.trace = self.servo.trace
            if not self.servo.arrived and self.servo.reason is None:
                if value is None:
                    return self._hold(now, self._issued)
                return self._track(value)
            self.reason = self.servo.reason
            self.stage_log.append({'stage': 'approach', 'reason': self.reason, 'ticks': self._ticks['approach']})
            posture = {int(k): int(v) for k, v in (value['pwm'] if value is not None else
                                                   {str(k): v for k, v in self._issued.items()}).items()}
            self.approach_reason = self.reason
            # A near-range handover (box cut off or lost close to the stop point) also goes to the aligner,
            # which first brings the box back into view. Other endings (search exhausted, timeout) do not.
            if self.reason in ('arrived', 'settled', 'handover_near_clipped', 'handover_near_no_blob'):
                self.aligner = self.align_mod.FaceAligner(
                    self.baseline, self.c, [dict(e) for e in self.entries], self.index, posture)
                self.stage = 'align'
            else:
                self.arrived = True
            return self._hold(now, posture)
        if self.stage == 'align':
            value = self.aligner.step(jpeg, now)
            if self.aligner.done or self._ticks['align'] >= ALIGN_LIMIT:
                self.align_reason = self.aligner.reason or 'alignment_budget'
                if self.approach_reason.startswith('handover_near') and self.align_reason.startswith('aligned_'):
                    self.reason = 'arrived'  # recovered and squared up: same handover state as an arrival
                self.arrived = True
                self.stage_log.append({'stage': 'align', 'reason': self.align_reason,
                                       'ticks': self._ticks['align'], 'pulses': len(self.aligner.pulses)})
                return self._hold(now, self._issued)
            return self._track(value)
        raise RuntimeError('unknown stage')

    def approach_seconds(self):
        """Own clock time spent in the approach stage only (0.1 s control ticks)."""
        return 0.1 * self._ticks['approach']

    def record(self):
        base = self.servo.record() if self.servo is not None else {}
        return dict(base, enabled=True, variant='approach_survey_v1', reason=self.reason,
                    inputs='own RGB, own issued commands, one observed-list index',
                    survey={'entries': self.entries, 'selected_index': self.index,
                            'evidence': dict(self.survey.evidence), 'pan_sequence': list(PAN_SEQUENCE)},
                    approach_reason=self.approach_reason,
                    alignment={'ran': self.aligner is not None, 'reason': self.align_reason,
                               'recover_steps': self.aligner.recover_used if self.aligner is not None else 0,
                               'pulses': list(self.aligner.pulses) if self.aligner is not None else [],
                               'face_type': self.aligner.face if self.aligner is not None else None,
                               'quarter_orbit_used': bool(self.aligner.quarter_used) if self.aligner is not None else False},
                    stage_ticks=dict(self._ticks), stage_log=list(self.stage_log))

    def alignment_trace(self):
        return list(self.aligner.trace) if self.aligner is not None else []
