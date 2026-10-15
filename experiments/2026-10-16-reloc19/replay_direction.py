"""Replay recorded map-waypoint safety rejects; no simulator/evaluator input."""
import argparse,hashlib,importlib.util,json,math,platform,subprocess
from pathlib import Path
from harness.static_keepouts import keepout_rects
from sim.grasp_act_visible_route import waypoint,segment_free
from sim.solo_carry_to_zone import CarryToZone
from scripts.zone_teacher import plan_path,PeerDisc
R=Path('/home/ugrp/ugrp-sim/runs')
def text(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def obj(p):return json.loads(text(p))
def discs(x):
 return [PeerDisc((*t['xy'],t['radius']+t['range_error_m']+(min(.20,.01*max(0,x['t']-t['seen_t'])) if t['kind']=='robot' else 0))) for t in x['carry_obstacles']['tracks']]
def endpoint(p,v):
 x,y,a=p;f,l,_=v
 return [x+.1*(math.cos(a)*f-math.sin(a)*l),y+.1*(math.sin(a)*f+math.cos(a)*l)]
def preserved(p,target):
 x,y,a=p;dx,dy=target[0]-x,target[1]-y
 f=.9*(math.cos(a)*dx+math.sin(a)*dy);l=.9*(-math.sin(a)*dx+math.cos(a)*dy)
 scale=min(1.,(.08 if f>=0 else .05)/abs(f) if f else math.inf,.06/abs(l) if l else math.inf)
 return [f*scale,l*scale,0.]
def main(n,candidate=None,out_name='direction-replay.json'):
 global preserved
 if candidate is not None:
  spec=importlib.util.spec_from_file_location('actual_direction_candidate',candidate);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);preserved=module.direction_drive
 assert platform.node().startswith('ugrp-sim-gcp2')
 b=R/f'reloc19-round{n}';q=obj(b/'queue.json');records=[]
 for t in q['runs']:
  if t['kind']!='carry':continue
  raw=Path(t['raw']);d=obj(raw/'result.json');c=[json.loads(s) for s in text(raw/'teacher-commands.jsonl').splitlines()]
  static=obj(raw/'carry-static-map.json');rects=keepout_rects(static,perimeter=True);radius=d['teacher']['carry']['radius_m']
  by={round(x['t'],5):x for x in c};a=d['teacher']['carry'].get('destination_visual_acquire',{});paths=[]
  for e in a.get('events',[]):
   if e['event']!='ellipse_search_waypoint':continue
   row=by[round(e['t'],5)];p=row['map_pose']['pose_estimate']
   path=plan_path(p[:2],e['xy'],static['bounds_m'],discs(row),rects=rects,radius=radius,budget=40000)
   paths.append((e['t'],path,e['xy']))
  cache={};counts=dict(blocked_expand_frames=0,reconstructed=0,original_reject=0,preserved_pass=0,no_waypoint=0)
  for x in c:
   a=x.get('destination_acquisition',{});last=a.get('last',{})
   if a.get('mode')!='expand' or last.get('reason')!='destination_motion_blocked' or last.get('t')!=x['t']:continue
   counts['blocked_expand_frames']+=1
   available=[y for y in paths if y[0]<=x['t']]
   if not available:continue
   at,path,goal=available[-1];p=x['map_pose']['pose_estimate'];ds=discs(x);target=waypoint(p[:2],path,ds,rects,radius)
   if target is None:counts['no_waypoint']+=1;continue
   key=json.dumps([p,target,ds,rects],separators=(',',':'))
   if key not in cache:
    old=CarryToZone.heading_drive(p,target,p[2]);new=preserved(p,target)
    cache[key]=dict(t=x['t'],pose=p,target=target,path_selected_t=at,search_goal=goal,discs=ds,rects=rects,radius=radius,
      source_sha=t['source_sha'],original_drive=old,preserved_drive=new,
      original_endpoint=endpoint(p,old),preserved_endpoint=endpoint(p,new),
      waypoint_segment_pass=segment_free(p[:2],target,ds,rects,radius),
      original_pass=segment_free(p[:2],endpoint(p,old),ds,rects,radius),
      preserved_pass=segment_free(p[:2],endpoint(p,new),ds,rects,radius),original_rejection=last,multiplicity=0)
   v=cache[key];v['multiplicity']+=1;counts['reconstructed']+=1
   counts['original_reject']+=not v['original_pass'];counts['preserved_pass']+=v['preserved_pass']
  cases=list(cache.values());records.append(dict(run=t['name'],raw=str(raw),counts=counts,unique_cases=cases))
 out=dict(round=n,candidate_file=str(candidate) if candidate else None,candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest() if candidate else None,analysis_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runs=records,
   scope='offline exact frozen map/own-command replay; uniform scaling preserves direction and original bounds; no physics success implied')
 (b/out_name).write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps([dict(run=x['run'],counts=x['counts'],unique=len(x['unique_cases'])) for x in records]))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);p.add_argument('--candidate-file',type=Path);p.add_argument('--out-name',default='direction-replay.json');a=p.parse_args();main(a.round,a.candidate_file,a.out_name)
