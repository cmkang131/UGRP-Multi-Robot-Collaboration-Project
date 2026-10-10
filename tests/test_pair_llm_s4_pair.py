"""Real scheduler/ledger, synthetic replies and actuator doubles. No physics/model."""
import copy
import io
import json
from types import SimpleNamespace

import pytest

from harness import s4_pair_handshake as hs
from harness import s4_pair_stage as stage
from harness.zone_send_ledger import completion_body
from tests.test_pair_llm_s4_host import (make_host, setup_data, no_external_work,
    RecordedWire, StubS3Link, StubController, FIXTURE)


def action(choice, epoch=0, peer=None):
    return dict(kind='pair_decision', epoch=epoch, choice=choice, peer_go_ref=peer)


def opened():
    h = hs.Handshake()
    for r in hs.PAIR:
        h.claim(r, 'claim-'+r)
        h.open(r, 0, 10.)
    return h


def decide(h, r, choice, request=11., now=12., seen=None, epoch=0, ref=None):
    seen = h.view(r, request) if seen is None else seen
    return h.decide(r, action(choice, epoch, ref), call_id=choice+'-'+r,
        requested_at=request, now=now, frame_t=request, frame_sha256='a'*64, seen=seen)


def test_two_go_are_insufficient_and_two_fresh_seen_acks_commit():
    h = opened()
    for r in hs.PAIR:
        assert decide(h, r, 'go')['accepted']
    assert not h.tick(12.)
    assert not decide(h, 'r1', 'ack_go', request=12., ref='go-r2')['accepted']
    for r, peer in [('r1','r2'), ('r2','r1')]:
        assert decide(h, r, 'ack_go', request=12.2, now=13., ref='go-'+peer)['accepted']
    assert h.tick(13.)
    assert all(h.allowed(r, 0) for r in hs.PAIR)
    assert h.permits[0]['ack_calls'] == {'r1':'ack_go-r1', 'r2':'ack_go-r2'}
    assert not decide(h, 'r1', 'go', request=13., now=14.)['accepted']
    assert not h.tick(23.) and h.failure == 'PAIR_VISUAL_LEASE_EXPIRED'


@pytest.mark.parametrize('requested,now,epoch', [(9.,11.,0),(10.,20.,0),(11.,12.,1),(float('nan'),12.,0)])
def test_old_delayed_wrong_epoch_votes_never_authorize(requested, now, epoch):
    h = opened()
    assert not decide(h, 'r1', 'go', request=requested, now=now, epoch=epoch)['accepted']
    assert not h.tick(12.)


def test_current_epoch_cannot_ack_unseen_go_or_restart_after_loss():
    h = opened()
    saved = h.view('r1', 11.)
    for r in hs.PAIR:
        decide(h, r, 'go')
    assert not decide(h,'r1','ack_go',request=13.,now=14.,seen=saved,ref='go-r2')['accepted']
    assert decide(h,'r2','grip_lost',request=13.,now=14.)['accepted']
    assert h.failure == 'OWN_RGB_GRIP_LOST'
    assert not h.open('r1',1,15.) and not h.allowed('r1',0)


class PairWire(RecordedWire):
    def __init__(self, *, lose=False):
        super().__init__()
        self.lose = lose

    def __call__(self, request, **kwargs):
        body = json.loads(request.data)
        text = next(p['text'] for p in body['messages'][-1]['content'] if p['type']=='text')
        payload = json.loads(text)
        r = payload['robot_id']; view = payload['pair_handshake']
        if view is None or view['phase'] in ('unclaimed','align_grasp','aborted'):
            return super().__call__(request, **kwargs)
        self.requests.append(bytes(request.data))
        choice = ('grip_lost' if self.lose and r=='r2' else 'held') if view['phase']=='carry' else (
            'go' if not view['own_go_sent'] else 'ack_go' if view['peer_go_ref'] and not view['own_ack_sent'] else 'unknown')
        reply = dict(request_id=payload['request_id'], action=action(choice, view['epoch'],
            view['peer_go_ref'] if choice=='ack_go' else None), decision_sources=['own_rgb'], messages=[])
        condition = payload['condition']
        peer = 'r2' if r=='r1' else 'r1'
        if condition != 'no_comm' and choice in ('go','ack_go','grip_lost'):
            if condition == 'structured':
                reply['messages'] = [dict(recipients=[peer], reply_to=None, message=dict(
                    act='cancel' if choice=='grip_lost' else 'accept' if choice=='ack_go' else 'inform',
                    item='beam_1', zone='B', role='end_neg' if r=='r1' else 'end_pos',
                    passage=None, location_ref=None, state='absent' if choice=='grip_lost' else 'held',
                    confidence='medium', observed_at_sim_s=payload['sim_time_s'], reply_to=None))]
            else:
                reply['messages'] = [dict(recipients=[peer], text={
                    'go':'자기 영상에서 빔이 유지되어 보여 출발에 동의합니다.',
                    'ack_go':'상대의 출발 동의를 확인했고 저도 준비됐습니다.',
                    'grip_lost':'자기 영상에서 빔이 집게를 벗어나 보여 정지합니다.'}[choice], reply_to=None)]
        raw = completion_body(json.dumps(reply, ensure_ascii=False), usage=FIXTURE['usage'], model='fixture-model')
        self.responses.append(raw)
        return io.BytesIO(raw)


class Controller(StubController):
    def __init__(self):
        super().__init__()
        self.state, self.seg = 'wait_carry', 0
        self.commands = []
        self.port = SimpleNamespace(hold=lambda now: self.commands.append({'kind':'hold'}))

    def _wait_carry(self, now, arm_idle):
        self.state = 'carry'
        self.commands.append({'kind':'mecanum','left':1.,'forward':0.,'turn':0.})


def build(tmp_path, setup_data, condition, *, lose=False):
    base, _, _, _ = make_host(tmp_path, setup_data, arm=condition, wire=PairWire(lose=lose))
    inner = {r:StubS3Link(r) for r in stage.si.ROBOTS}
    actors = {}
    for r in hs.PAIR:
        ctl = Controller()
        ep = SimpleNamespace(controller=ctl, terminal=False)
        ep._clear = lambda now, c=ctl: c.commands.clear()
        def abort(now, reason, e=ep):
            e.terminal = True
        ep.abort = abort
        ep.arm_step = lambda now: []
        def step(now, c=ctl, e=ep):
            if not e.terminal:
                if c.state=='wait_carry': c._wait_carry(now, True)
                else: c.commands.append({'kind':'mecanum','left':1.,'forward':0.,'turn':0.})
            cmds, c.commands = c.commands, []
            return dict(mode='tick', commands=cmds)
        actors[r] = SimpleNamespace(robot_id=r, _pair=ep, step=step)
    h = hs.Handshake()
    links = {}
    for r, own in inner.items():
        own.order = dict(order_id='order-1' if r=='r3' else 'order-5', destination_zone='A' if r=='r3' else 'B')
        links[r] = stage.Link(own, condition=condition, executor=actors.get(r), handshake=h)
        links[r].capture_frame()
    ledger = base.trial.send_ledger; ledger._owner = ledger._authorize = None
    host = stage.Host(setup_data[0], condition=condition, links=links, seed=601, map_bundle=setup_data[1],
        model_adapter=stage.old.s4.zi.ModelAdapter(base.trial.client_factory,ledger), horizon_s=45.)
    driver = stage.Driver(host, SimpleNamespace(actors=actors, team=SimpleNamespace(poll=lambda now: None)))
    return host, driver, inner


@pytest.mark.parametrize('condition', stage.old.CONDITIONS)
def test_scheduler_claim_go_ack_actuator_and_own_rgb_loss(tmp_path, setup_data, condition):
    host, driver, inner = build(tmp_path, setup_data, condition, lose=True)
    host.begin(); trace = []
    for i in range(1,351):
        t = i/10
        for r, own in inner.items():
            own.now = t; host.links[r].capture_frame()
        driver.poll(t); host.step_to(t)
        trace.extend((t,r,c) for r,c in driver.step(t))
    h = driver.handshake
    assert len(h.permits)==1, h.record()
    moves = [(t,r,c) for t,r,c in trace if c['kind']=='mecanum']
    assert moves and {r for _,r,_ in moves} == set(hs.PAIR)
    assert all(t>=h.permits[0]['at'] for t,_,_ in moves)
    loss = next(d for d in h.decisions if d['accepted'] and d['action']['choice']=='grip_lost')
    assert not any(t>=loss['at'] for t,_,_ in moves)
    assert all(a._pair.terminal for a in driver.runtime.actors.values())
    assert len(inner['r1'].s3_calls)==len(inner['r2'].s3_calls)==1
    assert h.failure=='OWN_RGB_GRIP_LOST'
    assert all(d['frame_sha256']==inner[d['robot_id']].sha for d in h.decisions)
    assert len({r['billed_tokens']['system_billed'] for r in host.trial.requests})==1
    channel = host.trial.channel_summary()
    if condition=='no_comm':
        assert not host.trial.envelopes
    else:
        assert host.trial.envelopes, channel
        assert all(e['encoding']==('schema' if condition=='structured' else 'free_ko')
                   for e in host.trial.envelopes.values())
    assert stage.components() == (stage.old.Link, stage.old.Host)
    (tmp_path/'handshake.json').write_text(json.dumps(h.record(), indent=2))
    (tmp_path/'stub-commands.json').write_text(json.dumps(trace))
    host.save(tmp_path/'llm')


def test_failed_or_missing_ack_never_releases_and_default_rejects_new_action(tmp_path, setup_data):
    host, driver, inner = build(tmp_path, setup_data, 'no_comm')
    raw = dict(request_id='req_fixture', action=action('go'), decision_sources=['own_rgb'], messages=[])
    kw = dict(request_id='req_fixture',condition='no_comm',actor='r1',order_ids=['order-5'])
    with pytest.raises(stage.pair.zp.ProtocolError): stage.pair.validate_reply(raw, **kw)
    raw['decision_sources'] = ['own_commands']
    with pytest.raises(stage.pair.zp.ProtocolError): stage.validate_reply(raw, **kw)
    h = opened(); decide(h,'r1','go')
    assert not h.tick(30.) and h.failure=='PAIR_GO_TIMEOUT'


def test_same_tick_partner_abort_removes_earlier_movement_and_arm_queue(tmp_path, setup_data):
    host, driver, inner = build(tmp_path, setup_data, 'no_comm')
    for r in hs.PAIR:
        driver.handshake.claim(r, 'claim-'+r)
        host.links[r].pair_started = True
    driver.runtime.actors['r1']._pair.controller.state = 'carry'
    later = driver.runtime.actors['r2']
    def fail(now):
        later._pair.terminal = True
        return dict(mode='tick', commands=[{'kind':'arm','servo_id':1,'pulse':2000}])
    later.step = fail
    assert driver.step(1.) == [('r1',{'kind':'hold'}),('r2',{'kind':'hold'})]
    assert all(a._pair.terminal for a in driver.runtime.actors.values())


def test_release_blocks_execution_and_memory_retry_preserves_exact_command(monkeypatch):
    from scripts import run_s4_pair_preparation as prep
    from scripts import submit_s4_pair_batch as batch
    with pytest.raises(ValueError, match='WAITING_FOR_S3FIX13'):
        prep.validate_release(json.loads(batch.RELEASE.read_text()))
    rows = batch.commands('a'*40)
    assert len(rows)==4 and len({n for n,_ in rows})==4
    seen=[]; waits=[]
    def invoke(argv, **kwargs):
        seen.append(copy.deepcopy(argv))
        return SimpleNamespace(returncode=3 if len(seen)==1 else 0, stdout='', stderr='')
    result=batch.submit_one('/tmp/oracle_run.sh','/tmp/wt',*rows[0],invoke=invoke,wait=waits.append)
    assert result['returncode']==0 and seen[0]==seen[1] and waits==[30.]
    assert batch.submit_one('/tmp/r','/tmp/wt',*rows[0],
        invoke=lambda *a,**kw:SimpleNamespace(returncode=2,stdout='',stderr=''),wait=waits.append)['admission_attempts']==1
