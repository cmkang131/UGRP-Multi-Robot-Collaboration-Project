import copy,json,math
from types import SimpleNamespace
import numpy as np
import pytest
from harness.own_teach_capture import TeachGraph,TeachReturn,attach,OPTION,vertex_decision
from harness.self_map_return_repeat import Return360
from harness import self_map_closed_loop as legacy
from harness.active_camera import SEARCH
from test_own_traversal_graph import sample


def observed(i):return dict(id=1,first_t=float(i),state='visually_seen')
def confirmed(i,t):return dict(source='own',candidate_id=1,first_t=float(i),t_sim=float(t),center_m=[0.,0.],entity={'id':'B'})


def test_vtr_yaml_geometry_thresholds_and_se2_log():
    assert vertex_decision([.29,0,0])=='candidate'
    assert vertex_decision([.31,0,0])=='vertex'
    assert vertex_decision([0,0,math.radians(3.01)])=='vertex'
    assert vertex_decision([0,0,math.radians(2.99)])=='candidate'
    assert vertex_decision([2.01,0,0])=='uncertain_jump'
    assert vertex_decision([0,0,math.radians(20.01)])=='uncertain_jump'


def test_recovery_continuous_dense_route_uncertain_and_B_first_pin():
    g=TeachGraph('r3');g.observe(sample(1),candidates=[observed(1)])
    g.observe(sample(2,.1,status='recover_backup'),candidates=[observed(1)])
    g.observe(sample(3,.32),confirmed(1,3),[observed(1)])
    g.observe(sample(4,.34,yaw=math.radians(4)));g.seal()
    assert g.goal_node==0 and g.nodes[0]['t']==1
    assert [r['frame_id'] for r in g.route(g.anchor)['samples']]==[4,3,2,1]
    assert len(g.edges)==2 and g.edges[0]['uncertain'] and not g.edges[1]['uncertain']
    assert g.nodes[1]['patch_sources'][0]['frame_id']==1
    assert g.nodes[0]['rgb_ref']['sha256']==sample(1)['frame_sha256']
    assert all(q['t']<=n['t'] for n in g.nodes for q in n['patch_sources'])


def test_motion_failure_promotes_candidate_and_retains_uncertain_edge():
    g=TeachGraph('r3');g.observe(sample(1));g.observe(sample(2,.1));g.observe(sample(3,3.))
    assert [n['frame_id'] for n in g.nodes]==[1,2,3]
    assert not g.edges[0]['uncertain'] and g.edges[1]['uncertain']
    assert g.edges[1]['uncertainty_reasons']==['vtr_motion_discontinuity']
    assert [p['frame_id'] for e in g.edges for p in e['samples']]==[1,2,2,3]


def test_prefix_future_peer_goal_and_missing_first_image_rejected():
    g=TeachGraph('r3');g.observe(sample(1),candidates=[observed(1)]);g.seal()
    with pytest.raises(ValueError):g.observe(sample(2))
    for goal in (dict(confirmed(1,1),source='peer'),confirmed(1,2)):
        with pytest.raises(ValueError):TeachGraph('r3').observe(sample(1),goal,[observed(1)])
    with pytest.raises(ValueError,match='FIRST_B_FRAME'):TeachGraph('r3').observe(sample(2),candidates=[observed(1)])


def test_repeat_failed_localization_zero_then_resumes_no_sweep(monkeypatch):
    g=TeachGraph('r3');g.observe(sample(1),confirmed(1,1),[observed(1)]);g.observe(sample(2,.31));g.seal()
    p=TeachReturn(g)
    monkeypatch.setattr(g,'match',lambda *a:dict(status='rejected',reason='unobservable',node=1))
    p.localize(sample(3,.31));v,status=p.twist([.31,0,0],3)
    assert not np.any(v) and status=='teach_localization_wait' and p.sweep_start is None
    p.localize(sample(4,.31));assert not np.any(p.twist([.31,0,0],4)[0])
    monkeypatch.setattr(g,'match',lambda *a:dict(status='accepted',reason='accepted',node=1))
    p.localize(sample(5,.31));assert p.route is not None and not p.blocked and p.failure is None
    assert p.twist([.31,0,math.pi],5)[1]!='teach_localization_wait'


def test_default_off_no_reads_and_unknown_rejected():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    p=Poison();assert attach(p) is p
    with pytest.raises(ValueError):attach(p,teach_capture='bad')


def test_capture_does_not_change_explore_commands_trace_or_rng(monkeypatch):
    monkeypatch.setattr(legacy,'own_measurement',lambda *a:dict(points=[],columns=[],uv=[]))
    class Grid:
        def __init__(self):
            self.odom=SimpleNamespace(pose=[0,0,0],covariance=np.eye(3));self.revision=0;self.best=0;self.resamples=0;self.ledger=[]
        def export(self):return dict(resolution_m=.1,cells=[])
    class Explorer:
        robot_id='r3';started=0.
        def __init__(self):self.memory=SimpleNamespace(self_map=Grid());self.navigator=SimpleNamespace(events=[])
        def receive(self,**kw):
            i=kw['frame_id'];g=self.memory.self_map;g.odom.pose=[i*.11,0,i*.07];g.revision=i
            cmd=dict(t=kw['t'],kind='hold')
            trace=dict(t=kw['t'],frame_id=i,pose=g.odom.pose,local_pose=g.odom.pose,status='recover_backup' if i==3 else 'following',
                goal=dict(robot_id='r3',coordinate_frame='r3/own_odom',candidates=[]))
            return cmd,trace
    records=[]
    for option in ('off',OPTION):
        c=attach(Return360(Explorer(),seed=49001),teach_capture=option)
        monkeypatch.setattr(c.sensor,'measure',lambda *a:[])
        result=[]
        for i in range(1,8):
            cmd,trace=c.receive(robot_id='r3',t=float(i),frame_id=i,rgb=np.zeros((48,64,3),np.uint8),servo=SEARCH,
                observation=dict(segments=sample(i)['segments'],camera=[0,0]),frame_sha256='a'*64)
            trace.pop('teach',None);result.append(dict(command=cmd,trace=trace))
        records.append(json.dumps(dict(result=result,inputs=c.inputs,events=c.events),sort_keys=True,default=lambda x:x.tolist()).encode())
    assert records[0]==records[1]


def test_registered_driver_bundle_and_workflow():
    from scripts.run_teach_capture import bundle,SEEDS
    from sim.workflow_manager import plan
    from pathlib import Path
    for s in SEEDS:
        b=bundle(s,'a'*40);assert b['options']['teach_capture']==OPTION and b['case_cap_s']==630.
        assert b['options']['wall_texture']=='tape_v1' and b['options']['camera_pose']=='SEARCH'
    p=plan(Path(__file__).parents[1],'own-teach-capture',['--seed','49001','--output','/tmp/no-physics','--expected-source-sha','a'*40])
    assert 'scripts.run_teach_capture' in p['command']
