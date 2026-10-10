import pytest
from scripts.profile_controller_replay import Timers


def test_nested_timers_are_a_partition_including_exception():
    times = iter([0., 1., 3., 5.])
    timers = Timers(clock=lambda: next(times))
    with pytest.raises(ValueError), timers.span('outer'):
        with timers.span('inner'):
            raise ValueError('stop')
    assert timers.total['outer'] == dict(calls=1, exclusive_s=3., inclusive_s=5.)
    assert timers.total['inner'] == dict(calls=1, exclusive_s=2., inclusive_s=2.)
    assert timers.stack == []


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
    held,owned=replay.acquire_slot('a'*40,'test')
    assert owned and held['pid']==replay.os.getpid() and len(calls)==2


def test_borrowed_lock_requires_our_live_ancestor(monkeypatch):
    from scripts import profile_controller_replay as replay, agent_lock
    held=dict(pid=123,pid_alive=True,owner='codex',branch='codex/sim-speed-ctrl',timing_sensitive=True)
    monkeypatch.setattr(agent_lock,'status',lambda root:held)
    monkeypatch.setattr(replay,'source_check',lambda expected:None)
    monkeypatch.setattr(replay,'ancestor',lambda pid,parent:False)
    with pytest.raises(AssertionError):replay.acquire_slot('a'*40,'test',lock_owner_pid=123)
    monkeypatch.setattr(replay,'ancestor',lambda pid,parent:True)
    assert replay.acquire_slot('a'*40,'test',lock_owner_pid=123)==(held,False)


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
