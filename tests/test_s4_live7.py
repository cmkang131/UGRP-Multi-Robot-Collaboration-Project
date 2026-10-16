"""All-phase release path and COM safety: synthetic only, no physics/network."""
import copy
import io
import json
import pytest
from harness import s4_pair_handshake as hs
from harness.zone_send_ledger import completion_body
from tests.test_s4_live6 import committed, renew
from tests.test_pair_llm_s4_pair import build, PairWire, decide
from tests.test_pair_llm_s4_host import setup_data, no_external_work, FIXTURE
from sim.s4_beam_drop_guard import DropGuard
from scripts import run_s4_pair_live7 as run, submit_s4_live7 as submit
from scripts.evaluate_s4_live7 import distances


@pytest.mark.parametrize('phase,action', [
    ('carry', {'kind':'carry_decision','choice':'continue'}),
    ('lower', {'kind':'carry_decision','choice':'set_down'}),
    ('open', {'kind':'continue'}), ('align', {'kind':'continue'}),
    ('refix_look', {'kind':'continue'}),
    ('refix_post_look', {'kind':'post_look_decision','choice':'regrasp'})])
def test_same_heartbeat_all_phases_even_actuator_refused(phase, action):
    h=committed(hs.ACTIVE_PHASE_HEARTBEAT)
    for r in hs.PAIR:
        seen={**h.view(r,19.), 'own_executor_phase':phase}
        row=h.renew_carry(r,action,call_id='fresh-'+r,command_accepted=False,
            decision_sources=['own_commands'],requested_at=19.,now=20.,frame_t=19.,
            frame_sha256='a'*64,seen=seen)
        assert row['accepted'] and not row['command_accepted'] and not row['grasp_success_claim']
    assert h.tick(23.) and not h.tick(30.)


@pytest.mark.parametrize('change', [dict(frame_t=9.),dict(now=23.),
    dict(seen={'phase':'carry','epoch':1}),dict(frame_sha256='z'*64),dict(frame_t=float('nan'))])
def test_all_phase_heartbeat_never_revives_or_accepts_stale(change):
    h=committed(hs.PHASE_HEARTBEAT);before=copy.deepcopy(h.own)
    assert not renew(h,**change)['accepted'] and h.own==before


def test_rgb_loss_and_unknown_still_stop_and_cannot_heartbeat():
    for choice in ('grip_lost','unknown'):
        h=committed(hs.PHASE_HEARTBEAT);decide(h,'r1',choice,request=19.,now=20.)
        assert h.failure and not renew(h)['accepted'] and not h.tick(20.)


def test_inactive_or_closed_executor_never_renews():
    for phase in (None,'done','failed','aborted','idle'):
        h=committed(hs.ACTIVE_PHASE_HEARTBEAT)
        assert not renew(h,seen={**h.view('r1',19.),'own_executor_phase':phase})['accepted']
    h=committed(hs.ACTIVE_PHASE_HEARTBEAT)
    for r in hs.PAIR:h.close(r,20.)
    assert not h.tick(99.) and h.failure is None
    assert h.view('r1',99.)['phase']=='completed' and not h.allowed('r1',0)
    assert not renew(h,now=21.)['accepted']


def test_terminal_failure_survives_team_removing_endpoint(tmp_path,setup_data):
    host,driver,inner=build(tmp_path,setup_data,'no_comm');h=driver.handshake;h.carry_lease_renewal=hs.ACTIVE_PHASE_HEARTBEAT
    host.begin()
    for i in range(1,141):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t);driver.step(t)
    assert h.permits
    endpoint=driver.endpoints['r1'];endpoint.terminal=True;endpoint.controller.state='failed'
    def remove(now):
        for actor in driver.runtime.actors.values():
            if actor._pair is not None and actor._pair.terminal:actor._pair=None
    driver.runtime.team.poll=remove
    assert all(c['kind']=='hold' for r,c in driver.step(14.1))
    assert h.failure=='S3_PAIR_TERMINAL' and driver.runtime.actors['r1']._pair is None


def test_scheduler_continue_in_lower_and_align_renews_both_endpoints(tmp_path,setup_data,monkeypatch):
    original=PairWire.__call__
    def wire(self,request,**kw):
        body=json.loads(request.data);payload=json.loads(next(p['text'] for p in body['messages'][-1]['content'] if p['type']=='text'))
        if (payload.get('pair_handshake') or {}).get('phase')!='carry':return original(self,request,**kw)
        self.requests.append(bytes(request.data))
        reply=dict(request_id=payload['request_id'],action=dict(kind='continue'),decision_sources=['own_commands'],messages=[])
        raw=completion_body(json.dumps(reply),usage=FIXTURE['usage'],model='fixture-model')
        self.responses.append(raw);return io.BytesIO(raw)
    monkeypatch.setattr(PairWire,'__call__',wire)
    host,driver,inner=build(tmp_path,setup_data,'no_comm');h=driver.handshake;h.carry_lease_renewal=hs.ACTIVE_PHASE_HEARTBEAT
    host.begin()
    for i in range(1,301):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        if h.permits:
            for ep in driver.runtime.actors.values():ep._pair.controller.state='lower' if t<17 else 'align'
        driver.poll(t);host.step_to(t);driver.step(t)
    assert h.failure is None
    for phase in ('lower','align'):
        rows=[r for r in h.renewals if r['accepted'] and r['own_executor_phase']==phase]
        assert {r['robot_id'] for r in rows}==set(hs.PAIR)
        for row in rows:
            dispatch=next(d for d in host.trial.dispatch_log if d['call_id']==row['call_id'])
            assert dispatch['carry_lease_renewal']==row and row['frame_sha256']==inner[row['robot_id']].sha


def test_supported_low_com_and_floor_are_not_drop_but_unsupported_fall_is():
    g=DropGuard()
    assert not g.observe(t=0,com_z=.15,origin_z=.135,finger_contact=True,floor_contact=False)['drop']
    for i,z in enumerate((.08,.0498,.0475,.03),1):
        assert not g.observe(t=i*.05,com_z=z,origin_z=z-.015,finger_contact=True,floor_contact=False)['drop']
    assert not g.observe(t=.3,com_z=.016,origin_z=.001,finger_contact=False,floor_contact=True)['drop']
    g=DropGuard();g.observe(t=0,com_z=.15,origin_z=.135,finger_contact=True,floor_contact=False)
    g.observe(t=.05,com_z=.14,origin_z=.125,finger_contact=False,floor_contact=False)
    r=g.observe(t=.1,com_z=.12,origin_z=.105,finger_contact=False,floor_contact=False)
    assert r['drop'] and r['unsupported_descent_m']>=.02


def test_fixed_eight_default_off_and_persistent_path(capsys):
    jobs=submit.commands('a'*40);assert len(jobs)==8 and len({n for n,_ in jobs})==8
    for name,argv in jobs:
        assert 'scripts.run_s4_pair_live7' in argv and argv.count('a'*40)==1
        assert argv[argv.index('--pair-drop-guard')+1]=='contact_com_v1'
    assert run.main(['--expected-source-sha','a'*40,'--output','/tmp/not-created',
        '--condition','no_comm','--relay-receipt','/tmp/not-read'])==0
    row=json.loads(capsys.readouterr().out)
    assert row['carry_lease_renewal']==row['pair_drop_guard']=='off'
    with pytest.raises(ValueError,match='persistent'):run.persistent_output(run.Path('/dev/shm/raw'))


def test_continued_distance_excludes_lowering_and_contact_gaps():
    states=[];contacts=[];truth=[]
    for t,x,s,touch in ((1,0,'carry',True),(1.05,.02,'carry',True),
        (1.1,.5,'lower',True),(2,.6,'carry',True),(2.05,.63,'carry',True),
        (2.1,.8,'carry',False),(2.15,.9,'carry',True)):
        states.append(dict(t=t,robots={r:dict(state=s,seg=int(t>=2)) for r in hs.PAIR}))
        contacts.append(dict(t=t,contacts=[dict(geom1='cargo_beam_1_geom',geom2=r+'__'+side+'_finger')
            for r in hs.PAIR for side in ('left','right')] if touch else []))
        truth.append(dict(t=t,items={'beam_1':dict(x=x,y=0,z=.1)}))
    d=distances(states,contacts,truth)
    assert d['contact_supported_path_m']==pytest.approx(.05)
    assert d['continued_transport_path_m']==pytest.approx(.03)
    assert d['continued_transport_distance_m']==pytest.approx(.03)
