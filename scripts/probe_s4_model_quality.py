"""Eight bounded API-only replies on four saved initial claims; executes no action."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request
from harness import s4_compact_prompt as cp
from harness.s4_pair_stage import validate_reply
from harness.zone_study_llm_driver import load_registry,live_proxy
from harness.zone_study_llm_transport import no_redirect_opener
from scripts.probe_s4_compact_tokens import saved_request,wire
from scripts.gemma_fallback_proxy import Gemma


def judge(response,body,condition):
    choice=(response.get('choices')or[{}])[0];raw=choice.get('message',{}).get('content','')
    errors=[];value=None
    try:
        if choice.get('finish_reason')!='stop':raise ValueError('non_normal_completion')
        value=validate_reply(raw,request_id=body['request_id'],condition=condition,actor='r1',
            order_ids=['order-1','order-5'],item_ids=['beam_1'],roles_by_order={'order-1':['west'],'order-5':['end_neg','end_pos']})
        if value['action']!={'kind':'claim','order_id':'order-5','role':'end_neg','destination_zone':'B'}:
            errors.append('initial_own_claim_not_selected')
        for m in value['messages']:
            if not set(m['recipients'])<=set(body['channel']['can_send_to']):errors.append('channel_topology')
            if cp.re.search('[\uac00-\ud7a3]',m.get('text','')):errors.append('language_not_english')
        if 'static_map' in value['decision_sources']:errors.append('removed_source_cited')
    except Exception as e:errors.append(str(e))
    return dict(passed=not errors,errors=errors,response_text=raw,
                scope='initial claim syntax/own role/channel only; no physical or visual-grasp correctness claim')


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True)
    p.add_argument('--images',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gemini-pid',type=int,required=True);a=p.parse_args(argv)
    a.output.mkdir(parents=True,exist_ok=False)
    profile=load_registry()['driver_profiles']['main_study_gemini_v1']
    identity,_=live_proxy(profile,a.gemini_pid)
    engine=Gemma(a.output/'gemma',expected_model='gemma-4-31b-it',expected_version='001',standard=True)
    tasks=[]
    for c in ('no_comm','peer_ko','leader_ko','structured'):
        source=a.raw_root/f's4live11-{c}-s601-v182/raw/llm/requests.json'
        r=cp.transform(saved_request(source,'call-0001-r1',a.images),compact=True,lang='en')
        for model in ('gemma-4-31b-it','gemini-3.8-flash'):
            tasks.append((c,model,r))
    def call(task):
        c,model,r=task;w=wire(r,model);raw=json.dumps(w).encode();request_id=f's4-standard-quality-{c}-{model}'
        started=time.monotonic()
        if model.startswith('gemma'):
            status,response,_=engine.complete(raw,request_id)
        else:
            current,_=live_proxy(profile,a.gemini_pid)
            if current!=identity:raise ValueError('Gemini identity changed')
            req=Request(profile['proxy_url'],data=raw,headers={'Content-Type':'application/json','X-UGRP-Call-ID':request_id})
            try:
                with no_redirect_opener().open(req,timeout=180) as reply:status,response=reply.status,reply.read(8_000_000)
            except HTTPError as e:status,response=e.code,e.read(8_000_000)
        value=json.loads(response);body=json.loads(r['messages'][1]['content'])
        result=dict(condition=cp.external_condition(c),requested_model=model,actual_model=value.get('model'),
            http_status=status,wall_s=time.monotonic()-started,usage=value.get('usage'),
            request_sha256=hashlib.sha256(raw).hexdigest(),request_id=request_id,
            system=r['messages'][0]['content'],user=r['messages'][1]['content'],image_refs=r['image_refs'],
            response=value,judgement=judge(value,body,c))
        (a.output/(request_id+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(call,tasks))
    summary=dict(research_result=False,scope='paired same-input initial-claim protocol probe; not general quality equivalence',
        physical_calls=0,model_calls=len(results),results=[{k:r[k] for k in ('condition','requested_model','actual_model','http_status','wall_s','usage','judgement')} for r in results])
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
