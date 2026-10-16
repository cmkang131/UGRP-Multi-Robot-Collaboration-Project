import pytest
from harness import body_decider_upstream as m


def payload(backend):return dict(backend=backend,call_id='test',state='own state',instructions='pick',candidates={'go':'go','hold':'hold'},image_jpeg_b64='eA==')


def test_jev_uses_pinned_model_without_image_and_keeps_receipts():
    sent=[];journal=[]
    def send(body,url,key,timeout):
        sent.append(body)
        return dict(status='ok',body={'answers':{'action':{'choice':'go','probabilities':{'go':.8,'hold':.2},'confidence':.8}},'usage':{'cost':.1}},latency_s=.2)
    r=m.decide(payload('jev'),keys={'jev':'secret'},send=send,journal=journal.append)
    assert r['choice']=='go' and sent[0]['model']=='jev-1.13.0' and 'images' not in sent[0]
    assert journal[0]['request']['state']=='own state' and journal[0]['response']['usage']['cost']==.1


def test_paid_d1_failure_does_not_fallback_to_free():
    sent=[]
    r=m.decide(payload('liquid_d1'),keys={'liquid':'secret'},send=lambda body,*args:sent.append(body) or {'status':'http_error','http_status':429})
    assert r['status']=='failed' and [b['model'] for b in sent]==['d1']


@pytest.mark.parametrize('reply',[{'choice':'bad'}, {'choice':'go','probabilities':{'go':float('nan')}}, {'choice':'go','probabilities':{'bad':1.}}])
def test_invalid_choices_rejected(reply):
    with pytest.raises(ValueError):m.parse({'answers':{'action':reply}}, {'go':'go','hold':'hold'})
