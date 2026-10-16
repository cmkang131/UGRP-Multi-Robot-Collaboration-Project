"""Actual Code speech assembly + retry fault injection; no provider or physics."""
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request
import pytest
from scripts.s4_proxy_relay import complete_dialogue
from scripts.d1_dialogue_upstream import Code
from harness.s4_tunnel_recovery import TunnelRecoveryMixin
from tests.test_e2e_dialogue_decider import user, request, speech, dd


@pytest.mark.parametrize('status,retry_after', [(402,None),(429,'60'),(503,'2')])
def test_speech_failure_preserves_status_body_and_retry_after(tmp_path,status,retry_after):
    body=user();body['dialogue_decider']=dd.CODE_MODE
    expected=(status,b'{"error":"provider failure"}',retry_after)
    seen=[]
    def send(raw,call_id,**kw):
        seen.append(kw['idempotency_key']);return expected
    result=complete_dialogue(Code(tmp_path),SimpleNamespace(complete=send),
        json.dumps(request(body)).encode(),'offline','a'*64)
    assert result==expected and len(seen)==1
    assert not (tmp_path/'speech.jsonl').exists()  # no action/message assembled


def test_success_assembly_retains_normal_contract(tmp_path):
    body=user();body['dialogue_decider']=dd.CODE_MODE
    fallback=SimpleNamespace(complete=lambda *a,**k:(200,json.dumps(speech()).encode(),None))
    status,raw,retry=complete_dialogue(Code(tmp_path),fallback,json.dumps(request(body)).encode(),'offline','b'*64)
    assert status==200 and retry is None
    reply=json.loads(raw)
    assert json.loads(reply['choices'][0]['message']['content'])['action']['choice']=='GO'


def test_402_is_not_a_tunnel_retry():
    class Wire:
        def __init__(self):
            self.entries=[];self.store_dir=None;self.run_key='offline';self.fatal=None
        def _send(self,*args):
            self.entries.append(dict(seq=1,body_sha256='a'*64))
            raise HTTPError('http://fixture',402,'Payment Required',{},io.BytesIO(b'{}'))
    class Ledger(TunnelRecoveryMixin,Wire):pass
    waits=[];ledger=Ledger(tunnel_recovery=True,sleep=waits.append)
    with pytest.raises(HTTPError) as exc:
        ledger._send('call','r1',Request('http://fixture',data=b'{}'),1)
    assert exc.value.code==402 and len(ledger.entries)==1 and not waits
    assert ledger.fatal is None
