"""Offline search13 forensic replay and saved JPEG contact sheets; no simulator.

Evaluator poses are used only for separately labelled audit metrics.
"""
import json,math,hashlib,subprocess
from pathlib import Path
from copy import deepcopy
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.replay_grasp_act_recovery import KW
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_visible_route import free
from scripts.zone_teacher import PeerDisc
from harness.static_keepouts import rect_distance
from PIL import Image,ImageDraw
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--run',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
RUN=args.run
OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
allrows=[];frames=[]
for ep in range(6,13):
 raw=RUN/'diagnostic'/f'episode-{ep:03d}'/'raw';proof=[]
 p=json.loads(verified(raw,'plan.json',proof));res=json.loads(verified(raw,'result.json',proof))
 assert res['source_sha']=='c3d700e5d44a50a2e7044fc3eeef2e2124486f93' and res['approach_coordination']=='off'
 labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl'+('.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else ''),proof).splitlines()] for r in p['roles']}
 ev=[json.loads(l) for l in verified(raw,'eval-only.jsonl.zst',proof).splitlines()]
 inputs=[{'t':v['t'],'measurements':v['visible_measurements']} for v in ev]
 prev={r:labels[r][0]['applied_command'] for r in labels};ms={r:VisibleWorld(r,e) for r,e in p['roles'].items()}
 ts={r:VisibleOnlyGraspTeacher(r,e,prev[r]['pwm'],**KW) for r,e in p['roles'].items()}
 clocks={r:IssuedClock() for r in labels};sync=GraspStartSync(p['roles'],res['grasp_start_delays_s']);traces={r:[] for r in labels};endworld={}
 for i,row in enumerate(inputs):
  now=row['t'];ws={r:ms[r].observe(row['measurements'][r],now) for r in labels}
  permits=sync.tick({r:t.prepare_signal(ws[r],now) for r,t in ts.items()},now)
  for r,t in ts.items():
   w=ws[r];skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
   elapsed=clocks[r].observe((skill,t.end,t.handoff),now,prev[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
   cmd,done=t.step(w,now,permit_pick=permits[r]);expect=labels[r][i]['clean_teacher_command']
   assert all(cmd[k]==expect[k] for k in ('t','wheels','pwm')) and max(abs(a-b) for a,b in zip(cmd['duration_s'],expect['duration_s']))<=1e-12,(ep,r,i)
   pose=w['robots'][r]['pose'];data={'t':now,'elapsed':now-inputs[0]['t'],'phase':t.phase,'pose':pose,'visible':w['visibility'][r], 'wheels':cmd['wheels'],'outcome':t.outcome,'planner_calls':t.planner_calls,'no_path':t.no_path_calls,'blocked':t.blocked_goal_calls,'search_age':None if t.search_since is None else now-t.search_since,'ever_seen':t.ever_seen,'pwm':cmd['pwm']}
   if w['beam']:
    _,g,h,goal=t._geometry(w);rad,ds,rs=t._constraints(w)
    data.update(goal=goal,distance=math.dist(pose[:2],goal),align_error=abs(math.atan2(math.sin(h-pose[2]),math.cos(h-pose[2]))),peers=[{'id':q,'distance':math.dist(pose[:2],v['pose'][:2]),'goal_clearance':math.dist(goal,v['pose'][:2])-.34,'fresh':q in w['visibility'][r]['peers']} for q,v in w['robots'].items() if q!=r],
     blockers=[{'type':'peer' if isinstance(d,PeerDisc) else 'cargo_or_beam','clearance':math.dist(goal,d[:2])-d[2]-rad,'geometry':list(d)} for d in ds if not free(goal,[d],[],rad)]+[{'type':'wall','clearance':rect_distance(goal,q)-rad,'geometry':list(q)} for q in rs if not free(goal,[],[q],rad)])
   traces[r].append(data)
   if t.outcome and r not in endworld:endworld[r]=deepcopy(w)
   t.remember_applied(labels[r][i]['applied_command']);prev[r]=labels[r][i]['applied_command'];ms[r].issue(prev[r])
 failures=[]
 for r,t in ts.items():
  if t.outcome!='approach_blocked_handoff' and not (ep==8 and r=='r1'):continue
  hist=traces[r];last=next((x for x in hist if x['outcome']),hist[-1]);ix=hist.index(last);old=min(hist[:ix+1],key=lambda x:abs(x['t']-(last['t']-3)));ei=next(j for j,v in enumerate(inputs) if v['t']==last['t']);oi=next(j for j,v in enumerate(inputs) if v['t']==old['t'])
  row={'rid':r,'last':last,'window_start':old,'issued_displacement_3s_m':math.dist(old['pose'][:2],last['pose'][:2]),'distance_decrease_3s_m':old['distance']-last['distance'] if 'distance' in old and 'distance' in last else None,'alignment_decrease_3s_rad':old.get('align_error',0)-last.get('align_error',0),'eval_only_actual_displacement_3s_m':math.dist(ev[oi]['robots'][r]['pose'][:2],ev[ei]['robots'][r]['pose'][:2]),'events':t.events,'world_at_failure':endworld.get(r,ws[r])}
  row['last_planner_rejection']=next((x for j,x in reversed(list(enumerate(hist[:ix+1]))) if x['no_path']>(hist[j-1]['no_path'] if j else 0)),None)
  row['window_all_wheels_zero']=all(not any(x['wheels']) for x in hist if old['t']<=x['t']<=last['t'])
  failures.append(row)
  print(ep,r,'end',t.end,'elapsed',round(last['elapsed'],2),'issued',round(row['issued_displacement_3s_m'],5),'actual',round(row['eval_only_actual_displacement_3s_m'],5),'goal',round(last.get('distance',0),4),'dd',row['distance_decrease_3s_m'],'blockers',last.get('blockers'),'peers',last.get('peers'),flush=True)
 allrows.append({'episode':ep,'seed':p['seed'],'sim_s':res['sim_s'],'verified_commands':len(inputs)*2,'failures':failures,'raw_proof':proof})
 data=json.dumps(traces).encode()
 compressed=subprocess.check_output(['zstd','-q','-c'],input=data)
 assert subprocess.check_output(['zstd','-q','-d','-c'],input=compressed)==data
 (OUT/f'ep{ep}-trace.json.zst').write_bytes(compressed)
 times=sorted(int(x.stem) for x in (raw/'eval-overview').glob('*.jpg'))
 idxs=sorted(set(round(j*(len(times)-1)/5) for j in range(6)))
 sheet=Image.new('RGB',(960,len(idxs)*265),'white');draw=ImageDraw.Draw(sheet)
 for k,j in enumerate(idxs):
  tick=times[j];paths=[raw/'eval-overview'/f'{tick:06d}.jpg',raw/'eval-own/r1'/f'{tick:06d}.jpg',raw/'eval-own/r2'/f'{tick:06d}.jpg']
  for c,f in enumerate(paths):
   im=Image.open(f);im.thumbnail((320,240));sheet.paste(im,(320*c,265*k+25));draw.text((320*c,265*k),f'ep{ep} {("overview","r1","r2")[c]} elapsed {tick*.1:.1f}s',fill='black')
   frames.append({'episode':ep,'tick':tick,'elapsed_sim_s':tick*.1,'t':inputs[min(tick,len(inputs)-1)]['t'],'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 sheet.save(OUT/f'ep{ep}-frames.jpg')
(OUT/'diagnosis.json').write_text(json.dumps({'rows':allrows},indent=2)+'\n')
(OUT/'frames.json').write_text(json.dumps(frames,indent=2)+'\n')
