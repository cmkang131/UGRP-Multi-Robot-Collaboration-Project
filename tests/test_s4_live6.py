"""Lease/real response-release path and evaluator only; zero physics/model."""
import io
import json
import copy
import pytest
from harness import s4_pair_handshake as hs
from tests.test_pair_llm_s4_pair import opened, decide, build, PairWire
from tests.test_pair_llm_s4_host import setup_data, no_external_work, FIXTURE
from harness.zone_send_ledger import completion_body
from scripts import run_s4_pair_live6 as run, submit_s4_live6 as submit
from scripts.evaluate_s4_live6 import physical_metrics


def committed(mode=hs.CARRY_RENEWAL):
    h=opened();h.carry_lease_renewal=mode
    for r in hs.PAIR:decide(h,r,'go')
    for r,p in [('r1','r2'),('r2','r1')]:decide(h,r,'ack_go',request=12.2,now=13.,ref='go-'+p)
    assert h.tick(13.)
    return h


def renew(h, rid='r1', **changes):
    kw=dict(call_id='carry-'+rid,command_accepted=True,decision_sources=('own_belief','own_commands'),
        requested_at=19.,now=20.,frame_t=19.,frame_sha256='a'*64,seen=h.view(rid,19.))
    kw.update(changes)
    return h.renew_carry(rid,dict(kind='carry_decision',choice='set_down'),**kw)


def test_default_off_and_two_admitted_carry_replies_extend_without_new_permit():
    off=committed('off');assert renew(off) is None
    assert not off.tick(23.)
    h=committed()
    for r in hs.PAIR:assert renew(h,r)['accepted']
    assert h.tick(23.) and len(h.permits)==1
    assert all(o['last_response_at']==20. for o in h.own.values())
    assert not h.tick(30.) and h.failure=='PAIR_VISUAL_LEASE_EXPIRED'
    assert hs.Handshake().carry_lease_renewal=='off'


@pytest.mark.parametrize('change',[
    {'command_accepted':False}, {'frame_t':9.}, {'requested_at':21.,'now':20.},
    {'now':23.}, {'frame_t':float('nan')}, {'frame_sha256':'z'*64},
    {'seen':{'phase':'carry','epoch':1}}, {'seen':{'phase':'wait_go','epoch':0}}])
def test_rejected_stale_wrong_epoch_or_uncommitted_replies_cannot_renew(change):
    h=committed();before=copy.deepcopy(h.own)
    assert not renew(h,**change)['accepted'] and h.own==before


def test_one_endpoint_duplicate_or_after_loss_never_preserves_pair():
    h=committed();assert renew(h)['accepted'];assert not renew(h)['accepted']
    assert not h.tick(23.)
    assert not renew(h,'r2',now=23.)['accepted']
    h=committed();decide(h,'r2','grip_lost',request=19.,now=20.)
    assert not renew(h)['accepted'] and h.failure=='OWN_RGB_GRIP_LOST'


def test_actual_scheduler_validated_carry_reply_links_command_and_lease(tmp_path,setup_data,monkeypatch):
    original=PairWire.__call__
    def wire(self,request,**kw):
        body=json.loads(request.data);payload=json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type']=='text'))
        if (payload.get('pair_handshake') or {}).get('phase')!='carry':return original(self,request,**kw)
        self.requests.append(bytes(request.data))
        reply=dict(request_id=payload['request_id'],action=dict(kind='carry_decision',choice='set_down'),
            decision_sources=['own_belief','own_commands'],messages=[])
        raw=completion_body(json.dumps(reply),usage=FIXTURE['usage'],model='fixture-model')
        self.responses.append(raw);return io.BytesIO(raw)
    monkeypatch.setattr(PairWire,'__call__',wire)
    host,driver,inner=build(tmp_path,setup_data,'no_comm')
    h=driver.handshake;h.carry_lease_renewal=hs.CARRY_RENEWAL
    host.begin();opened_window=False;trace=[]
    for i in range(1,301):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        if h.permits and not opened_window:
            for r in hs.PAIR:
                host.links[r].stop_adapter.window.on_event(dict(event='pair_progress',sim_s=t,
                    detail=dict(kind='carry_stop_reached',decide_at_s=t+10,latch_until_s=t+9)),origin_s=0.)
            opened_window=True
        driver.poll(t);host.step_to(t)
        trace.extend((t,r,c) for r,c in driver.step(t))
    admitted=[r for r in h.renewals if r['accepted']]
    assert {r['robot_id'] for r in admitted}==set(hs.PAIR)
    for row in admitted:
        d=next(d for d in host.trial.dispatch_log if d['call_id']==row['call_id'])
        assert d['ack']['accepted'] and d['carry_lease_renewal']==row
        assert row['frame_sha256']==inner[row['robot_id']].sha
    assert max(t for t,r,c in trace if c['kind']=='mecanum')>h.permits[0]['at']+hs.WINDOW_S
    # Once the finite command window closes, refused replies do not keep it alive.
    assert h.failure=='PAIR_VISUAL_LEASE_EXPIRED'


def test_fixed_eight_commands_resource_wait_and_default_no_execution(capsys):
    runs=submit.commands('a'*40);assert len(runs)==8
    assert len({n for n,_ in runs})==8
    for _,argv in runs:assert 'scripts.run_s4_pair_live6' in argv and argv.count('a'*40)==1
    samples=iter([dict(loadavg=[52],mem_available_GiB=20),dict(loadavg=[4],mem_available_GiB=5),dict(loadavg=[4],mem_available_GiB=6)])
    waited=[];assert submit.wait_resources(read=lambda:next(samples),wait=waited.append)['mem_available_GiB']==6
    assert waited==[30,30]
    assert run.main(['--expected-source-sha','a'*40,'--output','/tmp/not-created-s4live6',
        '--condition','no_comm','--relay-receipt','/tmp/not-read'])==0
    assert json.loads(capsys.readouterr().out)['carry_lease_renewal']=='off'


def test_contact_supported_later_segment_and_stable_vs_dropped_lowering():
    def state(t,s,seg):return dict(t=t,robots={r:dict(state=s,seg=seg) for r in hs.PAIR})
    def truth(t,x,z=.1,speed=0):return dict(t=t,items={'beam_1':dict(x=x,y=0,z=z,speed=speed)})
    def contact(t,kind):return dict(t=t,contacts=[dict(geom1='cargo_beam_1_geom',geom2=g) for g in
        ([r+'__'+side+'_finger' for r in hs.PAIR for side in ('left','right')] if kind=='held' else ['floor'] if kind=='floor' else [])])
    states=[state(1,'carry',0),state(2,'carry',1),state(3,'carry',1),state(4,'lower',1),state(4.5,'open',1),state(5,'open',1)]
    truths=[truth(1,0),truth(2,.1),truth(3,.13),truth(4,.13),truth(4.5,.13,.016),truth(5,.13,.016)]
    contacts=[contact(t,'held' if t<=4 else 'floor') for t in (1,2,3,4,4.5,5)]
    a=physical_metrics(states,contacts,truths,[[0,0],[.13,0]])
    assert a['continue_transport']['n']==a['goal_transport']['n']==a['lowering']['n']==1
    # A lower/free-fall trajectory cannot count as loaded transport.
    truths[3]=truth(4,.13,.1);truths.insert(4,truth(4.25,.13,.04,.3));contacts[3]=contact(4,'none');contacts.insert(4,contact(4.25,'none'))
    b=physical_metrics(states,contacts,truths,[[0,0],[.13,0]])
    assert b['lowering']['drop'] and not b['lowering']['n']
