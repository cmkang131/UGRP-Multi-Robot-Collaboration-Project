"""Offline fault injection only: no real model, physics or renderer."""
import copy
import hashlib
import json
import threading
from urllib.error import URLError

import pytest
from tests.test_pair_llm_s4_host import no_external_work, setup_data
from tests import test_pair_llm_s4_pair as fixture
from harness import pair_llm_live as live, s4_pair_epochs as ep, s4_reply_contract as rc
from harness.s4_relay_journal import Journal
from harness.s4_tunnel_recovery import TunnelRecoveryMixin
from scripts.s4_reverse_tunnel import supervise
from harness.zone_study_llm_driver import HostError
from urllib.request import Request


@pytest.mark.parametrize('condition', ['no_comm', 'peer_ko', 'leader_ko', 'structured'])
def test_disconnect_same_request_hold_and_single_action(tmp_path, setup_data, monkeypatch, condition):
    original=live.PairLiveLedger; wire=fixture.PairWire(); requests=[]; keys=[]; waits=[]
    state={'SIM': 0, 'commands': 0}
    class Ledger(TunnelRecoveryMixin, original):
        def __init__(self, **kwargs):
            super().__init__(tunnel_recovery=True, retry_429=True, sleep=waits.append, **kwargs)
            self.retry_snapshot=lambda:copy.deepcopy(state)
    def send(request, **kwargs):
        requests.append(request.data); keys.append(request.get_header('X-ugrp-idempotency-key'))
        if len(requests)<3: raise URLError('injected tunnel disconnect')
        return wire(request, **kwargs)
    monkeypatch.setattr(live, 'PairLiveLedger', Ledger)
    monkeypatch.setattr(fixture, 'PairWire', lambda **kw:send)
    def handshake(**kw):
        h=ep.Handshake(go_ack_rounds=True, epoch_reconnect=True,
            carry_lease_renewal=ep.hs.ACTIVE_PHASE_HEARTBEAT)
        h.retry_429=True; h.reply_contract=True; return h
    monkeypatch.setattr(fixture.hs, 'Handshake', handshake)
    monkeypatch.setattr(fixture.stage, 'Host', rc.Host)
    host,base,inner=fixture.build(tmp_path, setup_data, condition)
    host.begin()
    for i in range(1, 301):
        t=i/10; state['SIM']=t
        for own in inner.values(): own.now=t
        for link in host.links.values(): link.capture_frame()
        base.poll(t); host.step_to(t); state['commands']+=len(base.step(t))
    ledger=host.trial.send_ledger
    assert requests[0]==requests[1]==requests[2] and keys[0]==keys[1]==keys[2]
    assert len(keys[0])==64 and waits==[2.,4.]
    assert all(r['tunnel_recovered'] for r in ledger.entries[:2])
    assert all(r['hold_verified'] for r in ledger.retry_events if r['status']=='RESUMED')
    assert all(len(inner[r].s3_calls)==1 for r in ep.hs.PAIR)
    assert len(base.handshake.permits)==1
    assert not host.trial.scheduler.send_violations and not host.trial.scheduler.unreported_attempts


def test_response_cached_before_disconnected_client_retry(tmp_path):
    journal=Journal(tmp_path); key=hashlib.sha256(b'logical-request').hexdigest(); calls=[]
    def upstream(): calls.append(1); return 200,b'{"reply":"GO"}',None
    first,mode=journal.call(key,b'body',upstream)
    # Discard first reply, as when SSH dies after the upstream response.
    second,mode2=journal.call(key,b'body',upstream)
    assert first==second and mode=='forwarded' and mode2=='cached' and calls==[1]
    third,mode3=Journal(tmp_path).call(key,b'body',upstream)
    assert third==first and mode3=='cached' and calls==[1]
    assert journal.call(key,b'changed',upstream)[0][0]==409 and calls==[1]


def test_inflight_duplicate_waits_for_one_upstream(tmp_path):
    j=Journal(tmp_path); key='a'*64; entered=threading.Event(); finish=threading.Event(); calls=[]; results=[]
    def forward(): calls.append(1); entered.set(); assert finish.wait(2); return 200,b'{}',None
    one=threading.Thread(target=lambda:results.append(j.call(key,b'body',forward)))
    two=threading.Thread(target=lambda:results.append(j.call(key,b'body',forward)))
    one.start(); assert entered.wait(2); two.start(); finish.set(); one.join(2);two.join(2)
    assert calls==[1] and sorted(v[1] for v in results)==['cached','forwarded']


def test_ambiguous_crash_never_repeats_upstream(tmp_path):
    j=Journal(tmp_path); key='b'*64
    (tmp_path/(key+'.json')).write_text(json.dumps(dict(state='pending',request_sha256=hashlib.sha256(b'body').hexdigest())))
    def prohibited(): raise AssertionError('duplicate ambiguous upstream')
    assert j.call(key,b'body',prohibited)[0][0]==503


def test_duplicate_429_respects_retry_after(tmp_path):
    now=[0.]; j=Journal(tmp_path,clock=lambda:now[0]); calls=[]
    def upstream(): calls.append(1); return 429,b'{"error":"quota"}','60'
    assert j.call('a'*64,b'body',upstream)[1]=='forwarded'
    now[0]=59
    assert j.call('a'*64,b'body',upstream)[1]=='rate_limited' and calls==[1]
    now[0]=60
    assert j.call('a'*64,b'body',upstream)[1]=='forwarded' and calls==[1,1]


@pytest.mark.parametrize('enabled,attempts',[(False,1),(True,7)])
def test_exhausted_transport_is_host_error_before_another_command(enabled,attempts):
    class Wire:
        def __init__(self):
            self.entries=[]; self.store_dir=None; self.run_key='offline'; self.fatal=None
        def _send(self,*args):
            self.entries.append(dict(seq=len(self.entries)+1,body_sha256='a'*64))
            raise URLError('injected unavailable tunnel')
    class Ledger(TunnelRecoveryMixin,Wire): pass
    value=Ledger(tunnel_recovery=enabled,sleep=lambda s:None)
    request=Request('http://fixture',data=b'unchanged request_id')
    with pytest.raises(HostError if enabled else URLError):
        value._send('request-1','r1',request,180)
    assert len(value.entries)==attempts
    assert isinstance(value.fatal,HostError) if enabled else value.fatal is None


@pytest.mark.parametrize('enabled,expected',[(False,1),(True,2)])
def test_finite_tunnel_restart_only_own_child(tmp_path,enabled,expected):
    now=[0.];procs=[];commands=[]
    class Proc:
        pid=42
        def __init__(self,*args,**kwargs):
            commands.append(args[0]); self.returncode=None; self.start=now[0];procs.append(self)
        def poll(self):
            if now[0]-self.start>=2:self.returncode=255
            return self.returncode
        def terminate(self):self.returncode=-15
        def wait(self,**kw):return self.returncode
    def sleep(s):now[0]+=s
    assert supervise(15,tmp_path/'tunnel',reconnect=enabled,popen=Proc,clock=lambda:now[0],sleep=sleep)==expected
    assert all('ServerAliveInterval=15' in c and 'ServerAliveCountMax=3' in c for c in commands)
    assert all(p.poll() is not None for p in procs)


def test_own_map_admission_precedes_any_execution(tmp_path,monkeypatch):
    from scripts import run_s4_pair_live12 as run
    with pytest.raises(ValueError,match='OWN_MAP_TRANSPORT_NOT_CONNECTED'):
        run.run({},tmp_path/'never_created',tmp_path/'never_read')
    assert not (tmp_path/'never_created').exists()
    import inspect
    assert inspect.signature(run.bundle).parameters['tunnel_recovery'].default is False


def test_absolute_deadline_stops_owned_group_and_records_dev(tmp_path,monkeypatch):
    from scripts import s4_deadline_run as gate
    now=[100.];killed=[]
    monkeypatch.setattr(gate.Path,'home',lambda:tmp_path)
    root=tmp_path/'ugrp-sim/runs/owned';root.mkdir(parents=True)
    monkeypatch.setattr(gate.time,'time',lambda:now[0])
    class Proc:
        pid=9001;returncode=None
        def poll(self):return self.returncode
        def wait(self,timeout):
            if self.returncode is None:
                now[0]+=timeout
                raise gate.subprocess.TimeoutExpired('offline',timeout)
            return self.returncode
    child=Proc()
    monkeypatch.setattr(gate.subprocess,'Popen',lambda *a,**kw:child)
    def kill(pgid,sig):killed.append(pgid);child.returncode=-15
    monkeypatch.setattr(gate.os,'killpg',kill)
    assert gate.run(['offline-only'],root,110.,'a'*40)==124
    meta=json.loads((root/'RUN_META.json').read_text())
    assert meta['class']=='dev' and meta['pr']==425 and killed==[9001]
    assert now[0] <= 110 and meta['effective_deadline_unix']==105
    assert json.loads((root/'deadline-stop.json').read_text())['classification']=='HOST_ERROR'
