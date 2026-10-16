"""Pair scheduling/actuator isolation counterexamples; no simulator imports."""
import ast
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import numpy as np
import pytest
from scripts.warp_act_core import control_tape, multi_control_tape, contact_maps, exact_model_groups
from scripts.warp_flow_episode import Lane, compile_function, ADAPTER_SHA, TEACHER_SHA


def test_two_robot_tapes_preserve_each_fractional_servo_and_deadline():
    def rows(sign, end):
        return [dict(ctrl=np.zeros(20), wheels=[sign*.35]*4, deadlines=[end,0,0,0],
            applied=[1500.]*5, target=[1502.,1500.,1500.,1500.,1500.],
            servo_active=[True,False,False,False,False], now=2., servo_time=2.) for _ in range(2)]
    lookup = np.tile(np.arange(500,2501), (5,1))
    bindings = {rid: dict(lookup=lookup, wheel_ids=list(range(off,off+4)),
        servo_ids=[[j] for j in range(off+4,off+9)]) for rid,off in (('r1',0),('r2',10))}
    clock = dict(dt=.00025, steps=8, start_fraction=.325, kinetic_fraction=1/12, torque_cap_nm=1.)
    values = {'r1': rows(1,2.001), 'r2': rows(-1,2.0015)}
    states = {r: np.zeros((2,4),int) for r in values}
    tape, final = multi_control_tape(values, states, bindings, **clock)
    for rid,b in bindings.items():
        expected, state = control_tape(values[rid], states[rid], **b, **clock)
        columns = b['wheel_ids']+[j for ids in b['servo_ids'] for j in ids]
        assert np.array_equal(tape[:,:,columns], expected[:,:,columns])
        assert np.array_equal(final[rid]['relay'], state['relay'])
    assert tape[4,0,0] == 0 and tape[4,0,10] < 0
    with pytest.raises(ValueError,match='disjoint'):
        multi_control_tape(values, states, {'r1':bindings['r1'],'r2':bindings['r1']}, **clock)


def test_contact_membership_is_world_specific_and_accepts_multi_geom_beam():
    targets, fingers = contact_maps(10, [[0,1],[2,3]], [{4:0,5:1,6:2,7:3},{4:0,5:1,6:2,7:3}])
    assert targets[0,0] == 1 and targets[1,0] == 0
    assert targets[1,2] == 1 and targets[0,2] == 0
    assert fingers[:,6].tolist() == [2,2] and fingers[:,0].tolist() == [-1,-1]
    with pytest.raises(ValueError,match='distinct'):contact_maps(10,[[0]],[{0:0}])


def test_exact_model_partition_preserves_world_order_without_merging_variants():
    assert exact_model_groups(['a','b','a','c','b']) == [('a',[0,2]),('b',[1,4]),('c',[3])]
    groups=exact_model_groups([str(i%6) for i in range(16)])
    assert [len(ids) for _,ids in groups]==[3,3,3,3,2,2]
    assert sorted(i for _,ids in groups for i in ids)==list(range(16))


def test_group_router_enqueues_every_model_before_readback_and_routes_own_world(monkeypatch,tmp_path):
    from contextlib import nullcontext
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    from warp_act_backend import ExactModelGroups
    events=[]
    class Fake:
        wp=SimpleNamespace(ScopedStream=lambda stream:nullcontext())
        def __init__(self,name):self.name=name
        def prepare_step(self,contexts,active):events.append((self.name,'prepare',active.tolist()))
        def launch_step(self):events.append((self.name,'launch'))
        def finish_step(self,contexts):events.append((self.name,'finish'))
        def capture(self,index,world,robot):return (self.name,index,robot)
        def forces(self,index,*a):return (self.name,index)
    a,b=Fake('a'),Fake('b')
    router=ExactModelGroups({},'sha','mjwarp_batch_v1',tmp_path)
    router.groups=[(a,[],np.array([0,2]),None),(b,[],np.array([1]),None)]
    router.routes={0:(a,0),2:(a,1),1:(b,0)}
    router.step([],np.array([True,True,False]))
    assert events==[('a','prepare',[True,False]),('a','launch'),('b','prepare',[True]),('b','launch'),('a','finish'),('b','finish')]
    assert router.capture(2,None,'r2')==('a',1,'r2')
    assert router.forces(1,None,None,None,None)==('b',0)


def test_lane_globals_and_dynamic_imports_do_not_cross_worlds():
    original = sys.modules.get('harness')
    parent = ModuleType('harness'); parent.token = 'parent'
    sys.modules['harness'] = parent
    def factory(token):
        def build():
            module = ModuleType('harness');module.token=token
            sys.modules['harness']=module
            def gen():
                yield sys.modules['harness'].token
                sys.modules['harness'].token += '-updated'
                yield sys.modules['harness'].token
            return gen()
        return build
    a,b=Lane(factory('a'),Path('/a')),Lane(factory('b'),Path('/b'))
    try:
        assert next(a)=='a' and sys.modules['harness'] is parent
        assert next(b)=='b' and sys.modules['harness'] is parent
        assert next(a)=='a-updated' and next(b)=='b-updated'
        a.close();b.close();assert sys.modules['harness'] is parent
    finally:
        if original is None:sys.modules.pop('harness',None)
        else:sys.modules['harness']=original


def test_only_expected_frozen_scheduling_shapes_are_compiled():
    root=Path(__file__).resolve().parents[1]
    for sha,path,runner in [(ADAPTER_SHA,'scripts/run_beampair1.py',False),
                            (TEACHER_SHA,'scripts/run_grasp_act_teacher.py',True)]:
        source=subprocess.check_output(['git','show',sha+':'+path],cwd=root,text=True)
        function,audit=compile_function(source,'run',{},runner=runner)
        assert function.__code__.co_flags & 0x20  # generator; creation imports no simulator
        assert len(audit['source_sha256'])==64
    with pytest.raises(ValueError,match='shape changed'):
        compile_function('def run():\n    return 1\n','run',{},runner=True)


def test_barrier_preserves_return_and_target_order_without_native_advance():
    source='''def run(world, ports, scene):
    def advance(target):
        raise AssertionError('native advance executed')
    advance(1.)
    advance(2.)
    return {'done': True}
'''
    class Bridge:
        def advance(self,world,ports,scene,target):
            yield target
    function,_=compile_function(source,'run',{'__warp2_bridge__':Bridge()},runner=True)
    gen=function(None,None,None)
    assert next(gen)==1. and next(gen)==2.
    with pytest.raises(StopIteration) as done:next(gen)
    assert done.value.value=={'done':True}


def test_mac_and_default_off_deny_before_source_metadata_or_output(monkeypatch,tmp_path):
    from scripts import run_warp_flow_teacher as runner
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    for backend in ('off','mjwarp_batch_v1'):
        monkeypatch.setattr(sys,'argv',['runner','--physics-backend',backend,
            '--adapter-source',str(tmp_path),'--teacher-source',str(tmp_path),
            '--plan',str(tmp_path/'missing.json'),'--out',str(tmp_path/'out'),
            '--vm-hourly-usd','1.096'])
        with pytest.raises(SystemExit,match='2'):runner.main()
        assert not (tmp_path/'out').exists()
