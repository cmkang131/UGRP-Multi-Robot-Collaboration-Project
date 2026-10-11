"""Real scheduler with recorded doubles; no world, renderer, socket or real model."""
import copy,io,json
from types import SimpleNamespace
import pytest
from tests.test_pair_llm_s4_host import no_external_work,setup_data,FIXTURE
from tests import test_pair_llm_s4_pair as fixture
from harness import s4_pair_epochs as ep
from scripts import run_s4_pair_live10 as run,submit_s4_live10 as submit
from sim import s4_cyan_supervisor as cyan


def opened(rounds=False,reconnect=False):
    h=ep.Handshake(go_ack_rounds=rounds,epoch_reconnect=reconnect,carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT)
    for r in ep.hs.PAIR:h.claim(r,'claim-'+r);h.open(r,0,0.)
    return h


def vote(h,r,choice,request,now,peer=None):
    return h.decide(r,fixture.action(choice,0,peer),call_id=choice+'-'+r,
        requested_at=request,now=now,frame_t=request,frame_sha256='a'*64,seen=h.view(r,request))


@pytest.mark.parametrize('enabled',[False,True])
def test_late_go_has_bounded_separate_ack_round(enabled):
    h=opened(rounds=enabled)
    assert vote(h,'r1','go',17.,18.)['accepted'];assert vote(h,'r2','go',18.,19.)['accepted']
    assert h.deadline('r1')==(39. if enabled else 20.)
    a=[vote(h,r,'ack_go',23.,24.,'go-'+peer)['accepted'] for r,peer in [('r1','r2'),('r2','r1')]]
    assert all(a)==enabled;assert h.tick(24.)==enabled
    assert len(h.permits)==int(enabled)
    if enabled:assert not h.tick(34.) and h.failure=='PAIR_VISUAL_LEASE_EXPIRED'


@pytest.mark.parametrize('enabled',[False,True])
def test_precommit_ack_snapshot_rebinds_same_epoch_without_reviving_lease(enabled):
    h=opened(rounds=True,reconnect=enabled)
    for r in ep.hs.PAIR:vote(h,r,'go',1.,2.)
    for r,peer in [('r1','r2'),('r2','r1')]:vote(h,r,'ack_go',3.,4.,'go-'+peer)
    seen=h.view('r1',4.);seen['own_executor_phase']='wait_carry';original=copy.deepcopy(seen)
    assert h.tick(4.)
    row=h.renew_carry('r1',fixture.action('held'),call_id='new',command_accepted=True,decision_sources=['own_rgb'],
        requested_at=4.,now=5.,frame_t=4.,frame_sha256='a'*64,seen=seen)
    assert row['accepted']==enabled and seen==original
    assert not h.renew_carry('r1',{'kind':'continue'},call_id='too-late',command_accepted=False,
        decision_sources=['own_rgb'],requested_at=14.,now=15.,frame_t=14.,frame_sha256='a'*64,
        seen={**seen,'phase':'carry'})['accepted']
    assert h.open('r1',1001,6.)
    assert not h.renew_carry('r1',{'kind':'continue'},call_id='old-epoch',command_accepted=False,
        decision_sources=['own_rgb'],requested_at=6.,now=7.,frame_t=6.,frame_sha256='a'*64,seen=seen)['accepted']


class WrongAckWire(fixture.PairWire):
    def __init__(self,always=False,**kwargs):super().__init__(**kwargs);self.invalid=0;self.always=always
    def __call__(self,request,**kwargs):
        stream=super().__call__(request,**kwargs);outer=json.loads(stream.getvalue());reply=json.loads(outer['choices'][0]['message']['content'])
        if reply['action']['kind']=='pair_decision' and reply['action']['choice']=='ack_go' and reply['request_id'].endswith('_r1') and (not self.invalid or self.always):
            reply['action']['peer_go_ref']='call-0004-r1';self.invalid+=1
            outer['choices'][0]['message']['content']=json.dumps(reply);raw=json.dumps(outer).encode();self.responses[-1]=raw;return io.BytesIO(raw)
        return stream


@pytest.mark.parametrize('always,permits',[(False,1),(True,0)])
def test_semantic_wrong_ack_retry_is_once_and_has_explicit_feedback(tmp_path,setup_data,monkeypatch,always,permits):
    monkeypatch.setattr(fixture.stage,'Host',ep.Host)
    monkeypatch.setattr(fixture.hs,'Handshake',lambda **kw:ep.Handshake(go_ack_rounds=True,epoch_reconnect=True,carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT))
    wire=WrongAckWire(always=always);monkeypatch.setattr(fixture,'PairWire',lambda **kw:wire)
    host,base,inner=fixture.build(tmp_path,setup_data,'peer_ko');driver=ep.Driver(host,base.runtime,go_ack_retry=True)
    host.begin();moves=[]
    for i in range(1,441):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t);moves.extend(c for _,c in driver.step(t) if c['kind']=='mecanum')
    assert len(driver.handshake.permits)==permits
    assert len(driver.retry_events)==1 and driver.retry_events[0]['semantic_rejection']
    assert host.trial.epoch_retry_context[('r1',0)]['reason']=='STALE_OR_CLOSED_PAIR_WINDOW'
    if not permits:assert not moves
    assert all(len(inner[r].s3_calls)==1 for r in ep.hs.PAIR)
    reqs=[json.loads(next(v['text'] for v in json.loads(b)['messages'][1]['content'] if v['type']=='text')) for b in wire.requests]
    assert any(r.get('s4_round',{}).get('previous_rejection') for r in reqs)


@pytest.mark.parametrize('reason,bilateral,drop,suppress',[
    ('LOAD_DROP:cyan_1',True,False,True),('LOAD_DROP:cyan_1',False,True,False),('LOAD_DROP:beam_1',True,False,False)])
def test_supervisor_resumes_only_supported_cyan_evaluation(monkeypatch,reason,bilateral,drop,suppress):
    obj=object.__new__(cyan.PhysicsBackend);obj.bundle={'cyan_drop_supervisor':'contact_com_v1'};obj.stage_cyan_guard=object();calls=[]
    obj.cyan_row=lambda:{'drop':drop,'finger_contact':bilateral,'bilateral_finger_contact':bilateral};obj._append=lambda *a:calls.append(a)
    obj.record_dynamics=lambda:calls.append('dynamics');obj.progress=lambda:calls.append('progress');obj._pending_beam_setdown={}
    monkeypatch.setattr(cyan.Previous,'eval_sample',lambda self:(_ for _ in ()).throw(cyan.PhysicalStop(reason)))
    monkeypatch.setattr(cyan,'check_cyan',lambda *a:calls.append('guard'))
    if suppress:obj.eval_sample();assert 'guard' in calls and 'dynamics' in calls
    else:
        with pytest.raises(cyan.PhysicalStop,match=reason):obj.eval_sample()


def test_sealed_eight_default_off_and_proportional_horizon(capsys):
    b=run.bundle('a'*40,'no_comm',602)
    assert not b['epoch_reconnect'] and not b['go_ack_rounds'] and b['cyan_drop_supervisor']=='off'
    assert b['case_cap_s']==900 and b['wall_cap_s']==10800 and b['calls_per_actor']==450
    assert len(submit.commands('a'*40))==8
    assert run.main(['--expected-source-sha','a'*40,'--output','no-write','--condition','no_comm','--relay-receipt','no-read'])==0
    assert not json.loads(capsys.readouterr().out)['epoch_reconnect']


def test_open_carry_window_overrides_monitor_example_without_commands(tmp_path,setup_data,monkeypatch):
    monkeypatch.setattr(fixture.stage,'Host',ep.Host)
    monkeypatch.setattr(fixture.hs,'Handshake',lambda **kw:ep.Handshake(go_ack_rounds=True,epoch_reconnect=True,carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT))
    host,base,inner=fixture.build(tmp_path,setup_data,'no_comm');driver=ep.Driver(host,base.runtime,go_ack_retry=True)
    host.begin()
    for i in range(1,121):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t);driver.step(t)
    assert driver.handshake.permits
    host.trial.links['r1'].stop_adapter.window.current={'kind':'carry_decision','opened_at_sim_s':12.,'decide_at_sim_s':22.,'latch_until_sim_s':22.}
    call=SimpleNamespace(actor='r1',call_id='call-9999-r1',started_sim_s=12.)
    host.trial.snapshot(call);prepared=host.trial.prepare_call(call)
    context=prepared.bundled.context
    assert context['reply_example'] is None
    assert context['decision_actions']==[{'kind':'carry_decision','choice':c} for c in ('continue','set_down')]
    host.trial.links['r1'].stop_adapter.window.current=None
    base.runtime.actors['r1']._pair.controller.state='pregrasp_descend'
    call.call_id='call-9998-r1';host.trial.snapshot(call);prepared=host.trial.prepare_call(call)
    assert prepared.bundled.context['reply_example']['action']=={'kind':'continue'}


@pytest.mark.parametrize('condition',['no_comm','peer_ko','leader_ko','structured'])
@pytest.mark.parametrize('reconnect',[False,True])
def test_current_go_example_passes_real_condition_schema(tmp_path,setup_data,monkeypatch,condition,reconnect):
    monkeypatch.setattr(fixture.stage,'Host',ep.Host)
    monkeypatch.setattr(fixture.hs,'Handshake',lambda **kw:ep.Handshake(go_ack_rounds=True,epoch_reconnect=reconnect,carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT))
    host,driver,inner=fixture.build(tmp_path,setup_data,condition);h=host.trial.handshake
    for r in ep.hs.PAIR:h.claim(r,'claim-'+r);h.open(r,0,0.)
    call=SimpleNamespace(actor='r2',call_id='call-9999-r2',started_sim_s=0.)
    host.trial.snapshot(call);prepared=host.trial.prepare_call(call);reply=prepared.bundled.context['reply_example'];b=prepared.bundled
    checked=ep.base.validate_reply(reply,request_id=prepared.request_id,condition=condition,actor='r2',
        order_ids=b.order_ids(),item_ids=b.item_ids(),roles_by_order=b.roles_by_order(),vocabulary=b.vocabulary(),
        passages=b.passages(),location_refs=b.location_refs(),robots=ep.base.si.ROBOTS)
    assert checked['action']['choice']=='go' and bool(checked['messages'])==(condition!='no_comm')


@pytest.mark.parametrize('enabled',[False,True])
def test_own_ack_wait_heartbeat_refreshes_liveness_without_permit_or_deadline_extension(enabled):
    h=opened(rounds=True,reconnect=enabled)
    for r in ep.hs.PAIR:vote(h,r,'go',1.,2.)
    vote(h,'r1','ack_go',3.,4.,'go-r2');seen=h.view('r1',4.);seen['own_executor_phase']='wait_carry'
    deadline=h.deadline('r1')
    row=h.renew_carry('r1',fixture.action('held'),call_id='waiting',command_accepted=False,
        decision_sources=['own_rgb'],requested_at=4.,now=5.,frame_t=4.,frame_sha256='a'*64,seen=seen)
    assert row['accepted']==enabled and h.deadline('r1')==deadline
    assert not h.tick(5.) and not h.allowed('r1',0) and not h.permits
    assert not h.renew_carry('r1',{'kind':'continue'},call_id='expired-wait',command_accepted=False,
        decision_sources=['own_rgb'],requested_at=deadline-1,now=deadline,frame_t=deadline-1,
        frame_sha256='a'*64,seen=seen)['accepted']


def test_second_go_cannot_resurrect_other_endpoint_expired_same_tick():
    h=opened(rounds=True);h.own['r2']['opened']=5.
    assert vote(h,'r1','go',17.,18.)['accepted']
    assert vote(h,'r2','go',19.,20.)['accepted']
    assert h.rounds[0]['ack_opened'] is None
    assert not h.tick(20.) and h.failure=='PAIR_GO_TIMEOUT' and not h.permits


@pytest.mark.parametrize('enabled,floor,drop,suppress',[
    (False,True,False,False),(True,True,False,True),
    (True,False,True,False),(True,False,False,False)])
def test_floor_support_recovery_keeps_airborne_drop_fatal(monkeypatch,enabled,floor,drop,suppress):
    obj=object.__new__(cyan.PhysicsBackend);obj.bundle={'cyan_drop_supervisor':'contact_com_v1','cyan_floor_support':enabled}
    obj.stage_cyan_guard=object();calls=[]
    obj.cyan_row=lambda:{'drop':drop,'finger_contact':False,'bilateral_finger_contact':False,'floor_contact':floor}
    obj._append=lambda *a:calls.append(a);obj.record_dynamics=lambda:calls.append('dynamics')
    obj.progress=lambda:calls.append('progress');obj._pending_beam_setdown={}
    monkeypatch.setattr(cyan.Previous,'eval_sample',lambda self:(_ for _ in ()).throw(cyan.PhysicalStop('LOAD_DROP:cyan_1')))
    monkeypatch.setattr(cyan,'check_cyan',lambda *a:calls.append('guard'))
    if suppress:
        obj.eval_sample();assert 'guard' in calls and 'dynamics' in calls
        assert any(isinstance(c,tuple) and c[0].endswith('height-stop-classification.jsonl') and c[1]['classification']=='floor_supported_height_stop' for c in calls)
    else:
        with pytest.raises(cyan.PhysicalStop,match='LOAD_DROP:cyan_1'):obj.eval_sample()


class MissingIDWire(fixture.PairWire):
    def __init__(self,**kwargs):super().__init__(**kwargs);self.invalid=0
    def __call__(self,request,**kwargs):
        stream=super().__call__(request,**kwargs);outer=json.loads(stream.getvalue());reply=json.loads(outer['choices'][0]['message']['content'])
        if reply['action'].get('choice')=='held' and reply['request_id'].endswith('_r1') and not self.invalid:
            reply.pop('request_id');self.invalid+=1;outer['choices'][0]['message']['content']=json.dumps(reply)
            raw=json.dumps(outer).encode();self.responses[-1]=raw;return io.BytesIO(raw)
        return stream


@pytest.mark.parametrize('feedback',[False,True])
def test_invalid_carry_envelope_feedback_uses_regular_requests_no_invalid_action(tmp_path,setup_data,monkeypatch,feedback):
    monkeypatch.setattr(fixture.stage,'Host',ep.Host)
    monkeypatch.setattr(fixture.hs,'Handshake',lambda **kw:ep.Handshake(go_ack_rounds=True,epoch_reconnect=True,
        carry_protocol_feedback=feedback,carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT))
    wire=MissingIDWire();monkeypatch.setattr(fixture,'PairWire',lambda **kw:wire)
    host,base,inner=fixture.build(tmp_path,setup_data,'no_comm');driver=ep.Driver(host,base.runtime,go_ack_retry=True)
    host.begin()
    for i in range(1,221):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t);driver.step(t)
    invalid=[r for r in host.trial.scheduler.ledger.values() if r['status']=='failed']
    assert wire.invalid==1 and invalid
    invalid_ids={r['call_id'] for r in invalid}
    assert not any(r['call_id'] in invalid_ids for r in driver.handshake.renewals)
    events=[r for r in driver.retry_events if r.get('phase')=='carry']
    assert len(events)==int(feedback)
    assert all(not r['forced_new_send'] and not r['transport_retry'] for r in events)
    bodies=[json.loads(next(v['text'] for v in json.loads(b)['messages'][1]['content'] if v['type']=='text')) for b in wire.requests]
    assert any(r.get('s4_round',{}).get('previous_rejection') for r in bodies)==feedback
    assert driver.handshake.permits and not driver.handshake.failure


def test_continuation_defaults_off_and_all_eight_commands(capsys):
    from scripts import run_s4_pair_live10b as retry,submit_s4_live10b as batch
    b=retry.bundle('a'*40,'no_comm',602)
    assert not b['cyan_floor_support'] and not b['carry_protocol_feedback']
    assert b['bundle_id']=='zone-s4-pair-live-v180' if 'bundle_id' in b else b['execution_bundle_id']=='zone-s4-pair-live-v180'
    assert len(batch.commands('a'*40))==8
    assert retry.main(['--expected-source-sha','a'*40,'--output','no-write','--condition','no_comm','--relay-receipt','no-read'])==0
    assert not json.loads(capsys.readouterr().out)['carry_protocol_feedback']


@pytest.mark.parametrize('floor,tilted,stop',[(True,False,False),(False,False,True),(True,True,True)])
def test_real_s2_guard_accepts_grounded_release_but_keeps_air_loss_and_tilt(floor,tilted,stop):
    from sim.s2_realism import StopGuard,PhysicalStop
    from harness.zone_s2_realism_contract import SAFETY
    g=StopGuard();g.lifted=True;events=[]
    proxy=cyan.FloorSupportedGuard(g,{'floor_contact':floor,'drop':False},lambda *x:events.append(x))
    row={'t':207.55,'cyan_z_m':.0162,'cyan_min_z_m':-.0004,'finger_contacts':[False,False],
        'robot_tilt_deg':SAFETY['robot_tilt_limit_deg'] if tilted else .076}
    if stop:
        with pytest.raises(PhysicalStop):proxy.check(row,release_allowed=False)
    else:proxy.check(row,release_allowed=False);assert g.lost_since is None
    assert events and not events[0][1]['feedback_to_controller']


@pytest.mark.parametrize('enabled',[False,True])
def test_cyan_full_guard_chain_with_real_s2_guard_matches_recorded_floor_stop(monkeypatch,enabled):
    from sim.s2_realism import StopGuard
    obj=object.__new__(cyan.PhysicsBackend);obj.bundle={'cyan_drop_supervisor':'contact_com_v1','cyan_floor_support':enabled}
    obj.stage_cyan_guard=StopGuard();original=obj.stage_cyan_guard;original.lifted=True
    obj.cyan_row=lambda:{'drop':False,'finger_contact':False,'bilateral_finger_contact':False,'floor_contact':True}
    events=[];obj._append=lambda *a:events.append(a);obj.record_dynamics=lambda:None;obj.progress=lambda:None;obj._pending_beam_setdown={}
    monkeypatch.setattr(cyan.Previous,'eval_sample',lambda self:(_ for _ in ()).throw(cyan.PhysicalStop('LOAD_DROP:cyan_1')))
    monkeypatch.setattr(cyan,'check_cyan',lambda host,guard:guard.check({'t':207.55,'cyan_z_m':.0162,
        'cyan_min_z_m':-.0004,'finger_contacts':[False,False],'robot_tilt_deg':.076},release_allowed=False))
    if enabled:obj.eval_sample();assert any(e[0].endswith('release-supervisor.jsonl') for e in events)
    else:
        with pytest.raises(cyan.PhysicalStop):obj.eval_sample()
    assert obj.stage_cyan_guard is original
