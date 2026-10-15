"""Opt-in DART wheel exploration; clean labels and actual history stay separate.

A diagonal zero-mean Gaussian MLE needs squared residuals, not their signs.
The full cross-covariance cannot be recovered from absolute-error summaries.
No online truth, model call, arm noise or alternative student controller.
"""
from contextlib import contextmanager
from copy import deepcopy
import json

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_perturb import PERTURB_MODE, annotate_label

MODE = 'dart_wheels_v1'
PULSE_MODE = 'dart_effort_pulses_v2'
MODES = ('off', MODE, PULSE_MODE, PERTURB_MODE)
PHASES = ('approach', 'align')


def fit_diagonal(rows, *, expected_ids=None):
    seen=set(); errors=[]; selected=[]
    for row in rows:
        sid=row['sample_id']
        if sid in seen: raise ValueError('duplicate residual sample')
        seen.add(sid)
        if row['metadata']['skill']!='grasp': continue
        e=np.asarray(row['first_action']['mae_per_action_dimension'],dtype=float)
        if e.shape!=(c.ACTION_DIM,) or not np.isfinite(e).all() or (e<0).any() or row['first_action']['valid_actions']!=1:
            raise ValueError('unique first-action absolute residuals required')
        errors.append(e[:8]);selected.append(sid)
    if expected_ids is not None and seen!=set(expected_ids): raise ValueError('incomplete residual inventory')
    if len(errors)<2: raise ValueError('insufficient grasp residuals')
    variance=np.mean(np.square(errors),axis=0)
    return {'schema':'ugrp.act6.dart.v1','mode':MODE,'default':'off',
        'dimensions':['wheel0','wheel1','wheel2','wheel3','duration0/.15','duration1/.15','duration2/.15','duration3/.15'],
        'covariance':np.diag(variance).tolist(),'std':np.sqrt(variance).tolist(),
        'mean':[0.]*8,'grasp_rows':len(errors),'all_rows':len(seen),
        'estimator':'diagonal zero-mean Gaussian MLE E[e_j^2]; not centered sample covariance',
        'dart_scale_alpha_per_tick':float(variance.sum()),'scale_multiplier':1.,
        'off_diagonal':'unavailable from absolute errors; fixed diagonal model restriction',
        'phases':list(PHASES),'held_noise':False,'arm_noise':False,
        'projection':'existing decode_action wheel bounds/deadzone; PWM unchanged',
        'scope':'one DART-inspired update, heldout calibration; not iterative DART reproduction'}


class WheelNoise:
    def __init__(self, model=None, *, seed=0, mode='off'):
        if mode not in ('off', MODE, PULSE_MODE):raise ValueError('unknown recovery mode')
        self.mode=mode
        if mode=='off':self.rng=None;return
        if model.get('schema')!='ugrp.act6.dart.v1' or model.get('mode')!=MODE:
            raise ValueError('noise model schema mismatch')
        cov=np.asarray(model['covariance'],float)
        if cov.shape!=(8,8) or not np.isfinite(cov).all() or not np.allclose(cov,cov.T,atol=1e-12):
            raise ValueError('invalid wheel residual covariance')
        vals,vecs=np.linalg.eigh(cov)
        if vals.min() < -1e-12 or vals.max()<=0:raise ValueError('nonpositive residual covariance')
        self.factor=vecs@np.diag(np.sqrt(np.maximum(vals,0)))
        self.rng=np.random.default_rng(seed)
        self.block = None
        self.block_phase = None
        self.block_remaining = 0

    def effort_pulses(self, clean, phase):
        """Perturb body effort, then emit breakaway-safe pulses (opt-in only).

        Push the fitted 8D action residual through the local wheel-impulse
        Jacobian and the fixed mecanum inverse. Hold a draw for four control
        ticks (0.4 s); do not perturb four independent on/off clocks. The 40 ms
        floor is the pinned teacher's existing alignment candidate, extended
        here to approach only in this mode. Motion efficacy needs a new gate.
        """
        fresh = self.block_remaining == 0 or self.block_phase != phase
        if fresh:
            self.block = self.factor@self.rng.standard_normal(8)
            self.block_remaining = 4
            self.block_phase = phase
        self.block_remaining -= 1
        residual = self.block
        w = np.array(clean['wheels']); d = np.array(clean['duration_s'])
        # Expected wheel impulse per 100 ms; durations are never noised clocks.
        average = w*np.minimum(d, .1)/.1
        delta = (np.minimum(d,.1)*residual[:4] + w*.15*residual[4:])/.1
        inverse = np.array([[1,1,1,1],[-1,1,1,-1],[-1,1,-1,1]])/4
        drive = inverse@(average+delta)
        desired = np.array(c.wheel_mix(drive))
        peak = max(.35, float(abs(desired).max()))
        durations = .1*abs(desired)/peak
        moving = durations >= .001
        pulse_floor = moving & (durations < .04)
        wheels = np.where(moving, np.sign(desired)*.35, 0.)
        durations = np.where(moving, np.maximum(.04,durations), 0.)
        applied = c.command({**clean,'wheels':wheels.tolist(),'duration_s':durations.tolist()})
        return applied, {'noise':residual.tolist(), 'new_draw':fresh,
            'body_effort_delta':(inverse@delta).tolist(), 'pulse_floor_wheels':int(pulse_floor.sum()),
            'effort_scaled':peak>.35, 'pulse_floor_s':.04, 'hold_ticks':4,
            'executed_delta':(np.array(c.encode_action(applied))[:8]-np.array(c.encode_action(clean))[:8]).tolist()}

    def apply(self, clean, *, phase_before, phase_after, holding):
        clean=c.command(clean)
        if self.mode=='off' or holding or phase_before not in PHASES or phase_after not in PHASES:
            self.block_remaining = 0
            return deepcopy(clean),None
        if self.mode == PULSE_MODE:
            # A teacher hold/stop stays a hold; noise cannot create a new move.
            if not any(clean['wheels']):
                self.block_remaining = 0
                return deepcopy(clean),None
            return self.effort_pulses(clean, phase_after)
        residual=self.factor@self.rng.standard_normal(8)
        action=np.asarray(c.encode_action(clean));action[:8]+=residual
        decoded=c.decode_action(action)
        applied=c.command({'t':clean['t'],'wheels':decoded['wheels'],
                           'duration_s':decoded['duration_s'],'pwm':clean['pwm']})
        return applied,{'noise':residual.tolist(), 'executed_delta':(
            np.asarray(c.encode_action(applied))[:8]-np.asarray(c.encode_action(clean))[:8]).tolist()}


@contextmanager
def recovery_hooks(teacher_module, recording_module, noise, ledger):
    """Reuse the pinned teacher/recorder without copying their control logic.

    The runner applies the noisy return. Its recorder labels the clean action
    computed from the *current disturbed state*, then remembers the noisy one.
    All teacher propagation and the next student's context see actual commands.
    """
    Teacher,Recorder=teacher_module.SoloTeacher,recording_module.SoloRecorder
    state={}
    class RecoveryTeacher(Teacher):
        def step(self, now, **kwargs):
            before=self.phase
            perturb = noise.mode == PERTURB_MODE
            visible = kwargs.get('measurement') is not None
            if perturb and noise.active:
                # Let the original teacher advance its strict command clock,
                # but freeze the task phase while the external yaw is applied.
                kwargs = {**kwargs, 'measurement': None}
            clean,complete=super().step(now,**kwargs)
            arguments = dict(phase_before=before,phase_after=self.phase,holding=self.holding)
            if perturb:arguments['visible'] = visible
            applied,diagnostic=noise.apply(clean,**arguments)
            if perturb and diagnostic is not None:
                self.sink.pwm.update({int(s): v for s, v in applied['pwm'].items()})
                self.arm.commanded.update(self.sink.pwm)
                # The recovery starts with fresh visible observations. No
                # pre-perturbation target memory or alignment integral survives.
                self.target = self.seen_t = self.stable_t = None
                self._reset_alignment()
            self.remember_applied(applied)
            state.update(clean=deepcopy(clean),applied=deepcopy(applied),
                         perturbation_interval=perturb and diagnostic is not None)
            ledger.write(json.dumps({'t':now,'phase_before':before,'phase_after':self.phase,
                'clean_teacher_command':clean,'applied_command':applied,'disturbance':diagnostic,
                **({'target_visible':visible, 'perturbation_interval':state['perturbation_interval']}
                   if perturb else {})},allow_nan=False)+'\n')
            return applied,complete
    class RecoveryRecorder(Recorder):
        def target(self, value, **kwargs):
            if value!=state.get('applied'):raise ValueError('applied/label alignment mismatch')
            if noise.mode == PERTURB_MODE:
                original = self.label_file
                class AnnotatedWriter:
                    def write(_, text):
                        label = annotate_label(json.loads(text), perturbation_interval=state['perturbation_interval'])
                        return original.write(json.dumps(label,allow_nan=False)+'\n')
                self.label_file = AnnotatedWriter()
                try:super().target(state['clean'],**kwargs)
                finally:self.label_file = original
            else:super().target(state['clean'],**kwargs)
            self.history[-1]=deepcopy(c.command(value))
    if noise.mode=='off':
        yield
        return
    teacher_module.SoloTeacher,recording_module.SoloRecorder=RecoveryTeacher,RecoveryRecorder
    try:yield
    finally:teacher_module.SoloTeacher,recording_module.SoloRecorder=Teacher,Recorder
