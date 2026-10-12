import copy,json,hashlib
from dataclasses import asdict
from types import SimpleNamespace
import numpy as np
import pytest
from harness.own_traversal_reconnection import (ReconnectedGraph,PartialReturn,LOOP_OPTIONS,OPTION,PARTIAL_ANGLE,attach)
from harness.own_traversal_graph import TraversalGraph
from harness.self_pose_graph import GraphOptions,match_loop,between
from tests.test_own_traversal_graph import sample,goal
from tests.test_self_pose_graph import CORNER


def s(i,status='following',pose=(0.,0.,0.)):
    return dict(sample(i,*pose,status=status),segments=copy.deepcopy(CORNER))


def populated():
    g=ReconnectedGraph('r3')
    for i in range(1,11):g.observe(s(i),goal(1))
    g.observe(s(11,'recover_wait'))
    g.observe(s(12))
    return g


def test_acceptance_options_and_exact_cache_equivalence():
    assert asdict(LOOP_OPTIONS)==asdict(GraphOptions())
    g=populated();a,b=g.gaps[0]['a'],g.gaps[0]['b'];sm=g.submaps[a];row=g.nodes[b]['scan']
    direct=match_loop(sm,row,between(g.nodes[a]['pose'],g.nodes[b]['pose']),GraphOptions())
    cached=g.pair_match(a,b)
    assert json.dumps(direct,sort_keys=True)==json.dumps(cached,sort_keys=True)
    assert g.cache.stats()['pair_hits']>=1
    assert g.gaps[0]['accepted']
    e=next(e for e in g.edges if e.get('kind')=='recovery_bridge')
    assert [x['frame_id'] for x in e['samples']]==[10,11,12]
    assert e['relative_pose']==direct['relative_pose']


def test_rejected_bridge_is_retained_but_cannot_connect(monkeypatch):
    g=ReconnectedGraph('r3');g.observe(s(1),goal(1));g.observe(s(2))
    monkeypatch.setattr(g,'pair_match',lambda a,b:dict(accepted=False,reason='ambiguous_modes'))
    g.observe(s(3,'recover_wait'));g.observe(s(4));g.seal()
    assert g.route(g.anchor) is None
    assert [x['frame_id'] for x in g.gaps[0]['samples']]==[2,3,4]
    assert not g.gaps[0]['accepted'] and g.snapshot()['retained_frames']==4


def test_revisit_uses_same_acceptance_and_no_member_scan(monkeypatch):
    g=populated();g.seal()
    b=g.nodes[-1]['id']
    assert g.pair_match(b,b)['reason']=='member_scan'
    before=len(g.edges);event=g.connect(g.gaps[0]['a'],b,'place_recognition',[])
    assert event['accepted'] and len(g.edges)==before  # same pair never inserted twice


def test_five_candidates_keep_original_csm_and_try_past_nearest(monkeypatch):
    g=ReconnectedGraph('r3')
    g.nodes=[dict(id=i,pose=[i*.01,0,0],t=1.) for i in range(7)]
    calls=[]
    def fake(self,query,node_id=None):
        calls.append(node_id)
        return dict(status='accepted' if node_id==2 else 'rejected',reason='accepted' if node_id==2 else 'low_overlap',node=node_id,pose=query['pose'])
    monkeypatch.setattr(TraversalGraph,'match',fake)
    r=g.match(s(10));assert calls==[0,1,2,3,4] and r['node']==2 and r['candidates_checked']==5
    assert len(r['candidate_attempts'])==5


def test_partial_turn_one_half_fov_no_full_sweep_or_retry(monkeypatch):
    g=ReconnectedGraph('r3');g.nodes=[dict(id=0,pose=[0,0,np.pi])]
    monkeypatch.setattr(g,'match',lambda q,n=None:dict(status='rejected',reason='low_overlap',node=0))
    p=PartialReturn(g);p.localize(s(1))
    v,reason=p.twist([0,0,0],1.2);assert reason=='node_match_partial_turn' and v[0]==v[1]==0
    v,reason=p.twist([0,0,p.partial_direction*PARTIAL_ANGLE],2.)
    assert np.array_equal(v,np.zeros(3)) and reason=='node_match_failed_after_partial_turn'
    assert p.localize(s(3)) is None and len(p.partial_used)==1


def test_partial_turn_timeout_and_acceptance_stops_rotation(monkeypatch):
    g=ReconnectedGraph('r3');g.observe(s(1),goal(1));g.seal()
    monkeypatch.setattr(g,'match',lambda q,n=None:dict(status='rejected',reason='low_overlap',node=0))
    p=PartialReturn(g);p.localize(s(2));assert p.twist([0,0,0],12)[1]=='node_match_failed_after_partial_turn'
    p=PartialReturn(g);p.localize(s(2))
    monkeypatch.setattr(g,'match',lambda q,n=None:dict(status='accepted',reason='accepted',node=0,pose=[0,0,0]))
    p.localize(s(3));assert p.sweep_start is None and p.route is not None


def test_new_option_factory_off_identity_and_live_policy():
    from harness.self_map_return_repeat import attach as factory
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    x=Poison();assert attach(x) is x
    a=factory(SimpleNamespace(robot_id='r3',started=0.),map_utility='remembered_goal_360_v1',return_policy=OPTION)
    assert type(a).__name__=='Reconnected360' and isinstance(a.traversal_graph,ReconnectedGraph)
    b=factory(SimpleNamespace(robot_id='r3',started=0.),map_utility='remembered_goal_360_v1',return_policy='traversal_graph_v1')
    assert type(b).__name__=='Traversal360' and type(b.traversal_graph) is TraversalGraph


def test_prefix_freeze_no_future_and_only_own_cache():
    g=populated();before=json.dumps(g.seal(),sort_keys=True)
    with pytest.raises(ValueError):g.observe(s(13))
    assert before==json.dumps(g.snapshot(),sort_keys=True)
    for n in g.nodes:
        assert all(q['t']<=n['t'] for q in n['patch_sources'])
    with pytest.raises(ValueError,match='PEER'):g.cache.prepare([], 'r2')
