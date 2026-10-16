"""Offline actual scheduler/ledger tests, forbidden sockets/world/renderer."""
import copy,email.message,io,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError
import pytest
from tests.test_pair_llm_s4_host import no_external_work,setup_data
from tests import test_pair_llm_s4_pair as fixture
from harness import pair_llm_live as live,s4_pair_epochs as ep,s4_reply_contract as rc
from harness.s4_call_recovery import RetryMixin,server_delay
from scripts import run_s4_pair_live11 as run,submit_s4_live11 as submit


def error(code=429,after='2',body='rate limit'):
    h=email.message.Message()
    if after is not None:h['Retry-After']=after
    return HTTPError('http://fixture',code,'limited',h,io.BytesIO(body.encode()))


@pytest.mark.parametrize('value,expected',[('7',7),('Sun, 11 Oct 2026 00:00:09 GMT',9),('bad',0)])
def test_retry_after_seconds_date(value,expected):
    now=datetime(2026,10,11,tzinfo=timezone.utc).timestamp()
    assert server_delay({'Retry-After':value},'',now)==expected
    assert server_delay({},'Individual quota reached. Resets in 2h34m0s.',now)==9240


def make(tmp_path,setup_data,monkeypatch,condition,*,faults=2,code=429,after='2',enabled=True,body='rate limit'):
    original=live.PairLiveLedger;waits=[];wire=fixture.PairWire();actual=[];state={'time':0.,'commands':0}
    class Ledger(RetryMixin,original):
        def __init__(self,**kwargs):
            def sleep(delay):
                # Same SIM cursor and command count throughout a synchronous wall wait.
                before=copy.deepcopy(state);waits.append(delay);assert state==before
            super().__init__(retry_429=enabled,sleep=sleep,**kwargs)
    def send(request,**kwargs):
        actual.append(request.data)
        if len(actual)<=faults:raise error(code,after,body)
        return wire(request,**kwargs)
    monkeypatch.setattr(live,'PairLiveLedger',Ledger)
    monkeypatch.setattr(fixture,'PairWire',lambda **kw:send)
    def handshake(**kw):
        h=ep.Handshake(go_ack_rounds=True,epoch_reconnect=True,carry_protocol_feedback=True,
            carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT)
        h.retry_429=enabled;h.reply_contract=True;return h
    monkeypatch.setattr(fixture.hs,'Handshake',handshake)
    monkeypatch.setattr(fixture.stage,'Host',rc.Host)
    host,base,inner=fixture.build(tmp_path,setup_data,condition)
    return host,base,inner,actual,waits,state


@pytest.mark.parametrize('condition',['no_comm','peer_ko','leader_ko','structured'])
def test_429_retry_same_request_exact_accounting_and_single_claim(tmp_path,setup_data,monkeypatch,condition):
    host,base,inner,requests,waits,state=make(tmp_path,setup_data,monkeypatch,condition)
    host.begin()
    for i in range(1,301):
        t=i/10;state['time']=t
        for r,o in inner.items():o.now=t;host.links[r].capture_frame()
        base.poll(t);host.step_to(t);state['commands']+=len(base.step(t))
    ledger=host.trial.send_ledger
    assert len(waits)==2 and waits[1]>waits[0]>=2
    assert requests[0]==requests[1]==requests[2]
    assert not live.rate_limited_rows(ledger)
    assert [r['rate_limit_recovered'] for r in ledger.entries[:2]]==[True,True]
    assert all(r['error_response']['sha256'] for r in ledger.entries[:2])
    assert not host.trial.scheduler.send_violations
    assert not host.trial.scheduler.unreported_attempts
    assert len({r['budget_request_id'] for r in ledger.entries})==len(ledger.entries)
    assert all(len(inner[r].s3_calls)==1 for r in ep.hs.PAIR)
    assert len(base.handshake.permits)==1
    body=json.loads(next(v['text'] for v in json.loads(requests[0])['messages'][1]['content'] if v['type']=='text'))
    contract=body['reply_contract'];assert contract['schema']['required']==['request_id','action','decision_sources','messages']
    assert contract['example']['request_id']==body['request_id'] and contract['native_schema_enforced'] is False
    retried=next(c for c in host.trial.scheduler.calls if c.call_id==ledger.entries[0]['call_id'])
    assert retried.notes['usage_known'] is False


@pytest.mark.parametrize('enabled,code,after,body',[(False,429,'2','limit'),(True,400,'2','bad'),(True,429,'400','limit'),(True,429,None,'Individual quota reached. Resets in 2h34m0s.')])
def test_no_retry_for_disabled_non429_or_long_quota(tmp_path,setup_data,monkeypatch,enabled,code,after,body):
    host,base,inner,requests,waits,state=make(tmp_path,setup_data,monkeypatch,'no_comm',faults=100,
        enabled=enabled,code=code,after=after,body=body)
    try:host.begin();host.step_to(1.)
    except Exception:pass
    assert not waits
    assert len(requests)==1 if code==429 else len(requests)>=1
    assert not any(o.s3_calls for o in inner.values())


def test_preregistered_options_and_s3_bytes():
    import hashlib
    b=run.bundle('a'*40,'no_comm');assert all(b[k] is False for k in ('retry_429','reply_contract','clipped_backoff'))
    plan=json.loads((run.ROOT/run.RECORD/'plan.json').read_text())
    assert len(plan['runs'])==8 and plan['max_concurrent']==4
    assert len(submit.commands('a'*40,wave=601))==len(submit.commands('a'*40,wave=602))==4
    release=json.loads((run.ROOT/run.RECORD/'release.json').read_text())
    sources=next(v for k,v in release.items() if isinstance(v,dict) and 'harness/zone_s3_reacquire.py' in v)
    assert len(sources)==130
    assert all(hashlib.sha256((run.ROOT/p).read_bytes()).hexdigest()==h for p,h in sources.items())


def test_upstream_backoff_actual_port_and_two_pulse_bound(tmp_path,monkeypatch):
    from tests.test_s3_full_route import test_rgb_clipped_reverse_actual_port_minimum_single_axis_and_bounded_gate
    test_rgb_clipped_reverse_actual_port_minimum_single_axis_and_bounded_gate(tmp_path,monkeypatch)
