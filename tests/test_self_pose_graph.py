"""Offline graph geometry, outlier objective, isolation and frozen off bytes."""
import copy
import json
import math
from pathlib import Path
import types

import numpy as np
import pytest

from harness.self_pose_graph import (GraphOptions, apply_pose_graph, between, compose, make_submaps,
                                     match_loop, optimize, rebuild, robust_block)
from harness.self_wall_memory import SelfWallMemory
from tests.test_wall_projection_guard import FRONT, BACK, ORIGIN, ROT, rec

CORNER = [[[2.,-1.],[2.,1.]], [[.5,1.],[2.,1.]], [[.5,-1.],[.5,0.]]]


def row(i, pose=(0.,0.,0.), segments=None):
    return {'robot_id':'r1','frame_id':i,'t':float(i),'pose':list(pose),'camera':[.16,0.],
            'segments':copy.deepcopy(CORNER if segments is None else segments)}


def test_se2_relative_and_composition():
    a,b = np.array([1.,2.,.7]),np.array([-.3,.8,-2.8])
    np.testing.assert_allclose(compose(a,between(a,b)),b,atol=1e-12)
    r=np.array([[1.,0.,0.],[3.,0.,0.]])
    out=robust_block(r,1.5)
    np.testing.assert_allclose(np.sum(out*out,axis=1),[1.,6.75])


def test_submaps_overlap_no_members_can_form_loop_and_weight_preserved():
    rows=[row(i) for i in range(25)]
    rows[0]['insertion_weight']=.2
    submaps,edges=make_submaps('r1',rows,GraphOptions())
    assert [s['members'] for s in submaps]==[list(range(20)),list(range(10,25)),list(range(20,25))]
    assert len(edges)==40
    assert submaps[0]['grid'].export()['cells']==rebuild('r1',rows[:20]).export()['cells']
    out,path,d=apply_pose_graph(rows[:2],[],robot_id='r1',pose_graph='own_submap_v1')
    assert out==rows[:2] and path==[] and not d['changed']
    assert d['loop_counts']=={'member_scan':2}


def test_known_corner_revisit_matches_and_straight_wall_rejected():
    sm,_=make_submaps('r1',[row(i) for i in range(10)],GraphOptions())
    result=match_loop(sm[0],row(30),np.array([.3,-.2,.05]),GraphOptions())
    assert result['accepted'],result
    assert np.linalg.norm(result['relative_pose'][:2])<.15
    wall=[[[2.,-1.],[2.,1.]]]
    sm,_=make_submaps('r1',[row(i,segments=wall) for i in range(10)],GraphOptions())
    result=match_loop(sm[0],row(30,segments=wall),np.zeros(3),GraphOptions())
    assert not result['accepted'] and result['reason'] in ('ambiguous_modes','unobservable')


def test_repeated_corner_modes_rejected():
    repeated=np.concatenate([np.array(CORNER),np.array(CORNER)+[1.,0.]]).tolist()
    sm,_=make_submaps('r1',[row(i,segments=repeated) for i in range(10)],GraphOptions())
    result=match_loop(sm[0],row(30),np.array([.5,0.,0.]),GraphOptions())
    assert not result['accepted'] and result['reason'] in ('ambiguous_modes','search_boundary')


def test_spa_loop_moves_past_scan_and_fixed_submap_stays_at_origin():
    rows=[row(0),row(1,(.5,0.,0.))]
    cov=np.diag([.1,.1,.01]).tolist()
    sm=[{'pose':np.zeros(3)}]
    edges=[{'kind':'intra','submap':0,'scan':i,'relative_pose':r['pose'],'covariance':cov} for i,r in enumerate(rows)]
    edges.append({'kind':'loop','submap':0,'scan':1,'relative_pose':[0.,0.,0.],'covariance':(np.eye(3)*.01).tolist()})
    solved,d=optimize(sm,rows,edges,GraphOptions())
    assert d['accepted'] and d['final_cost']<d['initial_cost']
    np.testing.assert_array_equal(solved[0],np.zeros(3))
    assert abs(solved[-1,0])<.1
    assert rows[1]['pose']==[.5,0.,0.]


def test_peer_duplicate_invalid_path_and_range_are_rejected():
    for changes,reason in [({'robot_id':'r2'},'PEER'),({'segments':[[[5.,0.],[5.,1.]]]},'RANGE')]:
        with pytest.raises(ValueError,match=reason):
            apply_pose_graph([{**row(0),**changes}],[],robot_id='r1',pose_graph='own_submap_v1')
    with pytest.raises(ValueError,match='DUPLICATE'):
        apply_pose_graph([row(0),row(0)],[],robot_id='r1',pose_graph='own_submap_v1')
    with pytest.raises(ValueError,match='PEER'):
        apply_pose_graph([row(0)],[{'robot_id':'r2','t':0.,'pose':[0.,0.,0.]}],robot_id='r1',pose_graph='own_submap_v1')
    a,b=object(),object()
    assert apply_pose_graph(a,b,robot_id='r1')==(a,b,None)


@pytest.mark.parametrize('mode',['off','own_map_csm_v1','own_map_csm_v2','own_map_csm_prob_v1','own_map_rbpf_v1'])
@pytest.mark.parametrize('guard',['off','positive_depth_v1'])
def test_default_and_explicit_graph_off_frozen_bytes(mode,guard):
    old=types.ModuleType('before_graph')
    exec((Path(__file__).parent/'fixtures/self_wall_memory_before_pose_graph.py.txt').read_text(),old.__dict__)
    args=dict(self_map='odom_grid_v1',pose_correction=mode,self_map_options={'settle_s':None},
              wall_projection_guard=guard,clock=lambda:9.)
    ms=[old.SelfWallMemory('r1',**args),SelfWallMemory('r1',**args),SelfWallMemory('r1',pose_graph='off',**args)]
    for i in range(3):
        for m in ms:
            m.command({'t':float(i),'kind':'drive','forward':.01,'turn':.01,'duration_s':.2})
            m.observe_wall(rec([FRONT,BACK],float(i),i),camera_xy=ORIGIN[:2],robot_id='r1',camera_origin=ORIGIN,camera_rotation=ROT)
        values=[json.dumps([m.snapshot(),m.self_map.export()]).encode() for m in ms]
        assert values[0]==values[1]==values[2]
    assert ms[1].finalize_pose_graph(object()) is None


@pytest.mark.parametrize('mode',['own_map_csm_prob_v1','own_map_rbpf_v1'])
def test_memory_combination_finalization_is_offline_and_frontend_immutable(mode):
    with pytest.raises(ValueError,match='NEEDS_GUARDED'):
        SelfWallMemory('r1',pose_graph='own_submap_v1')
    m=SelfWallMemory('r1',self_map='odom_grid_v1',pose_correction=mode,self_map_options={'settle_s':None},
                     wall_projection_guard='positive_depth_v1',pose_graph='own_submap_v1')
    m.observe_wall(rec([FRONT],1.,1),camera_xy=ORIGIN[:2],robot_id='r1',camera_origin=ORIGIN,camera_rotation=ROT)
    before=json.dumps(m.self_map.export())
    result=m.finalize_pose_graph()
    assert result['ledger'] and not result['diagnostics']['changed']
    assert json.dumps(m.self_map.export())==before
    assert m._graph_view.export()['cells']==m.self_map.export()['cells']
    assert 'own submap graph' in m.snapshot()['self_map_text']
    m.command({'t':2.,'kind':'stop'})
    assert m._graph_view is None and m.pose_graph_result is None


def test_global_correction_transports_path_and_rebuilds_same_local_evidence(monkeypatch):
    import harness.self_pose_graph as graph
    rows=[row(0),row(10,(.4,0.,0.))]
    poses=[{'robot_id':'r1','t':float(t),'pose':p} for t,p in [(-1,[0.,0.,0.]),(0,[0.,0.,0.]),(10,[.4,0.,0.]),(11,[.5,0.,0.])]]
    # A known relative loop constraint isolates graph/path plumbing from matching.
    monkeypatch.setattr(graph,'match_loop',lambda sm,r,initial,o:{'accepted':True,'reason':'accepted',
        'relative_pose':[0.,0.,0.],'covariance':(np.eye(3)*.001).tolist()})
    corrected,path,d=apply_pose_graph(rows,poses,robot_id='r1',pose_graph='own_submap_v1',
        options={'submap_scans':2,'stride':1,'separation_s':1.})
    assert d['changed'] and d['loop_counts']['accepted']>0
    assert path[0]==poses[0]
    np.testing.assert_allclose(np.array(path[-1]['pose'])-path[-2]['pose'],[.1,0.,0.],atol=1e-5)
    assert any(a['pose']!=b['pose'] for a,b in zip(rows,corrected))
    assert all(a['segments']==b['segments'] and a['camera']==b['camera'] for a,b in zip(rows,corrected))
    assert rebuild('r1',corrected).frames==len(rows)


def test_frozen_section17_and_guard_criteria_are_both_required():
    import sys
    directory=Path(__file__).resolve().parents[1]/'experiments/2026-10-05-ego-wall-map-probe/code'
    sys.path.insert(0,str(directory))
    from own_submap_replay import graph_criteria
    off={'end_position_error_m':1.,'path_position_error':{'median_m':1.,'p95_m':1.,'rmse_m':1.},
         'final':{'precision_015':.4,'wall_coverage':.3,'recall_visible':.6,'wall_error_rmse_m':1.}}
    on=copy.deepcopy(off)
    on['end_position_error_m']=.6
    on['path_position_error']['rmse_m']=.7
    on['final']['wall_error_rmse_m']=.7
    assert all(graph_criteria(off,off,on,0,{'ok':True}).values())
    on['final']['recall_visible']=.579
    assert not graph_criteria(off,off,on,0,{'ok':True})['guard_visible_recall_within_2pp']
    on['final']['precision_015']=.399
    checks=graph_criteria(off,off,on,0,{'ok':True})
    assert not checks['guard_precision_nondecrease'] and not checks['map_precision_not_worse']
