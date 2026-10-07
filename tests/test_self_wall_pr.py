import copy
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
from harness.self_wall_pr import angular_span,distinct_cameras,grid_support,segment_support,apply,OPTION
from harness.self_pose_graph import rebuild


def ledger():
    return [dict(robot_id='r3',t=i,frame_id=i,pose=[0,y,0],camera=[0,0],
        segments=[[[2,-.2-y],[2,.2-y]]],insertion_weights=[.8]) for i,y in enumerate([0,.2,.4,.6])]


def test_angular_diversity_and_same_position_rotation_is_not_new_view():
    assert angular_span([2,0],[[0,0],[0,0]])==0
    assert len(distinct_cameras([2,0],[[0,0],[0,0],[0,.2]]))==2
    assert angular_span([2,0],[[0,0],[0,2]])==45
    assert abs(angular_span([0,0],[[1,.01],[1,-.01]])-1.145877395)<1e-6


def test_grid_nested_thresholds_free_and_frozen_v1():
    rows=ledger();grid=rebuild('r3',rows).export();support=grid_support(grid,rows,robot_id='r3')
    raw=json.dumps(grid);prior=None
    for n in range(1,6):
        view=apply(grid,support,wall_validation=OPTION,min_views=n,min_angle_deg=0)
        cells={tuple(c[:2]) for c in view['cells'] if c[2]>0}
        if prior is not None:assert cells<=prior
        prior=cells
        assert [c for c in view['cells'] if c[2]<=0]==[c for c in grid['cells'] if c[2]<=0]
    from harness.self_wall_validation import validated_grid
    old,_=validated_grid(grid,rows,robot_id='r3',wall_validation='multiview_weight_v1')
    new=apply(grid,support,wall_validation=OPTION,min_views=4,min_angle_deg=0)
    assert new['cells']==old['cells'] and json.dumps(grid)==raw
    assert apply(grid) is grid


def test_segment_filter_preserves_geometry_and_input_and_rejects_wrong_source():
    rows=ledger()
    base=dict(robot_id='r3',segments=[dict(endpoints_m=[[2,-.2],[2,.2]],frame_ids=[0,1,2,3],covariance=[[1,0],[0,1]])])
    support=segment_support(base,rows,robot_id='r3')
    assert apply(base) is base
    yes=apply(base,support,wall_validation=OPTION,min_views=4,min_angle_deg=15)
    assert yes['segments']==base['segments']
    no=apply(base,support,wall_validation=OPTION,min_views=4,min_angle_deg=30)
    assert no['segments']==[] and len(base['segments'])==1
    with pytest.raises(ValueError,match='EXPLICIT'):apply(base,support,wall_validation=OPTION)
    wrong=copy.deepcopy(base);wrong['segments'][0]['endpoints_m'][0][0]=3
    with pytest.raises(ValueError,match='MISMATCH'):apply(wrong,support,wall_validation=OPTION,min_views=1,min_angle_deg=0)
    with pytest.raises(ValueError,match='PEER'):segment_support(base,rows,robot_id='r2')


def test_preregistered_selection_feasible_fallback_ties_and_empty():
    path=Path(__file__).resolve().parents[1]/'experiments/2026-10-08-wall-pr-operating-point/code/selection.py'
    spec=importlib.util.spec_from_file_location('pr_selection',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def point(n,p,r,rmse=.1):
        return dict(min_views=n,min_angle_deg=0,metrics=dict(full=dict(precision_015=p,wall_coverage=r,wall_error_rmse_m=rmse)))
    candidates=[point(1,.85,.8),point(2,.90,.6),point(3,.95,.4),point(4,None,0,None)]
    chosen=module.select(candidates)
    assert chosen['operating_point']['min_views']==2 and chosen['status']=='precision_feasible'
    candidates=[point(1,.85,.8),point(2,.86,.6),point(3,.86,.6)]
    chosen=module.select(candidates)
    assert chosen['operating_point']['min_views']==2 and chosen['status']=='no_precision_feasible_diagnostic_only'
    assert module.select([point(1,None,0,None)])['operating_point'] is None
    before=point(1,.5,.6,.5)['metrics']['full']
    after=point(1,.95,.1,.1)['metrics']['full']
    assert not module.closer(before,after)['export_start']  # precision alone is insufficient
