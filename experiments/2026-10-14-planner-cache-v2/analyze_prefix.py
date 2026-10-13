"""Read-only prefix estimate. Characters calibrated to actual billed text tokens."""
import json,sys,subprocess,hashlib,statistics,collections,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from harness.task_planner_model import ordered_context
OUT=Path(__file__).parent
R80=Path('/Users/changmin/projects/ugrp-wt/e2e18/outputs/azure3-runs')
SPEECH=Path('/Users/changmin/projects/ugrp-wt/e2e18/outputs/e2e18-admin/protocol-relay-r17/code_v1-dialogue/speech.jsonl')
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def rows(p):return [json.loads(x) for x in read(p).splitlines()]
def lcp(a,b):
    return len(os.path.commonprefix((a,b)))
def text(system,ctx,order):return system+'\n'+json.dumps(ordered_context(ctx,order),ensure_ascii=True)
def fields(system,ctx,order):
    yield 'system',system+'\n'
    d=ordered_context(ctx,order)
    for i,(k,v) in enumerate(d.items()):yield k,('{' if i==0 else ', ')+json.dumps(k)+': '+json.dumps(v,ensure_ascii=True)
def prefix_detail(system,ctx,order,n):
    out={};pos=0
    for k,s in fields(system,ctx,order):out[k]=max(0,min(len(s),n-pos));pos+=len(s)
    return out
baseline=rows(ROOT/'outputs/task-planner-gemma-json-20261014/off-calls.jsonl')
cal=[]
for r in baseline:
    a=r['audit'][0];u=a.get('usage')
    if u:cal.append((len(text(a['request']['system'],a['request']['input'],'off')),u['prompt_tokens']))
ratio=sum(c for c,t in cal)/sum(t for c,t in cal)
relative_errors=[abs(c/ratio-t)/t for c,t in cal]
source={};envelopes=[]
for p in sorted(R80.glob('*-r80/raw/llm/requests.json.zst')):
    raw=read(Path(str(p)[:-4]));source[str(p)]=hashlib.sha256(raw).hexdigest()
    for r in json.loads(raw):envelopes.append(dict(run=p.parents[2].name,robot=r['robot'],sim_s=r['sim_s'],system=r['system'],input=json.loads(r['user']),request_id=r['request_id']))
groups=collections.defaultdict(list)
for r in envelopes:groups[(r['run'],r['robot'])].append(r)
changes={}
for k in sorted({k for r in envelopes for k in r['input']}):
    changes[k]=dict(groups=len(groups),changing_groups=sum(len({json.dumps(r['input'].get(k),sort_keys=True) for r in rs})>1 for rs in groups.values()),present=sum(k in r['input'] for r in envelopes))

def estimates(records,order,calibration):
    prior={};last_global={};out=[];parts=collections.Counter()
    for r in sorted(records,key=lambda r:(r['run'],r['sim_s'],r['request_id'])):
        key=r['run'],r['robot'];s=text(r['system'],r['input'],order)
        n=lcp(prior[key],s) if key in prior else 0
        global_n=lcp(last_global[r['run']],s) if r['run'] in last_global else 0
        for k,v in prefix_detail(r['system'],r['input'],order,n).items():parts[k]+=v/calibration
        out.append(dict(run=r['run'],robot=r['robot'],request_id=r['request_id'],sim_s=r['sim_s'],
                        same_robot_prefix_chars=n,interleaved_adjacent_prefix_chars=global_n,
                        same_robot_prefix_tokens_est=n/calibration,total_tokens_est=len(s)/calibration))
        prior[key]=s;last_global[r['run']]=s
    return dict(N=len(out),same_robot_prefix_tokens_sum_est=sum(x['same_robot_prefix_tokens_est'] for x in out),
        same_robot_ratio_est=sum(x['same_robot_prefix_chars'] for x in out)/sum(len(text(r['system'],r['input'],order)) for r in records),
        interleaved_adjacent_ratio_est=sum(x['interleaved_adjacent_prefix_chars'] for x in out)/sum(len(text(r['system'],r['input'],order)) for r in records),
        prefix_tokens_by_field_est=dict(parts),rows=out)

speech=[r for r in rows(SPEECH) if r['call_id'].split(':')[0].startswith('e2e18-') and '-r80:' in r['call_id']]
source[str(SPEECH)]=hashlib.sha256(read(SPEECH)).hexdigest()
lookup={(r['run'],r['request_id']):r for r in envelopes}
actual=[];speech_cal=[]
for r in speech:
    messages=r['request']['messages'];ctx=json.loads(messages[1]['content']);run=r['call_id'].split(':')[0]
    origin=lookup.get((run,ctx['request_id']))
    if not origin:raise ValueError('UNMATCHED_R80_PROVIDER_REQUEST')
    actual.append({**origin,'system':messages[0]['content'],'input':ctx})
    speech_cal.append((len(text(messages[0]['content'],ctx,'off')),r['response']['usage']['prompt_tokens']))
speech_ratio=sum(c for c,t in speech_cal)/sum(t for c,t in speech_cal)
current=[dict(run='fixed-dev',robot=r['condition']+'/'+r['audit'][0]['request']['input']['robot_id'],sim_s=i,
    request_id=r['case_id']+'/'+r['condition'],system=r['audit'][0]['request']['system'],input=r['audit'][0]['request']['input']) for i,r in enumerate(baseline)]
result=dict(schema='planner.cache.prefix.v1',calibration=dict(chars_per_token=ratio,N=len(cal),relative_total_token_error_median=statistics.median(relative_errors),
    relative_total_token_error_max=max(relative_errors),method='ratio of total serialized text characters to total observed Gemma prompt tokens; prefix tokens approximate, image tokens excluded',
    limitations='Chat template and token density vary by field. Character-derived prefix lengths are estimates, not tokenizer or provider guarantees.'),
    r80_field_variation=changes,r80_envelope={o:estimates(envelopes,o,ratio) for o in ('off','static_first_v2')},
    actual_r80_speech=dict(N=len(actual),image_requests=sum('image_url' in json.dumps(r['request']) for r in speech),
        chars_per_token=speech_ratio,prefix=estimates(actual,'off',speech_ratio),
        interpretation='These actual provider requests verbalize code-selected actions. They are not task-planner decisions.'),
    fixed400={o:estimates(current,o,ratio) for o in ('off','static_first_v2')},sources_sha256=source)
(OUT/'prefix-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(calibration=result['calibration'],envelope_N=len(envelopes),actual_speech_N=len(actual),
    fields_changing=[k for k,v in changes.items() if v['changing_groups']],
    fixed400={o:{k:v for k,v in x.items() if k not in ('rows','prefix_tokens_by_field_est')} for o,x in result['fixed400'].items()}),indent=2))
