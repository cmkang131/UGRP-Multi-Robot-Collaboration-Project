"""Post-seal egomap53 scoring. The acquisition/controller never imports this."""
from pathlib import Path
from collections import Counter
import json,hashlib,importlib.util,sys,numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
RAW=Path('/Users/changmin/projects/ugrp/outputs/teach-capture-v1')
OUT=RAW/'evaluation'
load=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(s) for s in p.open()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def rotation(ep):
 trace=rows(ep/'own-controller.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl');end=truth[-1]['t'];out={}
 for phase in ('explore','suffix','all'):
  duration=rotation=intervals=sweep=0.;count=0
  for i,r in enumerate(trace):
   if phase!='all' and ((r['stage']=='explore')!=(phase=='explore')):continue
   dt=max(0.,min(end,trace[i+1]['t'] if i+1<len(trace) else end)-r['t'])
   c=r['command'];turn=c.get('kind')=='mecanum' and abs(c.get('turn',0))>0
   duration+=dt;rotation+=min(dt,c.get('duration_s',dt)) if turn else 0
   intervals+=dt if turn else 0;sweep+=dt if r['status']=='sensor_sweep' else 0;count+=1
  out[phase]=dict(command_duration_s=duration,rotation_active_s=rotation,rotation_fraction=rotation/duration if duration else None,
   turn_interval_fraction=intervals/duration if duration else None,sensor_sweep_fraction=sweep/duration if duration else None,frames=count)
 return out
def score(seed):
 ep=RAW/f'seed{seed}'
 if (ep/'interruption.json').exists():
  audit=load(ep/'interrupted-artifacts.sha256.json')
  for p,h in audit.items():assert sha(ep/p)==h
  truth=rows(ep/'eval_only/trajectory.jsonl');trace=rows(ep/'own-controller.jsonl');contacts=rows(ep/'eval_only/contact-audit.jsonl')
  result=dict(seed=seed,acquisition=load(ep/'interruption.json'),started=True,valid_teach_trial=False,arrived=False,false_declarations=0,
   B_route=None,first_match=None,gate=False,sim_s=truth[-1]['t']-truth[0]['t'],teach_frames=0,
   contacts={kind:dict(episodes=sum(v and (i==0 or not mask[i-1]) for i,v in enumerate(mask)),frames=sum(mask))
    for kind in ('wall','robot') for mask in [[any(x['kind']==kind for x in r['pairs']) for r in contacts]]},rotation=rotation(ep))
 else:
  spec=importlib.util.spec_from_file_location('score49',ROOT/'experiments/2026-10-08-own-map-return-repeat/code/report.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  m.RAW=RAW;m.EXP=OUT;result=m.score(seed)
  g=load(ep/'teach-graph.json');ret=load(ep/'teach-return.json');trace=rows(ep/'own-controller.jsonl')
  first=next((r for r in trace if r['stage']=='return'),None)
  first_match=None if first is None else first['teach']['match']
  connected=ret['loss_route'] is not None
  result.update(valid_teach_trial=result['acquisition']['status']=='RECORDED',nodes=len(g['nodes']),edges=len(g['edges']),uncertain_edges=g['uncertain_edges'],
   B_route=connected,B_node=g['goal_node'],B_first_keyframe_t=None if g['goal_node'] is None else g['nodes'][g['goal_node']]['t'],
   first_match=first_match,rotation=rotation(ep),node_matches=dict(Counter(r['status']+'/'+r['reason'] for r in ret['matches'])),
   gate=bool(result['acquisition']['status']=='RECORDED' and connected and first_match and first_match['status']=='accepted' and result['arrived'] and not result['false_declarations']),
   prediction_seal=sha(ep/'teach-graph.json'),teach_frames=sum('teach' in r for r in trace))
 dump(OUT/f'{seed}.json',result);print(seed,'gate',result['gate'],'B',result['B_route'],'match',None if not result['first_match'] else result['first_match']['reason'],'arrive',result['arrived'])
 return result
if __name__=='__main__':
 for s in (49001,49002):score(s)
 reports=[load(OUT/f'{s}.json') for s in (49001,49002)]
 gate=dict(passed=all(r['gate'] for r in reports),seeds=[49001,49002],prediction_seals={str(r['seed']):r['prediction_seal'] for r in reports if 'prediction_seal' in r},
  physical_attempts=2,valid_teach_trials=sum(r['valid_teach_trial'] for r in reports),arrivals=sum(r['arrived'] for r in reports),
  conditional_seeds_not_started=[49003,49004,49005,49006] if not all(r['gate'] for r in reports) else [],preregistration='e9018927')
 dump(RAW/'stage1-gate.json',gate);print(gate)
 baseline=Path('/Users/changmin/projects/ugrp/outputs/own-map-return-repeat-v1')
 dump(OUT/'baseline-rotation.json',{str(s):rotation(baseline/f'seed{s}') for s in range(49001,49007)})
