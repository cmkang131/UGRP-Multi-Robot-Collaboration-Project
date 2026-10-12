"""E2E14 composition: #443 views/marker + #444 VO as independent default-off runner toggles."""
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.run_e2e_ownmap_live import Options, WALL_CAP_MAX_S, bundle, main

GEMMA = 'study_gemma4_31b_v1'
BASE = dict(enabled=True, relook='on_v1', options=Options(True, True, 'en'), exploration_progress='frontier_progress_v1',
            pose_fix='innovation', path_follow='rpp_v1', dev_light=True, stall_bundle=True, mapping_budget='case_cap_v1')
A12 = dict(stall_odometry='rgb_pulse_gate_v1', stall_recovery='backup_replan_v1', stall_noise='amcl_alpha_v1')
COMBO = dict(stall_odometry='rgb_vo_v1', boundary_views='candidate_views_v1', b_marker_detect='contrast_v1')


def test_paired_speed_options_and_relay_admission():
    from harness.e2e_exact_speedups import Options as Speed
    from scripts.s4_proxy_relay import accepted_call_id
    speed = {k: True for k in vars(Speed())}
    a = make(**COMBO, exact_speedups=speed, wall_cap_s=25200.)
    b = make(**A12, exact_speedups=speed, wall_cap_s=25200.)
    assert a['e2e_options']['exact_speedups'] == b['e2e_options']['exact_speedups'] == speed
    assert a['execution_bundle_id'] == 'e2e-combo14-v202'
    assert b['execution_bundle_id'] == 'e2e-exact-speed-v200'
    for group in ('a', 'b'):
        for seed in range(61001, 61005):
            assert accepted_call_id(f'e2e14-{group}-s{seed}:call-0001-r1:1')
    assert not accepted_call_id('e2e14-c-s61001:call-0001-r1:1')
    assert not accepted_call_id('e2e14-a-s61005:call-0001-r1:1')


def make(**kw):
    return bundle('x', 61001, GEMMA, **{**BASE, **kw})


def test_combo_bundle_v202_has_all_three_and_vo_contract():
    b = make(wall_cap_s=25200., **COMBO)
    o = b['e2e_options']
    assert (b['execution_bundle_id'], b['workflow_version'], b['schema']) == ('e2e-combo14-v202', '7.95.0', 'ugrp.e2e_ownmap_live.v202')
    assert (o['stall_odometry'], o['stall_recovery'], o['stall_noise']) == ('rgb_vo_v1', 'off', 'off')
    assert (o['boundary_views'], o['b_marker_detect']) == ('candidate_views_v1', 'contrast_v1')
    assert (o['path_follow'], o['pose_fix'], o['mapping_budget'], o['exploration_progress']) == \
        ('rpp_v1', 'innovation', 'case_cap_v1', 'frontier_progress_v1')
    assert b['wall_cap_s'] == 25200. and b['case_cap_s'] == 1800.
    assert 'configs/simulation_workflows.d/e2e_combo14_v202.json' in b['source_sha256']
    assert 'configs/simulation_workflows.d/e2e_rgb_vo_v201.json' in b['source_sha256']


def test_toggles_are_independent_and_old_bundles_have_no_new_keys():
    views = make(boundary_views='candidate_views_v1')['e2e_options']
    marker = make(b_marker_detect='contrast_v1')['e2e_options']
    assert (views['boundary_views'], views['b_marker_detect'], views['stall_odometry']) == ('candidate_views_v1', 'off', 'off')
    assert (marker['boundary_views'], marker['b_marker_detect']) == ('off', 'contrast_v1')
    vo = make(stall_odometry='rgb_vo_v1')
    assert vo['execution_bundle_id'] == 'e2e-rgb-vo-v201' and 'boundary_views' not in vo['e2e_options']
    a12 = make(**A12)
    assert a12['execution_bundle_id'] == 'e2e-stall-budget-v199' and a12['wall_cap_s'] == 12600.
    assert not {'boundary_views', 'b_marker_detect'} & set(a12['e2e_options'])
    off = bundle('x', 61001, GEMMA)
    assert off['execution_bundle_id'] == 'e2e-ownmap-live-v185' and 'boundary_views' not in off['e2e_options']


def test_wall_cap_ceiling_and_validation():
    assert WALL_CAP_MAX_S == 25200.
    assert make(**A12, wall_cap_s=25200.)['wall_cap_s'] == 25200.
    for bad in (25201., 0., -1.):
        with pytest.raises(ValueError, match='FINITE_WALL_CAP_REQUIRED'):
            make(**A12, wall_cap_s=bad)
    with pytest.raises(ValueError, match='UNKNOWN_B_BOUNDARY_VIEWS'):
        make(boundary_views='on')
    with pytest.raises(ValueError, match='UNKNOWN_B_MARKER_DETECT'):
        make(b_marker_detect='on')
    with pytest.raises(ValueError, match='FRONTIER_PROGRESS_V1_REQUIRED_BEFORE_VIEWS'):
        bundle('x', 61001, GEMMA, enabled=True, boundary_views='candidate_views_v1')
    with pytest.raises(ValueError, match='RGB_VO_REQUIRES_RECOVERY_AND_NOISE_OFF'):
        make(**{**COMBO, 'stall_recovery': 'backup_replan_v1'})


def test_cli_dry_run_and_catalog(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['run', '--expected-source-sha', 'x', '--output', '/tmp/unused', '--seed', '61001',
        '--driver-profile', GEMMA, '--relay-receipt', '/tmp/r.json', '--e2e-live', '--event-driven-llm', '--compact-prompt',
        '--setdown-only-when-relook', 'on_v1', '--exploration-progress', 'frontier_progress_v1', '--pose-fix', 'innovation',
        '--path-follow', 'rpp_v1', '--dev-light', '--stall-bundle', '--mapping-budget', 'case_cap_v1',
        '--stall-odometry', 'rgb_vo_v1', '--boundary-views', 'candidate_views_v1', '--b-marker-detect', 'contrast_v1',
        '--wall-cap-s', '25200'])
    main()
    b = json.loads(capsys.readouterr().out)
    assert b['execution_bundle_id'] == 'e2e-combo14-v202' and b['wall_cap_s'] == 25200.
    from sim.workflow_manager import catalog
    rows, _ = catalog(Path('.'))
    w = next(w for w in rows['workflows'] if w['id'] == 'e2e-combo14-v202')
    assert w['version'] == '7.95.0' and {'--boundary-views', '--b-marker-detect', '--stall-odometry'} <= set(w['required_inputs'])


def test_robot_with_all_three_wires_each_toggle():
    """Real make_goal path: VO wrapper, candidate navigator and contrast marker coexist."""
    import base64
    from harness.e2e_boundary_views import CandidateNavigator
    from harness.e2e_live_mapping import Robot
    from harness.e2e_stall_odometry import Options as Stall
    from harness.s4_event_policy import Options as Study
    cov = json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    r = Robot('r1', 61001, cov, Study(), exploration_progress='frontier_progress_v1', pose_fix='innovation',
              path_follow='rpp_v1', stall_options=Stall('rgb_vo_v1'), mapping_budget_s=1800.,
              boundary_views='candidate_views_v1', b_marker_detect='contrast_v1')
    assert hasattr(r.goal, 'e2e_vo') and not hasattr(r.goal, 'e2e_stall')
    assert isinstance(r.goal.explorer.navigator, CandidateNavigator)
    assert r.goal.e2e_gate.marker_detect == 'contrast_v1'
    rgb = np.zeros((480, 640, 3), np.uint8);_, data = cv2.imencode('.jpg', rgb);data = data.tobytes()
    trace = r.receive(dict(frame_id=1, sim_time=0., sha256=hashlib.sha256(data).hexdigest(),
                           image=base64.b64encode(data).decode()), rgb)
    assert trace['stall_odometry']['options']['stall_odometry'] == 'rgb_vo_v1'
    assert trace['boundary_view']['option'] == 'candidate_views_v1' and 'boundary_diagnostics' in trace
