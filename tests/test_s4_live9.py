import io
import json
from types import SimpleNamespace
import pytest
from tests.test_pair_llm_s4_host import no_external_work,setup_data
from tests import test_pair_llm_s4_pair as fixture
from harness.s4_pair_recovery import Driver,settle_without_commands
from scripts import run_s4_pair_live9 as run,submit_s4_live9 as submit


class InvalidAckWire(fixture.PairWire):
    def __init__(self,*,lose=False,always=False):
        super().__init__(lose=lose);self.invalid=0;self.always=always

    def __call__(self,request,**kwargs):
        stream=super().__call__(request,**kwargs)
        outer=json.loads(stream.getvalue());reply=json.loads(outer['choices'][0]['message']['content'])
        if (reply['action']['kind']=='pair_decision' and reply['action']['choice']=='ack_go'
                and reply['request_id'].endswith('_r1') and (not self.invalid or self.always)):
            self.invalid+=1;reply['messages']=[]
            outer['choices'][0]['message']['content']=json.dumps(reply)
            raw=json.dumps(outer).encode();self.responses[-1]=raw;return io.BytesIO(raw)
        return stream


@pytest.mark.parametrize('enabled,always,permits,retries',[(False,True,0,0),(True,False,1,1),(True,True,0,1)])
def test_invalid_normal_ack_reasks_once_same_epoch_without_duplicate_motion(tmp_path,setup_data,monkeypatch,enabled,always,permits,retries):
    monkeypatch.setattr(fixture,'PairWire',lambda **kw:InvalidAckWire(always=always,**kw))
    host,base,inner=fixture.build(tmp_path,setup_data,'peer_ko')
    driver=Driver(host,base.runtime,go_ack_retry=enabled)
    host.begin();moves=[]
    for i in range(1,351):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t)
        moves.extend((t,r,c) for r,c in driver.step(t) if c['kind']=='mecanum')
    assert len(driver.handshake.permits)==permits
    assert len(driver.retry_events)==retries
    if permits:
        assert {r for _,r,_ in moves}==set(fixture.hs.PAIR)
        assert all(t>=driver.handshake.permits[0]['at'] for t,_,_ in moves)
        assert driver.retry_events[0]['epoch']==driver.handshake.permits[0]['epoch']
    else:assert not moves
    assert all(len(inner[r].s3_calls)==1 for r in fixture.hs.PAIR)


def test_stopped_scheduler_censors_without_new_post_action_or_message_loss(tmp_path,setup_data):
    host,driver,inner=fixture.build(tmp_path,setup_data,'peer_ko')
    host.begin()
    for i in range(1,160):
        t=i/10
        for r,own in inner.items():own.now=t;host.links[r].capture_frame()
        driver.poll(t);host.step_to(t);driver.step(t)
    s=host.trial.scheduler
    assert s.messages and any(e['status']=='outstanding' for e in s.ledger.values())
    before=list(s.messages);host.failed=RuntimeError('synthetic terminal failure')
    row=settle_without_commands(host,t)
    assert row['before']==row['after'] and row['outstanding']==0 and s.messages==before
    assert row['censored'] and host.trial.channel_summary()['delivery_edges']==len(before)
    assert settle_without_commands(host,t)==row  # exactly once collection
    host.save(tmp_path/'closed')
    assert json.loads((tmp_path/'closed/result.json').read_text())['scheduler_settled']
    assert not s._queue and not s._pending


def test_real_upstream_inspect_pan_settle_and_fresh_frame(tmp_path,monkeypatch):
    from tests.test_s3_full_route import test_saved_floor_pan_through_outer_tick_returns_canonical_before_new_look
    test_saved_floor_pan_through_outer_tick_returns_canonical_before_new_look(tmp_path,monkeypatch)


def test_fixed_eight_plan_source_seal_and_default_off(capsys):
    from scripts import run_s4_pair_live9 as run,submit_s4_live9 as submit
    b=run.bundle('a'*40,'no_comm',602)
    assert not any(b[k] for k in ('inspect_before_look','go_ack_retry','terminal_censor'))
    assert b['case_cap_s']==600 and b['wall_cap_s']==3000
    assert b['seed']==602 and len(b['s3_release']['s3_file_sha256'])==130
    jobs=submit.commands('a'*40)
    assert len(jobs)==len({n for n,_ in jobs})==8
    for n,a in jobs:
        assert a[0]=='.venv-sim/bin/python' and a[2]=='scripts.run_s4_pair_live9'
        assert {'--inspect-before-look','--go-ack-retry','--terminal-censor'}<=set(a)
    assert run.main(['--expected-source-sha','a'*40,'--output','no-write','--condition','no_comm','--relay-receipt','no-read'])==0
    assert not json.loads(capsys.readouterr().out)['inspect_before_look']


def test_terminal_waits_fixed_settle_and_goal_needs_actual_all_leg_motion():
    from scripts.evaluate_s4_live9 import goal_metrics
    e=run.Extension(__import__('pathlib').Path('unused'),run.old.RENEWAL_MODE)
    e.pair_driver=SimpleNamespace(endpoints={r:SimpleNamespace(terminal=True) for r in ('r1','r2')})
    e.last_now=10.;assert not e.terminal()
    e.last_now=10.6;assert e.terminal()
    v=goal_metrics([[0,0],[.1,0]],[],[],[],[],{'permits':[]})
    assert v['n']==0 and v['held_segments']==[]
