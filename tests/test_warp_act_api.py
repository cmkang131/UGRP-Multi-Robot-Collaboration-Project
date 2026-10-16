"""Reference-contract boundary checks; no simulator/renderer/model imports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import types

import pytest

from scripts.warp_act_api import History, Owner, admit
from scripts.warp_act_rpc import Client


@pytest.fixture
def contract():
    root = Path(__file__).parent/'fixtures'/'warp3'
    raw = (root/'grasp_act_contract.py.txt').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == json.loads((root/'source.json').read_text())['sha256']
    module = types.ModuleType('warp3_reference_contract')
    exec(compile(raw, 'frozen_actor_contract', 'exec'), module.__dict__)
    return module


def initial():
    return dict(t=0., wheels=[0.]*4, duration_s=[0.]*4, pwm={str(s): 1500 for s in (1, 3, 4, 5, 6)})


def test_recording_retains_original_issued_command_and_error_ledger(tmp_path, monkeypatch):
    """A decoder failure must close the raw recording without admitting it."""
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    import run_warp_act_record as recording
    source, teacher, out = tmp_path/'qualified', tmp_path/'teacher', tmp_path/'capture'
    controller_out = tmp_path/'controller'
    (controller_out/'world-000').mkdir(parents=True)
    (controller_out/'world-000/teacher-commands.jsonl').write_text('{"t":0.0}\n')
    args = ['--scene-v5-v1','--numpy-teacher-v1','--batch-sleep-v1','--native-sleep-policy-compat-v1',
            '--physics-backend','mjwarp_batch_v1','--teacher-source',str(teacher),'--out',str(controller_out)]
    argfile = tmp_path/'args.json'; argfile.write_text(json.dumps(args))
    monkeypatch.setattr(recording, 'admit', lambda *a: {'cohort':{'host':{}},'n':40,'N':40})
    backend = types.ModuleType('warp_act_backend')
    backend.WarpTransport = type('Transport', (), {'capture':lambda *a:b'original-jpeg'})
    monkeypatch.setitem(sys.modules, 'warp_act_backend', backend)
    monkeypatch.setitem(sys.modules, 'sim', types.SimpleNamespace(__path__=[]))
    closed = []
    class Recorder:
        def __init__(self, *a): pass
        def close(self): closed.append(True)
    monkeypatch.setitem(sys.modules, 'harness.grasp_act_solo_recording', types.SimpleNamespace(
        SoloRecorder=Recorder, validate_recording=lambda *a,**k:None, validate_approval=lambda *a,**k:None))
    def broken_decode(*a): raise ValueError('injected invalid image')
    monkeypatch.setitem(sys.modules, 'cv2', types.SimpleNamespace(imdecode=broken_decode, IMREAD_COLOR=1))
    code = """def run():
    plan={'seed':1}
    teacher=SimpleNamespace(skill='grasp',phase='approach')
    now=0.0
    previous={'pwm':{'1':1500}}
    Backend.capture(None,0,None)
    previous['pwm']['1']=2500
"""
    namespace={'SimpleNamespace':types.SimpleNamespace,'Backend':backend.WarpTransport}
    exec(compile(code,str(source/'scripts/warp_act_episode.py'),'exec'),namespace)
    monkeypatch.setattr(recording.runpy,'run_path',lambda *a,**k:namespace['run']())
    monkeypatch.setattr(sys,'argv',['record','--enabled','--qualified-source',str(source),
        '--teacher-source',str(teacher),'--qualification',str(tmp_path/'gate'),
        '--runner-args-json',str(argfile),'--out',str(out)])
    with pytest.raises(RuntimeError,match='injected invalid image'): recording.main()
    context=json.loads((out/'world-000/capture-context.json').read_text())
    result=json.loads((out/'summary.json').read_text())
    assert context[0]['previous']['pwm']['1']==1500 and closed==[True]
    assert result['status']=='HOST_ERROR' and not result['data_admitted']
    assert (out/'world-000/capture/000000.jpg').read_bytes()==b'original-jpeg'


def test_default_off_and_mac_admission_precede_any_physics(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match='default OFF'):
        Owner([], tmp_path/'out', qualified_source='', teacher_source='', qualification='',
              references={}, compiled_reference='', compiled_geometry='')
    with pytest.raises(ValueError, match='default OFF'):
        Client(python='', qualified_source='', teacher_source='', qualification='', references='',
               compiled_reference='', compiled_geometry='', out=tmp_path/'client', nworld=2)
    import scripts.warp_act_api as api
    monkeypatch.setattr(api.platform, 'system', lambda: 'Darwin')
    with pytest.raises(RuntimeError, match='Mac physics/render forbidden'):
        admit('nonexistent', 'nonexistent', 'nonexistent')
    assert not (tmp_path/'out').exists() and not (tmp_path/'client').exists()


def test_history_uses_time_lags_and_isolates_worlds(contract):
    a, b = History(contract, 'A', initial()), History(contract, 'B', initial())
    plan = dict(kind='cyan', role='west')
    b_before = b.observe(0., b'B', plan, 'grasp')
    for tick in range(54):
        command = initial(); command['t'] = tick*.1
        a.issue(command)
        obs, jpgs = a.observe(tick*.1, str(tick).encode(), plan, 'grasp')
    assert len(jpgs) == 4 and jpgs[-1] == b'53'
    assert obs['rgb'][0]['t'] <= .1+1e-7 and obs['rgb'][-1]['t'] == pytest.approx(5.3)
    assert b_before[1] == (b'B',)*4 and len(b.frames) == 1 and b.index == 1
    command['pwm']['1'] = 2400
    assert a.issued[-1]['pwm']['1'] == 1500


def test_actor_read_is_pure_and_rejects_privileged_cache(contract):
    h = History(contract, 'actor', initial())
    obs, jpgs = h.observe(0., b'own-rgb', dict(kind='cyan', role='west'), 'grasp')
    owner = Owner.__new__(Owner); owner.c = contract; owner.current = [(obs, jpgs)]
    first = owner.read_actor(0); second = owner.read_actor(0)
    assert first == second and h.index == 1
    first[0]['issued'][-1]['pwm']['1'] = 2500
    assert owner.read_actor(0)[0]['issued'][-1]['pwm']['1'] == 1500
    owner.current[0][0]['qpos'] = [123]
    with pytest.raises(ValueError, match='whitelist'):
        owner.read_actor(0)


def test_instruction_updates_only_named_task_tokens(contract):
    h = History(contract, 'actor', initial())
    owner = Owner.__new__(Owner)
    owner.c, owner.n, owner.active = contract, 1, [True]
    owner.skills, owner.plans, owner.histories = ['grasp'], [dict(kind='cyan', role='west')], [h]
    owner.current = [h.observe(0., b'own-rgb', owner.plans[0], 'grasp')]
    before = deepcopy(owner.current)
    owner.instruct(0, 'release')
    assert owner.current[0][0]['destination_zone'] == 'pickup_site'
    assert owner.current[0][0]['issued'] == before[0][0]['issued']
    assert owner.current[0][1] == before[0][1] and h.index == 1
    with pytest.raises(ValueError): owner.instruct(0, 'go_to_truth_position')


def test_client_reset_callback_is_selected_and_after_success(tmp_path):
    calls = []
    client = Client.__new__(Client)
    client.nworld, client.proc = 3, object()
    client.on_reset = lambda indices: calls.append(indices)
    client.exchange = lambda request: request
    assert client.reset([{'seed': 1}], indices=[2]) == {'reset': [{'seed': 1}], 'indices': [2]}
    assert calls == [(2,)]
    def reject(request): raise ValueError('rejected by owner')
    client.exchange = reject
    with pytest.raises(ValueError): client.reset([{}], indices=[0])
    assert calls == [(2,)]
