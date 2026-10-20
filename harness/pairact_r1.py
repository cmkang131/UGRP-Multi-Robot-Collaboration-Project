"""pairact-r1 DRAFT: learned pair carry ACT candidate (P4). Default OFF, not executed.

Builds on the beamact3 arm A categorical-wheel ACT and the beamact4 learned
stage head / StudentBarrier / done recovery. Nothing here collects data, trains
or touches a simulator. Five default-off pieces:

1. Eight learned stages (beamact4's six + ``carry`` and ``place``). Stage
   targets come from teacher phases offline (sidecar file, never an input).
2. ``PairActBarrier``: beamact4 StudentBarrier READY -> GO/ACK semantics;
   ``carry``/``place`` are post-GO stages like ``execute``. Optional second
   sync point before lowering (``pairact_r1_place_sync_v1``, off by default).
3. ``PairActChunkExecutor``: beamact4 chunk executor + done recovery, generic
   over the stage tuple.
4. Own issued-command history dither/dropout identical to act18 A-r1
   (``scripts/act18_carry_r1.py`` @3a28d24b4): TRAIN only, targets unchanged.
5. v7 own-issued clock (C2c, deadband 2): +-1/+-2 PWM moves do not reset
   ``pwm_elapsed_s``. Deadband 0 is the unchanged contract ``IssuedClock``.
6. TRAIN-only transition oversampling (READY entry, READY->grasp execute,
   carry->place, place->complete) and sampler-mass completion priors.

Student inputs stay the v6 contract: own RGB history, own issued commands,
task tokens and own clocks. No stage, geometry, partner pose or truth is input.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from harness import grasp_act_contract as c
from harness.beamact_pair_student import StudentBarrier, STAGE_MODE as B4_STAGE_MODE

MODE = 'pairact_r1_v1'
PLACE_SYNC_MODE = 'pairact_r1_place_sync_v1'
RECOVERY_MODE = 'beamact4_done_recovery_v1'
SCHEMA = 'ugrp.grasp_act.adapter.pairact_r1.v1'
TARGET_SCHEMA = 'ugrp.pairact_r1.stage-target.v1'
STAGES = ('approach', 'alignment', 'ready', 'execute', 'carry', 'place', 'recover', 'complete')
WITHDRAW_STAGES = ('approach', 'alignment', 'recover')
POST_GO_STAGES = ('execute', 'carry', 'place', 'complete')
# beamact4 barrier semantics for each pair stage (carry/place need GO like execute).
BEAMACT4_EQUIVALENT = {'approach': 'approach', 'alignment': 'alignment', 'ready': 'ready',
                       'execute': 'execute', 'carry': 'execute', 'place': 'execute',
                       'recover': 'recover', 'complete': 'complete'}
# P5 funnel (pre-registered order). Evaluation only; never a student input.
FUNNEL = ('approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place')
PAD = -1

# Teacher phase vocabulary required from the P2 MJWarp carry/place teacher
# (COLLECT_SPEC.md section 4). Unknown phases are rejected, never guessed.
TEACHER_PHASE_TO_STAGE = {
    'start': 'approach', 'fold': 'approach', 'search': 'approach', 'approach': 'approach',
    'align': 'alignment',
    'ready': 'ready', 'wait_go': 'ready',
    'grasp': 'execute', 'close': 'execute', 'lift': 'execute', 'hold': 'execute',
    'carry': 'carry', 'door': 'carry',
    'lower': 'place', 'open': 'place', 'place': 'place', 'retreat': 'place',
    'recover': 'recover',
    'complete': 'complete', 'done': 'complete',
}
# P2 GPU carry teacher (``harness/pair_carry_teacher_warp.py`` PHASES on
# dsh/pairact-p2-carrypath, recorder label ``teacher_phase='carry:<phase>'``).
CARRY_TEACHER_PHASES = ('carry_hold', 'to_west_staging', 'rotate_door', 'to_door_entry', 'door_pass',
                        'to_east_staging', 'rotate_zone', 'to_zone', 'zone_settle', 'lower', 'open',
                        'raise', 'retreat', 'done')
TEACHER_PHASE_TO_STAGE.update({'carry:' + p: 'carry' for p in CARRY_TEACHER_PHASES[:9]})
TEACHER_PHASE_TO_STAGE.update({'carry:' + p: 'place' for p in ('lower', 'open', 'raise', 'retreat')})
TEACHER_PHASE_TO_STAGE['carry:done'] = 'complete'

# act18 A-r1 history augmentation (identical constants and semantics).
ENTRY = 14
PWM_OFFSET = 8
SERVO_COUNT = 5
COMMAND_SLICE = slice(0, 13)        # wheels, pulse widths, PWMs (age at 13 excluded)
REGISTERED_HISTORY = dict(dither_max_pwm=6, dither_prob=.5, dropout_prob=.1, dropout_min_k=12)
CLOCK_DEADBANDS = (0, 2)
# beamact3 arm A zeroes entries 0..10 after normalisation (COMPACT_HISTORY 5).
# act18 dropout draws k in 1..15, so only k>=12 touches a visible entry
# (effective 0.1*4/15). dropout_min_k=12 keeps every dropout event visible.
VISIBLE_MIN_K = 12
# Stage transition oversampling (h0 stage change, both sides of the change).
TRANSITIONS = (('alignment', 'ready'), ('ready', 'execute'), ('carry', 'place'), ('place', 'complete'))
REGISTERED_SAMPLING = dict(mode='pairact_r1_transition_weighted_v1', window_rows=10, weight=3.)


# ---------------------------------------------------------------- config

def validate_config(config):
    """Registered P4 config draft; any deviation is an explicit error."""
    required = {'mode', 'base_arm', 'stages', 'done_recovery', 'place_sync', 'history_augmentation',
                'issued_clock_deadband', 'steps', 'seed', 'batch_size', 'chunk', 'checkpoint_every',
                'selection', 'sampling'}
    missing = required - set(config)
    if missing:
        raise ValueError(f'pairact config missing {sorted(missing)}')
    if config['mode'] != MODE or tuple(config['stages']) != STAGES:
        raise ValueError('pairact-r1 mode/stage order mismatch')
    if config['base_arm'] != 'A':
        raise ValueError('pairact-r1 is registered on beamact3 arm A')
    if config['done_recovery'] not in ('off', RECOVERY_MODE):
        raise ValueError('unknown done recovery mode')
    if config['place_sync'] not in ('off', PLACE_SYNC_MODE):
        raise ValueError('unknown place sync mode')
    if config['issued_clock_deadband'] not in CLOCK_DEADBANDS:
        raise ValueError('issued clock deadband must be 0 (v6) or 2 (v7)')
    h = config['history_augmentation']
    validate_history_options(**h)
    validate_sampling(config['sampling'])
    if config['batch_size'] != 8 or config['chunk'] != c.CHUNK:
        raise ValueError('batch 8 / chunk 8 kept from beamact2-4')
    if type(config['steps']) is not int or not 1 <= config['steps'] <= 100000:
        raise ValueError('finite step count required')
    if config['checkpoint_every'] <= 0 or config['steps'] % config['checkpoint_every']:
        raise ValueError('checkpoint interval must divide the step count')
    if config['selection'].get('split') != 'validation':
        raise ValueError('checkpoint selection uses validation seeds only')
    return config


def load_config(path):
    return validate_config(json.loads(Path(path).read_text()))


# ---------------------------------------------------------------- stages

def stage_index(stage):
    if stage not in STAGES:
        raise ValueError(f'unknown pair stage {stage!r}')
    return STAGES.index(stage)


def stage_from_phase(phase):
    if phase not in TEACHER_PHASE_TO_STAGE:
        raise ValueError(f'unmapped teacher phase {phase!r}; reject row, do not guess')
    return TEACHER_PHASE_TO_STAGE[phase]


def stage_targets(phases, segment_ids, action_is_pad):
    """Chunk-aligned int64 stage targets for one episode's tensor rows.

    ``phases[i]``/``segment_ids[i]`` describe tensor row ``i`` in the same order
    as ``tensors.npz['state']``. Horizon h of row i targets row i+h; padded
    horizons are PAD and are never READY negatives. A non-padded horizon that
    leaves the row's segment is a conversion error.
    """
    pad = np.asarray(action_is_pad, dtype=bool)
    if pad.ndim != 2 or pad.shape[1] != c.CHUNK or len(phases) != len(pad) or len(segment_ids) != len(pad):
        raise ValueError('one phase/segment per tensor row and chunk-shaped padding required')
    stages = [stage_index(stage_from_phase(p)) for p in phases]
    out = np.full(pad.shape, PAD, dtype=np.int64)
    for i in range(len(pad)):
        for h in range(c.CHUNK):
            if pad[i, h]:
                continue
            j = i + h
            if j >= len(pad) or segment_ids[j] != segment_ids[i]:
                raise ValueError('non-padded horizon crosses a segment boundary')
            out[i, h] = stages[j]
    return out


def decode_stages(logits, stages=STAGES):
    values = np.asarray(logits, dtype=float)
    if values.shape != (c.CHUNK, len(stages)) or not np.isfinite(values).all():
        raise ValueError('finite, horizon-aligned learned stage logits required')
    if np.any((values == values.max(axis=-1, keepdims=True)).sum(axis=-1) != 1):
        raise ValueError('ambiguous learned stage; no readiness fallback')
    return [stages[i] for i in values.argmax(axis=-1)]


# ---------------------------------------------------------------- barrier

class PairActBarrier(StudentBarrier):
    """beamact4 learned-READY barrier over eight pair stages.

    ``carry``/``place`` are executed only after the grasp GO/ACK (like
    ``execute``). With ``place_sync`` on, the first ``place`` proposal after GO
    is frozen as a PLACE-READY (wheels stopped, PWM held: the beam stays held)
    until a second pinned-protocol GO/ACK permits lowering. Withdrawal stages
    clear both syncs. No geometry, partner pose or truth is read.
    """
    def __init__(self, *, place_sync='off'):
        if place_sync not in ('off', PLACE_SYNC_MODE):
            raise ValueError('unknown place sync mode')
        super().__init__(stage_mode=B4_STAGE_MODE)
        self.place_sync, self.pair_stage = place_sync, None
        self.place_pending, self.place_started = None, False

    @property
    def place_ready(self):
        if self.place_sync != PLACE_SYNC_MODE:
            return False
        return self.place_pending is not None or (
            self.place_started and self.pair_stage in ('place', 'complete'))

    def propose(self, value, done, previous, *, stage=None):
        if stage not in STAGES:
            raise ValueError('learned pair stage required; no PWM readiness fallback')
        self.pair_stage = stage
        if stage in WITHDRAW_STAGES:
            self.place_pending, self.place_started = None, False
        held = super().propose(value, done, previous, stage=BEAMACT4_EQUIVALENT[stage])
        if (self.place_sync == PLACE_SYNC_MODE and self.started and not self.blocked
                and self.pending is None and self.place_pending is None
                and stage == 'place' and not self.place_started):
            self.place_pending = (deepcopy(value), bool(done))
            self.events.append(dict(t=value['t'], event='PLACE_READY', source='own_ACT_stage_head'))
        return held

    def issue(self, now, previous, proposal, done, permit, place_permit=False):
        if self.place_pending is not None and self.started and not self.blocked and self.pending is None:
            if not (permit and place_permit):
                self.done = False
                return dict(deepcopy(previous), t=now, wheels=[0.] * 4, duration_s=[0.] * 4), False
            proposal, done = self.place_pending
            self.place_pending, self.place_started = None, True
            self.events.append(dict(t=now, event='place_proposal_released_after_GO_ACK'))
        return super().issue(now, previous, proposal, done, permit)


class PairActChunkExecutor:
    """beamact4 PairChunkExecutor generalized to the pair stage tuple."""
    def __init__(self, predict, *, stages=STAGES, done_recovery='off'):
        from harness.grasp_act_policy import ChunkExecutor
        if done_recovery not in ('off', RECOVERY_MODE):
            raise ValueError('unknown done recovery mode')
        self.stages, self.done_recovery = tuple(stages), done_recovery
        self.stage, self.stage_plan = None, []

        def wrapped(observation, jpegs):
            result = predict(observation, jpegs)
            if not isinstance(result, dict) or set(result) != {'chunk', 'stage_logits'}:
                raise ValueError('stage checkpoint output required; no legacy fallback')
            self.stage_plan = decode_stages(result['stage_logits'], self.stages)
            return result['chunk']
        self.core = ChunkExecutor(wrapped)

    def discard_pending(self):
        self.core.pending.clear()
        self.core.chunks.clear()
        self.stage_plan.clear()

    def step(self, observation, jpegs, *, interrupt=False):
        if self.done_recovery == RECOVERY_MODE and self.core.done_requested:
            self.core.done_requested = False
            self.discard_pending()
        identity = tuple(observation[k] for k in ('robot_id', 'skill', 'object_kind', 'role', 'destination_zone'))
        absorbing = (self.core.done_requested and self.core.identity == identity
                     and self.core.last_t is not None
                     and abs(observation['t'] - self.core.last_t - c.PERIOD_S) <= 1e-5)
        value, done = self.core.step(observation, jpegs, interrupt=interrupt)
        if interrupt:
            self.stage, self.stage_plan = None, []
        elif not absorbing:
            if not self.stage_plan:
                raise ValueError('stage/action horizon mismatch')
            self.stage = self.stage_plan.pop(0)
            if done:
                self.stage_plan.clear()
        return value, done


# ---------------------------------------------------------------- v7 clock

class DeadbandIssuedClock:
    """C2c v7 own-issued clock. deadband 0 == contract IssuedClock behaviour.

    With deadband 2 a servo move of |dPWM| <= 2 from the previously observed
    issued PWM does not reset ``pwm_elapsed_s``; |dPWM| >= 3 resets. Same rule
    as ``scripts/act18_evaluate.py`` DeadbandIssuedClock (C2c PASS, ac274afeb).
    """
    def __init__(self, deadband=0):
        if deadband not in CLOCK_DEADBANDS:
            raise ValueError('registered deadband 0 or 2 required')
        self.deadband = deadband
        self.skill = self.started = self.changed = self.pwm = None
        self.resets = 0

    def observe(self, instruction, now, issued_pwm):
        now = c.finite(now)
        if instruction != self.skill or self.started is None:
            self.skill, self.started = instruction, now
        current = {str(s): int(issued_pwm[str(s)]) for s in c.SERVOS}
        if self.changed is None:
            self.changed = now
        elif any(abs(current[k] - self.pwm[k]) > self.deadband for k in current):
            self.changed = now
            self.resets += 1
        self.pwm = current
        return {'skill_elapsed_s': now - self.started, 'pwm_elapsed_s': now - self.changed}


# ---------------------------------------------------------------- history augmentation

def validate_history_options(*, dither_max_pwm=None, dither_prob=None, dropout_prob=None, dropout_min_k=None):
    if dropout_min_k is not None and (dropout_prob is None or type(dropout_min_k) is not int
                                      or not 1 <= dropout_min_k < c.HISTORY):
        raise ValueError('dropout_min_k needs dropout and an integer in [1, 15]')
    if dither_max_pwm is not None:
        if type(dither_max_pwm) is not int or not 1 <= dither_max_pwm <= 9:
            raise ValueError('history dither max PWM must be an integer in [1, 9]')
        if dither_prob is None or not 0 < dither_prob <= 1:
            raise ValueError('history dither needs a probability in (0, 1]')
    elif dither_prob is not None:
        raise ValueError('dither probability requires dither_max_pwm')
    if dropout_prob is not None and not 0 < dropout_prob < 1:
        raise ValueError('history dropout probability must be in (0, 1)')
    return any(v is not None for v in (dither_max_pwm, dropout_prob))


def pwm_columns():
    return np.array([e * ENTRY + PWM_OFFSET + s for e in range(c.HISTORY) for s in range(SERVO_COUNT)],
                    dtype=np.int64)


def history_dither(state, rng, max_pwm, prob):
    """+-1..max_pwm integer PWM on each raw history PWM value with probability prob."""
    out = np.array(state, dtype=np.float32, copy=True)
    columns = pwm_columns()
    mask = rng.random(len(columns)) < prob
    steps = rng.integers(1, max_pwm + 1, size=len(columns)) * rng.choice((-1, 1), size=len(columns))
    pwm = np.rint(out[columns] * 1000. + 1500.)
    pwm = np.clip(pwm + np.where(mask, steps, 0), 500, 2500)
    out[columns] = ((pwm - 1500.) / 1000.).astype(np.float32)
    return out


def history_dropout(state, rng, prob, min_k=1):
    """With probability prob: entries 0..k-1 take the command content of entry k (ages kept).

    ``min_k=1`` is act18 A-r1 exactly; ``min_k=12`` draws k in 12..15 only."""
    out = np.array(state, dtype=np.float32, copy=True)
    if rng.random() >= prob:
        return out
    k = int(rng.integers(min_k, c.HISTORY))
    keep = out[k * ENTRY:k * ENTRY + ENTRY][COMMAND_SLICE].copy()
    for entry in range(k):
        out[entry * ENTRY:entry * ENTRY + 13] = keep
    return out


def augment_raw_state(raw, rng, options):
    if options.get('dither_max_pwm') is not None:
        raw = history_dither(raw, rng, options['dither_max_pwm'], options['dither_prob'])
    if options.get('dropout_prob') is not None:
        raw = history_dropout(raw, rng, options['dropout_prob'], options.get('dropout_min_k') or 1)
    return raw


# ---------------------------------------------------------------- stage targets / sampling

def segment_ids_from_samples(samples):
    """Contiguous same-skill rows at the control period form one segment."""
    out, current = [], -1
    for i, row in enumerate(samples):
        if i == 0 or row['skill'] != samples[i - 1]['skill'] or abs(row['t'] - samples[i - 1]['t'] - c.PERIOD_S) > 1e-5:
            current += 1
        out.append(current)
    return out


def episode_stage_targets(samples, phase_by_sample_id, action_is_pad):
    """Sidecar targets for one converted episode (rows in samples.json order)."""
    missing = [r['sample_id'] for r in samples if r['sample_id'] not in phase_by_sample_id]
    if missing:
        raise ValueError(f'{len(missing)} rows without teacher_phase; reject episode')
    phases = [phase_by_sample_id[r['sample_id']] for r in samples]
    return stage_targets(phases, segment_ids_from_samples(samples), action_is_pad)


def transition_row_weights(h0_stages, segment_ids, *, window_rows, weight):
    """Rows within window_rows of a registered h0 stage transition get ``weight``."""
    stages = list(h0_stages)
    out = np.ones(len(stages), dtype=np.float64)
    pairs = {(stage_index(a), stage_index(b)) for a, b in TRANSITIONS}
    for i in range(1, len(stages)):
        if segment_ids[i] != segment_ids[i - 1]:
            continue
        if (stages[i - 1], stages[i]) in pairs:
            lo, hi = max(0, i - window_rows), min(len(stages), i + window_rows)
            for j in range(lo, hi):
                if segment_ids[j] == segment_ids[i]:
                    out[j] = weight
    return out


def validate_sampling(sampling):
    if sampling is None or sampling.get('mode') == 'off':
        return None
    if (sampling.get('mode') != REGISTERED_SAMPLING['mode'] or type(sampling.get('window_rows')) is not int
            or not 1 <= sampling['window_rows'] <= 50 or not 1 <= float(sampling.get('weight', 0)) <= 20):
        raise ValueError('unknown or out-of-range transition sampling')
    return sampling


def weighted_completion_priors(skills, done_h0, weights):
    """Balanced-BCE priors under the declared sampler mass (act18 A-r1 form)."""
    totals = {}
    for skill, positive, w in zip(skills, done_h0, weights):
        if positive not in (0., 1.):
            raise ValueError('binary TRAIN completion required')
        v = totals.setdefault(skill, dict(mass=0., positive_mass=0., positive_n=0, rows_N=0))
        v['mass'] += float(w); v['positive_mass'] += float(w) * positive
        v['positive_n'] += int(positive); v['rows_N'] += 1
    return {k: {**v, 'positive_fraction': v['positive_mass'] / v['mass'],
                'source': 'TRAIN h0 labels under the pairact-r1 transition-weighted sampler'}
            for k, v in totals.items() if v['rows_N'] and 0 < v['positive_mass'] < v['mass']}


# ---------------------------------------------------------------- dataset

def pair_dataset_class():
    """Lazily built: GraspDataset + stage sidecar + TRAIN-only history augmentation.

    The audited tensor shard whitelist is unchanged. Stage targets live in a
    separate sidecar manifest (``stage-targets.json``) with per-episode
    ``stage_target.npy`` (int64, rows x CHUNK, PAD=-1) and sha256.
    """
    from harness.grasp_act_data import GraspDataset, safe_path, sha256

    class PairActDataset(GraspDataset):
        def __init__(self, root, split, *, stage_manifest, seed=None, history=None, sampling=None, blank=False):
            history = dict(history or {})
            validate_history_options(**history)
            sampling = validate_sampling(sampling)
            if split != 'train' and (any(v is not None for v in history.values()) or sampling):
                raise ValueError('history augmentation / transition sampling are TRAIN only')
            super().__init__(root, split, blank=blank)
            self.sampling = sampling
            self.history, self.augment = history, False
            self.rng = np.random.default_rng(seed)
            sidecar = json.loads(Path(stage_manifest).read_text())
            if sidecar.get('schema') != TARGET_SCHEMA or tuple(sidecar.get('stages', ())) != STAGES:
                raise ValueError('pairact stage sidecar schema mismatch')
            if sidecar.get('dataset_manifest_sha256') != sha256(self.root / 'manifest.json'):
                raise ValueError('stage sidecar is bound to another dataset')
            by_path = {e['path']: e for e in sidecar['episodes']}
            self.targets = []
            for episode in self.manifest['episodes']:
                if episode['split'] != split:
                    continue
                entry = by_path.get(episode['path'])
                if entry is None:
                    raise ValueError('missing stage targets for episode')
                path = safe_path(Path(stage_manifest).parent, entry['file'])
                if sha256(path) != entry['sha256']:
                    raise ValueError('stage target hash mismatch')
                self.targets.append(np.load(path, allow_pickle=False))
            for shard, target in zip(self.shards, self.targets):
                pad = shard['action_is_pad']
                if (target.dtype != np.int64 or target.shape != pad.shape
                        or np.any((target == PAD) != pad)
                        or np.any((target[~pad] < 0) | (target[~pad] >= len(STAGES)))):
                    raise ValueError('stage target/padding alignment mismatch')
            self.segments = []
            for episode in self.manifest['episodes']:
                if episode['split'] == split:
                    folder = safe_path(self.root, episode['path'])
                    self.segments.append(segment_ids_from_samples(json.loads((folder / 'samples.json').read_text())))
            weights = []
            for target, segments in zip(self.targets, self.segments):
                if len(segments) != len(target):
                    raise ValueError('samples.json/tensor row mismatch')
                if sampling:
                    weights.append(transition_row_weights(target[:, 0], segments,
                                                          window_rows=sampling['window_rows'],
                                                          weight=float(sampling['weight'])))
                else:
                    weights.append(np.ones(len(target)))
            self.row_weights = np.concatenate(weights)

        def sample(self, generator, batch_size):
            import torch
            if not self.sampling:
                return torch.randint(len(self), (batch_size,), generator=generator).tolist()
            weights = torch.from_numpy(self.row_weights)
            return torch.multinomial(weights, batch_size, replacement=True, generator=generator).tolist()

        def completion_priors(self):
            skills, done = [], []
            for shard in self.shards:
                for state, action in zip(shard['state'], shard['action'][:, 0]):
                    task = state[c.HISTORY * ENTRY:c.HISTORY * ENTRY + len(c.SKILLS)]
                    if not np.isin(task, [0., 1.]).all() or task.sum() != 1:
                        raise ValueError('one-hot skill required for completion weighting')
                    skills.append(c.SKILLS[int(task.argmax())]); done.append(float(action[-1]))
            return weighted_completion_priors(skills, done, self.row_weights)

        def __getitem__(self, index):
            batch = super().__getitem__(index)
            j, i = self.index[index]
            if self.augment:
                raw = augment_raw_state(self.shards[j]['state'][i], self.rng, self.history)
                batch['observation.state'] = ((raw - np.asarray(self.stats['state_mean'], np.float32))
                                              / np.asarray(self.stats['state_std'], np.float32))
            batch['stage_target'] = self.targets[j][i].copy()
            return batch

    return PairActDataset


# ---------------------------------------------------------------- model

def install_stage_head(policy, *, stages=STAGES):
    """beamact4 shared-decoder stage head with len(stages) classes."""
    from torch import nn

    class ActionAndStage(nn.Module):
        def __init__(self, action):
            super().__init__()
            self.action = action
            self.stage = nn.Linear(policy.config.dim_model, len(stages))
            self.stage_logits = None

        @property
        def logits(self):
            return self.action.logits

        def forward(self, features):
            self.stage_logits = self.stage(features)
            return self.action(features)

    policy.model.action_head = ActionAndStage(policy.model.action_head).to(next(policy.parameters()).device)
    return policy


def policy_loss(policy, batch, *, stages=STAGES, **kwargs):
    """beamact3 loss + unweighted valid-horizon stage CE (beamact4 form)."""
    import torch
    import torch.nn.functional as F
    from harness import beamact3
    if 'stage_target' not in batch:
        raise ValueError('explicit pair stage targets required')
    target, valid = batch['stage_target'], ~batch['action_is_pad']
    if (target.shape != valid.shape or target.dtype != torch.long or not valid.any()
            or not torch.all((target[valid] >= 0) & (target[valid] < len(stages)))):
        raise ValueError('aligned categorical stage targets required')
    model_batch = {k: v for k, v in batch.items() if k != 'stage_target'}
    head = policy.model.action_head
    head.stage_logits = None
    loss, metrics = beamact3.policy_loss(policy, model_batch, **kwargs)
    logits = head.stage_logits
    if logits is None or logits.shape != (*valid.shape, len(stages)):
        raise ValueError('missing shared-decoder stage logits')
    stage_loss = F.cross_entropy(logits[valid], target[valid])
    return loss + stage_loss, {**metrics, 'stage_ce_loss': stage_loss.detach().item()}


def save_actor(policy, output, stats, provenance, *, config, blank=False, done_mode='balanced_bce_v1'):
    from harness import beamact3
    from harness.grasp_act_data import sha256, write_json
    validate_config(config)
    if not hasattr(policy.model.action_head, 'stage'):
        raise ValueError('explicit pair stage head required')
    beamact3.save_actor(policy, output, stats, provenance, arm=config['base_arm'], blank=blank,
                        done_mode=done_mode)
    output = Path(output)
    meta = json.loads((output / 'adapter.json').read_text())
    meta.update(schema=SCHEMA, pairact_r1=MODE, learned_stages=list(STAGES),
                stage_target_schema=TARGET_SCHEMA, stage_loss='unweighted_valid_mean_cross_entropy',
                stage_decoder='unique_argmax', done_recovery=config['done_recovery'],
                place_sync=config['place_sync'], issued_clock_deadband=config['issued_clock_deadband'],
                training_history_augmentation=config['history_augmentation'],
                pairact_source_sha256=sha256(Path(__file__)))
    write_json(output / 'adapter.json', meta)
    write_json(output / 'SHA256.json', {n: sha256(output / n)
                                        for n in ('model.safetensors', 'config.json', 'adapter.json')})


class PairActActor:
    """Deployment wrapper: same prior inference for actions and stages."""
    def __init__(self, beam3, meta):
        self.beam3, self.meta = beam3, meta
        self.policy, self.stats = beam3.policy, beam3.stats
        self.device, self.done_mode = beam3.device, beam3.done_mode

    def predict(self, observation, jpegs):
        raise ValueError('explicit predict_staged required; no stage-dropping fallback')

    def predict_staged(self, observation, jpegs):
        chunk = self.beam3.predict(observation, jpegs)
        logits = self.policy.model.action_head.stage_logits[0].detach().cpu().numpy()
        decode_stages(logits)
        return {'chunk': chunk, 'stage_logits': np.asarray(logits).tolist()}

    @classmethod
    def load(cls, root, *, device='cpu'):
        import draccus
        from safetensors.torch import load_file
        from harness import beamact3
        from harness.grasp_act_data import sha256
        from harness.grasp_act_policy import GraspActor, make_policy
        root = Path(root)
        hashes = json.loads((root / 'SHA256.json').read_text())
        if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'} or any(
                sha256(root / n) != v for n, v in hashes.items()):
            raise ValueError('pairact inventory/hash mismatch')
        meta = json.loads((root / 'adapter.json').read_text())
        if (meta.get('schema') != SCHEMA or meta.get('pairact_r1') != MODE
                or meta.get('learned_stages') != list(STAGES)
                or meta.get('stage_target_schema') != TARGET_SCHEMA
                or meta.get('pairact_source_sha256') != sha256(Path(__file__))
                or meta.get('adapter_source_sha256') != sha256(Path(beamact3.__file__))
                or meta.get('beamact3_v1') != 'A' or meta.get('blank_images')
                or meta.get('done_mode') != 'balanced_bce_v1'
                or meta.get('issued_clock_deadband') not in CLOCK_DEADBANDS
                or meta.get('contract_sha256') != sha256(Path(c.__file__))):
            raise ValueError('pairact adapter mismatch')
        policy = install_stage_head(beamact3.install_head(make_policy(device=device), meta['stats']))
        saved = json.loads((root / 'config.json').read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        saved['device'] = actual['device']
        if saved != actual:
            raise ValueError('pairact config mismatch')
        policy.load_state_dict(load_file(str(root / 'model.safetensors')), strict=True)
        base = GraspActor(policy, meta['stats'], device=device, done_mode=meta['done_mode'])
        return cls(beamact3.Beam3Actor(base, 'A'), meta)


# ---------------------------------------------------------------- offline gate (validation split only)

# Pre-registered thresholds (experiments/2026-10-21-pairact-r1/OFFLINE_GATE.md).
GATE = dict(stage_macro_acc_min=.80, premature_ready_max=.02, premature_post_go_max=.02,
            done_false_positive_max=.01, done_recall_min=.80, transition_recall_min=.80,
            transition_window_rows=10, dither_stage_acc_drop_max=.05, dither_done_false_positive_max=.02)
DONE_THRESHOLD = .65   # grasp_act_contract.decode_action
PRE_GO = ('approach', 'alignment', 'recover')


def transition_recall(pred, target, segments, window_rows):
    """Per registered transition: fraction of true h0 transitions whose 'to' stage is
    predicted within window_rows rows after the change (same segment)."""
    out = {}
    for a, b in TRANSITIONS:
        ia, ib = stage_index(a), stage_index(b)
        hits = total = 0
        for i in range(1, len(target)):
            if segments[i] != segments[i - 1] or (target[i - 1], target[i]) != (ia, ib):
                continue
            total += 1
            hits += any(pred[j] == ib for j in range(i, min(len(target), i + window_rows + 1))
                        if segments[j] == segments[i])
        out[f'{a}->{b}'] = dict(hits=hits, total=total, recall=hits / total if total else None)
    return out


def offline_metrics(pred, target, segments, done_score, done_target, *, window_rows=GATE['transition_window_rows']):
    """h0 metrics over one split. pred/target are stage indices, done_* per row."""
    pred, target = np.asarray(pred), np.asarray(target)
    done_score, done_target = np.asarray(done_score, float), np.asarray(done_target, float)
    if not (len(pred) == len(target) == len(segments) == len(done_score) == len(done_target)) or not len(pred):
        raise ValueError('aligned nonempty offline rows required')
    per_stage = {}
    for i, name in enumerate(STAGES):
        rows = target == i
        if rows.any():
            per_stage[name] = dict(n=int(rows.sum()), acc=float((pred[rows] == i).mean()))
    pre = np.isin(target, [stage_index(s) for s in PRE_GO])
    done_pred = done_score >= DONE_THRESHOLD
    negatives, positives = done_target == 0, done_target == 1
    return dict(rows=int(len(pred)), per_stage=per_stage,
                stage_macro_acc=float(np.mean([v['acc'] for v in per_stage.values()])),
                premature_ready=float((pred[pre] == stage_index('ready')).mean()) if pre.any() else None,
                premature_post_go=float(np.isin(pred[pre], [stage_index(s) for s in POST_GO_STAGES]).mean())
                if pre.any() else None,
                done_false_positive=float(done_pred[negatives].mean()) if negatives.any() else None,
                done_recall=float(done_pred[positives].mean()) if positives.any() else None,
                transitions=transition_recall(pred.tolist(), target.tolist(), segments, window_rows))


def gate(clean, dithered=None, thresholds=GATE):
    """Return (passed, reasons). Missing measurements fail; nothing is waived."""
    t, reasons = thresholds, []
    def need(ok, why):
        if not ok:
            reasons.append(why)
    need(clean['stage_macro_acc'] >= t['stage_macro_acc_min'], 'G1 stage macro accuracy')
    need(clean['premature_ready'] is not None and clean['premature_ready'] <= t['premature_ready_max'],
         'G2 READY before alignment end')
    need(clean['premature_post_go'] is not None and clean['premature_post_go'] <= t['premature_post_go_max'],
         'G2 post-GO stage before READY')
    need(clean['done_false_positive'] is not None and clean['done_false_positive'] <= t['done_false_positive_max'],
         'G3 done false positive')
    need(clean['done_recall'] is not None and clean['done_recall'] >= t['done_recall_min'], 'G3 done recall')
    for name, v in clean['transitions'].items():
        need(v['total'] > 0 and v['recall'] >= t['transition_recall_min'], f'G4 transition {name}')
    if dithered is None:
        reasons.append('G5 dithered-history check missing')
    else:
        need(clean['stage_macro_acc'] - dithered['stage_macro_acc'] <= t['dither_stage_acc_drop_max'],
             'G5 stage accuracy under dithered history')
        need(dithered['done_false_positive'] is not None
             and dithered['done_false_positive'] <= t['dither_done_false_positive_max'],
             'G5 done false positive under dithered history')
    return not reasons, reasons


def select_checkpoint(rows):
    """rows: [{'step', 'passed', 'clean'}]; validation split only.

    Among passing checkpoints: max of the minimum transition recall, then
    stage macro accuracy, then the earliest step. None passing -> None (NOT_READY).
    """
    passing = [r for r in rows if r['passed']]
    if not passing:
        return None
    def key(r):
        recalls = [v['recall'] for v in r['clean']['transitions'].values()]
        return (min(recalls), r['clean']['stage_macro_acc'], -r['step'])
    return max(passing, key=key)['step']
