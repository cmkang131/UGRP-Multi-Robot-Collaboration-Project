"""Host-only fidelity/capability regressions; no physics or renderer imports."""
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.warp10_host import Readback,device_reads,blend_staged,command_tapes,EvaluationExport,destination_recorder
from scripts.warp5_render import blend_native
from scripts.warp_act_core import control_tape
from scripts.warp9_first30 import summarize


def test_staged_blend_is_exact_in_both_world_orders():
    rng=np.random.default_rng(13)
    opaque=rng.random((4,8,9,3),dtype=np.float32)
    layers=[(rng.random(opaque.shape,dtype=np.float32),rng.random(opaque.shape[:-1])>.7) for _ in range(3)]
    order=np.array([rng.permutation(3) for _ in range(4)]);alpha=[.2,.35,.4]
    expected=blend_native(opaque.astype(float)*255,[(rgb.astype(float)*255,mask) for rgb,mask in layers],alpha,order)
    np.testing.assert_array_equal(blend_staged(opaque,layers,alpha,order),expected)


def test_command_axis_batch_preserves_fractional_accumulator_deadline_and_untouched_controls():
    rng=np.random.default_rng(55);n=4;tables=[];groups=[];relays=[];expected=[]
    lookup=np.tile(np.arange(500,2501),(5,1))*.0001
    kwargs=dict(dt=.00025,steps=400,start_fraction=.325,kinetic_fraction=1/12,torque_cap_nm=1.4)
    for rid in range(3):
        wheels=list(range(rid*10,rid*10+4));servos=[[rid*10+4,rid*10+5]]+[[rid*10+6+k] for k in range(4)]
        tables.append((lookup,wheels,servos));rows=[]
        for i in range(n):
            rows.append(dict(ctrl=rng.random(31),wheels=rng.uniform(-1,1,4),deadlines=[2.0005,0,2.00075,0],
                applied=1500+rng.random(5),target=rng.integers(1490,1540,5),servo_active=[True,False,True,True,True],
                now=2.,servo_time=2.))
        relay=np.zeros((n,4),int);groups.append(rows);relays.append(relay)
        expected.append(control_tape(rows,relay,lookup=lookup,wheel_ids=wheels,servo_ids=servos,**kwargs))
    actual=command_tapes(groups,relays,tables,**kwargs)
    for (tape,state),(reference,refstate) in zip(actual,expected):
        np.testing.assert_array_equal(tape,reference)
        for key in state:np.testing.assert_array_equal(state[key],refstate[key])


class Array:
    dtype='f4'
    def __init__(self,shape):self.shape=shape;self.capacity=int(np.prod(shape))*4;self.value=np.zeros(shape)
    def numpy(self):return self.value


def test_pinned_group_waits_once_before_host_views_and_reuses_slots():
    calls=[];pending=[]
    def copy(dst,src):pending.append((dst,src));calls.append('enqueue')
    def wait(event):
        calls.append('wait')
        for dst,src in pending:dst.value[:]=src.value
        pending.clear()
    def empty(shape,**kw):
        assert kw==dict(dtype='f4',device='cpu',pinned=True)
        calls.append('allocate');return Array(shape)
    wp=SimpleNamespace(empty=empty,copy=copy,Event=object,record_event=lambda e:None,synchronize_event=wait)
    staging=Readback(wp,object(),'test');arrays=[Array((2,3)),Array((2,5))]
    for tick in range(2):
        for key,array in enumerate(arrays):array.value[:]=tick+4;staging.enqueue(key,array)
        result=staging.finish()
        assert all(np.all(value==tick+4) for value in result.values())
    assert calls.count('wait')==2 and calls.count('allocate')==2
    assert staging.syncs==2


def native_export(result,model,d,world_id=0):
    result['one']=d.qpos.numpy()[world_id]
    result['two']=d.qpos.numpy()[world_id]
    result['three']=d.contact.force.numpy()[world_id]


def test_evaluator_manifest_is_deduplicated_and_separate_from_actor_fields():
    paths,_=device_reads(native_export)
    assert paths==[('contact','force'),('qpos',)]


def test_evaluation_reads_each_array_once_for_all_worlds_and_refreshes_next_tick():
    transfers=[]
    def copy(dst,src):transfers.append(src);dst.value[:]=src.value
    wp=SimpleNamespace(empty=lambda shape,**kw:Array(shape),copy=copy,Event=object,
        record_event=lambda e:None,synchronize_event=lambda e:None)
    d=SimpleNamespace(qpos=Array((4,3)),contact=SimpleNamespace(force=Array((4,2))))
    owner=SimpleNamespace(wp=wp,wd=d,mjw=SimpleNamespace(get_data_into=native_export))
    e=EvaluationExport(owner)
    for tick in range(2):
        d.qpos.value[:]=tick+5;e.stage()
        for world in range(4):
            result={};e.export(result,None,d,world)
            assert np.all(result['one']==tick+5)
            np.testing.assert_array_equal(result['one'],result['two'])
    assert len(transfers)==4  # two arrays x two ticks, independent of world count
    assert e.audit()['actor_reads']==0


def conditional_export(result,model,d,world_id=0):
    result.qpos[:]=d.qpos.numpy()[world_id]
    if model.discrete:result.efm_c[:]=d.efm_c.numpy()[world_id]


def test_audit_records_executed_export_destinations_not_unused_copy_workspace():
    writes=set();fn=destination_recorder(conditional_export,writes.add)
    d=SimpleNamespace(qpos=Array((1,3)),efm_c=Array((1,3)))
    result=SimpleNamespace(qpos=np.zeros(3),efm_c=np.ones(3)*999)
    fn(result,SimpleNamespace(discrete=False),d)
    assert writes=={('qpos',)} and np.all(result.efm_c==999)
    fn(result,SimpleNamespace(discrete=True),d)
    assert writes=={('qpos',),('efm_c',)}


def test_reference_audit_uses_independent_cached_numpy_for_all_worlds():
    d=SimpleNamespace(qpos=Array((4,3)),efm_c=Array((4,3)))
    cache={};reads=[]
    def read(array):
        if id(array) not in cache:reads.append(array);cache[id(array)]=array.numpy()
        return cache[id(array)]
    fn=destination_recorder(conditional_export,lambda p:None,read)
    for world in range(4):fn(SimpleNamespace(qpos=np.zeros(3)),SimpleNamespace(discrete=False),d,world)
    assert reads==[d.qpos]


def test_per_execution_gate_does_not_drop_batch_measurement():
    samples=[dict(sim_s=i,delta_sim_s=1,wall_s=83.) for i in range(1,31)]
    result=summarize(samples,shared_load=False,nworld=16,per_execution=True)
    assert result['status']=='PASS' and result['warning']
    assert result['median_wall_per_sim']==83/16
    assert result['batch_median_wall_per_sim']==83
    assert summarize(samples,shared_load=False,nworld=16)['status']=='SPEED_GATE_FAIL'
    with pytest.raises(ValueError):summarize(samples,shared_load=False,nworld=0,per_execution=True)
