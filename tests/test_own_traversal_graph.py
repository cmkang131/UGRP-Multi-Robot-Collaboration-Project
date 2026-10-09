import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness.own_traversal_graph import TraversalGraph, TraversalReturn, attach, OPTION, own_sample
from harness.active_wall_mapping import pulse_command


def sample(i,x=0.,y=0.,yaw=0.,status='following'):
    return dict(t=float(i),frame_id=i,pose=[x,y,yaw],covariance=np.diag([.01,.01,.01]).tolist(),
        status=status,excluded_reason=None,segments=[[[1.,-1.],[1.,1.]],[[1.,1.],[-1.,1.]]],camera=[0.,0.],
        frame_sha256=str(i)*64,rgb_summary=[[0]*16]*12)


def goal(t):
    return dict(source='own',first_t=t,t_sim=t,center_m=[0.,0.],obs_id='own',entity={'id':'B'})


def test_off_does_not_read_object_and_invalid_option():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    a=Poison();assert attach(a) is a
    with pytest.raises(ValueError):attach(a,return_policy='bad')


def test_dense_edges_reverse_no_corner_shortcuts_and_causal_entities():
    g=TraversalGraph('r3')
    for s in [sample(1),sample(2,.2),sample(3,.2,.2),sample(4,.4,.2)]:
        g.observe(s,goal(1))
    g.seal();r=g.route(g.anchor)
    assert r['nodes'][-1]==0 and r['samples'][-1]['frame_id']==1
    assert [p['frame_id'] for p in r['samples']]==[4,3,2,1]
    assert r['length_m']==pytest.approx(.6)
    assert all(p['t']<=n['t'] for n in g.nodes for p in n['patch_sources'])
    with pytest.raises(ValueError):g.observe(sample(5))


def test_recovery_severs_component_no_distance_shortcut():
    g=TraversalGraph('r3');g.observe(sample(1),goal(1));g.observe(sample(2,.31))
    g.observe(sample(3,.32,status='recover_backup'));g.observe(sample(4,.33));g.seal()
    assert g.route(g.anchor) is None and len(g.edges)==1 and len(g.breaks)==1


def test_bad_goal_node_is_isolated_and_future_or_peer_rejected():
    g=TraversalGraph('r3');g.observe(sample(1,status='contact_backup'),goal(1));g.observe(sample(2,.01));g.seal()
    assert g.goal_node==0 and g.route(g.anchor) is None
    for v in (dict(goal(2),source='peer'),goal(3)):
        with pytest.raises(ValueError):TraversalGraph('r3').observe(sample(2),v)


def test_match_uses_past_local_patch_and_propagates_covariance():
    g=TraversalGraph('r3');g.observe(sample(1));g.seal()
    assert g.match(sample(1))['reason']=='query_not_after_node'
    assert g.match(sample(2,2))['reason']=='outside_local_neighborhood'
    s=sample(2);r=g.match(s)
    assert r['status']=='accepted' and r['residual_m']<.05
    np.testing.assert_allclose(r['pose'],[0,0,0],atol=.06)


def test_no_goal_not_manufactured_and_goal_never_blacklisted():
    g=TraversalGraph('r3');g.observe(sample(1));g.seal();p=TraversalReturn(g)
    p.localize(sample(2));assert p.failure=='disconnected_B_route'
    assert p.twist([0,0,0],2)[1]=='disconnected_B_route'
    assert not hasattr(p,'blacklist')


def test_sweep_only_after_match_failure_and_bounded():
    g=TraversalGraph('r3');g.observe(sample(1),goal(1));g.seal();p=TraversalReturn(g)
    assert np.array_equal(p.twist([0,0,0],2)[0],np.zeros(3))
    p.localize(dict(sample(2),segments=[]))
    assert p.twist([0,0,0],3)[0][2]==.5
    assert p.twist([0,0,0],32)[1]=='node_match_failed_after_sweep'


def test_reverse_edge_rotates_then_front_forward():
    g=TraversalGraph('r3');g.observe(sample(1),goal(1));g.observe(sample(2,.31));g.seal()
    p=TraversalReturn(g);p.route=g.route(g.anchor);p.matched_node=g.anchor
    # At final teach node facing +x, reverse route is -x.
    v,status=p.twist(np.array([.31,0,0]),3)
    assert status=='traversal_rotate_forward' and v[0]==v[1]==0 and abs(v[2])==.5
    p.matched_node=0
    v,status=p.twist(np.array([.31,0,np.pi]),4)
    assert v[0]>0 and v[1]==0 and v[2]==0


def test_own_sample_provenance_and_no_gt_keys():
    s=own_sample(dict(t=1,frame_id=2,local_pose=[0,0,0],status='following'),
        dict(segments=[],camera=[0,0]),rgb=np.zeros((48,64,3),np.uint8),frame_sha256='x'*64)
    assert np.shape(s['rgb_summary'])==(12,16) and s['frame_sha256']=='x'*64
    assert all('gt' not in k for k in s)


def test_lattice_forbids_lateral_and_backward_without_changing_off():
    for twist in ([.12,0,0],[-.12,0,0],[0,.12,0],[0,0,.5],[0,0,-.5]):
        args=dict(motion_model='s2_pulse_v122_rotL_v1')
        assert json.dumps(pulse_command(twist,1,**args))==json.dumps(pulse_command(twist,1,translation_policy='off',**args))
        cmd,p=pulse_command(twist,1,translation_policy='forward_only_v1',**args)
        assert cmd.get('left',0)==0 and cmd.get('forward',0)>=0


def test_live_adapter_seals_prefix_and_requires_matched_B_node(monkeypatch):
    from pathlib import Path
    from harness import self_map_closed_loop as legacy
    from harness.self_map_return_repeat import Return360
    from harness.active_camera import SEARCH
    f=json.loads((Path(__file__).parent/'fixtures/own_map_tempering/golden.json').read_text())
    c=attach(Return360(SimpleNamespace(robot_id='r3',started=0.),seed=49001),return_policy=OPTION)
    c.last_snapshot=dict(t=359.8,frame_id=1799,grid=f['grid'],ledger=[dict(t=359.8)])
    c.goal=dict(goal(1),candidate_id='own')
    c.traversal_graph.observe(sample(1),c.goal)
    c.lose(360.,1801);c.stage='return';c.streak=5
    assert c.traversal_graph.sealed and c.pf.n==100000
    monkeypatch.setattr(legacy,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
    monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
    monkeypatch.setattr(c.pf,'step',lambda **kw:dict(pose=[0,0,0],covariance=np.eye(3).tolist(),resolved=True,global_std_xy_m=.1))
    monkeypatch.setattr(legacy,'pulse_command',lambda *a,**kw:(dict(t=a[1],kind='hold'),{}))
    _,r=c.receive(robot_id='r3',t=360.2,frame_id=1802,rgb=np.zeros((2,2,3),np.uint8),servo=SEARCH,
        observation=dict(segments=[],floor_xy=[],camera=[0,0]),frame_sha256='x'*64)
    assert not r['declared_goal'] and r['traversal']['match']['reason']=='insufficient_points'
    assert r['status']=='node_match_sensor_sweep'


def test_evaluation_geometry_continuous_corner_and_footprint():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).parents[1]/'experiments/2026-10-09-own-traversal-return/code/offline.py'
    spec=importlib.util.spec_from_file_location('score51',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    walls=np.array([[0,0,.1,1.]])
    assert m.line_hits([-1,0],[1,0],walls)
    assert not m.line_hits([-1,2],[1,2],walls)
    assert m.footprint_hits([.2,0,0],walls)
    assert not m.footprint_hits([.3,0,0],walls)
    assert m.geometry([[-1,0,0],[1,0,0]],walls)['center_crossing_segments']==1
