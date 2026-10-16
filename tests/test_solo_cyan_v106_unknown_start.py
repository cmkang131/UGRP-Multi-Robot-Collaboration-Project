import copy
import json
import math

import numpy as np
import pytest

from harness import zone_solo_cyan_unknown_start as m
from harness import zone_solo_cyan_contract_v106 as legacy_contract
from harness import zone_s2_unknown_start_contract as contract
from scripts import run_s2_unknown_start as runner
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision


def test_default_off_preserves_v133_carry_command_and_record_bytes(static, cal):
    runs = [cls(static, None, None,
                provider_factory=lambda *a, **k: FakePose(copy.deepcopy(cal)),
                vision_factory=FakeVision, **kw)
            for cls, kw in [(m.Carry, {}), (m.Runtime, {}),
                            (m.Runtime, dict(start_prior='off', global_localization='off', particle_sampling='off'))]]
    try:
        for r in runs:
            r.initial_commands(0., {'r3': {1:2000, 3:740, 4:2320, 5:1320, 6:1500}})
        for t in (1., 1.05, 1.65):
            actions = [r.step(t) for r in runs]
            assert len({json.dumps(x).encode() for x in actions}) == 1
            for r, row in zip(runs, actions):
                for rid, action in row:
                    r.on_command(rid, t, action)
        assert len({json.dumps(r.record()).encode() for r in runs}) == 1
    finally:
        for r in runs:
            r.close()


def test_full_composition_never_calls_spawn_or_gaussian_prior_and_handoffs(static, monkeypatch):
    from sim import zone_model_conventions
    from harness.zone_solo_cyan_kld_start import PARAMS
    def forbidden(*a, **k):
        raise AssertionError('start-area/row/dock prior was accessed')
    monkeypatch.setattr(zone_model_conventions, 'spawn_layout', forbidden)
    from harness.zone_solo_cyan_camera_v3 import build_provider
    made = []
    def provider(*a, **kw):
        source = build_provider(*a, **kw)
        source.init_prior = forbidden
        source.provider.init_prior = forbidden
        source.provider.loc._pf.init_gaussian = forbidden
        made.append(source)
        return source
    provider.controller_geometry_id = build_provider.controller_geometry_id
    provider.uses_landmark_tags = False
    b = contract.bundle('a'*40, 1059, **contract.NEW_OPTIONS)
    runtime = runner.runtime_factory(b)(static, legacy_contract.ROOT/legacy_contract.CALIBRATION,
        legacy_contract.CALIBRATION_SHA, **b['task'], provider_factory=provider)
    try:
        pf = runtime.pose.provider.loc._pf
        assert pf.n == PARAMS['max_samples'] == 100000
        assert np.all(pf._map_logprior(pf.px) == 0)
        x0, x1, y0, y1 = pf.bounds
        assert np.ptp(pf.px[:, 0]) > .9*(x1-x0)
        assert np.ptp(pf.px[:, 1]) > .9*(y1-y0)
        assert pf.px[:, 2].min() < -3.1 and pf.px[:, 2].max() > 3.1
        assert np.allclose(pf._weights(), 1/pf.n)
        assert runtime.global_policy.active
        assert runtime.carry_pose == 'look_ahead_v1'
        assert runtime.sensor_landmarks == 'floor_zones_doors_v1'
        assert runtime.pose_estimate == 'amcl_best_cluster_v1'
        runtime.initial_commands(0., {'r3': {1:2000, 3:740, 4:2320, 5:1320, 6:1500}})
        runtime.on_command('r3', 0., dict(kind='hold'))
        assert runtime.global_policy.active and pf.n == 100000
        runtime.on_command('r3', .05, dict(kind='mecanum', forward=.35, left=0., turn=0., duration_s=.1))
        assert not runtime.global_policy.active and pf.n == 2000
        assert runtime.kld_audit['handoff']['before'] == 100000
        assert runtime.pose.provider.prior['known_own_dock'] is False
        assert 'mean' not in runtime.pose.provider.prior
        assert runtime.record()['start_prior']['dock_prior_calls'] == 0
    finally:
        runtime.close()


def test_incomplete_or_unknown_options_are_rejected_before_provider(static):
    for kwargs in [dict(start_prior='bad'), dict(start_prior='none_v1'),
                   dict(global_localization='augmented_active_v1')]:
        with pytest.raises(ValueError):
            m.Runtime(static, None, None, **kwargs)


def test_off_full_v133_options_preserve_real_pf_and_record_bytes(static):
    from scripts.run_s2_landmarks_dev import runtime_factory as frozen_factory
    b = contract.bundle('a'*40, 1059)
    old = copy.deepcopy(b)
    for key in contract.NEW_OPTIONS:
        old['options'].pop(key)
    args = (static, legacy_contract.ROOT/legacy_contract.CALIBRATION, legacy_contract.CALIBRATION_SHA)
    runs = [factory(bundle)(*args, **bundle['task'])
            for factory, bundle in [(frozen_factory, old), (runner.runtime_factory, b)]]
    try:
        for r in runs:
            r.initial_commands(0., {'r3': {1:2000, 3:740, 4:2320, 5:1320, 6:1500}})
        for t in (0., .05, .1):
            commands = [r.step(t) for r in runs]
            assert json.dumps(commands[0]).encode() == json.dumps(commands[1]).encode()
            for r, issued in zip(runs, commands):
                for rid, command in issued:
                    r.on_command(rid, t, command)
        particles = [r.pose.provider.loc._pf for r in runs]
        assert particles[0].px.tobytes() == particles[1].px.tobytes()
        assert particles[0].logw.tobytes() == particles[1].logw.tobytes()
        assert json.dumps(particles[0].rng.bit_generator.state) == json.dumps(particles[1].rng.bit_generator.state)
        assert json.dumps(runs[0].record()).encode() == json.dumps(runs[1].record()).encode()
    finally:
        for r in runs:
            r.close()


def test_admission_frozen_constants_and_original_bundle_are_preserved():
    plan = contract.registration()
    assert plan['seeds'] == [1059, 1060, 1061]
    from harness.zone_solo_cyan_kld_start import PARAMS
    from harness.zone_solo_cyan_augmented_start import ALPHA_SLOW, ALPHA_FAST
    assert PARAMS == dict(min_samples=2000, max_samples=100000, epsilon=.05,
                         confidence=.99, bins=[.5, .5, math.pi/18])
    assert (ALPHA_SLOW, ALPHA_FAST) == (.001, .1)
    b = contract.bundle('a'*40, 1059, **contract.NEW_OPTIONS)
    contract.require_execution(b)
    assert b['case_cap_s'] == 900.
    assert {k:v for k,v in b['options'].items() if k not in contract.NEW_OPTIONS} == plan['baseline_options']
    for key in contract.NEW_OPTIONS:
        bad = copy.deepcopy(b)
        bad['options'][key] = 'off'
        with pytest.raises(ValueError):
            contract.require_execution(bad)
    with pytest.raises(ValueError):
        contract.bundle('a'*40, 1051, **contract.NEW_OPTIONS)
    with pytest.raises(ValueError):
        contract.require_execution(contract.bundle('a'*40, 1059))
    template = json.loads((contract.ROOT/plan['template']).read_text())
    assert template['execution_bundle_id'] == 'zone-s2-realism-v133'
    assert 'start_prior' not in template['options']


def test_evaluation_detects_false_convergence_without_control_gt():
    from scripts.evaluate_s2_unknown_start import score
    truth = [dict(t=0., robot_xyz_m=[0.,0.,0.], robot_yaw_rad=0.),
             dict(t=1., robot_xyz_m=[1.,0.,0.], robot_yaw_rad=0.)]
    cov = [[.001,0.,0.], [0.,.001,0.], [0.,0.,.001]]
    pose = dict(t_est=.5, x_m=1., y_m=0., cov=cov,
                observation_quality={'diagnostics': {'pose_estimate': {
                    'cluster_count':1, 'selected_cluster_cov':cov}}})
    record = dict(poses=[dict(t=.6, t_est=.5, x=1., y=0., yaw=0., std_xy_m=.04)],
        global_full_decisions=[dict(t=.6, state='search_move', report=pose, pose_uncertain=False)])
    q = score(record, truth)
    assert q['first_convergence']['wrong_mode'] is True
    assert q['first_convergence']['actual_traveled_before_release_m'] == pytest.approx(.6)
    assert q['first_convergence']['actual_xy_error_m'] == pytest.approx(.5)
    assert q['unflagged_gt_25cm'] == 1
    assert q['nees_comparable_to_v133']['above_chi2_95'] == 1
    record['poses'][0]['std_xy_m'] = .051
    assert score(record, truth)['first_convergence'] is None
