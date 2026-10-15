import hashlib,json,math,subprocess,sys,time
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]

def data(p):
 p=Path(p)
 if not p.exists():p=Path(str(p)+'.zst')
 b=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
 return b,dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),decoded_sha256=hashlib.sha256(b).hexdigest())
def obj(p):return json.loads(data(p)[0])
def lines(p):return [json.loads(v) for v in data(p)[0].splitlines()]
def summarize(folder):
 rows=obj(folder/'plan.json');summary=[]
 for r in rows:
  raw=ROOT/'outputs/gcp1-runs'/r['name']/'raw'
  if not raw.exists():continue
  try:res=obj(raw/'result.json')
  except (FileNotFoundError,subprocess.CalledProcessError):continue
  ev=lines(raw/'eval-only.jsonl');phases={};pulses={};stats={};sources=[]
  for p in ['result.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl']:
   _,s=data(raw/p);sources.append(s)
  for rid in ['r1','r2']:
   ts=lines(raw/f'teacher-{rid}.jsonl');dist=Counter();signs=[];alignment=[];quantum=[]
   epoch=0;in_alignment=False
   for t in ts:
    active=t['teacher_phase'] in ('align','ready')
    if active and not in_alignment:epoch+=1
    in_alignment=active
    if active and t.get('crate18_states'):quantum.append(t['crate18_states'])
    if 'applied_command' not in t:continue
    c=t['applied_command']
    if t['teacher_phase'] not in ('align','ready') or not any(c['wheels']):continue
    dist.update(round(d,3) for w,d in zip(c['wheels'],c['duration_s']) if w)
    w=c['wheels'];v=(sum(w),-w[0]+w[1]+w[2]-w[3],-w[0]+w[1]-w[2]+w[3]);axis=max(range(3),key=lambda i:abs(v[i]))
    alignment.append(dict(epoch=epoch,t=t['t'],axis=axis,sign=math.copysign(1,v[axis]),duration_s=c['duration_s']))
   reversals=Counter()
   prev={}
   for t in alignment:
    axis=t['axis'];sg=t['sign']
    if prev.get('epoch')!=t['epoch']:prev={}
    prev['epoch']=t['epoch']
    reversals[axis]+=int(axis in prev and prev[axis]!=sg);prev[axis]=sg
   pulses[rid]={'N':len(alignment),'wheel_width_histogram':dict(sorted(dist.items())),'axis_reversals':dict(reversals),'trace':alignment,
    'max_policy_reversals':[max((s[i]['total_reversals'] for s in quantum),default=0) for i in range(3)],
    'max_policy_pulses':[max((s[i]['pulses'] for s in quantum),default=0) for i in range(3)],
    'settle_observations':sum(all(v['settled'] for v in s) for s in quantum),'final_states':quantum[-1] if quantum else None}
   phases[rid]=dict(Counter(t['teacher_phase'] for t in ts))
  row=dict(**r,status=res['status'],success=bool(res.get('prefix_held') and res.get('release_success')) if res['status']=='complete' else None,prefix_held=res.get('prefix_held'),release_success=res.get('release_success'),
   release_outcome=res.get('release_outcome'),outcomes={k:v['outcome'] for k,v in res.get('prefix',{}).get('teachers',{}).items()},
   source_sha=res['source_sha'],host=res['execution_host'],sim_s=res['sim_s'],wall_s=res['wall_s'],input_audit=res['input_audit'],phases=phases,pulses=pulses,
   pick_permits=sum(any(v.get('pick_permits',{}).values()) for v in ev),lift_permits=sum(any(v.get('lift_permits',{}).values()) for v in ev),
   aligned={rid:any(t.get('teacher_phase') in ('ready','pick','closed','lift','complete') for t in lines(raw/f'teacher-{rid}.jsonl')) for rid in ('r1','r2')},
   sources=sources,raw=f"gcp1:/home/ugrp/ugrp-sim/runs/{r['name']}")
  summary.append(row)
 (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 for r in summary:print(json.dumps({k:r[k] for k in ['name','status','success','aligned','pick_permits','lift_permits','outcomes','release_outcome','sim_s']},ensure_ascii=False))
if __name__=='__main__':summarize(Path(sys.argv[1]))
