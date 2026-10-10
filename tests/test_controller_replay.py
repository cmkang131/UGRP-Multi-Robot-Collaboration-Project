import pytest
from scripts.profile_controller_replay import Timers


def test_private_binding_timings_reach_copied_pure_globals(monkeypatch):
    import sys
    from types import ModuleType
    from harness.zone_final_pair_binding import bind
    module=ModuleType('harness._binding_timing_test')
    exec('def helper(x): return x+1\ndef calculate(x): return helper(x)*2',module.__dict__)
    module.bind=bind
    monkeypatch.setitem(sys.modules,module.__name__,module)
    original=module.helper
    # A pre-bound dependency retains the original pure helper in private globals.
    private=bind(module.calculate)
    timer=Timers()
    timer.aliases(original,'pf_update')
    timer.track_bindings()
    try:
        measured=module.bind(private)
        assert measured(4)==private(4)==10
        assert timer.total['pf_update']['calls']==1
        assert private.__globals__['helper'] is original
    finally:
        # track_bindings is process-scoped in the replay CLI; restore test peers.
        wrapped_bind=module.bind
        for name,owner in list(sys.modules.items()):
            if name.startswith(('harness.','scripts.')):
                for attr,value in list(vars(owner).items()):
                    if value is wrapped_bind:setattr(owner,attr,bind)


def test_nested_timers_are_a_partition_including_exception():
    times = iter([0., 1., 3., 5.])
    timers = Timers(clock=lambda: next(times))
    with pytest.raises(ValueError), timers.span('outer'):
        with timers.span('inner'):
            raise ValueError('stop')
    assert timers.total['outer'] == dict(calls=1, exclusive_s=3., inclusive_s=5.)
    assert timers.total['inner'] == dict(calls=1, exclusive_s=2., inclusive_s=2.)
    assert timers.stack == []


def test_rgb_child_timing_survives_snapshot_and_preserves_partition():
    times=iter([0.,1.,3.,5.])
    timers=Timers(clock=lambda:next(times))
    with timers.span('vision'):
        with timers.span('rgb_preprocess'):pass
    snapshot=timers.snapshot()
    assert snapshot['rgb_preprocess']['exclusive_s']==2.
    assert sum(row['exclusive_s'] for row in snapshot.values())==5.


def test_adapter_fingerprint_rejects_edit_add_and_remove(tmp_path):
    from scripts.profile_controller_replay import verify_adapter
    source=tmp_path/'harness/matcher.py';source.parent.mkdir()
    source.write_text('answer=1\n')
    original=verify_adapter(tmp_path)
    assert original['files']=={'harness/matcher.py':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}
    source.write_text('answer=2\n')
    with pytest.raises(ValueError,match='SOURCE_ADAPTER_CHANGED'):verify_adapter(tmp_path,original['sha256'])
    source.write_text('answer=1\n')
    extra=tmp_path/'dependency.py';extra.write_text('answer=3\n')
    with pytest.raises(ValueError,match='SOURCE_ADAPTER_CHANGED'):verify_adapter(tmp_path,original['sha256'])
    extra.unlink();assert verify_adapter(tmp_path,original['sha256'])==original
    source.unlink()
    with pytest.raises(ValueError,match='EMPTY_SOURCE_ADAPTER'):verify_adapter(tmp_path,original['sha256'])


def test_managed_catalog_plans_without_execution(tmp_path):
    from pathlib import Path
    from sim.workflow_manager import plan
    root = Path(__file__).resolve().parents[1]
    result = plan(root, 'controller-replay-profile', ['--kind', 'egomap', '--raw', str(tmp_path),
        '--adapter', str(tmp_path), '--output', str(tmp_path / 'new'), '--expected-source-sha', 'a' * 40])
    assert result['execution_started'] is False
    assert not (tmp_path / 'new').exists()
    result = plan(root, 'saved-physics-profile', ['--kind', 's3', '--raw', str(tmp_path),
        '--adapter', str(tmp_path), '--output', str(tmp_path / 'native'), '--expected-source-sha', 'a' * 40])
    assert result['execution_started'] is False
    assert not (tmp_path / 'native').exists()


def test_atomic_slot_wait_handles_status_to_acquire_race(monkeypatch):
    from scripts import profile_controller_replay as replay, agent_lock
    calls=[]
    def acquire(*args, **kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise RuntimeError('lock held: another task')
        return {'pid':kwargs['pid']}
    monkeypatch.setattr(agent_lock,'acquire',acquire)
    monkeypatch.setattr(replay,'source_check',lambda expected:None)
    monkeypatch.setattr(replay.time,'sleep',lambda seconds:None)
    monkeypatch.setattr(replay.subprocess,'check_output',lambda *a,**k:'codex/sim-speed-ctrl2\n')
    held,owned=replay.acquire_slot('a'*40,'test')
    assert owned and held['pid']==replay.os.getpid() and len(calls)==2


def test_borrowed_lock_requires_our_live_ancestor(monkeypatch):
    from scripts import profile_controller_replay as replay, agent_lock
    held=dict(pid=123,pid_alive=True,owner='codex',branch='codex/sim-speed-ctrl',timing_sensitive=True)
    monkeypatch.setattr(agent_lock,'status',lambda root:held)
    monkeypatch.setattr(replay,'source_check',lambda expected:None)
    monkeypatch.setattr(replay.subprocess,'check_output',lambda *a,**k:'codex/sim-speed-ctrl\n')
    monkeypatch.setattr(replay,'ancestor',lambda pid,parent:False)
    with pytest.raises(AssertionError):replay.acquire_slot('a'*40,'test',lock_owner_pid=123)
    monkeypatch.setattr(replay,'ancestor',lambda pid,parent:True)
    assert replay.acquire_slot('a'*40,'test',lock_owner_pid=123)==(held,False)


def test_lossless_stream_unicode_determinism_and_direct_decoded_bytes(tmp_path):
    from harness.lossless_recording import RecordStream, logical_equal, logical_open
    a,b,c=(tmp_path/x/'record.jsonl' for x in ('a','b','c'))
    receipts=[]
    lines=('{"name":"운반","value":-0.0}\n','{"cells":[[1,2,0.3]]}\n')*200
    for path,storage in ((a,'off'),(b,'gzip-v1'),(c,'gzip-v1')):
        stream=RecordStream(path,storage=storage)
        for line in lines:
            stream.write(line)
        assert stream.tell()==sum(len(line.encode('utf-8')) for line in lines)
        stream.close();receipts.append(stream.receipt())
    assert logical_equal(a,b) and logical_equal(b,c)
    assert b.with_name(b.name+'.gz').read_bytes()==c.with_name(c.name+'.gz').read_bytes()
    assert receipts[0]['logical_sha256']==receipts[1]['logical_sha256']
    assert receipts[1]['stored_bytes'] < receipts[1]['logical_bytes']
    with pytest.raises(FileExistsError):RecordStream(a)
    b.write_bytes(b'conflict')
    with pytest.raises(ValueError,match='ambiguous'):logical_open(b)


def test_abba_rejects_load_confounding_and_checks_both_crossovers(tmp_path):
    import json
    from scripts.benchmark_controller_replay import load_assessment
    paths=[tmp_path/str(i) for i in range(4)]
    for path,load in zip(paths,(4.8,2.9,2.9,4.8)):
        path.mkdir();(path/'trend.json').write_text(json.dumps([{'loadavg':[load,load,load]}]))
    assert not load_assessment(paths)['comparable']
    for path,load in zip(paths,(2.8,2.9,3.,2.9)):
        (path/'trend.json').write_text(json.dumps([{'loadavg':[load,load,load]}]))
    assert load_assessment(paths)['comparable']
    for path,load in zip(paths,(2.,5.,2.,5.)):
        (path/'trend.json').write_text(json.dumps([{'loadavg':[load,load,load]}]))
    assert not load_assessment(paths)['comparable']  # aggregate equality alone is insufficient


def test_abba_direct_proof_rejects_corrupted_behavior_or_missing_callback(tmp_path):
    import json
    from harness.lossless_recording import RecordStream
    from scripts.benchmark_controller_replay import S3_FILES, compare_runs
    paths=[tmp_path/str(i) for i in range(4)]
    for i,path in enumerate(paths):
        path.mkdir()
        (path/'result.json').write_text(json.dumps(dict(input_sha256={'frame':'a'},failure=None,
            frames=2,available_frames=2,adapter_sha256='source1')))
        for name in S3_FILES:
            stream=RecordStream(path/name,storage='gzip-v1' if i in (1,2) else 'off')
            stream.write('{"rng":"state","particles":"bits"}\n');stream.close()
    assert compare_runs(paths,'s3')['verified']
    metadata=json.loads((paths[3]/'result.json').read_text())
    metadata['adapter_sha256']='source2';(paths[3]/'result.json').write_text(json.dumps(metadata))
    assert not compare_runs(paths,'s3')['verified']
    metadata['adapter_sha256']='source1';(paths[3]/'result.json').write_text(json.dumps(metadata))
    (paths[3]/'state.json').write_text('{"rng":"different"}\n')
    assert not compare_runs(paths,'s3')['verified']


def test_abba_requires_current_s3_final_result_and_explicit_return(tmp_path):
    import json
    from scripts.benchmark_controller_replay import priority_check, sha
    result=tmp_path/'result.json';result.write_text('{"status":"DEV_NOT_DELIVERED"}\n')
    receipt=tmp_path/'receipt.json'
    data=dict(result_path=str(result),result_sha256=sha(result),released_for_speedctrl=False,
              coordination_url='https://github.com/example/repo/pull/1#issuecomment-2')
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='EXPLICIT_S3'):priority_check(receipt,tmp_path)
    data['released_for_speedctrl']=True;receipt.write_text(json.dumps(data))
    assert priority_check(receipt,tmp_path)==data
    with pytest.raises(ValueError,match='CURRENT_S3'):priority_check(receipt,tmp_path/'old')
    result.write_text('{}')
    with pytest.raises(ValueError,match='HASH'):priority_check(receipt,tmp_path)
    for invalid in ({'status':'RUNNING'},{},{'status':'arbitrary'}):
        result.write_text(json.dumps(invalid));data['result_sha256']=sha(result)
        receipt.write_text(json.dumps(data))
        with pytest.raises(ValueError,match='TERMINAL_S3'):priority_check(receipt,tmp_path)


def test_local_accuracy_uses_saved_spawn_frame_only_after_replay(tmp_path):
    import json
    from scripts.benchmark_controller_replay import trajectory_accuracy
    raw=tmp_path/'raw';out=tmp_path/'out'
    (raw/'eval_only').mkdir(parents=True);out.mkdir()
    (raw/'eval_only/setup.json').write_text(json.dumps({'spawns':{'r3':[3.,2.,0.,0.]}}))
    truth=dict(t=1.,robot_xyz_m=[4.,2.,0.],robot_yaw_rad=.1)
    (raw/'eval_only/trajectory.jsonl').write_text(json.dumps(truth)+'\n')
    from scripts.benchmark_controller_replay import sha
    (raw/'artifacts.sha256.json').write_text(json.dumps({str(p.relative_to(raw)):sha(p) for p in (raw/'eval_only/setup.json',raw/'eval_only/trajectory.jsonl')}))
    (out/'frontend-poses.json').write_text(json.dumps([dict(t=1.,pose=[1.,0.,.1])]))
    r=trajectory_accuracy(out,raw)
    assert r['xy_rmse_m']==r['yaw_rmse_rad']==0. and r['samples']==1
    (out/'frontend-poses.json').write_text(json.dumps([dict(t=2.,pose=[1.,0.,.1])]))
    with pytest.raises(ValueError,match='TIMESTAMP_MISSING'):trajectory_accuracy(out,raw)
    (raw/'eval_only/setup.json').write_text('{}')
    with pytest.raises(ValueError,match='EVAL_INPUT_HASH'):trajectory_accuracy(out,raw)


def test_online_map_accuracy_uses_held_graph_transform_only_after_its_stamp(tmp_path):
    import json
    from scripts.benchmark_controller_replay import estimated_trajectory
    poses=[dict(t=t,pose=[1.,0.,0.]) for t in (1.,2.,3.)]
    (tmp_path/'frontend-poses.json').write_text(json.dumps(poses))
    graphs=[dict(t=2.,map_to_odom=[2.,1.,0.])]
    (tmp_path/'graphs.json').write_text(json.dumps(graphs))
    assert [r['pose'] for r in estimated_trajectory(tmp_path,frame='online_map')]==[[1.,0.,0.],[3.,1.,0.],[3.,1.,0.]]
    assert estimated_trajectory(tmp_path)==poses


def test_native_selection_preserves_first_arm_commands_and_finite_window(tmp_path):
    import json
    from scripts.profile_saved_physics import selection
    path=tmp_path/'robots/r3';path.mkdir(parents=True)
    frames=[dict(sim_time=t) for t in (1.3,1.5,1.7,1.9)]
    (path/'frames.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in frames))
    commands=[dict(kind='initial_servo_command',t=0.),dict(kind='arm',t=1.3,servo_id=3,pulse=777),
              dict(kind='hold',t=1.7),dict(kind='drive',t=1.9)]
    (path/'commands.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in commands))
    robots,reference,times,schedule=selection(tmp_path,'egomap',.4)
    assert robots==('r3',) and times==[1.3,1.5,1.7]
    assert schedule=={1.3:[('r3',dict(kind='arm',servo_id=3,pulse=777))],1.7:[('r3',dict(kind='hold'))]}


def test_numpy_graph_evidence_serializes_without_losing_numeric_values(tmp_path):
    import json
    import numpy as np
    from scripts.profile_controller_replay import write
    write(tmp_path / 'evidence.json', {'covariance': np.eye(3), 'node': np.int64(2)})
    assert json.loads((tmp_path / 'evidence.json').read_text()) == {
        'covariance': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], 'node': 2}
    with pytest.raises(ValueError):
        write(tmp_path / 'invalid.json', {'covariance': np.array([np.nan])})
    write(tmp_path / 'unicode.json', {'label':'운반'}, ensure_ascii=False)
    assert '운반' in (tmp_path / 'unicode.json').read_text()


def test_profile_windows_toggle_only_at_boundaries():
    import cProfile
    timer = Timers()
    timer.profiler = cProfile.Profile()
    timer.profile_window = 2
    timer.profiler.enable()
    timer.profile_active = True
    try:
        for index in range(10):
            timer.profile_frame(index, 10)
            assert timer.profile_active == (index < 2 or index >= 8)
    finally:
        timer.profiler.disable()


def test_timing_split_preserves_state_and_original_measurements():
    from scripts.profile_controller_replay import split_timing
    original={'provider':{'pose':[1.,2.], 'inference_wall_ms':{'p50':19.}},
              'other':[{'inference_wall_ms':{'p99':40.}, 'particles':[3.,4.]}]}
    result, timing=split_timing(original)
    assert result=={'provider':{'pose':[1.,2.]},'other':[{'particles':[3.,4.]}]}
    assert timing=={'/provider/inference_wall_ms':{'p50':19.},
                    '/other/0/inference_wall_ms':{'p99':40.}}
    assert original['provider']['inference_wall_ms']=={'p50':19.}


def test_s3_timer_surface_exists_without_starting_a_simulation(monkeypatch):
    from scripts.profile_controller_replay import attach_timers
    timer=Timers()
    seen=[]
    monkeypatch.setattr(timer,'aliases',lambda function,category:seen.append((function,category)))
    monkeypatch.setattr(timer,'method',lambda cls,name,category:seen.append((getattr(cls,name),category)))
    attach_timers(timer,'s3')
    assert all(callable(function) for function,category in seen)
    assert {'vision','pf_update','posterior_summary'} <= {category for function,category in seen}


def test_egomap_records_observation_before_remembering_issued_command(tmp_path, monkeypatch):
    import importlib
    import json
    import sys
    from types import SimpleNamespace as S, ModuleType
    import numpy as np
    from scripts import profile_controller_replay as replay
    raw, out = tmp_path / 'raw', tmp_path / 'out'
    (raw / 'robots/r3').mkdir(parents=True)
    out.mkdir()
    frames = [dict(sim_time=1.3 + i*.2, frame_id=i, sha256='frame') for i in range(11)]
    (raw / 'robots/r3/frames.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in frames))
    (raw / 'robots/r3/commands.jsonl').write_text(json.dumps({'kind':'initial'})+'\n'+
        json.dumps({'t':frames[-1]['sim_time'], 'kind':'hold'})+'\n')
    (raw / 'bundle.json').write_text(json.dumps({'task':{'seed':1}}))
    (raw / 'own-inputs.json').write_text(json.dumps([{'frame_id':10, 'own_range':None}]))
    (raw / 'own-controller.jsonl').write_text(json.dumps({'frame_id':10})+'\n')
    grid = S(odom=S(pose=(0.,0.,0.),covariance=np.eye(3)), maps=[S(cells={})],
             poses=np.zeros((1,3)),weights=np.ones(1),pending_cov=np.zeros((3,3)),
             rng=np.random.default_rng(1),revision=0,best=0,resamples=0,ledger=[],decisions=[],
             _observe=lambda *a:None,export=lambda: {})
    class Memory:
        self_map = grid
        def finalize_pose_graph(self): pass
    explorer = S(memory=Memory(),graphs=[],poses=[],events=[],navigator=S(events=[]))
    class Controller:
        inputs=[];events=[];heading_host=S(rows=[]);navigator=S(events=[])
        def receive(self, **kwargs): return {'kind':'hold'}, {'pose':list(grid.odom.pose)}
        def command(self, row):
            grid.odom.pose=(1.,0.,0.);grid.ledger.append('issued');grid.revision+=1
        def snapshot(self): return {}
    fake_modules = {
        'harness.active_camera':dict(SEARCH={}),
        'harness.active_wall_vision':dict(observe=lambda *a,**k:{}),
        'scripts.run_own_map_return_repeat':dict(actor=lambda *a,**k:explorer),
        'scripts.run_goal_route_continuous':dict(base=S(install_profile=lambda *a,**k:None),
                                               controller=lambda e:Controller())}
    for name, attributes in fake_modules.items():
        module=ModuleType(name);vars(module).update(attributes)
        monkeypatch.setitem(sys.modules,name,module)
        parent, _, leaf=name.rpartition('.')
        monkeypatch.setattr(importlib.import_module(parent),leaf,module,raising=False)
    monkeypatch.setattr(replay,'frame',lambda raw,row:(row,np.zeros((1,1,3),np.uint8)))
    result=replay.egomap(raw,out,Timers())
    assert result['frames']==result['available_frames']==11
    assert json.loads((out/'online-maps.jsonl').read_text())['ledger']==[]
    assert json.loads((out/'frontend-covariances.jsonl').read_text())['pose']==[0.,0.,0.]
    assert json.loads((out/'frontend-ledger.json').read_text())==['issued']


def test_host_budget_replay_uses_completed_inputs_without_fabricating_range():
    from scripts.profile_controller_replay import recorded_control_prefix
    frames = [dict(frame_id=i, sim_time=i*.2, sha256=str(i)) for i in range(13)]
    inputs = [dict(frame_id=i, own_range={'valid':False}) for i in (10,11)]
    original = dict(status='HOST_ERROR', failure=dict(type='TimeoutError', message='HOST_BUDGET_60_MINUTES'))
    selected, audit = recorded_control_prefix(frames, inputs, [10,11], original)
    assert selected == frames[:12] and inputs[-1]['own_range'] == {'valid':False}
    assert audit['excluded_interrupted_captures'] == [frames[-1]]
    assert audit['completed_controller_inputs'] == 2
    assert 'terminal state not reconstructed' in audit['scope']
    with pytest.raises(ValueError, match='NON_PREFIX'):
        recorded_control_prefix(frames, [inputs[-1]], [11], original)
    with pytest.raises(ValueError, match='INCOMPLETE_CONTROLLER_CALLBACK'):
        recorded_control_prefix(frames, inputs, [10], original)
    with pytest.raises(ValueError, match='UNEXPLAINED_CAPTURE'):
        recorded_control_prefix(frames, inputs, [10,11], dict(status='RECORDED'))


def test_release_slot_keeps_another_codex_tasks_lease(monkeypatch):
    from scripts import profile_controller_replay as replay, agent_lock
    ours=dict(owner='codex',branch='codex/sim-speed-ctrl2',pid=123,acquired_unix=1.)
    current={**ours,'pid':456,'branch':'codex/research'}
    released=[]
    monkeypatch.setattr(agent_lock,'status',lambda root:current)
    monkeypatch.setattr(agent_lock,'release',lambda *a,**k:released.append(k) or current)
    assert replay.release_slot(ours,True) is None and released==[]
    current={**ours,'acquired_unix':2.}
    assert replay.release_slot(ours,True) is None and released==[]
    current=ours.copy()
    assert replay.release_slot(ours,False) is None and released==[]
    assert replay.release_slot(ours,True)==ours
    assert released==[{'owner':'codex'}]


def test_interrupted_invoke_waits_for_managed_cli_cleanup(tmp_path,monkeypatch):
    import signal,time
    from types import SimpleNamespace
    from scripts import benchmark_controller_replay as abba
    monkeypatch.setattr(abba,'source_check',lambda expected:None)
    monkeypatch.setattr(abba,'verify_adapter',lambda *a:None)
    events=[]
    class Child:
        def wait(self):
            events.append('wait')
            if events.count('wait')==1:raise InterruptedError('HOST_INTERRUPTED:SIGTERM')
            events.append('worker group cleaned');return 130
        def poll(self):return None
        def send_signal(self,sig):events.append(('signal',sig))
    def popen(command,**kwargs):
        assert kwargs['start_new_session'] is True
        assert '--timeout' in command
        return Child()
    monkeypatch.setattr(abba.subprocess,'Popen',popen)
    args=SimpleNamespace(expected_source_sha='a'*40,deadline=time.monotonic()+60,profile=False)
    case=dict(id='s3',kind='s3',raw='unused',adapter='unused',adapter_sha256='fixed')
    with pytest.raises(InterruptedError,match='HOST_INTERRUPTED'):
        abba.invoke(case,tmp_path/'new',args,scan='off',storage='off')
    assert events==['wait',('signal',signal.SIGTERM),'wait','worker group cleaned']


@pytest.mark.parametrize('signal_name',['SIGTERM','SIGHUP'])
def test_abba_signal_retains_completed_case_and_failure_and_restores_handlers(
        tmp_path,monkeypatch,signal_name):
    import json,os,signal,sys
    from scripts import benchmark_controller_replay as abba, agent_lock
    signum=getattr(signal,signal_name)
    previous={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGHUP)}
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(priority_run='unused',cases=[
        dict(id=name,kind='s3',adapter=str(tmp_path/'adapter'),raw='unused')
        for name in ('complete-case','interrupted-case')])))
    original=plan.read_bytes();output=tmp_path/'result'
    held=dict(owner='codex',branch='codex/sim-speed-ctrl2',pid=os.getpid(),acquired_unix=1.)
    monkeypatch.setattr(sys,'argv',['abba','--plan',str(plan),'--output',str(output),
        '--priority-receipt',str(tmp_path/'unused'),'--expected-source-sha','a'*40,'--execute'])
    monkeypatch.setattr(abba,'source_check',lambda expected:None)
    monkeypatch.setattr(abba.subprocess,'check_output',lambda *a,**k:'0')
    monkeypatch.setattr(abba,'priority_check',lambda *a:{})
    monkeypatch.setattr(abba,'verify_adapter',lambda *a:{'sha256':'fixed-source'})
    monkeypatch.setattr(abba,'acquire_slot',lambda *a,**k:(held,True))
    monkeypatch.setattr(agent_lock,'status',lambda root:held)
    releases=[]
    def release(*args,**kwargs):
        # A repeated TERM/HUP during cleanup must not lose the failure record.
        os.kill(os.getpid(),signum)
        releases.append(kwargs);return held
    monkeypatch.setattr(agent_lock,'release',release)
    calls=[]
    def invoke(case,path,*args,**kwargs):
        path.mkdir();calls.append(case['id'])
        if case['id']=='interrupted-case':os.kill(os.getpid(),signum)
    monkeypatch.setattr(abba,'invoke',invoke)
    monkeypatch.setattr(abba,'compare_runs',lambda *a:dict(verified=True,adapter_source_hashes_equal=True))
    monkeypatch.setattr(abba,'components',lambda *a:[dict(wall_per_input_sim=1.) for _ in range(4)])
    monkeypatch.setattr(abba,'load_assessment',lambda *a:dict(comparable=True))
    with pytest.raises(InterruptedError,match='HOST_INTERRUPTED:'+signal_name):abba.main()
    result=json.loads((output/'abba.json').read_text())
    assert result['complete'] is False
    assert [row['id'] for row in result['cases']]==['complete-case']
    assert result['failure']==dict(type='InterruptedError',message='HOST_INTERRUPTED:'+signal_name)
    assert calls==['complete-case']*4+['interrupted-case']
    assert releases==[{'owner':'codex'}]
    assert json.loads((output/'lock.json').read_text())['release_skipped'] is False
    assert plan.read_bytes()==original
    assert {s:signal.getsignal(s) for s in previous}==previous


@pytest.mark.parametrize('signal_name',['SIGTERM','SIGHUP','SIGINT'])
def test_invoke_defers_startup_signal_until_cli_handle_and_waits(tmp_path,monkeypatch,signal_name):
    import os,signal,time
    from types import SimpleNamespace
    from scripts import benchmark_controller_replay as abba
    signum=getattr(signal,signal_name)
    watched=(signal.SIGINT,signal.SIGTERM,signal.SIGHUP)
    previous={s:signal.getsignal(s) for s in watched}
    monkeypatch.setattr(abba,'source_check',lambda expected:None)
    monkeypatch.setattr(abba,'verify_adapter',lambda *a:None)
    monkeypatch.setattr(abba.shutil,'disk_usage',lambda _:SimpleNamespace(free=20*2**30))
    events=[]
    class Child:
        def poll(self):return None
        def send_signal(self,sig):events.append(('signal',sig))
        def wait(self):
            # Repeated interruption during cleanup must not lose ownership.
            os.kill(os.getpid(),signum)
            events.append('group cleaned');return 130
    def popen(*a,**k):
        events.append('OS child created')
        os.kill(os.getpid(),signum)
        events.append('handle returned')
        return Child()
    monkeypatch.setattr(abba.subprocess,'Popen',popen)
    args=SimpleNamespace(expected_source_sha='a'*40,deadline=time.monotonic()+60,profile=False)
    case=dict(kind='s3',raw='unused',adapter='unused',adapter_sha256='fixed')
    exception=KeyboardInterrupt if signum==signal.SIGINT else InterruptedError
    with pytest.raises(exception):abba.invoke(case,tmp_path/'new',args,scan='off',storage='off')
    assert events==['OS child created','handle returned',('signal',signal.SIGTERM),'group cleaned']
    assert {s:signal.getsignal(s) for s in watched}==previous
