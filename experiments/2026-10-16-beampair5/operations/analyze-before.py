"""Run on gcp2 before control edits; reconstruct only visible measurements + own commands."""
import pathlib,sys,json,collections,hashlib,math
root=pathlib.Path('/home/ugrp/ugrp-sim');src=root/'src/d72efd13957ce450c5cccc3fd93a555a37dd4705';dep=root/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'
sys.path.insert(0,str(src))
from scripts.audit_beampair1 import read,read_bytes,ordered_funnel
import harness,sim
harness.__path__.append(str(dep/'harness'));sim.__path__.append(str(dep/'sim'))
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_search22 import uncertainty
from sim.grasp_act_search23 import rectangle_gaps,GRID_M
import numpy as np
raw=root/'runs/beampair4-r3-gcp2-d72efd13/round/diagnostic/episode-001/raw'
out=root/'ops-reviews/beampair5';out.mkdir(exist_ok=True)
r=read(raw/'result.json');plan=read(raw/'plan.json');ev=[json.loads(x) for x in read_bytes(raw/'eval-only.jsonl')[0].splitlines()]
labels={rid:{round(l['applied_command']['t'],5):l for l in map(json.loads,read_bytes(raw/f'teacher-{rid}.jsonl')[0].splitlines())} for rid in plan['roles']}
origin=ev[0]['t'];models={rid:VisibleWorld(rid,end,odometry='search17_fixed_v1',search22='search22_v1',search23='search23_v1') for rid,end in plan['roles'].items()}
events=collections.defaultdict(list)
for event in r['teachers']['r2']['search22_log']:
 if 'candidates' in event:events[round(event['t'],5)].extend(event['candidates'])
windows={'all':[],'before_reobserve':[],'during_reobserve':[],'after_reobserve':[]};snapshots=[];wall_updates=collections.defaultdict(list)
for e in ev:
 now=e['t'];key=round(now,5)
 worlds={rid:models[rid].observe(e['visible_measurements'][rid],now) for rid in models}
 w=worlds['r2'];ms=w['visibility']['r2']['observations']
 for m in e['visible_measurements']['r2']:
  if m['kind']=='wall':wall_updates[m['id']].append(dict(t=now,elapsed=now-origin,relative=m,issued_memory=ms[m['id']]))
 if key in events:
  candidates=events[key];windows['all']+=candidates
  windows['before_reobserve' if now<18.9-1e-6 else 'during_reobserve' if now<21.3+1e-6 else 'after_reobserve']+=candidates
  sample=candidates[0];heading=w['beam']['pose'][2]+math.pi+math.radians(sample['offset_deg']) if w['beam'] else None
  walls=[]
  for name,m in ms.items():
   if m['kind']!='wall':continue
   rect=(*m['xyz'][:2],*m['half_extents'],m['yaw']);u=uncertainty(m,w['robots']['r2']['pose'])
   gap=float(rectangle_gaps(np.array([sample['goal']]),np.array([heading]),rect)[0]) if heading is not None else None
   walls.append(dict(id=name,seen_t=m['seen_t'],age_s=now-m['seen_t'],xyz=m['xyz'],yaw=m['yaw'],half_extents=m['half_extents'],uncertainty=u,representative_goal_gap_m=gap))
  snapshots.append(dict(t=now,elapsed_sim_s=now-origin,pose=w['robots']['r2']['pose'],beam=w['beam'],representative_goal=sample['goal'],goal_cell=[math.floor(v/GRID_M) for v in sample['goal']],heading=heading,walls=walls,candidate_N=len(candidates)))
 for rid in models:
  if key in labels[rid]:models[rid].issue(labels[rid][key]['applied_command'])
def table(cs):
 counts=collections.Counter(c['reason'] for c in cs);blocks=collections.defaultdict(list)
 for c in cs:
  ds=c.get('failure_audit') or [d for d in c.get('collision_audit',[]) if d['blocked']]
  for d in ds:blocks[(c['reason'],d['category'],d['id'])].append(d)
 stages=('ik_unreachable','gripper_angle','outside_bounds','blocked_goal','blocked_retreat','no_path','unsafe_body_sweep','band_not_visible')
 n=len(cs);f=[]
 for name in stages:
  rejected=counts[name];f.append(dict(gate=name,entered=n,cumulative_passed=n-rejected,rejected=rejected));n-=rejected
 return dict(candidate_N=len(cs),first_rejection_counts=dict(counts),candidate_funnel=f,blocker_occurrences=[dict(reason=k[0],category=k[1],blocked_object=k[2],N=len(ds),min_gap_m=min(d['gap_m'] for d in ds if d.get('gap_m') is not None),max_gap_m=max(d['gap_m'] for d in ds if d.get('gap_m') is not None),margin_min_m=min(d['margin_m'] for d in ds),margin_max_m=max(d['margin_m'] for d in ds)) for k,ds in sorted(blocks.items(),key=lambda kv:-len(kv[1]))])
report=dict(schema='ugrp.beampair5.pre_edit.v1',source_sha=src.name,host='gcp2',raw=str(raw),windows={k:table(cs) for k,cs in windows.items()},snapshots=snapshots,wall_updates={k:dict(N=len(v),first=v[0],last=v[-1]) for k,v in wall_updates.items()},reobserve=r['teachers']['r2']['reobserve_log'],representation='continuous remembered wall rectangles; A* discretized at GRID_M=.025; no stored occupancy-cell log odds',clearing=dict(wall_rays=0,wall_cells_cleared=0,reason='search22.update_world skips all kind!=cargo; no wall miss model'),inputs='visible_measurements + issued wheels only; no evaluator pose used in replay',sources={str(read_bytes(raw/n)[1]):read_bytes(raw/n)[2] for n in ('result.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl')},reproduce=f'{root}/ugrp/.venv-sim/bin/python {out}/analyze-before.py',analysis_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
report['frame_funnel']=ordered_funnel(len(ev)*2,[('any_assigned_probe',sum(e['visibility'][rid]['visible_probes']>0 for e in ev for rid in plan['roles'])),('meaningful_5_probes',sum(e['visibility'][rid]['visible_probes']>=5 for e in ev for rid in plan['roles'])),('measurement_admitted',sum(any(m['id']=='band_'+plan['roles'][rid] for m in e['visible_measurements'][rid]) for e in ev for rid in plan['roles']))])
phase_sets=[{e.get('to') for e in t['events']} for t in r['teachers'].values()]
report['event_funnel']=ordered_funnel(2,[(name,sum(bool(v&phases) for v in phase_sets)) for name,phases in [('ready',{'ready','pick','complete'}),('pick',{'pick','complete'}),('complete',{'complete'})]])
(out/'rejection_table-before.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(windows=report['windows'],last_snapshot=snapshots[-1],wall_updates={k:(v['N'],v['first']['t'],v['last']['t']) for k,v in report['wall_updates'].items()}),indent=2))
