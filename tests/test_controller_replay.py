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


def test_numpy_graph_evidence_serializes_without_losing_numeric_values(tmp_path):
    import json
    import numpy as np
    from scripts.profile_controller_replay import write
    write(tmp_path / 'evidence.json', {'covariance': np.eye(3), 'node': np.int64(2)})
    assert json.loads((tmp_path / 'evidence.json').read_text()) == {
        'covariance': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], 'node': 2}
    with pytest.raises(ValueError):
        write(tmp_path / 'invalid.json', {'covariance': np.array([np.nan])})


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
