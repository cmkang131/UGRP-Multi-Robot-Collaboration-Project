"""Default-OFF RL preparation skeleton on top of ACT + MJWarp (warp3 RECORD_API_READY).

No physics or GPU training is executed by this module. RL training remains gated
until base ACT beats the zero-hold persistence baseline on validation wheel MAE
and achieves non-zero closed-loop task completions (beamact2: 0/20, wheel MAE
0.054589 vs persistence 0.023129; beamact3 A/B in progress).

Every constant below cites its hardware spec, empirical percentile, or primary
literature source per the 2026-10-15 UGRP constant-grounding rule:
- SIM_TICK_S = 0.1: ACT15 control tick period (10 Hz, harness/grasp_act_contract.py).
- EPISODE_CAP_TICKS = 900 (90.0 SIMs): ACT15 full episode horizon (warp_act_api.py:410).
- RING_BUFFER_TICKS = 100 (10.0 SIMs @ 10 Hz): playback1 finding (7/10 failures
  missed fast oscillation at 1 Hz); recording-only ring buffer (warp_act_api.py:107).
- DEFAULT_NWORLD_PILOT = 8, DEFAULT_NWORLD_FULL = 16: warp1 gcp2 L4 benchmark
  (N=16 wall/SIM median 0.415 s/SIMs, 4.9x faster than CPU) and MuJoCo Playground
  (Zakka et al. 2025, arXiv:2502.08844v1 Sec. IV-D1: vision CNN/backbone updates
  take 57-91% of step time, bounding vision batch size on a single 24 GiB L4).
- PILOT_MAX_TRANSITIONS = 7200 (720.0 SIMs = 8 worlds x 10 episodes x 90 SIMs),
  STAGE1_MAX_TRANSITIONS = 72000 (7200.0 SIMs = 16 worlds x 50 episodes x 90 SIMs):
  SIM-time / transition-count budget caps (2026-10-15 rule: never cap planning or
  learning steps by wall-clock seconds).
- EXPLORATION_WARMUP_FRACTION = 0.20: Policy Decorator (Yuan et al., ICLR 2025,
  arXiv:2412.13630v1 Sec. 3.2 Eq. 2 & Table 2: linear epsilon ramp over H=100K/500K
  = 20% of manipulation budget to preserve base policy trajectories early on).
- GAMMA = 0.995, N_STEP = 3, ACTOR_DELAY = 4, TAU = 0.005, LR = 3e-4, BATCH_SIZE = 128:
  ResFiT (ankile/resfit, arXiv:2509.19301v1 Sec. III-C Table II) & TD3 (Fujimoto
  et al., ICML 2018); gamma=0.995 @ 10 Hz gives a 13.8 SIMs half-life matching
  ACT15's 10-15 s approach-and-lift window.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from scripts.rl_act_actor import compose
from scripts.rl_act_env import ActorEnv, ActorInput, TrainingOutput
from scripts.rl_act_reward import GAMMA, Heuristics, TrainingTruth, reward_transition

SIM_TICK_S = 0.1
EPISODE_CAP_TICKS = 900
EPISODE_CAP_SIM_S = EPISODE_CAP_TICKS * SIM_TICK_S
RING_BUFFER_TICKS = 100

DEFAULT_NWORLD_PILOT = 8
DEFAULT_NWORLD_FULL = 16
PILOT_MAX_TRANSITIONS = 7200
PILOT_MAX_SIM_S = PILOT_MAX_TRANSITIONS * SIM_TICK_S
STAGE1_MAX_TRANSITIONS = 72000
STAGE1_MAX_SIM_S = STAGE1_MAX_TRANSITIONS * SIM_TICK_S

EXPLORATION_WARMUP_FRACTION = 0.20

WARP3_SOURCE_SHA = '0362037280c6cbc4677f70366db43b9892b23690'
WARP3_CONTROLLER_SHA = 'f0db6b1abb842ea65b71c433738210254f300a7c'
WARP3_GATE_RAW_SHA = 'a7f0a28cf927f718245c4c1c31bcf4cc760ad5526be5ff62bfe4a5727bd329be'
WARP3_GATE_MIN_PASS = 38  # warp3 gate contract: n >= 38 out of N == 40 (warp_act_api.py:46)
WARP3_GATE_TOTAL = 40

FORBIDDEN_ACTOR_KEYS = frozenset({
    'qpos', 'qvel', 'xpos', 'xmat', 'contact', 'contact_forces', 'finger_forces',
    'distance_m', 'alignment_rad', 'target_xy', 'stable_lift', 'lift_ok',
    'clearance_m', 'tilt_deg', 'weld', 'weld_active', 'critic', 'reward',
    'privileged', 'training', 'ground_truth', 'top', 'top_rgb',
})

VALID_GAP_STATUSES = frozenset({'measured', 'unobserved', 'unmeasured', 'not_geometric'})


@dataclass(frozen=True)
class RejectionRecord:
    """2026-10-15 rule #2: non-empty category, blocking_object, and minimum_gap_m/status."""
    category: str
    blocking_object: str
    minimum_gap_m: float | None
    minimum_gap_status: str = 'measured'
    cap_end: bool = False
    detail: str = ''

    def __post_init__(self):
        if type(self.category) is not str or not self.category.strip():
            raise ValueError('rejection category must be a non-empty string')
        if type(self.blocking_object) is not str or not self.blocking_object.strip():
            raise ValueError('blocking_object must be a non-empty string')
        if self.minimum_gap_status not in VALID_GAP_STATUSES:
            raise ValueError('invalid minimum_gap_status: ' + str(self.minimum_gap_status))
        if type(self.cap_end) is not bool:
            raise ValueError('cap_end must be a boolean')
        if self.minimum_gap_m is None:
            if self.minimum_gap_status == 'measured':
                raise ValueError('missing minimum_gap_m requires explicit non-measured status')
        else:
            if (type(self.minimum_gap_m) not in (int, float)
                    or type(self.minimum_gap_m) is bool
                    or not math.isfinite(float(self.minimum_gap_m))):
                raise ValueError('minimum_gap_m must be finite float or None with status')


@dataclass(frozen=True)
class FunnelStage:
    """Single sequential gate in a funnel/rejection table (2026-10-15 rule #6)."""
    gate_id: str
    input_count: int
    passed_count: int
    rejected_count: int
    rejections: tuple[RejectionRecord, ...] = ()

    def __post_init__(self):
        if type(self.gate_id) is not str or not self.gate_id.strip():
            raise ValueError('gate_id must be non-empty')
        for v in (self.input_count, self.passed_count, self.rejected_count):
            if type(v) is not int or v < 0:
                raise ValueError('funnel counts must be nonnegative integers')
        if self.passed_count + self.rejected_count != self.input_count:
            raise ValueError(f'funnel conservation mismatch at {self.gate_id}')
        if self.rejected_count > 0 and not self.rejections:
            raise ValueError(f'rejected_count > 0 at {self.gate_id} requires RejectionRecord entries')


@dataclass(frozen=True)
class FunnelTable:
    """Sequential cumulative pass/reject funnel table required for queue approval."""
    experiment_id: str
    source_path: str
    reproduce_command: str
    initial_candidates: int
    stages: tuple[FunnelStage, ...]

    def __post_init__(self):
        if not self.experiment_id.strip() or not self.source_path.strip() or not self.reproduce_command.strip():
            raise ValueError('funnel metadata (experiment_id, source_path, reproduce_command) required')
        if type(self.initial_candidates) is not int or self.initial_candidates <= 0 or not self.stages:
            raise ValueError('positive initial_candidates and at least one FunnelStage required')
        expected = self.initial_candidates
        for stage in self.stages:
            if stage.input_count != expected:
                raise ValueError(f'stage {stage.gate_id} input_count {stage.input_count} != previous passed {expected}')
            expected = stage.passed_count

    def to_dict(self) -> dict:
        return {
            'schema': 'ugrp.funnel_rejection_table.v1',
            'experiment_id': self.experiment_id,
            'source_path': self.source_path,
            'reproduce_command': self.reproduce_command,
            'initial_candidates': self.initial_candidates,
            'final_passed_count': self.stages[-1].passed_count,
            'stages': [
                {
                    'gate_id': s.gate_id,
                    'input_count': s.input_count,
                    'passed_count': s.passed_count,
                    'rejected_count': s.rejected_count,
                    'rejections': [asdict(r) for r in s.rejections],
                }
                for s in self.stages
            ],
        }

    def write_json(self, path: str | Path) -> Path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + '\n')
        return target


def validate_queue_rejection_table(queue_payload: dict) -> dict:
    """Enforce 2026-10-15 rule #6: queue JSON must carry an absolute rejection_table path."""
    if 'rejection_table' not in queue_payload:
        raise ValueError('queue payload missing required rejection_table key')
    raw_path = queue_payload['rejection_table']
    if type(raw_path) is not str or not raw_path.strip():
        raise ValueError('rejection_table must be a non-empty string path')
    path = Path(raw_path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError('rejection_table must be an existing absolute file path: ' + raw_path)
    data = json.loads(path.read_text())
    if data.get('schema') != 'ugrp.funnel_rejection_table.v1' or not data.get('stages'):
        raise ValueError('invalid funnel rejection_table schema')
    stages = tuple(
        FunnelStage(
            gate_id=s['gate_id'],
            input_count=s['input_count'],
            passed_count=s['passed_count'],
            rejected_count=s['rejected_count'],
            rejections=tuple(RejectionRecord(**r) for r in s.get('rejections', ())),
        )
        for s in data['stages']
    )
    FunnelTable(
        experiment_id=data['experiment_id'],
        source_path=data['source_path'],
        reproduce_command=data['reproduce_command'],
        initial_candidates=data['initial_candidates'],
        stages=stages,
    )
    return data


def verify_warp3_readiness(record_api_ready_path: str | Path, *, heuristics: Heuristics = Heuristics()) -> dict:
    """Verify warp3 RECORD_API_READY.json contract and heuristic compatibility."""
    path = Path(record_api_ready_path)
    if not path.is_file():
        raise FileNotFoundError(f'warp3 RECORD_API_READY file not found: {path}')
    doc = json.loads(path.read_text())
    if doc.get('status') != 'RECORD_API_READY' or doc.get('backend') != 'mjwarp_batch_v1':
        raise ValueError('backend is not RECORD_API_READY mjwarp_batch_v1')
    if doc.get('source_sha') != WARP3_SOURCE_SHA or doc.get('controller_source') != WARP3_CONTROLLER_SHA:
        raise ValueError('unexpected warp3 source_sha or controller_source')
    gate = doc.get('gate', {})
    if (not gate.get('passed')
            or gate.get('N') != WARP3_GATE_TOTAL
            or gate.get('n', 0) < WARP3_GATE_MIN_PASS
            or gate.get('raw_sha256') != WARP3_GATE_RAW_SHA):
        raise ValueError('warp3 teacher gate proof invalid or below 38/40 threshold')
    if heuristics.h1_center_v1 and not doc.get('centre_mask_annotation_supported', False):
        raise ValueError('h1_center_v1 requires centre_mask_annotation_supported=True (false in warp3)')
    return doc


@dataclass(frozen=True)
class BasePolicyMetrics:
    """Empirical base ACT metrics required before admitting RL training (rl2 gate)."""
    checkpoint_id: str
    wheel_mae: float
    persistence_wheel_mae: float
    closed_loop_success_n: int
    closed_loop_total_N: int

    def __post_init__(self):
        if not self.checkpoint_id.strip():
            raise ValueError('checkpoint_id required')
        if not all(math.isfinite(v) and v >= 0 for v in (self.wheel_mae, self.persistence_wheel_mae)):
            raise ValueError('nonnegative finite MAE values required')
        if (type(self.closed_loop_success_n) is not int or type(self.closed_loop_total_N) is not int
                or self.closed_loop_total_N <= 0 or not 0 <= self.closed_loop_success_n <= self.closed_loop_total_N):
            raise ValueError('valid closed-loop n/N integers required')


def evaluate_pre_rl_gate(
    *,
    record_api_ready_path: str | Path,
    base_metrics: BasePolicyMetrics,
    queue_payload: dict,
    heuristics: Heuristics = Heuristics(),
    reproduce_command: str = 'pytest tests/test_rl_act_prep.py',
) -> dict:
    """Evaluate sequential Pre-RL Admission Gates (backend -> rejection_table -> persistence -> closed-loop)."""
    stages: list[FunnelStage] = []
    current = 1

    # Gate 1: warp3 RECORD_API_READY verification
    try:
        verify_warp3_readiness(record_api_ready_path, heuristics=heuristics)
        stages.append(FunnelStage('warp3_record_api_ready', current, current, 0))
    except Exception as exc:
        rec = RejectionRecord('backend_not_ready', 'mjwarp_batch_v1', None, 'not_geometric', detail=str(exc))
        stages.append(FunnelStage('warp3_record_api_ready', current, 0, current, (rec,)))
        current = 0

    # Gate 2: Queue rejection_table verification
    if current > 0:
        try:
            validate_queue_rejection_table(queue_payload)
            stages.append(FunnelStage('queue_rejection_table', current, current, 0))
        except Exception as exc:
            rec = RejectionRecord('missing_rejection_table', 'queue_config', None, 'not_geometric', detail=str(exc))
            stages.append(FunnelStage('queue_rejection_table', current, 0, current, (rec,)))
            current = 0
    else:
        stages.append(FunnelStage('queue_rejection_table', 0, 0, 0))

    # Gate 3: Base ACT wheel MAE must beat zero-hold persistence MAE (actdiag / beamact2 rule)
    if current > 0:
        if base_metrics.wheel_mae < base_metrics.persistence_wheel_mae:
            stages.append(FunnelStage('base_beats_persistence_mae', current, current, 0))
        else:
            rec = RejectionRecord(
                category='base_policy_below_persistence',
                blocking_object=base_metrics.checkpoint_id,
                minimum_gap_m=None,
                minimum_gap_status='not_geometric',
                detail=(f'wheel_mae={base_metrics.wheel_mae:.6f} >= '
                        f'persistence_wheel_mae={base_metrics.persistence_wheel_mae:.6f}'),
            )
            stages.append(FunnelStage('base_beats_persistence_mae', current, 0, current, (rec,)))
            current = 0
    else:
        stages.append(FunnelStage('base_beats_persistence_mae', 0, 0, 0))

    # Gate 4: Non-zero closed-loop task completion before residual RL refinement
    if current > 0:
        if base_metrics.closed_loop_success_n > 0:
            stages.append(FunnelStage('base_nonzero_closed_loop_success', current, current, 0))
        else:
            rec = RejectionRecord(
                category='base_policy_zero_closed_loop_success',
                blocking_object=base_metrics.checkpoint_id,
                minimum_gap_m=None,
                minimum_gap_status='not_geometric',
                detail=f'closed_loop={base_metrics.closed_loop_success_n}/{base_metrics.closed_loop_total_N}',
            )
            stages.append(FunnelStage('base_nonzero_closed_loop_success', current, 0, current, (rec,)))
            current = 0
    else:
        stages.append(FunnelStage('base_nonzero_closed_loop_success', 0, 0, 0))

    funnel = FunnelTable(
        experiment_id='2026-10-16-rlprep',
        source_path=str(Path(record_api_ready_path)),
        reproduce_command=reproduce_command,
        initial_candidates=1,
        stages=tuple(stages),
    )
    return {
        'admitted': current == 1,
        'status': 'ADMITTED' if current == 1 else 'WAITING_FOR_BASE_ACT',
        'funnel': funnel.to_dict(),
    }


def audit_actor_input(actor_input: ActorInput) -> dict:
    """Enforce held_world_reads=0, invisible_measurements=0, forbidden_input_fields=0, top=0."""
    if not isinstance(actor_input, ActorInput):
        raise ValueError('ActorInput instance required')
    obs = actor_input.observation
    if not isinstance(obs, dict):
        raise ValueError('observation must be a dict')
    forbidden = set(obs) & FORBIDDEN_ACTOR_KEYS
    if forbidden:
        raise ValueError('forbidden privileged/top key in actor observation: ' + ','.join(sorted(forbidden)))
    rgb_refs = obs.get('rgb', ())
    if not isinstance(rgb_refs, (list, tuple)) or len(rgb_refs) != len(actor_input.jpegs):
        raise ValueError('actor rgb reference count must match own JPEG tuple')
    for ref, jpeg in zip(rgb_refs, actor_input.jpegs):
        if not isinstance(ref, dict) or type(jpeg) is not bytes:
            raise ValueError('invalid rgb reference or JPEG bytes')
        if ref.get('robot_id') == 'top' or 'top' in str(ref.get('path', '')).lower():
            raise ValueError('TOP camera forbidden in actor input')
        if set(ref) & FORBIDDEN_ACTOR_KEYS:
            raise ValueError('forbidden key inside rgb reference')
        if 'sha256' in ref and hashlib.sha256(jpeg).hexdigest() != ref['sha256']:
            raise ValueError('actor JPEG SHA-256 mismatch')
    for cmd in obs.get('issued', ()):
        if not isinstance(cmd, dict) or (set(cmd) & FORBIDDEN_ACTOR_KEYS):
            raise ValueError('forbidden key inside issued command history')
    return {
        'held_world_reads': 0,
        'invisible_measurements': 0,
        'forbidden_input_fields': 0,
        'top': 0,
        'weld': 0,
        'own_rgb_frames': len(actor_input.jpegs),
    }


def build_privileged_critic_input(
    actor_features: np.ndarray,
    executed_action: np.ndarray,
    truth: TrainingTruth,
    critic_state: tuple[float, ...] | np.ndarray,
    *,
    remaining_sim_s: float,
    distance_p95: float = 1.0,
    training: bool = False,
) -> np.ndarray:
    """Build asymmetric critic vector (Policy Decorator App. E.2 + MuJoCo Playground Sec. IV-B).

    Concatenates detached actor features + executed 14D command (a_base + a_res) +
    privileged simulator state (qpos, qvel, contact_forces) + normalized task truth.
    Strictly raises RuntimeError when training=False.
    """
    if not training:
        raise RuntimeError('privileged critic input is training-only; forbidden in evaluation')
    if not isinstance(truth, TrainingTruth):
        raise ValueError('TrainingTruth required for privileged critic input')
    if not math.isfinite(remaining_sim_s) or remaining_sim_s < 0 or not math.isfinite(distance_p95) or distance_p95 <= 0:
        raise ValueError('nonnegative finite remaining_sim_s and positive distance_p95 required')
    feat = np.asarray(actor_features, dtype=np.float32).copy()
    act = np.asarray(executed_action, dtype=np.float32).copy()
    priv = np.asarray(critic_state, dtype=np.float32).copy()
    if feat.ndim != 1 or act.shape != (14,) or priv.ndim != 1 or priv.size == 0:
        raise ValueError('1D actor_features, 14D executed_action, and non-empty 1D critic_state required')
    if not (np.isfinite(feat).all() and np.isfinite(act).all() and np.isfinite(priv).all()):
        raise ValueError('nonfinite values in privileged critic input')
    geom = np.asarray([
        min(truth.distance_m / distance_p95, 1.0),
        math.sin(truth.alignment_rad),
        math.cos(truth.alignment_rad),
        float(truth.stable_lift),
        min(remaining_sim_s / EPISODE_CAP_SIM_S, 1.0),
    ], dtype=np.float32)
    return np.concatenate([feat, act, priv, geom], axis=0)


def progressive_exploration_epsilon(
    transition_step: int,
    warmup_transitions: int = int(PILOT_MAX_TRANSITIONS * EXPLORATION_WARMUP_FRACTION),
    *,
    progressive_explore_v1: bool = False,
) -> float:
    """Policy Decorator (ICLR 2025, arXiv:2412.13630v1 Eq. 2) linear epsilon ramp.

    Default off (`progressive_explore_v1=False` returns 1.0); new candidates enable
    `progressive_explore_v1=True` so epsilon ramps linearly 0 -> 1 over H steps.
    """
    if type(transition_step) is not int or transition_step < 0:
        raise ValueError('nonnegative integer transition_step required')
    if type(warmup_transitions) is not int or warmup_transitions <= 0:
        raise ValueError('positive integer warmup_transitions required')
    if type(progressive_explore_v1) is not bool:
        raise ValueError('progressive_explore_v1 must be a boolean')
    if not progressive_explore_v1:
        return 1.0
    return min(1.0, float(transition_step) / float(warmup_transitions))


def sample_progressive_residual(
    policy_residual: np.ndarray,
    *,
    transition_step: int,
    rng: np.random.Generator,
    warmup_transitions: int = int(PILOT_MAX_TRANSITIONS * EXPLORATION_WARMUP_FRACTION),
    noise_scale: float = 0.2,
    progressive_explore_v1: bool = False,
) -> tuple[np.ndarray, float, bool]:
    """Sample residual action under Policy Decorator controlled exploration.

    With probability (1 - epsilon), returns exact zero residual so the base ACT
    action is executed unmodified. With probability epsilon, returns the bounded
    residual in [-1, 1].
    """
    res = np.asarray(policy_residual, dtype=np.float64)
    if res.shape != (14,) or not np.isfinite(res).all() or np.any(np.abs(res) > 1.0):
        raise ValueError('bounded finite 14D policy_residual in [-1, 1] required')
    if not math.isfinite(noise_scale) or noise_scale < 0:
        raise ValueError('nonnegative finite noise_scale required')
    eps = progressive_exploration_epsilon(
        transition_step, warmup_transitions, progressive_explore_v1=progressive_explore_v1
    )
    if float(rng.uniform(0.0, 1.0)) >= eps:
        return np.zeros(14, dtype=np.float64), eps, False
    noisy = np.clip(res + rng.uniform(-noise_scale, noise_scale, size=14), -1.0, 1.0)
    return noisy, eps, True


class WarpBatchRLWrapper:
    """Default-OFF MJWarp batch RL environment wrapper with SIM-time / transition caps.

    Wraps ActorEnv and binds:
    - world-local chunk reset callback (`on_reset`) for partial reset isolation,
    - transition-count and SIM-time caps (`sim_budget_cap_v1`, default False, new candidates True),
    - explicit `cap_end=True` and structured `RejectionRecord` logging on budget/horizon cap,
    - recording-only 10 Hz / 10 SIMs own-camera ring buffer (`RING_BUFFER_TICKS=100`).
    """
    def __init__(
        self,
        backend,
        validate_observation,
        validate_command,
        *,
        nworld: int = DEFAULT_NWORLD_PILOT,
        enabled: bool = False,
        training: bool = False,
        heuristics: Heuristics = Heuristics(),
        distance_p95: float = 1.0,
        centre_mask_annotation_supported: bool = False,
        sim_budget_cap_v1: bool = False,
        episode_cap_ticks: int = EPISODE_CAP_TICKS,
        max_transitions: int = PILOT_MAX_TRANSITIONS,
        max_sim_s: float = PILOT_MAX_SIM_S,
        on_reset=None,
    ):
        if not enabled:
            raise ValueError('WarpBatchRLWrapper is default OFF')
        if type(sim_budget_cap_v1) is not bool or type(centre_mask_annotation_supported) is not bool:
            raise ValueError('toggle flags must be booleans')
        if heuristics.h1_center_v1 and not centre_mask_annotation_supported:
            raise ValueError('h1_center_v1 requires centre_mask_annotation_supported=True')
        if (type(episode_cap_ticks) is not int or episode_cap_ticks <= 0
                or type(max_transitions) is not int or max_transitions <= 0
                or not math.isfinite(max_sim_s) or max_sim_s <= 0):
            raise ValueError('positive finite SIM-time and transition caps required')
        self.env = ActorEnv(
            backend,
            validate_observation,
            validate_command,
            nworld=nworld,
            enabled=True,
            training=training,
            heuristics=heuristics,
            distance_p95=distance_p95,
        )
        self.nworld = nworld
        self.training = training
        self.sim_budget_cap_v1 = sim_budget_cap_v1
        self.episode_cap_ticks = episode_cap_ticks
        self.max_transitions = max_transitions
        self.max_sim_s = float(max_sim_s)
        self.on_reset = on_reset

        self.world_ticks = [0] * nworld
        self.world_sim_s = [0.0] * nworld
        self.cap_end_flags = [False] * nworld
        self.total_transitions = 0
        self.total_sim_s = 0.0
        self.budget_exhausted = False
        self.rings = [deque(maxlen=RING_BUFFER_TICKS) for _ in range(nworld)]
        self.ledger: list[RejectionRecord] = []

    def _record_ring(self, inputs: tuple[ActorInput, ...], indices):
        for i in indices:
            audit_actor_input(inputs[i])
            if inputs[i].jpegs:
                self.rings[i].append((self.world_ticks[i], inputs[i].jpegs[-1]))

    def reset(self, plans, indices=None) -> tuple[ActorInput, ...]:
        target_indices = tuple(range(self.nworld)) if indices is None else tuple(indices)
        inputs = self.env.reset(plans, indices=target_indices)
        for i in target_indices:
            self.world_ticks[i] = 0
            self.world_sim_s[i] = 0.0
            self.cap_end_flags[i] = False
            self.rings[i].clear()
        if self.on_reset is not None:
            self.on_reset(target_indices)
        self._record_ring(inputs, target_indices)
        return inputs

    def step(self, actions):
        if self.sim_budget_cap_v1 and self.budget_exhausted:
            raise RuntimeError('SIM/transition budget cap already exhausted (cap_end=True)')
        was_terminal = list(self.env.terminal)
        before_truth = list(self.env.previous)
        before_latched = list(self.env.done_latched)
        inputs, backend_terminal, training_outputs = self.env.step(actions)
        training_outputs = list(training_outputs)
        active_indices = [i for i, term in enumerate(was_terminal) if not term]

        for i in active_indices:
            self.world_ticks[i] += 1
            self.world_sim_s[i] = round(self.world_ticks[i] * SIM_TICK_S, 6)
            self.total_transitions += 1
            self.total_sim_s = round(self.total_transitions * SIM_TICK_S, 6)
        self._record_ring(inputs, active_indices)

        budget_hit = self.sim_budget_cap_v1 and (
            self.total_transitions >= self.max_transitions
            or self.total_sim_s >= self.max_sim_s - 1e-9
        )
        if budget_hit:
            self.budget_exhausted = True

        merged_terminal = list(backend_terminal)
        for i in active_indices:
            ep_cap = self.sim_budget_cap_v1 and (self.world_ticks[i] >= self.episode_cap_ticks)
            if ep_cap and not backend_terminal[i] and self.training:
                first_done = bool(actions[i]['done'] and not before_latched[i])
                rew = reward_transition(
                    before_truth[i],
                    self.env.previous[i],
                    distance_p95=self.env.distance_p95,
                    first_done=first_done,
                    terminal=True,
                    heuristics=self.env.heuristics,
                )
                training_outputs[i] = TrainingOutput(rew, training_outputs[i].critic)
            if ep_cap or budget_hit:
                merged_terminal[i] = True
                self.env.terminal[i] = True
                self.cap_end_flags[i] = True
                self.ledger.append(
                    RejectionRecord(
                        category='transition_budget_cap' if (budget_hit and not ep_cap) else 'episode_sim_time_cap',
                        blocking_object='not_applicable',
                        minimum_gap_m=None,
                        minimum_gap_status='not_geometric',
                        cap_end=True,
                        detail=f'world={i} ticks={self.world_ticks[i]} total_transitions={self.total_transitions}',
                    )
                )
        return inputs, tuple(merged_terminal), tuple(training_outputs), tuple(self.cap_end_flags)

    def ring_snapshot(self, world_index: int) -> tuple[tuple[int, bytes], ...]:
        if type(world_index) is not int or not 0 <= world_index < self.nworld:
            raise ValueError('valid world_index required')
        return tuple(self.rings[world_index])
