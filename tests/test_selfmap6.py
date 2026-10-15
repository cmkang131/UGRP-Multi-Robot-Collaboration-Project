"""Offline admission, repeated-room ambiguity and real rollback seams; no plant."""
import copy
from dataclasses import replace
import math
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness import self_map_integration as sm
from harness import selfmap4_geometry as geometry
from harness import selfmap5_registration as reg
from harness import selfmap5_revision as rev
from harness import selfmap6_safety as safety
from harness.natural_floor_slam import Observation
from test_self_map_integration import fixture_mapper, receive
from test_self_map_executor import Sweep, step
from harness.self_map_executor import SelfMapExecutor
from test_selfmap5 import edges_and_lines


def gate_call(gate, *, i=1, yaw=.77, ids=None, view=None, t=None):
    return gate.consider([0, 0, 0], [0, 0, yaw], np.eye(3)*.001, np.eye(3)*.0001,
        t=float(i) if t is None else t, frame_id=i, source='visual',
        view=[0, 0, i*.3] if view is None else view, evidence_ids=[i] if ids is None else ids)


def test_large_correction_needs_three_independent_consecutive_unique_confirmations():
    gate = safety.CorrectionGate()
    assert not gate_call(gate)['accepted']
    assert not gate_call(gate, i=2)['accepted']
    assert gate_call(gate, i=3)['confirmed_outlier']
    gate = safety.CorrectionGate()
    for i in range(1, 5):
        assert not gate_call(gate, i=i, ids=[1])['accepted']
    assert gate.last['confirmations'] == 1  # reused map matches cannot vote again
    gate = safety.CorrectionGate()
    for i in range(1, 5):
        assert not gate_call(gate, i=i, view=[0, 0, 0])['accepted']
    gate = safety.CorrectionGate()
    gate_call(gate)
    assert gate_call(gate, i=2, yaw=-.77)['hypothesis_count'] == 2
    assert not gate_call(gate, i=3)['accepted']
    assert gate_call(gate, i=10)['confirmations'] == 1  # expired evidence


@pytest.mark.parametrize('static', [False, True])
def test_rejected_orb_and_static_do_not_mutate_pose_bank_or_keyframes(static, monkeypatch):
    slam = safety.GatedPriorSLAM('r3', max_sigma_xy_m=.15, max_sigma_yaw_rad=.2)
    rng = np.random.default_rng(1)
    points = rng.uniform([.2, -.6], [1, .6], (25, 2))
    descriptors = rng.integers(0, 255, (25, 32), dtype=np.uint8)
    def obs(i):
        return Observation(i, float(i), points, descriptors, str(i))
    slam.step(obs(1), command_delta=np.zeros(3), command_covariance=np.zeros((3, 3)))
    before = copy.deepcopy(slam.landmarks); frames = copy.deepcopy(slam.keyframes)
    slam._gate_prediction = np.eye(3)*.001
    def admit(p, q, P, detail):
        return safety.CorrectionGate().consider(p, q, P, detail['covariance'], t=2.,
            frame_id=2, source='static' if static else 'visual', view=[0, 0, 0], evidence_ids=[1])
    # Force the real core fit seam to propose the recorded scale of bad yaw.
    if not static:
        from harness.natural_floor_slam import NaturalFloorSLAM
        monkeypatch.setattr(NaturalFloorSLAM, '_fit', lambda *a: (np.array([.02, 0, .77]), [], dict(
            covariance=np.eye(3)*.0001, matched=[(0, 0)], matches=13, inliers=8,
            fit_rms_m=.01, spread_m=.1, reason='visual_relocalized')))
    event = slam.guarded_step(obs(2), command_delta=np.zeros(3), command_covariance=np.eye(3)*.001,
        correction_gate=admit, pose_override=(np.array([.02, 0, .77]), np.eye(3)*.0001) if static else None)
    assert event['status'] == 'command_only' and event['reason'] == 'pose_correction_rejected'
    assert not event['correction_gate']['accepted'] and event['prior_landmarks_added'] == 0
    np.testing.assert_array_equal(slam.pose, np.zeros(3))
    assert slam.keyframes == frames and set(slam.landmarks) == set(before)
    for k in before:
        np.testing.assert_array_equal(slam.landmarks[k].position, before[k].position)
        assert slam.landmarks[k].observations == before[k].observations


@pytest.mark.parametrize('static_correction', [False, True])
def test_full_receive_routes_both_sources_through_admission(monkeypatch, static_correction):
    template, state = fixture_mapper(monkeypatch)
    static, _ = geometry.static_input()
    options = sm.Options(self_map_integration=sm.OPTION, bootstrap='command_prior_v1',
        recovery_profile=geometry.PROFILE, revision_gate=rev.OPTION,
        multiframe_registration=reg.OPTION, correction_safety=safety.OPTION)
    mapper = sm.SelfMapIntegration('r1', options=options, static_map=static)
    mapper.zones = template.zones
    mapper.command(dict(t=0., kind='initial_servo_command', pulses=template.servo))
    monkeypatch.setattr(mapper.flow, 'step', lambda rgb, servo, t, settled, delta, Q: (delta, Q, {}))
    obs = dict(camera=[0., 0.], segments=[], floor_xy=[], features=[])
    monkeypatch.setattr(geometry, 'observe', lambda *a: obs)
    monkeypatch.setattr(mapper.registration, 'step', lambda *a: None)
    receive(mapper, 1)
    before = copy.deepcopy(mapper.slam.landmarks)
    if static_correction:
        monkeypatch.setattr(mapper.registration, 'step', lambda *a: (np.array([0., 0., .77]), np.eye(3)*.0001))
    else:
        state['pose'] = np.array([0., 0., .77])
    row = receive(mapper, 2)
    assert not row['correction_admission']['accepted'] and not row['rebuild_required']
    assert row['correction_admission']['source'] == ('static' if static_correction else 'visual')
    np.testing.assert_allclose(row['pose'], [0, 0, 0], atol=1e-10)
    for key in before:
        np.testing.assert_array_equal(before[key].position, mapper.slam.landmarks[key].position)


def test_global_line_search_rejects_collapsed_pf_in_repeated_and_rotated_rooms():
    edges, lines = edges_and_lines()
    evidence = reg.MultiFrameEvidence(); evidence.begin(0); evidence.add(dict(features=lines), [0, 0, 0], 0)
    covariance = np.eye(3)*.0001
    unique = safety.registration_hypotheses(evidence, edges, [0, 0, 0], covariance)
    assert unique['unique'] and unique['candidate_count'] == 1
    repeated = edges+[{**e, 'a': e['a']+[4, 0], 'b': e['b']+[4, 0]} for e in edges]
    assert safety.registration_hypotheses(evidence, repeated, [0, 0, 0], covariance)['candidate_count'] == 2
    rotated = edges+[{**e, 'a': -e['a']+[4, 4], 'b': -e['b']+[4, 4], 'normal': -e['normal']} for e in edges]
    assert safety.registration_hypotheses(evidence, rotated, [0, 0, 0], covariance)['candidate_count'] == 2


@pytest.mark.parametrize('repeated', [False, True])
def test_static_registration_requires_a_unique_mode_before_latching(monkeypatch, repeated):
    static, _ = geometry.static_input()
    r = geometry.StaticRegistration(static, multiframe_registration=reg.OPTION, correction_safety=safety.OPTION)
    edges, lines = edges_and_lines()
    r.pf.landmark_map.edges = (edges+[{**e, 'a': e['a']+[4, 0], 'b': e['b']+[4, 0]} for e in edges]
                               if repeated else edges)
    output = dict(pose=[0., 0., 0.], covariance=(np.eye(3)*1e-6).tolist(), updated=True,
        resolved=True, cluster={'mass': 1.}, sensor={})
    monkeypatch.setattr(r.pf, 'step', lambda **kw: copy.deepcopy(output))
    r.begin_sweep(0)
    results = [r.step(dict(features=lines, segments=[]), [0, 0, 0], {6: pan}, t, [0, 0, 0])
               for t, pan in enumerate([1500, 1750, 2000])]
    if repeated:
        assert all(result is None for result in results)
        assert not r.confirmations and r.map_from_own is None
        assert r.last['geometry']['ambiguity']['candidate_count'] == 2
    else:
        assert results[-1] is not None and len(r.confirmations) == 3
        assert r.last['geometry']['ambiguity']['candidate_count'] == 1
        assert r.last['geometry']['fresh_evidence_edge_ids'] == ['static:0', 'static:1']


def enable_fixture(mapper):
    mapper.options = replace(mapper.options, recovery_profile=geometry.PROFILE,
        revision_gate=rev.OPTION, multiframe_registration=reg.OPTION, correction_safety=safety.OPTION)
    mapper.slam.__class__ = safety.GatedFloorSLAM
    mapper.correction_gate = safety.CorrectionGate()
    mapper.registration = SimpleNamespace(map_from_own=None, confirmations=[], confirmation_views=set(),
        end_sweep=lambda: None)
    mapper.flow = SimpleNamespace(previous=None)


@pytest.mark.parametrize('failed_attempts,at', [(2, 7.), (0, 12.)])
def test_actual_rollback_preserves_map_and_restores_bank_with_command_propagation(monkeypatch, failed_attempts, at):
    mapper, _ = fixture_mapper(monkeypatch); receive(mapper, 1); enable_fixture(mapper)
    old_bank = copy.deepcopy(mapper.slam.landmarks); old_grid = copy.deepcopy(mapper.grid.navigation.odds)
    old_pose = mapper.slam.pose.copy()
    mapper.checkpoint_revision(2., old_pose, np.eye(3)*.001)
    mapper.slam.pose = np.array([1., 1., .77]); mapper.slam.landmarks.clear()
    mapper.rebuild_required = True; mapper.pending_revision = {'distance': 0}
    mapper.rebuilds.extend([dict(committed=False)]*failed_attempts)
    mapper.revision_checkpoint['pose'] = old_pose+np.array([.1, 0, 0])
    receipt = mapper.release_quarantine(at)
    assert receipt['failed_attempts'] == failed_attempts and not receipt['complete']
    assert not mapper.rebuild_required and mapper.pending_revision is None
    np.testing.assert_allclose(mapper.slam.pose, old_pose+[.1, 0, 0])
    assert mapper.grid.navigation.odds == old_grid and set(mapper.slam.landmarks) == set(old_bank)
    assert mapper.rebuild_attempts() == 0


def test_release_resets_executor_episode_before_exhaustion(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, recovery_profile=geometry.PROFILE)
    controller = SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=180.)
    original = mapper.receive
    def released(**kw):
        row = original(**kw); row['quarantine_release'] = dict(reason='last_consistent_state_rollback')
        return row
    monkeypatch.setattr(mapper, 'receive', released)
    controller.recovery_started = -100.; controller.recovery_attempts = 3
    command, row = step(controller, 1, 1.)
    assert not controller.done and row['executor_stop_reason'] is None


def test_receive_releases_on_deadline_without_another_visual_fit(monkeypatch):
    mapper, state = fixture_mapper(monkeypatch); receive(mapper, 1); enable_fixture(mapper)
    mapper.checkpoint_revision(2., mapper.slam.pose.copy(), np.eye(3)*.001)
    mapper.slam.pose = np.array([0., 0., .77])
    mapper.rebuild_required = True
    state['blank'] = True
    row = mapper.receive(robot_id='r1', frame_id=2, t=12., rgb=np.zeros((480, 640, 3), np.uint8))
    assert row['quarantine_release']['reason'] == 'last_consistent_state_rollback'
    assert row['pose_source'] == 'command_only' and not row['rebuild_required']
    np.testing.assert_allclose(row['pose'], [0, 0, 0])


def test_default_off_bundle_and_dependency_validation():
    from scripts.run_self_map_diagnostic import bundle
    assert sm.Options().correction_safety == 'off'
    with pytest.raises(ValueError, match='REQUIRES_REVISION'):
        sm.Options(correction_safety=safety.OPTION)
    old = bundle('a'*40, 1, 30)
    assert 'correction_safety' not in old['options']
    b = bundle('a'*40, 1, 30, recovery_profile=geometry.PROFILE, revision_gate=rev.OPTION,
        multiframe_registration=reg.OPTION, correction_safety=safety.OPTION)
    assert b['check'] == 'selfmap6' and b['options']['correction_safety'] == safety.OPTION


def test_actual_frame254_fixture_rejects_11sigma_44degree_proposal():
    f = json.loads((Path(__file__).parent/'fixtures/selfmap6_frame254.json').read_text())
    result = safety.CorrectionGate().consider(f['prior'], f['candidate'], f['predicted'], f['measured'],
        t=f['t'], frame_id=f['frame_id'], source='visual', view=f['prior'], evidence_ids=[])
    assert result['mahalanobis'] == pytest.approx(11.239332501859277)
    assert math.degrees(result['innovation'][2]) == pytest.approx(44.27881185890391)
    assert not result['accepted'] and result['confirmations'] == 0


def test_queue_has_only_three_serial_smooth_runs_and_no_execution_flags():
    from scripts.prepare_selfmap6_queue import make_queue
    q = make_queue('d'*40)
    assert len(q['runs']) == 3 and q['max_parallel'] == 1
    def inspect(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, bool) and (key in ('approved', 'enabled', 'ready', 'execute', 'stage_ready')
                        or key.endswith(('_ready', '_authorized')) or key in ('automatic_promotion', 'runs_enabled')):
                    assert value is False, key
                inspect(value)
        elif isinstance(obj, list):
            for value in obj: inspect(value)
    inspect(q)
    assert all('--execute' not in r['command'] and r['scene_version'] == 'floor_light_v1' for r in q['runs'])
    assert q['runs'][1]['depends_on'] == q['runs'][0]['name']
    assert q['runs'][2]['depends_on'] == q['runs'][1]['name']
