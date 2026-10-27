"""Non-physics unit tests for rlprep (Pre-RL gate, MJWarp batch wrapper, critic/actor separation)."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pytest

from scripts.rl_act_actor import compose
from scripts.rl_act_env import ActorInput
from scripts.rl_act_prep import (
    BasePolicyMetrics,
    FunnelStage,
    FunnelTable,
    RejectionRecord,
    WARP3_CONTROLLER_SHA,
    WARP3_GATE_RAW_SHA,
    WARP3_SOURCE_SHA,
    WarpBatchRLWrapper,
    audit_actor_input,
    build_privileged_critic_input,
    evaluate_pre_rl_gate,
    progressive_exploration_epsilon,
    sample_progressive_residual,
    validate_queue_rejection_table,
    verify_warp3_readiness,
)
from scripts.rl_act_reward import GAMMA, Heuristics, TrainingTruth, potential, shaped_reward


def _make_warp3_ready_file(tmp_path, *, centre_mask_supported=False):
    ready_path = tmp_path / 'RECORD_API_READY.json'
    ready_path.write_text(json.dumps({
        'status': 'RECORD_API_READY',
        'backend': 'mjwarp_batch_v1',
        'source_sha': WARP3_SOURCE_SHA,
        'controller_source': WARP3_CONTROLLER_SHA,
        'centre_mask_annotation_supported': centre_mask_supported,
        'gate': {
            'passed': True,
            'n': 40,
            'N': 40,
            'raw_sha256': WARP3_GATE_RAW_SHA,
        },
    }, indent=2) + '\n')
    return ready_path


def _own_actor_obs(seed=1, jpeg=b'own-fisheye-jpeg'):
    digest = hashlib.sha256(jpeg).hexdigest()
    return {
        'schema': 'ugrp.grasp_act_observation.v1',
        'robot_id': 'r1',
        'sample_id': f'ep-{seed}:0:r1',
        't': 0.0,
        'skill': 'grasp',
        'object_kind': 'cyan',
        'role': 'solo',
        'destination_zone': 'none',
        'rgb': [{'path': 'rgb/r1/000000.jpg', 'sha256': digest, 't': 0.0, 'robot_id': 'r1'}],
        'issued': [{'t': 0.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4, 'pwm': {'1': 1500}}],
    }


class _DummyWarpBackend:
    def __init__(self, nworld=2):
        self.nworld = nworld
        self.jpeg = b'own-camera-frame'
        self.public = [_own_actor_obs(i, self.jpeg) for i in range(nworld)]
        self.private = [TrainingTruth(0.8, 0.4, None, False) for _ in range(nworld)]
        self.private_reads = 0

    def reset(self, plans, *, indices):
        for i, plan in zip(indices, plans):
            self.public[i] = _own_actor_obs(plan['seed'], self.jpeg)
            self.private[i] = TrainingTruth(0.8, 0.4, None, False)

    def read_actor(self, i):
        return self.public[i], (self.jpeg,)

    def read_training(self, i):
        self.private_reads += 1
        t = self.private[i]
        return t, (t.distance_m, t.alignment_rad, 0.5, 0.5)

    def step(self, actions):
        for i in range(self.nworld):
            t = self.private[i]
            self.private[i] = TrainingTruth(max(0.1, t.distance_m - 0.1), max(0.0, t.alignment_rad - 0.05), None, False)
        return [bool(a['done']) for a in actions]


def test_pre_rl_admission_gate_blocks_below_persistence_and_validates_funnel_table(tmp_path):
    # 1. RejectionRecord enforces non-empty category, blocking_object, and explicit gap status.
    with pytest.raises(ValueError, match='category'):
        RejectionRecord('', 'beam_1', 0.02)
    with pytest.raises(ValueError, match='blocking_object'):
        RejectionRecord('collision', '   ', 0.02)
    with pytest.raises(ValueError, match='non-measured status'):
        RejectionRecord('cap_end', 'not_applicable', None, 'measured')

    # 2. warp3 RECORD_API_READY verification and h1_center_v1 guard when centre mask is unsupported.
    ready_path = _make_warp3_ready_file(tmp_path, centre_mask_supported=False)
    doc = verify_warp3_readiness(ready_path)
    assert doc['status'] == 'RECORD_API_READY'
    with pytest.raises(ValueError, match='h1_center_v1'):
        verify_warp3_readiness(ready_path, heuristics=Heuristics(h1_center_v1=True))

    # 3. Queue rejection_table validation (rule #6).
    funnel_file = tmp_path / 'rejection_table.json'
    FunnelTable(
        experiment_id='2026-10-16-rlprep',
        source_path=str(ready_path),
        reproduce_command='pytest tests/test_rl_act_prep.py',
        initial_candidates=40,
        stages=(
            FunnelStage('warp3_teacher_gate', 40, 40, 0),
            FunnelStage(
                'beamact2_student_gate',
                40,
                0,
                40,
                (RejectionRecord('hold_segment_wheel_noise', 'beam_target', None, 'not_geometric'),),
            ),
        ),
    ).write_json(funnel_file)
    with pytest.raises(ValueError, match='missing required rejection_table'):
        validate_queue_rejection_table({})
    queue_payload = {'rejection_table': str(funnel_file.resolve())}
    assert validate_queue_rejection_table(queue_payload)['final_passed_count'] == 0

    # 4. Pre-RL gate blocks beamact2 (MAE 0.054589 >= persistence 0.023129, 0/20 closed-loop).
    beamact2 = BasePolicyMetrics(
        checkpoint_id='beamact2-act15',
        wheel_mae=0.054589,
        persistence_wheel_mae=0.023129,
        closed_loop_success_n=0,
        closed_loop_total_N=20,
    )
    blocked = evaluate_pre_rl_gate(
        record_api_ready_path=ready_path,
        base_metrics=beamact2,
        queue_payload=queue_payload,
    )
    assert not blocked['admitted'] and blocked['status'] == 'WAITING_FOR_BASE_ACT'
    stage_map = {s['gate_id']: s for s in blocked['funnel']['stages']}
    assert stage_map['base_beats_persistence_mae']['rejected_count'] == 1
    assert stage_map['base_beats_persistence_mae']['rejections'][0]['category'] == 'base_policy_below_persistence'

    # 5. Pre-RL gate admits when base ACT beats persistence MAE and has non-zero closed-loop success.
    qualified_base = BasePolicyMetrics(
        checkpoint_id='act-qualified-candidate',
        wheel_mae=0.018500,
        persistence_wheel_mae=0.023129,
        closed_loop_success_n=5,
        closed_loop_total_N=20,
    )
    admitted = evaluate_pre_rl_gate(
        record_api_ready_path=ready_path,
        base_metrics=qualified_base,
        queue_payload=queue_payload,
    )
    assert admitted['admitted'] and admitted['status'] == 'ADMITTED'
    assert admitted['funnel']['final_passed_count'] == 1


def test_warp_batch_rl_wrapper_sim_budget_caps_on_reset_and_progressive_exploration():
    backend = _DummyWarpBackend(nworld=2)
    validate_obs = lambda obs: None
    validate_cmd = lambda cmd: None

    # Default-OFF check
    with pytest.raises(ValueError, match='default OFF'):
        WarpBatchRLWrapper(backend, validate_obs, validate_cmd, nworld=2, enabled=False)

    reset_calls = []
    wrapper = WarpBatchRLWrapper(
        backend,
        validate_obs,
        validate_cmd,
        nworld=2,
        enabled=True,
        training=True,
        sim_budget_cap_v1=True,
        episode_cap_ticks=2,
        max_transitions=5,
        max_sim_s=0.5,
        on_reset=lambda idx: reset_calls.append(idx),
    )

    wrapper.reset([{'seed': 10}, {'seed': 20}])
    assert reset_calls == [(0, 1)]
    assert len(wrapper.ring_snapshot(0)) == 1

    act = [dict(command={'issued': 1}, done=False) for _ in range(2)]
    _, term1, out1, cap1 = wrapper.step(act)
    assert term1 == (False, False) and cap1 == (False, False)
    assert wrapper.total_transitions == 2 and wrapper.total_sim_s == pytest.approx(0.2)

    # Step 2 hits episode_cap_ticks=2 for both worlds -> cap_end=True and terminal potential shaping.
    _, term2, out2, cap2 = wrapper.step(act)
    assert term2 == (True, True) and cap2 == (True, True)
    expected_terminal_shaping = shaped_reward(
        potential(0.7, 0.35, 1.0),
        potential(0.6, 0.30, 1.0),
        first_success=False,
        terminal=True,
        gamma=GAMMA,
    )['reward']
    assert out2[0].reward['reward'] == pytest.approx(expected_terminal_shaping)
    assert all(r.cap_end and r.category == 'episode_sim_time_cap' for r in wrapper.ledger)

    # Partial reset on world 0 only: world-local callback receives (0,) and world 1 remains terminal.
    wrapper.reset([{'seed': 11}], indices=[0])
    assert reset_calls[-1] == (0,)
    assert wrapper.world_ticks == [0, 2]
    assert wrapper.cap_end_flags == [False, True]

    # Step 3 advances only active world 0 (total_transitions becomes 5 -> hits max_transitions=5).
    _, term3, _, cap3 = wrapper.step(act)
    assert wrapper.total_transitions == 5 and wrapper.budget_exhausted
    assert term3 == (True, True) and cap3 == (True, True)
    assert wrapper.ledger[-1].category == 'transition_budget_cap'
    with pytest.raises(RuntimeError, match='budget cap already exhausted'):
        wrapper.step(act)

    # Policy Decorator progressive exploration schedule (Eq. 2):
    rng = np.random.default_rng(42)
    base_raw = np.linspace(-0.5, 0.5, 14)
    policy_res = np.full(14, 0.5)
    res0, eps0, used0 = sample_progressive_residual(
        policy_res, transition_step=0, rng=rng, warmup_transitions=100, progressive_explore_v1=True
    )
    assert eps0 == 0.0 and not used0 and np.all(res0 == 0.0)
    assert compose(base_raw, res0, np.ones(14), lambda v: v) == base_raw.tolist()

    assert progressive_exploration_epsilon(50, 100, progressive_explore_v1=True) == pytest.approx(0.5)
    res_full, eps_full, used_full = sample_progressive_residual(
        policy_res, transition_step=100, rng=rng, warmup_transitions=100, progressive_explore_v1=True
    )
    assert eps_full == 1.0 and used_full and np.all(np.abs(res_full) <= 1.0)


def test_actor_safety_audit_and_privileged_critic_separation():
    jpeg = b'valid-own-fisheye-frame'
    obs = _own_actor_obs(1, jpeg)
    valid_input = ActorInput(obs, (jpeg,))
    audit = audit_actor_input(valid_input)
    assert audit == {
        'held_world_reads': 0,
        'invisible_measurements': 0,
        'forbidden_input_fields': 0,
        'top': 0,
        'weld': 0,
        'own_rgb_frames': 1,
    }

    # Injecting privileged keys, TOP camera, or corrupted JPEG SHA-256 is rejected.
    for bad_key in ('qpos', 'distance_m', 'contact_forces', 'weld', 'top'):
        leaked = _own_actor_obs(1, jpeg)
        leaked[bad_key] = 1.0
        with pytest.raises(ValueError, match='forbidden'):
            audit_actor_input(ActorInput(leaked, (jpeg,)))

    top_obs = _own_actor_obs(1, jpeg)
    top_obs['rgb'][0]['robot_id'] = 'top'
    with pytest.raises(ValueError, match='TOP camera forbidden'):
        audit_actor_input(ActorInput(top_obs, (jpeg,)))

    with pytest.raises(ValueError, match='SHA-256 mismatch'):
        audit_actor_input(ActorInput(_own_actor_obs(1, jpeg), (b'tampered-bytes',)))

    # Privileged critic input is strictly forbidden in evaluation mode.
    feat = np.ones(16, dtype=np.float32)
    act = np.full(14, 0.25, dtype=np.float32)
    truth = TrainingTruth(distance_m=0.4, alignment_rad=math.pi / 6, target_xy=None, stable_lift=True)
    critic_state = (0.1, -0.2, 0.5, 0.6)
    with pytest.raises(RuntimeError, match='training-only'):
        build_privileged_critic_input(
            feat, act, truth, critic_state, remaining_sim_s=45.0, distance_p95=0.8, training=False
        )

    # In training mode, builds [actor_features(16), executed_action(14), critic_state(4), geom(5)] = 39D.
    vec = build_privileged_critic_input(
        feat, act, truth, critic_state, remaining_sim_s=45.0, distance_p95=0.8, training=True
    )
    assert vec.shape == (16 + 14 + 4 + 5,) and vec.dtype == np.float32
    assert np.allclose(vec[-5:], [0.5, 0.5, math.cos(math.pi / 6), 1.0, 0.5])
