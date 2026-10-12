import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness import own_route_zone_arrival as m
from harness import turn_lateral_calibration as motion
from harness.own_route_reference import install as route_install,Options
from scripts import run_own_route_turn_lateral as runner
from test_own_route_traversed import prepared,frame
from test_turn_lateral_calibration import calibration
from harness.self_pulse_rotation import RotationPulseOdometry


def track(c):
    c.entities['B']['observation']=dict(candidate_id=1)
    c.explorer.goal.options.cell_m=.1
    c.explorer.goal.tracks=[dict(id=1,confirmed_t=1,cells={(0,0),(1,0)},last_center=np.array([.1,0]))]
    return c


def test_default_off_same_full_frame_bytes(monkeypatch):
    a,_=prepared(monkeypatch);b,_=prepared(monkeypatch)
    m.install(b);motion.install(b)
    assert json.dumps(frame(a),sort_keys=True)==json.dumps(frame(b),sort_keys=True)
    assert json.dumps(a.snapshot(),sort_keys=True)==json.dumps(b.snapshot(),sort_keys=True)


def test_passive_two_criteria_do_not_change_legacy_outputs(monkeypatch):
    a=track(prepared(monkeypatch)[0]);b=track(prepared(monkeypatch)[0]);rows=[]
    runner.passive_metrics(b,rows)
    assert json.dumps(frame(a),sort_keys=True)==json.dumps(frame(b),sort_keys=True)
    assert len(rows)==1 and rows[0]['zone_streak']==1


def test_wrong_prefix_quarantined_without_static_goal_or_rejecting_valid_B(monkeypatch):
    c=track(prepared(monkeypatch)[0]);c.explorer.memory.self_map.odom.pose=[0,0,0]
    c.explorer.goal.detector=lambda *a,**kw:([dict(component=1,center_body_m=[.1,0])],np.ones((12,16),int),{})
    c.navigator.reset_action=lambda:None
    c.explorer.navigator.phase=None
    c.explorer.navigator.core=c.navigator.core
    m.install(c,arrival_zone=m.ARRIVAL,B_color_confirmation=m.COLOR,
        prefix_rgb=np.full((12,16,3),[31,92,179],np.uint8),prefix_servo={})
    _,trace=frame(c)
    assert 'B' not in c.entities and not c.reached
    assert c.explorer.goal.tracks[0]['confirmed_t'] is None
    assert any(x['reason']=='remembered_B_quarantined' for x in c.events)


def test_observed_cell_only_five_frames_no_bbox_infill_and_legacy_separate(monkeypatch):
    c=track(prepared(monkeypatch)[0]);m.install(c,arrival_zone=m.ARRIVAL)
    for t in range(2,8):c._arrival(t,t,np.array([.21,0,0]),False)
    assert not c.reached
    for t in range(8,12):c._arrival(t,t,np.array([.01,.01,0]),False)
    assert not c.reached
    c._arrival(12,12,np.array([.01,.01,0]),False)
    assert c.reached['B']['criterion']==m.ARRIVAL
    assert c._legacy_declared is None and c._zone_declared==12
    assert c.reached['B']['pose']==[.01,.01,0]


def test_color_palette_rejects_pickup_across_achromatic_blend_without_new_threshold():
    for color in m.PALETTE:
        for gray in (.15,.5,.8):
            rgb=np.full((20,20,3),255*(.5*np.array(m.PALETTE[color])+.5*gray),np.uint8)
            r=m.classify(rgb,np.ones((20,20),bool))
            assert r['accepted']==(color=='B')


@pytest.mark.parametrize('condition',tuple(runner.CONDITIONS))
def test_all_four_actual_accelerated_receive_paths_first_frame(monkeypatch,condition):
    c,active=prepared(monkeypatch);track(c)
    c.explorer.memory.self_map.odom.driver=RotationPulseOdometry()
    c.explorer.memory.self_map.odom.pose=[0,0,0]
    route_install(c,runner.CONDITIONS[condition],traversed_free='footprint_history_v1' if 'traversed' in condition else 'off')
    if condition!='baseline':
        # Patch globals back automatically after this isolated test.
        from harness import active_wall_mapping
        monkeypatch.setattr(active_wall_mapping,'selected_model',active_wall_mapping.selected_model)
        motion.install(c,motion_model_turn_lateral_v2=motion.OPTION,calibration=calibration())
        assert c.heading_host.profiles is c.explorer.memory.self_map.odom.driver.profiles
    if condition.endswith('zone'):
        rgb=np.full((12,16,3),[51,102,242],np.uint8)
        c.explorer.goal.detector=lambda *args,**kw:([dict(component=1,center_body_m=[.1,0],rect_sides_m=[.6,1.4])],np.ones((12,16),int),{})
        m.install(c,arrival_zone=m.ARRIVAL,B_color_confirmation=m.COLOR,prefix_rgb=rgb,prefix_servo={})
    _,trace=frame(c)
    assert active==[True]
    if condition.endswith('zone'):assert trace['zone_arrival']['calls']==1 and trace['zone_arrival']['receive_executed']
    if 'traversed' in condition:assert trace['reference_navigation']['execution']['calls']==1


def test_registered_24_commands_unique_fixed_seeds():
    jobs=runner.jobs('/unused');assert len(jobs)==24
    assert len({j['name'] for j in jobs})==24
    assert {j['seed'] for j in jobs}==set(range(63001,63007))


def test_partial_blue_piece_is_not_full_B_identity_but_size_tolerance_unchanged():
    rgb=np.full((12,16,3),[51,102,242],np.uint8);region=np.ones((12,16),bool)
    assert m.confirm_component(rgb,region,dict(rect_sides_m=[.6,1.4]))['accepted']
    assert not m.confirm_component(rgb,region,dict(rect_sides_m=[.2,.5]))['accepted']
    assert not m.confirm_component(rgb,region,dict(rect_sides_m=[.8,1.4]))['accepted']
