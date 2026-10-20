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

# act18 A-r1 history augmentation (identical constants and semantics).
ENTRY = 14
PWM_OFFSET = 8
SERVO_COUNT = 5
COMMAND_SLICE = slice(0, 13)        # wheels, pulse widths, PWMs (age at 13 excluded)
REGISTERED_HISTORY = dict(dither_max_pwm=6, dither_prob=.5, dropout_prob=.1)
CLOCK_DEADBANDS = (0, 2)


# ---------------------------------------------------------------- config

def validate_config(config):
    """Registered P4 config draft; any deviation is an explicit error."""
    required = {'mode', 'base_arm', 'stages', 'done_recovery', 'place_sync', 'history_augmentation',
                'issued_clock_deadband', 'steps', 'seed', 'batch_size', 'chunk', 'checkpoint_every',
                'selection'}
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

def validate_history_options(*, dither_max_pwm=None, dither_prob=None, dropout_prob=None):
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


def history_dropout(state, rng, prob):
    """With probability prob: entries 0..k-1 take the command content of entry k (ages kept)."""
    out = np.array(state, dtype=np.float32, copy=True)
    if rng.random() >= prob:
        return out
    k = int(rng.integers(1, c.HISTORY))
    keep = out[k * ENTRY:k * ENTRY + ENTRY][COMMAND_SLICE].copy()
    for entry in range(k):
        out[entry * ENTRY:entry * ENTRY + 13] = keep
    return out


def augment_raw_state(raw, rng, options):
    if options.get('dither_max_pwm') is not None:
        raw = history_dither(raw, rng, options['dither_max_pwm'], options['dither_prob'])
    if options.get('dropout_prob') is not None:
        raw = history_dropout(raw, rng, options['dropout_prob'])
    return raw


# ---------------------------------------------------------------- dataset

def pair_dataset_class():
    """Lazily built: GraspDataset + stage sidecar + TRAIN-only history augmentation.

    The audited tensor shard whitelist is unchanged. Stage targets live in a
    separate sidecar manifest (``stage-targets.json``) with per-episode
    ``stage_target.npy`` (int64, rows x CHUNK, PAD=-1) and sha256.
    """
    from harness.grasp_act_data import GraspDataset, safe_path, sha256

    class PairActDataset(GraspDataset):
        def __init__(self, root, split, *, stage_manifest, seed=None, history=None, blank=False):
            super().__init__(root, split, blank=blank)
            history = dict(history or {})
            validate_history_options(**history)
            if split != 'train' and any(v is not None for v in history.values()):
                raise ValueError('history augmentation is TRAIN only')
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
