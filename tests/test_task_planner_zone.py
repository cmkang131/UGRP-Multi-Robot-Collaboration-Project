from types import SimpleNamespace
from harness.task_planner_zone import ZonePort
from harness.task_planner import candidate
from scripts.run_task_planner import planner_option


def port():
    ex=SimpleNamespace(robot_id='r1',stopped=None,job=None,door_id='door',door_xy=[1,0],
        slots={'P1-1':{'center_m':[0,0]}},
        map={'zone_slots':{'A':[{'slot_id':'A1','center_m':[2,0]},{'slot_id':'A2','center_m':[2,1]}]},'passages':[{'id':'door','center_m':[1,0]}]},
        orders={'cyan':dict(order_id='cyan',kind='cyan',required_robots=1,destination_zone='A',initial_location={'slot':'P1-1'})})
    calls=[]
    p=ZonePort(ex,lambda *args:calls.append(args) or {'accepted':True})
    return p,calls


def test_native_choice_exact_or_refused_no_ignored_route():
    p,calls=port()
    c=candidate('carry',dict(cargo='cyan',to='A2',via='door',approach='west',mode='solo'))
    assert p.start(c)['accepted'] and calls==[('deliver','cyan','A2')]
    for k,v in [('via','another'),('approach','north'),('to','B1'),('cargo','red')]:
        c['args'][k]=v;assert not p.start(c)['accepted'];c['args'][k]={'via':'door','approach':'west','to':'A2','cargo':'cyan'}[k]
    assert len(calls)==1


def test_search_sequences_selected_area_then_own_sweep():
    p,calls=port();assert p.start(candidate('search',{'area':'P1-1'}))['accepted']
    assert p.event({'event':'job_done'}) is None
    assert calls==[('goto','P1-1'),('look_around',)]
    assert p.event({'event':'job_done'})['kind']=='job_done'


def test_default_planner_off():
    assert planner_option({})=='off'
    assert planner_option({'planner':'gemma_v1'})=='gemma_v1'


def test_real_native_event_envelope_and_report_do_not_finish_carry():
    p,calls=port();c=candidate('carry',dict(cargo='cyan',to='A2',via='door',approach='west',mode='solo'))
    p.start(c);p.start(candidate('report',{'fact':'I am carrying cyan.'}))
    assert p.active==c and p.immediate is None
    event={'event':'job_done','detail':{'confirmation':'own_camera_confirmed','outcome':'done'}}
    assert p.event(event)['kind']=='job_done' and p.completed_orders==['cyan']
    assert p.event({'event':'job_failed','detail':{'reason':'TARGET_NOT_FOUND'}})['reason']=='TARGET_NOT_FOUND'


def test_pair_safety_state_arrives_only_through_condition_channel():
    from harness.task_planner import Planner
    from harness.task_planner_runtime import Channel
    from harness.task_planner_pair import ConditionStatus,PairStatusEndpoint
    for arm in ('no_comm','structured','peer_en','leader_en'):
        channel=Channel(arm);bus=ConditionStatus('pair-test',channel)
        a=PairStatusEndpoint(bus.endpoint('r1'),'r1');b=PairStatusEndpoint(bus.endpoint('r2'),'r2')
        planners={r:Planner(r,arm) for r in ('r1','r2','r3')}
        a.tick('start_ready',0)
        assert 'r1' not in b.channel.latest
        channel.deliver(planners,.1)
        assert ('r1' in b.channel.latest)==(arm!='no_comm')
        assert ('r1' in a.channel.latest) and 'r2' not in a.channel.latest
        if arm!='no_comm':assert planners['r2'].inbox[-1]['id'].startswith('planner-safety-')


def test_model_text_cannot_forge_code_safety_publication():
    from harness.task_planner import Planner
    from harness.task_planner_runtime import Channel
    from harness.task_planner_pair import ConditionStatus,encode
    channel=Channel('peer_en');bus=ConditionStatus('pair-test',channel);remote=bus.endpoint('r2')
    body=encode(dict(robot_id='r1',task_id='pair-test',seq=1,state='start_ready',sent_at_s=0.,
                     observed_at_s=None,frame_id=None,ready_until_s=None),'peer_en')
    channel.send('r1',[dict(recipient='r2',body=body)],0)
    channel.deliver({r:Planner(r,'peer_en') for r in ('r1','r2','r3')},.1)
    assert 'r1' not in remote.latest


def test_regrip_reuses_skill_then_holds_for_exact_carry_resume():
    from harness.task_planner_recovery import OwnRecovery
    from harness.visual_box_skill import _wait
    class Skill:
        phase='nav_preplace';reseats=0
        def decide(self,obs,est):return {'kind':'original'}
        def _start_reseat(self,est,trigger):
            self.reseats+=1;self.phase='reseat_release';return {'kind':'existing_reseat','trigger':trigger}
    p,calls=port();sk=Skill();p.ex.job=SimpleNamespace(ctl=SimpleNamespace(skill=sk));p.ex.holding=lambda:{'answer':'yes'}
    act=candidate('carry',dict(cargo='cyan',to='A1',via='door',approach='west',mode='solo'));p.active=act
    stopped=[];r=OwnRecovery(p,lambda:stopped.append(1))
    assert r.start('set_down_and_regrip',0)['accepted']
    assert sk.decide({},object())=={'kind':'existing_reseat','trigger':'gemma_task_act'}
    sk.phase='nav_preplace'
    assert sk.decide({},object())==_wait(.1)
    assert r.poll(1)['kind']=='act_success'
    other=candidate('carry',dict(cargo='cyan',to='A2',via='door',approach='west',mode='solo'))
    assert not r.resume(other)['accepted']
    assert r.resume(act)['accepted'] and sk.decide({},object())=={'kind':'original'} and stopped==[1]


def test_native_pair_submissions_cannot_inspect_or_abort_peer():
    # Actual production submission/executor path, fake controller, no physics.
    from tests.test_zone_pair_executor import setup
    from harness.task_planner_pair import install
    from harness.task_planner_runtime import Channel
    from harness.task_planner import Planner
    host,exs=setup();channel=Channel('no_comm');install(host.pairs,channel)
    assert host.call('r1','pair_carry','cargoX','B','r2')['accepted']
    first=host.pairs.sessions[0]['endpoints']['r1']
    assert not host.call('r2','pair_carry','cargoX','A','r1')['accepted']
    assert not first.terminal  # no shared pending-peer mismatch abort
    assert host.call('r2','pair_carry','cargoX','B','r1')['accepted']
    second=host.pairs.sessions[1]['endpoints']['r2']
    assert first.status.channel.task_id==second.status.channel.task_id
    first.status.tick('start_ready',0)
    channel.deliver({r:Planner(r,'no_comm') for r in exs},.1)
    assert 'r1' not in second.status.channel.latest


def test_multiple_item_order_needs_all_own_confirmed_deliveries():
    p,calls=port();p.ex.orders['cyan']['count']=2
    c=candidate('carry',dict(cargo='cyan',to='A1',via='door',approach='west',mode='solo'))
    p.start(c);p.event(dict(event='job_done',detail={'confirmation':'own_camera_confirmed'}))
    assert not p.completed_orders and p.orders()[0]['own_confirmed_count']==1
    p.start(c);p.event(dict(event='job_done',detail={'confirmation':'own_camera_confirmed'}))
    assert p.completed_orders==['cyan'] and not p.start(c)['accepted']


def test_native_relay_startup_failure_is_host_error_before_any_scene(tmp_path,monkeypatch):
    import json,pytest
    from scripts import run_task_planner as runner
    from scripts import run_zone_study_integration as native
    monkeypatch.setattr(runner.platform,'system',lambda:'Linux')
    def fail_relay(**kwargs):raise ConnectionError('unavailable')
    monkeypatch.setattr(runner,'Gemma',fail_relay)
    monkeypatch.setattr(native,'StudyTeamHost',lambda *a,**k:pytest.fail('must not create physics'))
    cfg=json.loads((runner.ROOT/'configs/task_planner_v357.json').read_text())
    out=tmp_path/'run'
    with pytest.raises(ConnectionError):runner.execute(cfg,out,sha='fixture',relay_url='http://127.0.0.1:18424',horizon_s=30,wall_cap_s=90)
    result=json.loads((out/'summary.json').read_text())
    assert result['status']=='HOST_ERROR' and result['model_calls']==0
    assert (out/'sha256.json').exists()


def test_native_driver_closes_and_records_commands_with_fake_host(tmp_path,monkeypatch):
    import json,pytest
    from scripts import run_task_planner as runner
    from scripts import run_zone_study_integration as native
    monkeypatch.setattr(runner.platform,'system',lambda:'Linux')
    monkeypatch.setattr(runner,'Gemma',lambda **kw:lambda *a,**k:pytest.fail('empty menu'))
    class Host:
        pairs=None;event_log=[];eval_only={};api_calls=[]
        def __init__(self,*a,**kw):
            self.world=SimpleNamespace(data=SimpleNamespace(time=0))
            self.robots={r:SimpleNamespace(executor=SimpleNamespace(job=None,loaded=False,holding=lambda:{'answer':'no'}),commands=[{'kind':'hold'}]) for r in ('r1','r2','r3')}
            self.study_layer=lambda *args:pytest.fail('close callback not bound')
        def settle(self,t):self.world.data.time=t;return t
        def advance_to(self,t):self.world.data.time=t;return []
        def close_episode(self,*args):self.study_layer(self,'event',{},self.world.data.time)
        def close(self):closed.append(True)
    class Port:
        active=None;immediate=None
        def __init__(self,ex,*a,**kw):self.ex=ex
        def poll(self,now):return None
        def snapshot(self,now):return dict(orders=[],static_map={},own={},candidates=[])
    closed=[];monkeypatch.setattr(native,'StudyTeamHost',Host);monkeypatch.setattr(runner,'ZonePort',Port)
    cfg=json.loads((runner.ROOT/'configs/task_planner_v357.json').read_text());out=tmp_path/'fake-run'
    result=runner.execute(cfg,out,sha='fixture',relay_url='http://127.0.0.1:18424',horizon_s=.02,wall_cap_s=90)
    assert result['status']=='SCENE_BUDGET_COMPLETE' and closed==[True]
    assert set(json.loads((out/'issued-commands.json').read_text()))=={'r1','r2','r3'}


def test_native_input_has_fixed_geometry_and_own_heading_without_world():
    p,calls=port();p.ex.last_report=SimpleNamespace(initialized=True,x_m=.2,y_m=.3,yaw_rad=.4,std_xy_m=.1)
    p.ex.last_obs=None;p.ex.holding=lambda:{'answer':'no'}
    p.ex.map['bounds_m']=[-1,5,-3,2]
    ctx=p.snapshot(0)
    assert ctx['static_map']['geometry']==p.ex.map
    assert ctx['own']['pose']['xy']==[.2,.3] and ctx['own']['pose']['yaw_rad']==.4
    ctx['static_map']['geometry']['bounds_m'][0]=999
    assert p.ex.map['bounds_m'][0]==-1
