"""Assertions against frozen real reports and frames; no physics fixtures."""
import importlib.util
import math
from pathlib import Path

import replay


def test_boundary_rejects_simulator_and_learned_models():
    import pytest
    for name in ('mujoco','torch','tensorflow'):
        with pytest.raises(ImportError,match='parity boundary'):
            replay.Boundary().find_spec(name)


def test_saved_gate_rejections_are_not_low_threshold_or_dwell_failures():
    data=replay.read(Path(__file__).parent/'dev-main.json')
    runs={r['id']:r for r in data['runs']}
    d6=runs['dev06']['robots']['r2']['first_postapproach_gate_reject']
    assert d6['sim_s']==193.7 and d6['phase']=='wait_lift'
    assert d6['report']['std_xy_m']<.06
    assert d6['report']['std_yaw_rad']>math.radians(3)
    d8=runs['dev08']['robots']['r2']['first_postapproach_gate_reject']
    assert d8['sim_s']==175.6 and d8['phase']=='align'
    assert d8['report']['std_xy_m']>.07
    assert d8['report']['std_yaw_rad']<math.radians(3)
    assert d8['report']['load_state']=='unloaded'


def test_reconstructed_unissued_command_is_rejected_only_by_attached_volume():
    main=replay.read(Path(__file__).parent/'dev-main.json')['runs'][2]['robots']['r1']['grasp_command_replay']
    latest=replay.read(Path(__file__).parent/'dev-grasp-v4.json')['runs'][2]['robots']['r1']['grasp_command_replay']
    assert main['matched_issued_commands']==latest['matched_issued_commands']==65
    assert main['reconstructed_unissued_batch']==latest['reconstructed_unissued_batch']
    assert main['aborts'][0]['reason']=='PAIR_COLLISION_GUARD'
    assert latest['aborts']==[] and latest['checked_output']==latest['reconstructed_unissued_batch']


def test_v5_real_partial_reject_has_valid_m2_grip_and_fresh_track():
    d=replay.read(Path(__file__).parent/'dev-grasp-v4.json')['runs'][4]['robots']['r1']
    assert d['m2_at_actual_stop']['grip_view_m2']['seen']
    assert d['m2_at_actual_stop']['beam_obs']['reason']=='END_CLIPPED'
    assert d['preclose_replay']['accepted'] is False
    assert d['preclose_replay']['track']['std_xy_m']<.05
    assert d['preclose_replay']['track']['std_yaw_rad']<math.radians(3)
    assert d['preclose_replay']['sim_s']-d['preclose_replay']['track']['anchor_time_s']<3


def test_no_post_submission_or_future_frames_used_for_admission_and_stops():
    d=replay.read(Path(__file__).parent/'dev-main.json')
    for run in d['runs']:
        for robot in run['robots'].values():
            assert robot['replayed_admission']['observation']['age_s']>=0
            assert (robot['replayed_admission']['state']=='available')==robot['actual_admission']['accepted']
            stop=robot['m2_at_actual_stop']
            if stop: assert stop['last_causal_frame_s']<=stop['sim_s']+1e-6


def test_latest_grasp_v5_repairs_partial_predicate_but_only_requests_a_new_view():
    d=replay.read(Path(__file__).parent/'dev-grasp-v5.json')
    r7=d['runs'][4]['robots']['r1']['preclose_replay']
    assert r7['accepted'] is True
    assert r7['logs'][-1]['beam']['partial_reason']=='END_CLIPPED'
    assert abs(r7['logs'][-1]['clearance_after_margin_m']-.6808772693)<1e-8
    r8=d['runs'][5]['robots']['r2']['v5_first_in_align_relook']
    assert r8['sim_s']==166.3 and r8['reason']=='tag_gap'
    assert len(r8['safe_static_pan_candidates'])==7
    assert r8['report']['std_xy_m']<.07
