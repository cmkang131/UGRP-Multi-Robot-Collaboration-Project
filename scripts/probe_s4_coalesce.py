"""Five paired saved-input API probes through the multi-key Gemma gateway.

Ten logical generateContent requests, at most three attempts each (30 total).
No simulated action, live service mutation, or physics. Metadata/countTokens
calls are counted separately. One missing/failed pair is never called a match.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from harness import s4_compact_prompt as cp
from harness.s4_pair_stage import validate_reply
from scripts.probe_s4_compact_tokens import saved_request, wire
from scripts.gemma_fallback_proxy import Gemma, google, generate_body, keychain_keys


def decision(response,body):
    try:
        choice=response['choices'][0]
        if choice['finish_reason']!='stop':raise ValueError('non_normal_completion')
        value=validate_reply(choice['message']['content'],request_id=body['request_id'],
            condition=cp.legacy_condition(body['condition']),actor=body['robot_id'],
            order_ids=['order-1','order-5'],item_ids=['beam_1'],
            roles_by_order={'order-1':['west'],'order-5':['end_neg','end_pos']})
        if 'static_map' in value['decision_sources']:raise ValueError('removed_source_cited')
        if any(not set(m['recipients'])<=set(body['channel']['can_send_to']) for m in value['messages']):
            raise ValueError('channel_topology')
        return dict(valid=True,action=value['action'])
    except (KeyError,IndexError,ValueError,TypeError) as exc:
        return dict(valid=False,error=type(exc).__name__+':'+str(exc)[:180])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--images',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    a.output.mkdir(parents=True,exist_ok=False)
    keys=keychain_keys()
    if len(keys)<2:raise ValueError('multi-key probe requires at least two registered keys')
    calls=Counter();rows=[];pairs=[]
    def send(path,payload=None,**kwargs):
        kind='generation' if path.endswith(':generateContent') else 'countTokens' if path.endswith(':countTokens') else 'models_list'
        if kind=='generation' and calls[kind]>=30:raise AssertionError('generation cap')
        calls[kind]+=1
        return google(path,payload,timeout=40,**kwargs)
    source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    summary=dict(research_result=False,source_sha=source_sha,physical_calls=0,render_calls=0,
                 key_count=len(keys),generation_cap=30,scope='saved-input protocol/action comparison; not visual or physical success')
    def save():
        summary.update(api_calls=dict(calls),rows=rows,pairs=pairs)
        summary['paired_action_matches']=sum(p['action_match'] is True for p in pairs)
        summary['valid_pairs']=sum(p['both_valid'] for p in pairs)
        summary['pair_denominator']=len(pairs)
        (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    try:
        engine=Gemma(a.output/'gemma',send=send,expected_model='gemma-4-31b-it',expected_version='001',
                     standard=True,multi_key_v1=True,keys=keys)
    except Exception as exc:
        summary.update(status='HOST_ERROR',startup_error=type(exc).__name__);save();return 1
    cases=[(c,'call-0001-r1') for c in ('no_comm','peer_ko','leader_ko','structured')]
    cases.append(('peer_ko','call-0261-r1'))
    for condition,call_id in cases:
        source=a.raw_root/f's4live11-{condition}-s601-v182/raw/llm/requests.json'
        original=saved_request(source,call_id,a.images)
        all_rows=json.loads(source.read_text());before=[]
        for row in all_rows:
            if row['call_id']==call_id:break
            if row['robot']=='r1':before=row
        seen={m['message_id'] for m in json.loads(before['user']).get('inbox',[])} if before else set()
        historical=next((r['action'] for r in json.loads((source.parent/'dispatch.json').read_text()) if r['call_id']==call_id),None)
        pair=[]
        for variant in ('baseline','trim'):
            if calls['generation']+len(keys)>30:
                summary.update(status='BUDGET_STOP',unfinished_case=condition+':'+call_id+':'+variant)
                save();return 1
            r=cp.transform(original,compact=True,lang='en',context_trim_v1=variant=='trim',
                           map_as_image_v1=variant=='trim',seen_message_ids=seen)
            raw=json.dumps(wire(r)).encode();rid=f'coalesce-{condition}-{call_id}-{variant}'
            try:
                status,response,_=engine.complete(raw,rid);value=json.loads(response)
            except Exception as exc:
                status,value=502,dict(error=type(exc).__name__,failure_class='HOST_ERROR',
                                      scope='local exception; upstream HTTP status unknown')
            body=json.loads(r['messages'][1]['content']);judged=decision(value,body)
            record=dict(case=condition+':'+call_id,variant=variant,http_status=status,
                source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                request_sha256=hashlib.sha256(raw).hexdigest(),system=r['messages'][0]['content'],
                user=r['messages'][1]['content'],image_refs=r['image_refs'],response=value,judgement=judged,
                historical_action=historical,old_action_match=judged.get('action')==historical if judged['valid'] and historical else None)
            (a.output/(rid+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
            small={k:v for k,v in record.items() if k not in ('system','user','response','image_refs')}
            small.update(count_tokens=value.get('ugrp_count_tokens',{}).get('totalTokens'),
                retry_metrics=value.get('ugrp_retry_metrics'),failure_class=value.get('failure_class'),usage=value.get('usage'))
            rows.append(small);pair.append(small);save()
            print(json.dumps({k:small[k] for k in ('case','variant','http_status','count_tokens','judgement')}),flush=True)
        valid=all(r['judgement']['valid'] for r in pair)
        pairs.append(dict(case=condition+':'+call_id,both_valid=valid,
            action_match=pair[0]['judgement'].get('action')==pair[1]['judgement'].get('action') if valid else None))
        save()
    # Isolate the requested historical static text -> existing figure change.
    # This diagnostic input is counted, never generated/executed for own-map B.
    map_counts=[]
    for image_only in (False,True):
        r=cp.transform(original,lang='en',map_as_image_v1=image_only)
        try:
            count=engine.count_tokens(generate_body(wire(r)))
        except Exception as exc:
            count=dict(totalTokens=None,error=type(exc).__name__)
        map_counts.append(dict(map_as_image_v1=image_only,totalTokens=count['totalTokens'],error=count.get('error'),image_refs=r['image_refs'],
            request_sha256=r['request_sha256'],scope='legacy static-map token diagnostic only; not an own-map admissible input'))
    summary['legacy_map_counts']=map_counts;summary['status']='COMPLETE';save()


if __name__=='__main__':main()
