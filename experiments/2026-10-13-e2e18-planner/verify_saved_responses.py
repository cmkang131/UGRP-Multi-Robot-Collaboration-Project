"""Replay saved outputs and verify original wire hashes; zero new model calls. Run from repo root."""
from pathlib import Path
import json, hashlib
from collections import Counter
from scripts.evaluate_task_planner import adapt, ARMS, supplements
from harness.task_planner import ModelReply, signature
root=Path.cwd();out=root/'outputs/task-planner-v357-full-20261013'
source=root/'outputs/task-planner-v357-source-20261013'
rows=json.loads((source/'cases_public.json').read_text())
index={(r['case_id'],r['condition']):r for r in rows}
count=0;requests=0;failures=Counter();errors=Counter();costs=0;recovered=[]
for line in (out/'calls.jsonl').open():
    saved=json.loads(line);p,ctx,labels=adapt(index[saved['case_id'],ARMS[saved['condition']]],saved['condition'])
    old=[x for x in saved['audit'] if 'request' in x];pos=[0]
    def replay(request,**kw):
        row=old[pos[0]];pos[0]+=1
        # Old audit used a mutable ctx reference. Recover only the preceding
        # refusals; prove every recovered request against the captured wire hash.
        expected=json.loads(json.dumps(row['request']))
        prior=[dict(attempt=i,reason=r['rejection']) for i,r in enumerate(old[:pos[0]-1]) if 'rejection' in r]
        expected['input'].pop('refusals',None)
        if prior:expected['input']['refusals']=prior
        if request!=expected:raise BaseException(('INPUT_CHANGED',saved['case_id'],pos[0]))
        body=dict(model='gemma-4-31b-it',temperature=0,max_tokens=320,
            messages=[dict(role='system',content=request['system']),
                      dict(role='user',content=json.dumps(request['input'],ensure_ascii=True))])
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        if digest!=row['usage']['request_sha256']:raise BaseException('WIRE_HASH_MISMATCH')
        recovered.append(dict(call_id=row['usage']['call_id'],request=request,request_sha256=digest,origin='calls.jsonl',case_id=saved['case_id']))
        if row.get('failure'):raise {'TimeoutError':TimeoutError}.get(row['failure'],RuntimeError)()
        return ModelReply(row['response'],row['finish_reason'],row['elapsed_s'],row.get('usage'))
    result=p.decide(ctx,replay)
    assert pos[0]==len(old)
    assert result['fallback']==saved['fallback']
    assert labels.get(signature(result['decision']))==saved['choice']
    for r in old:
        if r.get('failure'):failures[r['failure']]+=1
        if r.get('rejection'):failures[r['rejection']]+=1
    if saved['fallback']:errors['ambiguous' if saved['ambiguous'] else 'nonambiguous']+=1
    count+=1;requests+=len(old)
solo=json.loads((out/'solo.json').read_text())
for saved,(p,ctx,best) in zip(solo,supplements()):
    old=iter(r for r in saved['audit'] if 'request' in r)
    def replay(request,**kw):
        row=next(old);assert request==row['request']
        body=dict(model='gemma-4-31b-it',temperature=0,max_tokens=320,
            messages=[dict(role='system',content=request['system']),dict(role='user',content=json.dumps(request['input'],ensure_ascii=True))])
        digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
        assert digest==row['usage']['request_sha256']
        recovered.append(dict(call_id=row['usage']['call_id'],request=request,request_sha256=digest,origin='solo.json',case_id=saved['id']))
        return ModelReply(row['response'],row['finish_reason'],row['elapsed_s'],row.get('usage'))
    result=p.decide(ctx,replay)
    assert (not result['fallback'] and signature(result['decision'])==best)==saved['correct']
recovered_file=out/'verified_wire_requests.jsonl'
recovered_text=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in recovered)
if recovered_file.exists():assert recovered_file.read_text()==recovered_text
else:recovered_file.write_text(recovered_text)
report=dict(verified_wire_requests=len(recovered),verified_wire_requests_sha256=hashlib.sha256(recovered_file.read_bytes()).hexdigest(),schema='ugrp.task_planner.saved_response_replay.v1',new_model_calls=0,
    audit_note='Old request audit references included later refusals; reconstructed actual context from refusal prefix and verified captured wire body SHA for every original call. Originals retained. New code freezes request audit.',
    source_sha=json.loads((out/'RUN_META.json').read_text())['sha'],
    exact_request_and_decision_replays=count,actual_requests=requests,solo_replays=len(solo),
    failures=dict(failures),failed_cases_by_ambiguity=dict(errors),
    candidate_files_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.glob('harness/task_planner*.py'))},
    scope='Saved-response regression after native adapter edits, not new independent model evidence or physics')
(root/'experiments/2026-10-13-e2e18-planner/replay_verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
