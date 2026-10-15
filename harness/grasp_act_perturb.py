"""Opt-in, command-only recovery coverage probe; no world/pose inputs.

This is DART-inspired collection, not the optimized DART noise algorithm.
The fixed probe parameters must pass a new physical gate on GCP.
"""
from copy import deepcopy
import math
import random
import hashlib
import json
from pathlib import Path
import subprocess

from harness import grasp_act_contract as c

PERTURB_MODE = 'recovery_perturb_v1'
PHASES = ('approach', 'align')


class RecoveryPerturb:
    mode = PERTURB_MODE

    def __init__(self, model, *, seed):
        if (model.get('schema') != 'ugrp.act9.perturb.v1'
                or model.get('mode') != PERTURB_MODE or model.get('default') != 'off'):
            raise ValueError('recovery perturb schema mismatch')
        if any(model.get(k) != v for k, v in {
                'wheel_duty': .35, 'pulse_s': .1, 'max_injections_per_run': 1,
                'phases': list(PHASES), 'held_noise': False, 'arm_noise': False,
                'perturbation_targets_excluded': True}.items()):
            raise ValueError('fixed robot-only perturbation contract mismatch')
        self.probability = model['probability_per_eligible_tick']
        self.ticks = model['burst_ticks']
        self.delay = model['minimum_eligible_ticks']
        if (type(self.probability) not in (int, float) or not math.isfinite(self.probability)
                or not 0 < self.probability <= 1 or type(self.ticks) is not int
                or not 1 <= self.ticks <= 12 or type(self.delay) is not int or self.delay < 1):
            raise ValueError('invalid bounded recovery perturb schedule')
        self.rng = random.Random(seed)
        self.remaining = self.eligible_ticks = self.injections = 0
        self.direction = self.pwm = None

    @property
    def active(self):
        return self.remaining > 0

    def apply(self, clean, *, phase_before, phase_after, holding, visible):
        clean = c.command(clean)
        eligible = not holding and phase_before in PHASES and phase_after in PHASES
        if not eligible:
            self.remaining = 0
            return deepcopy(clean), None
        if not self.active and not self.injections and visible and any(clean['wheels']):
            self.eligible_ticks += 1
            if self.eligible_ticks >= self.delay and self.rng.random() < self.probability:
                self.injections = 1
                self.remaining = self.ticks
                self.direction = self.rng.choice((-1, 1))
                self.pwm = deepcopy(clean['pwm'])
        if not self.active:
            return deepcopy(clean), None
        self.remaining -= 1
        # A fixed robot yaw command, never teleportation or cargo displacement.
        # Freeze issued gaze during this exogenous interval so tracking cannot
        # cancel the probe. The native camera mount/FOV are unchanged.
        wheels = [self.direction * w for w in (-.35, .35, -.35, .35)]
        applied = c.command({**clean, 'wheels': wheels, 'duration_s': [.1]*4, 'pwm': self.pwm})
        return applied, {'mode': self.mode, 'episode_id': 1, 'kind': 'fixed_body_yaw',
            'direction': self.direction, 'tick': self.ticks-self.remaining,
            'burst_ticks': self.ticks, 'training_target': False}


def annotate_label(label, *, perturbation_interval):
    """Teacher-side metadata only; the student observation allowlist stays intact."""
    label = {**label, 'perturbation_interval': bool(perturbation_interval),
             'training_target': bool(label['local_skill_sample'] and not perturbation_interval)}
    if perturbation_interval:
        label.update(local_skill_sample=False, done=False, terminal_reason=None)
    return label


def validate_recorded_labels(labels, audit):
    if len(labels) != audit['command_ticks']:
        raise ValueError('perturbation recording/ledger length mismatch')
    for label in labels:
        if (type(label.get('perturbation_interval')) is not bool
                or type(label.get('training_target')) is not bool
                or label['training_target'] != label['local_skill_sample']
                or (label['perturbation_interval'] and (label['training_target'] or label['done']))):
            raise ValueError('missing or inconsistent perturbation training mask')
    if [l['clean_teacher_command']['t'] for l in labels if l['perturbation_interval']] != audit['perturbation_times']:
        raise ValueError('perturbation recording/ledger mask mismatch')


def recovery_statistics(rows):
    """Count probe-attributed visible -> lost -> reacquired episodes from a ledger.

    Visibility is the existing own-camera input gate, not evaluation pose or
    physical success. A reacquisition during the exogenous burst does not count.
    Unresolved loss at phase exit/end is a recovery failure, once per probe.
    """
    episodes = []
    current = None
    perturbed = 0
    for row in rows:
        visible = row['target_visible']
        if type(visible) is not bool:
            raise ValueError('boolean own-camera visibility required')
        diagnostic = row['disturbance']
        injection = diagnostic is not None and diagnostic.get('mode') == PERTURB_MODE
        if row['perturbation_interval'] is not injection:
            raise ValueError('perturbation label/command mismatch')
        perturbed += injection
        if injection and diagnostic['tick'] == 1:
            if current is not None:
                raise ValueError('overlapping recovery probes')
            current = {'episode_id': diagnostic['episode_id'], 'start_t': row['t'],
                       'lost_t': None, 'reacquired_t': None, 'failure': False}
            episodes.append(current)
        if current is not None:
            if not visible and current['lost_t'] is None:
                current['lost_t'] = row['t']
            if visible and current['lost_t'] is not None and not injection:
                current['reacquired_t'] = row['t']
                current = None
            elif row['phase_after'] not in (*PHASES, 'relook'):
                current['failure'] = current['lost_t'] is not None
                current = None
    if current is not None:
        current['failure'] = current['lost_t'] is not None
    return {'schema': 'ugrp.act9.recovery_audit.v1', 'command_ticks': len(rows),
        'perturbation_ticks': perturbed, 'perturbation_fraction': perturbed/max(1, len(rows)),
        'perturbation_times': [r['t'] for r in rows if r['perturbation_interval']],
        'lost_N': sum(e['lost_t'] is not None for e in episodes),
        'reacquired_N': sum(e['reacquired_t'] is not None for e in episodes),
        'recovery_scene_N': sum(e['reacquired_t'] is not None for e in episodes),
        'recovery_failure_N': sum(e['failure'] for e in episodes),
        'perturbation_no_loss_N': sum(e['lost_t'] is None for e in episodes),
        'episodes': episodes,
        'scope': 'own-camera visibility gate; reacquisition is not task success'}


def verified_recovery_audit(result, result_path):
    """Recount the decoded-hash-bound ledger next to a retrieved raw result."""
    recovery = result['recovery']
    path = Path(result_path).parent.parent / Path(recovery['ledger']).name
    if path.exists():
        raw = path.read_bytes()
    else:
        raw = subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])
    if hashlib.sha256(raw).hexdigest() != recovery['sha256']:
        raise ValueError('recovery ledger hash mismatch')
    audit = recovery_statistics([json.loads(line) for line in raw.splitlines() if line.strip()])
    if audit != recovery.get('audit') or recovery.get('perturbation_targets_excluded') is not True:
        raise ValueError('recovery audit/label exclusion mismatch')
    return audit
