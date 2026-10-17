"""Small nonphysics regressions for peer deadlines and visible motion input."""
from types import SimpleNamespace
from copy import deepcopy
import pytest

from harness.grasp_act_peer_rendezvous import MODE,PeerRendezvous,RendezvousTeacherMixin


def test_observed_peer_velocity_uses_only_current_own_camera_and_issued_frame():
    rv=PeerRendezvous(MODE)
    world={'robots':{'r1':{'pose':[0,0,0]},'r2':{'pose':[1,0,0]}},
        'visibility':{'r1':{'peers':['r2']}}}
    rv.observe(world,'r1',1.)
    world['robots']['r2']['pose']=[1.1,.2,0];rv.observe(world,'r1',2.)
    assert rv.velocity['r2']==pytest.approx((.1,.2))
    world['visibility']['r1']['peers']=[];rv.observe(world,'r1',3.)
    assert rv.velocity=={}  # Remembered motion cannot renew a fresh observation.


class Base:
    def _step(self,world,now,*,permit_pick):
        self.called=True
        self.outcome='approach_blocked_handoff' if self.peer_wait_since is not None and now-self.peer_wait_since>=12-1e-8 else None
        return 'command',False


def teacher(mode):
    class T(RendezvousTeacherMixin,Base):pass
    t=T();t.rid='r1';t.peer_wait_since=8.9;t.outcome=None;t.called=False
    t.rendezvous=SimpleNamespace(mode=mode,observe=lambda *a:None,expire_yield=lambda *a:None)
    def retry(*a):t.peer_wait_since=None;t.outcome=None
    t.rendezvous.retry=retry
    return t


def test_deadline_replans_before_the_legacy_terminal_return():
    t=teacher(MODE)
    assert t._step({},20.9,permit_pick=False)==('command',False)
    assert t.called and t.outcome is None and t.peer_wait_since is None


def test_toggle_off_preserves_the_saved_terminal_behavior():
    t=teacher('off');t._step({},20.9,permit_pick=False)
    assert t.outcome=='approach_blocked_handoff'


def test_hidden_target_retry_does_not_query_cargo_geometry():
    rv=PeerRendezvous(MODE)
    class T:
        rid='r1';folded_ready=True;peer_wait_since=1.;peer_wait_ids={'r2'}
        reobserver=SimpleNamespace(active=None)
        peer_trigger=SimpleNamespace(reset=lambda:None)
        peer_progress=SimpleNamespace(reset=lambda:None)
        progress=SimpleNamespace(reset=lambda:None)
        def _geometry(self,w):raise AssertionError('hidden cargo geometry read')
    t=T();world={'beam':None,'visibility':{'r1':{'visible_probes':0}}}
    rv.retry(t,world,13.,'encounter_deadline_replan')
    assert t.peer_wait_since is None and t.outcome is None
    assert rv.events[0]['reason_category']=='target_not_visible'


def test_batch_accepts_a_compressed_final_adapter(tmp_path,monkeypatch):
    import scripts.audit_beampair1 as audit
    from scripts.run_beampair1_batch import final_adapter_result
    path=tmp_path/'result.json';packed=tmp_path/'result.json.zst';packed.write_bytes(b'fixture')
    expected={'result':{'status':'complete','physical_success':True}}
    monkeypatch.setattr(audit,'read',lambda p:expected)
    assert final_adapter_result(path)==expected
    packed.unlink()
    assert final_adapter_result(path) is None


def test_candidate_and_event_populations_are_explicit_even_without_a_yield():
    from scripts.analyze_beampair1 import candidate_funnels
    assert candidate_funnels({'teachers':{}})['rendezvous_wait_candidates']=={
        'N':0,'ordered_funnel':[
            {'gate':'current_and_predicted_clear_path','entered':0,'passed':0,'rejected':0},
            {'gate':'nonrepeated_selected_wait','entered':0,'passed':0,'rejected':0}]}


def test_all_recording_sinks_accept_numpy_before_execution(tmp_path):
    import json
    import numpy as np
    from harness.grasp_act_data import write_json
    from harness.json_encoding import dumps
    from scripts.run_beampair1 import recording_json
    row={'blocked':np.bool_(True),'count':np.int64(3),'gap':np.float32(.25),
         'path':np.array([[np.float64(.5),1.]]),
         'nested':[{'accepted':np.bool_(False),'mask':np.array([True,False])}]}
    expected={'blocked':True,'count':3,'gap':.25,'path':[[.5,1.]],
              'nested':[{'accepted':False,'mask':[True,False]}]}
    old_write=lambda *a:None
    runner=SimpleNamespace(json=json,write=old_write)
    with recording_json(runner):
        for name in ('diagnostic-snapshot.json','result.json','progress.json',
                     'start-protocol.json'):
            runner.write(tmp_path/name,{'teachers':{'r1':{'rendezvous_log':[row]}}})
            assert json.loads((tmp_path/name).read_text())['teachers']['r1']['rendezvous_log']==[expected]
        for name in ('eval-only.jsonl','teacher-r1.jsonl'):
            (tmp_path/name).write_text(runner.json.dumps(row)+'\n')
            assert json.loads((tmp_path/name).read_text())==expected
        assert json.dumps is not dumps
    assert runner.json is json and runner.write is old_write
    write_json(tmp_path/'beampair1-result.json',row)
    (tmp_path/'beampair1-commands.jsonl').write_text(dumps(row)+'\n')
    assert json.loads((tmp_path/'beampair1-result.json').read_text())==expected
    assert json.loads((tmp_path/'beampair1-commands.jsonl').read_text())==expected


def test_recording_encoder_stays_strict_and_restores_on_error(tmp_path):
    import json
    import numpy as np
    from harness.grasp_act_data import write_json
    from scripts.run_beampair1 import recording_json
    runner=SimpleNamespace(json=json,write=lambda *a:None)
    original=runner.write
    with pytest.raises(TypeError):
        with recording_json(runner):
            runner.write(tmp_path/'result.json',{'unsupported':object()})
    assert runner.json is json and runner.write is original
    for bad in (np.float64(float('nan')),np.array([float('inf')])):
        with pytest.raises(ValueError):write_json(tmp_path/'bad.json',{'value':bad})
    assert not (tmp_path/'bad.json').exists()


def test_second_regression_failure_prevents_filling_the_round(tmp_path,monkeypatch):
    import json
    import scripts.run_beampair1_batch as batch
    monkeypatch.setattr(batch.sys,'platform','linux')
    monkeypatch.setattr(batch,'python_processes',lambda:0)
    monkeypatch.setattr(batch.subprocess,'check_output',lambda *a,**kw:'a'*40)
    launched=[]
    class Process:
        pid=123
        def __init__(self,cmd,**kwargs):
            launched.append(cmd[cmd.index('--episode')+1])
            self.code=0 if len(launched)==1 else 1
        def wait(self):return self.code
        def poll(self):return self.code
    monkeypatch.setattr(batch.subprocess,'Popen',Process)
    monkeypatch.setattr(batch,'final_adapter_result',lambda p:{'result':{'physical_success':True}})
    plan=tmp_path/'plan.json';plan.write_text(json.dumps({'episodes':[{}]*6}))
    root=tmp_path/'round'
    batch.run(SimpleNamespace(plan=plan,root=root,dependency_root=tmp_path,
        candidate='baseline',rendezvous=MODE,first_episode_first=False,first_episodes=2))
    assert launched==['0','1']
    stop=json.loads((root/'SUPERVISOR_STOP.json').read_text())
    assert stop['episode']=='episode-001' and stop['reason']=='sentinel_seed_failed'
    assert json.loads((root/'batch-result.json').read_text())['supervisor_stopped']


@pytest.mark.parametrize('visible',[True,False])
def test_asymptotic_wait_cannot_outlive_its_prediction_horizon(visible):
    from harness.grasp_act_peer_rendezvous import BOUNDED_MODE
    rv=PeerRendezvous(BOUNDED_MODE);rv.yield_goal=(1.,0.);rv.yield_until=21.
    calls=[]
    t=SimpleNamespace(rid='r2',path=['stale'],path_goal=(1.,0.),peer_route=['stale'],
        progress=SimpleNamespace(reset=lambda:calls.append('reset')))
    rv.audit=lambda *a: {'event':'yield_plan_expired'}
    world={'beam':{} if visible else None}
    # Arbitrarily close to the wait point still cannot extend plan validity.
    rv.expire_yield(t,world,20.9)
    assert rv.yield_goal is not None and not calls
    rv.expire_yield(t,world,21.)
    assert rv.yield_goal is None and rv.yield_until is None
    assert t.path==t.peer_route==[] and t.next_plan==t.peer_route_next==21.
    assert calls==['reset']
    if not visible:assert rv.events[-1]['blocked_object']=='assigned_band_not_visible'


def test_original_rendezvous_replay_keeps_its_old_yield_lifetime():
    rv=PeerRendezvous(MODE);rv.yield_goal=(1.,0.);rv.yield_until=21.
    rv.expire_yield(None,{},99.)
    assert rv.yield_goal==(1.,0.)
