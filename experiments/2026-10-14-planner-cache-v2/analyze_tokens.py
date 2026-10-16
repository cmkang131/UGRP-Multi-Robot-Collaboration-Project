"""Public Gemma tokenizer prefix ceiling, not an assumption about cache retention."""
import sys,json,collections,subprocess,statistics,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'outputs/planner-cache-tokenizer-runtime')]
from tokenizers import Tokenizer
from jinja2 import Environment
from harness.task_planner_model import ordered_context
T=ROOT/'outputs/planner-cache-tokenizer'
blob=(T/'tokenizer.json').read_bytes() if (T/'tokenizer.json').exists() else subprocess.check_output(['zstd','-qdc',str(T/'tokenizer.json.zst')])
tokenizer=Tokenizer.from_str(blob.decode())
config=json.loads((T/'tokenizer_config.json').read_text());template=Environment().from_string((T/'chat_template.jinja').read_text())
def read(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
def lines(p):return [json.loads(x) for x in read(p).splitlines()]
def common(a,b):
    for i,(x,y) in enumerate(zip(a,b)):
        if x!=y:return i
    return min(len(a),len(b))
def encode(system,ctx,order):
    ctx=ordered_context(ctx,order);user=json.dumps(ctx,ensure_ascii=True)
    prompt=template.render(messages=[{'role':'system','content':system},{'role':'user','content':user}],add_generation_prompt=True,**config)
    enc=tokenizer.encode(prompt);pos=prompt.index(user);bounds=[(0,'system_and_chat_template')]
    for i,(k,v) in enumerate(ctx.items()):
        bounds.append((pos,k));pos+=len(('{' if i==0 else ', ')+json.dumps(k)+': '+json.dumps(v,ensure_ascii=True))
    labels=[];j=0
    for start,end in enc.offsets:
        while j+1<len(bounds) and start>=bounds[j+1][0]:j+=1
        labels.append(bounds[j][1])
    return enc.ids,labels

def analyze(rows,order):
    by_robot={};last={};past=collections.defaultdict(list);records=[];fields=collections.Counter()
    for r in rows:
        ids,labels=encode(r['system'],r['input'],order);key=(r['run'],r['robot'])
        n=common(by_robot[key],ids) if key in by_robot else 0
        adj=common(last[r['run']],ids) if r['run'] in last else 0
        upper=max((common(p,ids) for p in past[r['run']]),default=0)
        fields.update(labels[:n]);records.append(dict(run=r['run'],robot=r['robot'],request_id=r['request_id'],sim_s=r['sim_s'],
            tokens=len(ids),same_robot_prefix=n,interleaved_adjacent_prefix=adj,all_past_prefix=upper,all_past_floor32=upper//32*32))
        by_robot[key]=ids;last[r['run']]=ids;past[r['run']].append(ids)
    total=sum(r['tokens'] for r in records)
    return dict(N=len(rows),total_tokens=total,ratios={k:sum(r[k] for r in records)/total for k in ('same_robot_prefix','interleaved_adjacent_prefix','all_past_prefix','all_past_floor32')},
        same_robot_prefix_tokens_by_field=dict(fields),rows=records)
base=lines(ROOT/'outputs/task-planner-gemma-json-20261014/off-calls.jsonl')
records=[];errors=[]
for i,r in enumerate(base):
    a=r['audit'][0];q=a['request'];c=q['input'];ids,_=encode(q['system'],c,'off')
    if a.get('usage'):errors.append(len(ids)-a['usage']['prompt_tokens'])
    records.append(dict(run='fixed400',robot=c['robot_id'],request_id=r['case_id']+'/'+r['condition'],sim_s=i,system=q['system'],input=c))
r80=[]
for p in sorted(Path('/Users/changmin/projects/ugrp-wt/e2e18/outputs/azure3-runs').glob('*-r80/raw/llm/requests.json.zst')):
    for r in json.loads(read(Path(str(p)[:-4]))):r80.append(dict(run=p.parents[2].name,robot=r['robot'],sim_s=r['sim_s'],system=r['system'],input=json.loads(r['user']),request_id=r['request_id']))
r80.sort(key=lambda r:(r['run'],r['sim_s'],r['request_id']))
lookup={(r['run'],r['request_id']):r for r in r80}
speech=[]
for r in lines(Path('/Users/changmin/projects/ugrp-wt/e2e18/outputs/e2e18-admin/protocol-relay-r17/code_v1-dialogue/speech.jsonl')):
    run=r['call_id'].split(':')[0]
    if not run.startswith('e2e18-') or not run.endswith('-r80'):continue
    m=r['request']['messages'];c=json.loads(m[1]['content']);origin=lookup[(run,c['request_id'])]
    speech.append({**origin,'system':m[0]['content'],'input':c})
speech.sort(key=lambda r:(r['run'],r['sim_s'],r['request_id']))
result=dict(tokenizer='google/gemma-4-31B-it@842da3794eaa0b77d5f08bae87a17459d91ff475',
    tokenizer_sha256=hashlib.sha256(blob).hexdigest(),
    template_sha256=hashlib.sha256((T/'chat_template.jinja').read_bytes()).hexdigest(),
    validation=dict(N=len(errors),predicted_minus_billed_tokens=dict(collections.Counter(errors))),
    fixed400={o:analyze(records,o) for o in ('off','static_first_v2')},
    r80_input_envelope={o:analyze(r80,o) for o in ('off','static_first_v2')},
    r80_actual_provider_speech={o:analyze(speech,o) for o in ('off','static_first_v2')},
    limitations=['all_past is an ideal no-eviction ceiling within each run, not guaranteed hit rate.',
      '32-token flooring is an observed ledger granularity hypothesis, not documented Gemma contract.',
      'r80 envelope is pre-relay; actual provider wire was code_v1 speech without images, not this new planner.',
      'Text tokenizer ceiling excludes vision expansion; image-last prevents image changes from breaking the text prefix.'])
Path(__file__).with_name('token-prefix-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:({o:{a:b for a,b in v.items() if a not in ('rows','same_robot_prefix_tokens_by_field')} for o,v in value.items()} if k in ('fixed400','r80_input_envelope','r80_actual_provider_speech') else value) for k,value in result.items()},indent=2))
