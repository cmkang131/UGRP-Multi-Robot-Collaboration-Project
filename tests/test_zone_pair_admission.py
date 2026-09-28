"""Private refusal evidence and saved dev geometry; no physics/model calls."""
import copy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from harness.zone_own_guards import OwnPose, SweepGuard
from harness.zone_pair_admission import readiness_snapshot
from scripts.diagnose_zone_pair_dev import guard_receipt, reconstruct_gate
from scripts.zone_pair_dev_runtime import Jsonl, flush_admission_audit
from tests.test_zone_pair_executor import MAP, robot, setup

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / 'experiments/2026-09-27-zone-pair-dev/diagnosis_v3.json'


@pytest.mark.parametrize('fault,failed', [
    ('gate', 'gate_ok'), ('mode', 'mode_m1'), ('no_report', 'report_present'),
    ('uninitialized', 'report_initialized'), ('stale_report', 'report_fresh'),
    ('future_report', 'report_fresh'), ('nan_xy', 'std_xy_finite'), ('inf_yaw', 'std_yaw_finite'),
    ('no_obs', 'observation_present'), ('stale_obs', 'observation_fresh'),
    ('future_obs', 'observation_fresh'), ('servo', 'servo_complete')])
def test_each_uncertain_predicate_is_private_and_json_safe(fault, failed):
    ex = robot('r1')
    if fault == 'gate': ex.gate.state = 'uncertain'
    elif fault == 'mode': ex.mode = 'diagnostic'
    elif fault == 'no_report': ex.last_report = None
    elif fault == 'uninitialized': ex.last_report = replace(ex.last_report, initialized=False)
    elif fault == 'stale_report': ex.last_report = replace(ex.last_report, t_est=-.31)
    elif fault == 'future_report': ex.last_report = replace(ex.last_report, t_est=.1)
    elif fault == 'nan_xy': ex.last_report = replace(ex.last_report, std_xy_m=float('nan'))
    elif fault == 'inf_yaw': ex.last_report = replace(ex.last_report, std_yaw_rad=float('inf'))
    elif fault == 'no_obs': ex.last_obs = None
    elif fault == 'stale_obs': ex.last_obs['sim_time'] = -.31
    elif fault == 'future_obs': ex.last_obs['sim_time'] = .1
    else: del ex.servo[4]
    assert ex.pair_readiness(0., 'cargoX', 'B') == 'uncertain'
    ack = ex._ack('pair_carry', {'order_id': 'cargoX', 'target_ref': 'B'}, False, 'SELF_UNCERTAIN')
    receipt, = ex.pair_admission_log
    assert failed in receipt['failed_checks']
    assert receipt['action_id'] == ack['action_id']
    assert receipt['rejected_reason'] == 'SELF_UNCERTAIN'
    json.dumps(receipt, allow_nan=False)
    public = json.dumps([ack, ex.api_log, ex.events, ex.status(), ex.belief_projection()])
    assert 'ugrp.zone_pair_admission' not in public and 'failed_checks' not in public
    assert 'candidate_since_sim_s' not in public


def test_host_refusal_records_once_without_telling_peer_and_flushes_once(tmp_path):
    host, exs = setup()
    exs['r1'].gate.state = 'uncertain'
    peer_before = copy.deepcopy((exs['r2'].api_log, exs['r2'].events, exs['r2'].status()))
    ack = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert not ack['accepted'] and ack['rejected_reason'] == 'SELF_UNCERTAIN'
    assert len(exs['r1'].pair_admission_log) == 1
    assert exs['r2'].pair_admission_log == [] and host.pairs.sessions == []
    assert peer_before == (exs['r2'].api_log, exs['r2'].events, exs['r2'].status())
    path = tmp_path / 'eval_only/pair_admission.jsonl'
    stream, cursors = Jsonl(path), {}
    try:
        flush_admission_audit(host, stream, cursors)
        flush_admission_audit(host, stream, cursors)
    finally:
        stream.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]['action_id'] == ack['action_id']
    assert rows[0]['failed_checks'] == ['gate_ok']


@pytest.mark.parametrize('case,reason,failed', [
    ('busy', 'SELF_BUSY', 'idle'), ('stopped', 'SELF_STOPPED', 'not_stopped'),
    ('image', 'SELF_INVALID_IMAGE', 'image_valid'), ('holding', 'SELF_OCCUPIED', 'empty_handed')])
def test_other_refusals_keep_reason_and_failed_predicate(case, reason, failed):
    host, exs = setup()
    ex = exs['r1']
    if case == 'busy': ex.hold(1.)
    elif case == 'stopped': ex.stopped = {'reason': 'test'}
    elif case == 'image': ex.last_obs['image'] = 'bad-image'
    else: ex.holding = lambda: {'answer': 'unknown'}
    ack = host.call('r1', 'pair_carry', 'cargoX', 'B', 'r2')
    assert ack['rejected_reason'] == reason
    assert failed in ex.pair_admission_log[0]['failed_checks']


def test_dwell_is_not_relaxed_and_tag_age_is_informational():
    ex = robot('r1')
    ex.gate.state = 'uncertain'
    ex.last_report = replace(ex.last_report, std_xy_m=.05033, std_yaw_rad=.01533, since_tag_s=58.6)
    for t in (0., .2, .4):
        ex.gate.update(t, True, .05033, .01533)
    assert ex.pair_readiness(0.) == 'uncertain'
    for t in (.6, .8): ex.gate.update(t, True, .049, .015)
    assert ex.pair_readiness(0.) == 'uncertain'
    ex.gate.update(1., True, .049, .015)
    ex.last_report = replace(ex.last_report, std_xy_m=.049)
    assert ex.pair_readiness(0.) == 'available'
    assert readiness_snapshot(ex, 0.)['report']['since_tag_s'] == 58.6


def test_multiple_faults_and_full_precision_survive_receipt():
    ex = robot('r1')
    ex.gate.state = 'uncertain'
    sigma = .050330123456789
    ex.last_report = replace(ex.last_report, std_xy_m=sigma, t_est=-1.)
    ex.last_obs['sim_time'] = -1.
    del ex.servo[3]
    d = readiness_snapshot(ex, 0.)
    assert d['report']['std_xy_m'] == sigma
    assert d['failed_checks'] == ['gate_ok', 'report_fresh', 'observation_fresh', 'servo_complete']
    assert d['missing_servo_ids'] == [3]


def test_saved_dev_guards_reconstruct_exact_clearance_without_unsafe_escape():
    diag = json.loads(DIAG.read_text())
    guard = SweepGuard(MAP)
    count = 0
    for run in diag['runs'].values():
        for robot_result in run['robots'].values():
            for saved in robot_result['blocked_sweeps']:
                actual = json.loads(json.dumps(guard_receipt(guard, saved['recorded'])))
                assert actual == saved
                assert actual['recomputed']['limiting'] == saved['recorded']['limiting']
                assert actual['zero_sigma_transition_clear']
                assert not actual['transition_clear'] and not actual['safe_alternative_pans']
                assert not actual['east_8cm_translation_clear']
                count += 1
    assert count == 3


def test_static_dock_blocks_even_perfect_pose_and_inset_is_only_a_candidate():
    guard = SweepGuard(MAP)
    assert guard.chassis_clearance(OwnPose(-.85, -.85, 0., 0., 0.))[0] == pytest.approx(-.01)
    assert guard.chassis_clearance(OwnPose(-.70, -.85, 0., .05, .06))[0] == pytest.approx(.019008573)
    assert guard.chassis_clearance(OwnPose(-.65, -.85, 0., .05, .06))[0] == pytest.approx(.069008573)


def test_gate_reconstruction_preserves_cutoff_and_dwell():
    frames = [{'t': t, 'report': {'initialized': True, 'std_xy_m': xy, 'std_yaw_rad': .015}}
              for t, xy in [(59.9, .05033), (60.1, .04983), (60.3, .04947), (60.5, .04916)]]
    assert not reconstruct_gate(frames, 60.).ok
    assert not reconstruct_gate(frames, 60.3).ok
    assert reconstruct_gate(frames, 60.5).ok
