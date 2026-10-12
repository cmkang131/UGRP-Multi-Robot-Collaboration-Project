import copy,json,importlib.util
from pathlib import Path
import numpy as np
import pytest
from scripts.run_frontier_duration import bundle,actor,ROOT
from scripts.run_active_wall_rotleft import frozen_bundle
from scripts.run_active_frontier_cycle import bundle as previous_b
from harness.active_camera import SEARCH
from harness.active_wall_recovery import make_mapper as old_actor,RecoveryMapper
from harness.active_frontier_cycle import VisibilityMapper,OPTION
spec=importlib.util.spec_from_file_location('duration_timeline',ROOT/'experiments/2026-10-08-frontier-duration/code/timeline.py')
timeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(timeline)


def comparable(b):
    b=copy.deepcopy(b)
    for k in ('source_sha','execution_bundle_id','check','admission','preregistration','condition'):b.pop(k,None)
    return b


def test_only_seed_duration_and_cycle_option_differ():
    a,b=bundle('A','f'*40),bundle('B','f'*40)
    assert a['task']['seed']==b['task']['seed']==46001
    assert a['case_cap_s']==b['case_cap_s']==360.
    b['options'].pop('frontier_observation')
    assert comparable(a)==comparable(b)
    for condition,old in [('A',frozen_bundle('new-seed','f'*40)),('B',previous_b('f'*40))]:
        fresh=bundle(condition,'f'*40)
        fresh['task']['seed']=old['task']['seed'];fresh['case_cap_s']=180.
        assert comparable(fresh)==comparable(old)
    with pytest.raises(ValueError):bundle('C','f'*40)


def test_default_off_trace_bytes_and_b_same_class():
    args=dict(active_mapping='frontier_rbpf_v1',active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1',seed=46001)
    a=actor('A')('r3',0,SEARCH,**args);old=old_actor('r3',0,SEARCH,**args)
    assert type(a) is type(old) is RecoveryMapper
    assert isinstance(actor('B')('r3',0,SEARCH,**args),VisibilityMapper)
    rgb=np.zeros((480,640,3),np.uint8);obs=dict(segments=[],features=[],camera=[.124,0.],floor_xy=[[.7,.2],[.7,-.2]])
    for i,t in enumerate([2.,2.2,3.]):
        x=a.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        y=old.receive(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,observation=obs)
        assert json.dumps([x,a.memory.self_map.export()])==json.dumps([y,old.memory.self_map.export()])


def test_timeline_uses_past_only_and_censors_failure():
    ss=[dict(t=t,tag=str(t)) for t in [10.,121.3,121.5,181.3,241.5,361.3]]
    r=timeline.select_snapshots(ss,start=1.3,end=361.3)
    assert [x['snapshot']['t'] for x in r]==[121.3,181.3,181.3,361.3]
    r=timeline.select_snapshots(ss,start=1.3,end=200)
    assert [x['status'] for x in r]==['observed','observed','censored','censored']
    assert r[2]['snapshot'] is None
    assert timeline.select_snapshots([],start=0,end=360)[0]['status']=='no_map_yet'
    with pytest.raises(ValueError):timeline.select_snapshots(ss[::-1],start=0,end=360)
