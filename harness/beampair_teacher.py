"""Default-off pair-gate contracts; command history, never simulator inputs."""
from copy import deepcopy
from harness.grasp_act_perturb import RecoveryPerturb

MODE = 'beampair1_v1'
DEPENDENCY_SHA = '26f84d0f0ada1c33473c83cca2d3415ce51bd247'
V7_SOURCE_SHA = '13f50f31a40f2e87e3964137c8c2d6d3075ba4e1'


def validate_plan(plan):
    if (plan.get('object_kind') != 'long_beam' or plan.get('target_item') != 'beam_1'
            or set(plan.get('roles', {})) != {'r1','r2'}
            or sorted(plan['roles'].values()) != ['blue','teal']):
        raise ValueError('one distinct colored end per robot required')
    if plan.get('end_color_scene') != 'grasp_act_teal_blue_v1':
        raise ValueError('colored beam scene required')
    ticks=plan.get('burst_ticks')
    # User 2026-10-15 requested the full 1..12 tick probe envelope. This is
    # coverage, not an estimated physical noise distribution or DART optimum.
    if type(ticks) is not int or not 1 <= ticks <= 12:
        raise ValueError('mixed 1..12 tick probe required')


class HeldCargoGuard:
    """Conservative close-command-to-end interval, shared across both robots.

    OPEN=2000 and CLOSED=1500 are the pinned teacher's existing commands.
    This finite grasp-only gate never releases; any close latches hiding for
    both robots. No contact, measured joint or cargo height enters this state.
    """
    def __init__(self):
        self.active=False
        self.first_close_t=None
        self.hidden_measurement_ticks=0
        self.held_world_reads=0

    def issued(self, command):
        if int(command['pwm']['1']) == 1500:
            if not self.active:self.first_close_t=command['t']
            self.active=True

    def sanitize_memory(self, model):
        if self.active:
            model.memory={k:v for k,v in model.memory.items()
                          if k != 'beam_1' and not k.startswith('band_')}

    def validate_measurements(self, rows):
        bad=sum(r['id']=='beam_1' or r['id'].startswith('band_') for r in rows) if self.active else 0
        self.held_world_reads+=bad
        if bad:raise ValueError('held cargo measurement attempted')

    def sanitize_world(self, world):
        if not self.active:return world
        value=deepcopy(world);value['beam']=None
        value['objects'].pop('beam_1',None)
        for vis in value['visibility'].values():
            vis['visible_probes']=0
            vis['objects']=[k for k in vis.get('objects',[]) if k!='beam_1']
            vis['observations']={k:v for k,v in vis.get('observations',{}).items()
                                 if k!='beam_1' and not k.startswith('band_')}
        return value


def perturb_model(ticks):
    # Reuse ACT9's already recorded .35 duty / .1 SIMs pulse and schedule;
    # vary only the explicitly requested burst coverage. No new acceptance
    # threshold is introduced. See act9-scope.json and act11-noise.json.
    return dict(schema='ugrp.act9.perturb.v1',mode='recovery_perturb_v1',default='off',
        probability_per_eligible_tick=.1,minimum_eligible_ticks=12,burst_ticks=ticks,
        max_injections_per_run=1,wheel_duty=.35,pulse_s=.1,phases=['approach','align'],
        held_noise=False,arm_noise=False,perturbation_targets_excluded=True)


def defer_ready_during_probe(teacher, previous_phase, previous_phase_t, active):
    """An exogenous burst must finish before a READY/GO transition is offered."""
    if active and teacher.phase=='ready' and previous_phase in ('approach','align'):
        teacher.phase=previous_phase;teacher.phase_t=previous_phase_t
        if teacher.events and teacher.events[-1].get('to')=='ready':teacher.events.pop()


class PairRecoveryPerturb(RecoveryPerturb):
    """Finish an already issued burst across visible-loss recovery transitions.

    Trigger eligibility stays approach/align with own visible target. Search
    is the response being tested, so it must not shorten that exogenous burst.
    Holding/pick/completion still cancel it. Limits and wheel values are the
    unchanged RecoveryPerturb contract; only the requested duration is fixed.
    """
    def apply(self, clean, *, phase_before, phase_after, holding, visible):
        recovery=('approach','align','search','relook','ready')
        if self.active and not holding and phase_before in recovery and phase_after in recovery:
            phase_before=phase_after='approach'
        return super().apply(clean,phase_before=phase_before,phase_after=phase_after,
                             holding=holding,visible=visible)
