"""Offline saved decision inputs; no simulation/render/remote calls."""
import argparse, hashlib, json, math, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from scripts.run_crate_teacher import make_grasp_teacher
from sim.crate_observation_v12 import tagged_world
from sim.cargo_teacher_profile import CRATE
from sim.grasp_act_goal_set import geometry
from sim.crate_navigation_v12 import WallFootprint,FOOTPRINT,PAD_M
from harness.static_keepouts import polygon_at,rect_corners,_axes
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
NAMES=['crate-diag-77990-fd724191','crate-reproduction-77978-fd724191','crate-reproduction-77981-fd724191']
def read(p):
 p=Path(p)
 if not p.exists():p=Path(str(p)+'.zst')
 return subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
def js(p):return json.loads(read(p))
def rows(p):return [json.loads(l) for l in read(p).splitlines()]
def wall_gap(pose,rect):
 a=polygon_at(pose,FOOTPRINT);b=rect_corners(rect,margin=PAD_M)
 return max(max(min(x*ax+y*ay for x,y in b)-max(x*ax+y*ay for x,y in a),min(x*ax+y*ay for x,y in a)-max(x*ax+y*ay for x,y in b)) for ax,ay in (*_axes(a),*_axes(b)))
def geometry_audit(w,t,row):
 nav=WallFootprint(w,t.rid,t.folded_ready,CRATE,t.bounds);items=[]
 for c in row['candidates']:
  if c['reason']=='grasp_geometry':continue
  choice=(math.radians(c['offset_deg']),c['distance_m']);_,_,h,g=geometry(w,t.rid,t.end,choice)
  items.append({**c,'disc_gap_mm':[(math.dist(g,d[:2])-d[2]-nav.radius)*1000 for d in nav.discs],
   'wall_sat_gap_mm':[1000*wall_gap((*g,h),r) for r in nav.rects], 'start_disc_gap_mm':[(math.dist(nav.pose[:2],d[:2])-d[2]-nav.radius)*1000 for d in nav.discs]})
 return {'t':row['t'],'rid':t.rid,'world':w,'radius':nav.radius,'discs':nav.discs,'candidates':items}
def replay(name,mode='baseline'):
 raw=RAW/name/'raw';res=js(raw/'result.json');ev=[r for r in rows(raw/'eval-only.jsonl') if r['stage']=='grasp'];roles=res['prefix']['assigned']
 lab={r:[v for v in rows(raw/f'teacher-{r}.jsonl') if 'clean_teacher_command' in v] for r in roles}
 opts={k:res.get(k,'off') for k in ('teacher_stability','teacher_search','approach_goal_set','crate_lift_pose','crate_approach_recovery','crate_wall_footprint','crate_stances','crate_pulse_safety')}
 if mode!='baseline':opts['crate_candidate_recovery']='crate_candidates_v1'
 ts={r:make_grasp_teacher(r,e,lab[r][0]['applied_command']['pwm'],**opts) for r,e in roles.items()}
 ms={r:VisibleWorld(r,e,profile=CRATE,static_walls=res['static_walls']) for r,e in roles.items()};audit=new_input_audit(True,'issued')
 clocks={r:IssuedClock() for r in roles};sync=GraspStartSync(tuple(roles),res['grasp_start_delays_s']);lift=GraspStartSync(tuple(roles),{r:0. for r in roles})
 mism=[];checked=0;geo=[];traces={r:[] for r in roles}
 for i,row in enumerate(ev):
  now=row['t'];holding=any(t.phase in ('lift','complete') for t in ts.values())
  plain={r:ms[r].observe(row['visible_measurements'][r],now) for r in roles}
  ws={r:AuditedTeacherInput(tagged_world(plain[r],holding=holding),audit,provenance='value_sources_v1') for r in roles}
  permits=sync.tick({r:t.prepare_signal(ws[r],now) for r,t in ts.items()},now);lifts=lift.tick({r:t.lift_ready() for r,t in ts.items()},now)
  for r,t in ts.items():
   prev=lab[r][max(0,i-1)]['applied_command'];skill='wait' if ((t.phase=='ready' and not permits[r]) or (t.phase=='closed' and not lifts[r])) else 'grasp'
   c=clocks[r].observe((skill,t.end,t.handoff),now,prev['pwm']);t.skill_started=now-c['skill_elapsed_s'];n=len(t.goal_set_log)
   command,done=t.step(ws[r],now,permit_pick=permits[r],permit_lift=lifts[r]);exp=lab[r][i]['clean_teacher_command']
   same=all(command[k]==exp[k] for k in ('t','wheels','pwm')) and all(abs(a-b)<=1e-10 for a,b in zip(command['duration_s'],exp['duration_s'])) and done==lab[r][i]['done'] and t.phase==lab[r][i]['teacher_phase']
   checked+=int(same)
   if not same:mism.append({'tick':i,'t':now,'robot':r,'old':exp,'new':command,'old_phase':lab[r][i]['teacher_phase'],'new_phase':t.phase,'recoveries':t.crate_recovery_log[-3:]})
   if len(t.goal_set_log)>n:geo.append(geometry_audit(plain[r],t,t.goal_set_log[-1]))
   traces[r].append({'t':now,'issued_pose':plain[r]['robots'][r]['pose'],'eval_pose':row['robots'][r]['pose']})
   t.remember_applied(lab[r][i]['applied_command']);ms[r].issue(lab[r][i]['applied_command'])
  if mism:break
 files=['result.json','plan.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl']
 return {'run':name,'mode':mode,'matched_commands':checked,'complete_ledger_match':not mism,'first_differences':mism,'geometry':geo,'pose_eval_only':traces,'input_audit':audit,
  'input_sha256':{f:hashlib.sha256(read(raw/f)).hexdigest() for f in files},'scope':'saved decision replay only, stop first divergence; physical effect unverified'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mode',default='baseline');p.add_argument('--out',type=Path,required=True);a=p.parse_args();allrows=[]
 for n in NAMES:
  r=replay(n,a.mode);allrows.append(r);print(n,r['complete_ledger_match'],r['matched_commands'],str(r['first_differences'])[:450],flush=True)
 a.out.write_text(json.dumps(allrows,indent=2)+'\n')
