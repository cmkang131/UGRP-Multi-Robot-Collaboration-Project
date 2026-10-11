"""Fake credentials/HTTP server only; no provider, physics or active relay changes."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import inspect
import json
import threading
from types import SimpleNamespace

import pytest

from scripts import gemma_fallback_proxy as g
from tests.test_gemma_fallback_proxy import MODEL, BODY, REPLY, api

KEYS = {1:'fixture-only-credential-one', 3:'fixture-only-credential-three'}
KEYCHAIN_READER = g.keychain_key
KEYCHAIN_KEYS = g.keychain_keys


@pytest.fixture(autouse=True)
def no_real_keys(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('real Keychain forbidden')
    monkeypatch.setattr(g, 'keychain_key', forbidden)
    monkeypatch.setattr(g, 'keychain_keys', forbidden)


def engine(tmp_path, responses=None, now=None, keys=KEYS):
    calls = []
    replies = list(responses or [(200,copy.deepcopy(REPLY),{})]*30)
    def send(path, payload=None, *, key=None, secrets=()):
        if path.startswith('models?'):
            return 200, {'models':[MODEL]}, {}
        if path.endswith(':countTokens'):
            return 200, {'totalTokens':11}, {}
        calls.append((key, copy.deepcopy(payload)))
        value = replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    clock = (lambda:now[0]) if now else g.time.time
    return g.Gemma(tmp_path, send=send, clock=clock, keys=keys, multi_key_v1=True,
                   shared_quota=g.SharedQuota(tmp_path/'shared',clock=clock)), calls


def test_keychain_inventory_gaps_account_and_duplicates(monkeypatch):
    monkeypatch.setattr(g,'keychain_key',KEYCHAIN_READER)
    inventory = '\n'.join('keychain: "fixture"\n"acct"<blob>="'+account+'"\n"svce"<blob>="'+service+'"'
        for service,account in [(g.SERVICE,'aistudio'),(g.SERVICE+'-3','aistudio'),
                                (g.SERVICE+'-10','aistudio'),(g.SERVICE+'-2','other'),('unrelated','aistudio')])
    seen=[]
    def run(args, **kwargs):
        seen.append(args)
        if args == ['security','dump-keychain']:
            return SimpleNamespace(returncode=0,stdout=inventory.encode())
        assert args[-3:] == ['-a','aistudio','-w']
        service=args[args.index('-s')+1]
        return SimpleNamespace(returncode=0,stdout=(KEYS[1] if service.endswith('-10') else
            KEYS[3] if service.endswith('-3') else KEYS[1]).encode())
    monkeypatch.setattr(g.subprocess,'run',run)
    assert KEYCHAIN_KEYS() == KEYS
    assert len(seen)==4 and all('-d' not in args for args in seen)


@pytest.mark.parametrize('status',[200,403,429,503])
def test_default_off_and_single_key_legacy_equivalence(tmp_path,monkeypatch,status):
    assert inspect.signature(g.Gemma).parameters['multi_key_v1'].default is False
    now=[1791740000.]
    monkeypatch.setattr(g.time,'monotonic',lambda:10.)
    replies=[(status,copy.deepcopy(REPLY) if status==200 else {'error':'fixture reject'},
              {'Retry-After':'60'} if status==429 else {})]*30
    legacy,old_calls=api(tmp_path/'old',responses=replies,now=now)
    single,new_calls=engine(tmp_path/'new',responses=replies,now=now,keys={1:KEYS[1]})
    assert single.key_pool is None
    for i in range(12):
        request_id='legacy-'+str(i)
        assert single.complete(BODY,request_id)==legacy.complete(BODY,request_id)
    assert [p for _,p in new_calls]==[p for _,p in old_calls]
    for relative in ('shared/bucket.json','shared/reservations.jsonl','quota.json','ledger.jsonl'):
        assert (single.root/relative).read_bytes()==(legacy.root/relative).read_bytes()


def test_distribution_and_same_id_cached_after_switch(tmp_path):
    now=[1791740000.];e,calls=engine(tmp_path,now=now)
    assert e.complete(BODY,'one')[0]==200
    assert e.complete(BODY,'two')[0]==200
    assert [key for key,_ in calls]==list(KEYS.values())
    assert e.complete(BODY,'one')[0]==200 and len(calls)==2
    for index,bucket in e.key_pool.buckets.items():
        state=json.loads((bucket.root/'bucket.json').read_text())
        assert state['day_requests']==1
        row=json.loads((bucket.root/'reservations.jsonl').read_text())
        assert row['key_index']==index and row['effective_limits']==g.KeyPool.LIMITS


def test_metadata_switch_and_retry_info_cooldown(tmp_path):
    now=[1791740000.];seen=[]
    def send(path,payload=None,*,key=None,secrets=()):
        seen.append(key)
        if key==KEYS[1]:
            return 403, {'error':'fixture project unavailable'}, {'Retry-After':'120'}
        return 200, {'models':[MODEL]}, {}
    e=g.Gemma(tmp_path,send=send,multi_key_v1=True,keys=KEYS,
               shared_quota=g.SharedQuota(tmp_path/'shared',clock=lambda:now[0]),clock=lambda:now[0])
    assert seen==list(KEYS.values())
    info={'error':{'details':[{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'180s'}]}}
    e.key_pool.observe(3,503,info,{})
    assert e.key_pool.select(1,exclude={1})['retry_after_s']==180
    assert e.key_pool.select(1)['retry_after_s']==120


@pytest.mark.parametrize('status',[403,429,500,503,599])
def test_cooldown_switch_and_logical_idempotency(tmp_path,status):
    now=[1791740000.]
    e,calls=engine(tmp_path,[(status,{'error':'fixture reject'},{'Retry-After':'120'}),(200,REPLY,{})],now)
    logical=hashlib.sha256(b'logical-call').hexdigest()
    one=e.complete(BODY,'wire-1',idempotency_key=logical)
    assert one[0]==200 and [key for key,_ in calls]==list(KEYS.values())
    result=json.loads(one[1]);assert result['key_index']==3
    assert [r['status'] for r in result['ugrp_key_attempts']]==[status,200]
    assert e.complete(BODY,'wire-2',idempotency_key=logical)==one and len(calls)==2
    assert calls[0][1]==calls[1][1]==g.generate_body(json.loads(BODY))
    bucket=e.key_pool.buckets[1]
    assert json.loads((bucket.root/'bucket.json').read_text())['hold_until']>=now[0]+120
    rows=[json.loads(line) for line in (e.root/'ledger.jsonl').read_text().splitlines()]
    assert [r['key_index'] for r in rows]==[1,3]


def test_all_keys_wait_then_same_request_resumes_after_restart(tmp_path):
    now=[1791740000.]
    e,calls=engine(tmp_path,[(503,{'error':'down'},{'Retry-After':'60'})]*2,now)
    first=e.complete(BODY,'queued')
    assert first[0]==429 and first[2]=='60' and len(calls)==2
    assert e.complete(BODY,'queued')[0]==429 and len(calls)==2
    restarted=g.KeyPool(tmp_path/'shared',KEYS,clock=lambda:now[0])
    assert restarted.select(1411)['retry_after_s']==60
    with pytest.raises(g.PoolUnavailable):engine(tmp_path,now=now)
    now[0]+=61
    e2,calls2=engine(tmp_path,now=now)
    assert e2.complete(BODY,'queued')[0]==200 and len(calls2)==1
    assert e2.complete(BODY,'queued')[0]==200 and len(calls2)==1


@pytest.mark.parametrize('failure',[TimeoutError('ambiguous'),ValueError('invalid JSON')])
def test_ambiguous_result_never_switches(tmp_path,failure):
    e,calls=engine(tmp_path,[failure])
    assert e.complete(BODY,'ambiguous')[0]==502 and len(calls)==1
    assert e.complete(BODY,'ambiguous')[0]==502 and len(calls)==1


def test_independent_rpm_tpm_daily_and_legacy_key_one_state(tmp_path):
    now=[1791740000.];pool=g.KeyPool(tmp_path,KEYS,clock=lambda:now[0])
    # Pre-existing legacy reservations must remain visible to the pool.
    legacy=g.SharedQuota(tmp_path,clock=lambda:now[0])
    assert legacy.reserve(14000,request_id='active-relay',request_sha256='a'*64)['admitted']
    assert pool.select(3000)['key_index']==3
    now[0]+=61
    for q in pool.buckets.values():
        for i in range(30):
            assert q.reserve(1,request_id=str(i),request_sha256='a'*64)['admitted']
    assert pool.select(1)['retry_after_s']==60
    now[0]+=61
    for q in pool.buckets.values():
        with q.locked() as s:s['day_requests']=14400
    assert pool.select(1)['retry_after_s']>60
    now[0]=g.Quota(tmp_path/'midnight',clock=lambda:now[0]).midnight()+1
    assert pool.select(16000)['admitted']
    assert pool.select(16000)['admitted']
    assert pool.select(1)['retry_after_s']==60


def test_atomic_selection_across_pools_and_concurrent_duplicate(tmp_path):
    now=[1791740000.]
    pools=[g.KeyPool(tmp_path/'buckets',KEYS,clock=lambda:now[0]) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        rows=list(executor.map(lambda p:p.select(15000),pools))
    assert sorted(r['key_index'] for r in rows)==[1,3]
    e,calls=engine(tmp_path/'engine',now=now)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:e.complete(BODY,'same'),range(2)))
    assert results[0]==results[1] and len(calls)==1


def test_fake_http_server_header_only_redaction_switch(tmp_path,monkeypatch):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):self.reply({'models':[MODEL]})
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']))
            key=self.headers['x-goog-api-key']
            assert key not in self.path and key.encode() not in raw
            if self.path.endswith(':countTokens'):
                self.reply({'totalTokens':11});return
            seen.append(key)
            if key==KEYS[1]:
                self.reply({'error':{'message':' '.join(KEYS.values())}},503)
            else:self.reply(REPLY)
        def reply(self,body,status=200):
            raw=json.dumps(body).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(g,'API','http://127.0.0.1:'+str(server.server_port)+'/')
    try:
        e=g.Gemma(tmp_path,keys=KEYS,multi_key_v1=True,
                   shared_quota=g.SharedQuota(tmp_path/'shared'))
        assert e.complete(BODY,'http-fixture')[0]==200
        assert seen==list(KEYS.values())
        for path in tmp_path.rglob('*'):
            if path.is_file():
                assert all(key.encode() not in path.read_bytes() for key in KEYS.values())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
