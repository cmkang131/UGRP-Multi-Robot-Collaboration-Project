import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from harness.reloc20_motion import LoadedRoute, VisualStall, heading_forward, install


def static():
    return dict(bounds_m=[-2,2,-2,2],obstacles=[],fixed_floor_keepouts=[
        dict(id='cargo_beam_1',center_m=[0,0],half_extents_m=[.30,.02],yaw_rad=math.pi/2)])


def test_heading_forward_removes_crab_before_translation():
    assert heading_forward([0,0,0],[0,1]) == (0,0,.1)
    assert heading_forward([0,0,math.pi/2],[0,1]) == (.08,0,0)
    assert heading_forward([0,0,math.pi],[1,0])[0:2] == (0,0)


def test_static_beam_replans_every_swept_edge_without_margin_release():
    route=LoadedRoute(static())
    path=route.plan((-.8,0),(.8,0),static()['bounds_m'],[],radius=route.radius)
    assert path and len(path)>2
    assert all(route.segment(a,b,[])[0] for a,b in zip(path,path[1:]))
    assert any(x['blocked_object']=='cargo_beam_1' for x in route.events)


def test_blocked_goal_and_start_never_bypass_footprint():
    route=LoadedRoute(static())
    assert route.plan((-.8,0),(0,0),static()['bounds_m'],[]) is None
    assert route.last['reason']=='goal_enclosure_overlap'
    assert route.last['minimum_gap_m']<0
    assert route.plan((0,0),(.8,0),static()['bounds_m'],[]) is None
    assert route.last['reason']=='start_enclosure_overlap'


def test_diagonal_corner_between_nodes_is_checked():
    s=dict(bounds_m=[-2,2,-2,2],obstacles=[dict(id='wall',center_m=[0,0],half_extents_m=[.001,.001])])
    r=LoadedRoute(s)
    assert not r.segment((-.5,-.5),(.5,.5),[])[0]


def test_default_off_preserves_predictor_and_planner():
    model=object();planner=object()
    carry=SimpleNamespace(loc=SimpleNamespace(drive_model=model),plan_path=planner)
    install(carry,{})
    assert carry.loc.drive_model is model and carry.plan_path is planner
    assert not carry.reloc20_heading and carry.reloc20_stall is None and carry.reloc20_route is None


def test_ode_is_separate_and_includes_asymmetric_pulse_yaw():
    from harness.drive_model import CommandDriveModel as Legacy
    from harness.reloc20_drive_ode import CommandDriveModel as ODE
    a=Legacy().delta([.5]*4,[.1,.1,.05,.1],.1)
    b=ODE().delta([.5]*4,[.1,.1,.05,.1],.1)
    assert a!=b and b[2]!=0 and all(map(math.isfinite,b))


def test_stall_requires_camera_agreement_and_inflates_no_certainty(monkeypatch):
    import harness.e2e_stall_odometry as flow
    monkeypatch.setattr(flow,'flow_pair',lambda a,b:dict(status='stationary_view',tracks=20,cells=4,median_px=0.,p90_px=0.,mean_abs_diff=0.))
    d=VisualStall(dict(stationary_thresholds=dict(median_px=.1,p90_px=.3,mean_abs_diff=.04)))
    rgb=np.zeros((480,640,3),np.uint8);pwm={3:1500}
    d.observe(rgb,0,pwm,True);d.issue((.06,0,0),.5);d.observe(rgb,.5,pwm,True)
    assert d.suppressed and d.recovering
    assert d.issue((.06,0,0),.5)==(0,0,0)
    assert d.pose[0]==pytest.approx(.12)  # independent detector remains alive
    d.observe(rgb,1,{3:1600},True)
    assert not d.suppressed


def test_unknown_texture_does_not_zero_motion(monkeypatch):
    import harness.e2e_stall_odometry as flow
    monkeypatch.setattr(flow,'flow_pair',lambda a,b:dict(status='unknown_texture',tracks=0,cells=0,median_px=None,p90_px=None,mean_abs_diff=None))
    d=VisualStall(dict(stationary_thresholds=dict(median_px=.1,p90_px=.3,mean_abs_diff=.04)))
    rgb=np.zeros((480,640,3),np.uint8)
    d.observe(rgb,0,{},True);d.issue((.06,0,0),.5);d.observe(rgb,.5,{},True)
    assert not d.suppressed and d.issue((.01,0,0),.1)==(.01,0,0)


def test_issued_load_enclosure_uses_catalogue_and_command_fk():
    from sim.grasp_act_solo_teacher import cargo
    from harness.visual_arm_v3 import solve_grip_site_ik
    r=LoadedRoute(static())
    p={1:1500,**solve_grip_site_ik((.20,0,.024))}
    r.update_load(True,'yellow',p,p)
    assert r.footprint is not None
    assert all(math.hypot(*x)<r.radius for x in r.footprint)


def test_both_required_transport_scenarios_have_hash_bound_map_declarations():
    import hashlib
    root=Path(__file__).resolve().parents[1]
    d=json.loads((root/'experiments/2026-10-16-reloc20/fixed-floor-map.json').read_text())
    for name in ('s8_mixed_tiers_v7','s7_pair_with_solo_v7'):
        row=d['scenarios'][name]
        assert hashlib.sha256((root/row['scenario_source']).read_bytes()).hexdigest()==row['scenario_source_sha256']
        assert row['obstacles'][0]['id']=='cargo_beam_1'


def test_wall_mask_fragments_do_not_become_new_obstacles():
    from sim.solo_carry_obstacles import wall_component_filter
    from harness.zone_own_perception import _components
    raw=np.zeros((100,100),np.uint8);raw[10:60,10:60]=255;raw[70:80,70:80]=255
    wall=np.zeros_like(raw,dtype=bool);wall[10:50,10:60]=True
    cut=raw.copy();cut[wall]=0
    old,_=_components(cut,6.);parents,_=_components(raw,6.)
    assert len(old)==2  # the wall's unclassified fringe becomes a phantom
    new=wall_component_filter(parents,wall)
    assert len(new)==1 and new[0]['bbox']==(70,70,10,10)


def test_turn_density_conserves_requested_on_time_and_emits_full_control_ticks():
    from harness.reloc20_motion import TurnDensity
    d=TurnDensity(.1);wheel=[-.35,.35,-.35,.35]
    for i in range(1000):
        w,t=d.apply(wheel,[.018571428571428576]*4,i*.1)
        assert w==wheel or w==[0.]*4
        assert t==[.1]*4 or t==[0.]*4
    assert 0<=d.requested-d.emitted<d.period
    assert d.requested-d.emitted==pytest.approx(d.debt)


def test_turn_density_cannot_execute_old_turn_after_stop_or_direction_change():
    from harness.reloc20_motion import TurnDensity
    d=TurnDensity(.1);left=[-.35,.35,-.35,.35]
    for i in range(4):d.apply(left,[.02]*4,i*.1)
    assert d.apply([0.]*4,[0.]*4,.4)==([0.]*4,[0.]*4)
    assert d.apply(left,[.02]*4,.5)==([0.]*4,[0.]*4)
    for i in range(3):d.apply(left,[.02]*4,.6+i*.1)
    assert d.apply([.35,-.35,.35,-.35],[.02]*4,.9)==([0.]*4,[0.]*4)
    assert d.debt==pytest.approx(.02)


def test_rotation_stationarity_does_not_require_expected_xy_motion(monkeypatch):
    import harness.e2e_stall_odometry as flow
    monkeypatch.setattr(flow,'flow_pair',lambda a,b:dict(status='stationary_view',tracks=20,cells=4,median_px=0.,p90_px=0.,mean_abs_diff=0.))
    d=VisualStall(dict(stationary_thresholds=dict(median_px=.1,p90_px=.3,mean_abs_diff=.04)),rotation=True)
    rgb=np.zeros((480,640,3),np.uint8)
    d.observe(rgb,0,{},True);d.issue((0.,0.,2*d.angular_min),.5);d.observe(rgb,.5,{},True)
    assert d.suppressed and d.last['expected_motion_kind']=='angular_or_mixed'
