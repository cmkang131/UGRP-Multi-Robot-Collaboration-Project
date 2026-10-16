"""Compare near-obstacle and reacquisition situations in saved visible ledgers."""
import argparse,json,math,hashlib
from pathlib import Path
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_input_audit import new_input_audit,AuditedTeacherInput
from scripts.run_grasp_act_teacher import audit_visible_input
from scripts.replay_grasp_act_nominal_handoff import verified
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_visible_route import constraints
from harness.static_keepouts import rect_distance


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    ROOT=a.run;rows=[]
    for raw in sorted(ROOT.glob('cohort-*/episode-*/raw')):
     proof=[];plan=json.loads(verified(raw,'plan.json',proof));res=json.loads(verified(raw,'result.json',proof))
     labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl'+('.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else ''),proof).splitlines()] for r in plan['roles']}
     inputs=[{'t':v['t'],'measurements':v['visible_measurements']} for l in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (v:=json.loads(l))]
     audit=new_input_audit(True,'issued');ms={r:VisibleWorld(r,e) for r,e in plan['roles'].items()};metrics={r:{'cargo_min_m':None,'wall_min_m':None,'cargo_block_ticks':0,'wall_block_ticks':0,'lost_bouts':[],'seen':False,'lost_start':None} for r in ms};t0=inputs[0]['t']
     for k,row in enumerate(inputs):
      for rid,m in ms.items():
       audit_visible_input(audit,row['measurements'][rid]);w=AuditedTeacherInput(m.observe(row['measurements'][rid],row['t']),audit);s=metrics[rid];label=labels[rid][k];v=w['visibility'][rid]['visible_probes']>=5
       if label['teacher_phase'] not in ('pick','complete'):
        if v:
         if s['lost_start'] is not None:s['lost_bouts'].append([s['lost_start']-t0,row['t']-t0,row['t']-s['lost_start'],True]);s['lost_start']=None
         s['seen']=True
        elif s['seen'] and s['lost_start'] is None:s['lost_start']=row['t']
        if v and w['beam'] is not None:
         goal=geometry(w,rid,plan['roles'][rid],(0,.203))[3];rad,ds,rects=constraints(w,rid,True)
         # Separate cargo, wall, peer; folded comparison on identical visible rows.
         for name,vals in [('cargo',[math.dist(goal,o['xy'])-.13-o['radius']-(.005 if o['top_z_bound_m']<=.1 else .06) for key,o in w['objects'].items() if key!='beam_1']),('wall',[rect_distance(goal,r)-rad for r in rects])]:
          if vals:
           val=min(vals);key=name+'_min_m';s[key]=val if s[key] is None else min(s[key],val);s[name+'_block_ticks']+=int(val<0)
       m.issue(label['applied_command'])
     for rid,s in metrics.items():
      if s['lost_start'] is not None:s['lost_bouts'].append([s['lost_start']-t0,inputs[-1]['t']-t0,inputs[-1]['t']-s['lost_start'],False])
      del s['lost_start'];del s['seen']
     rows.append({'episode':int(raw.parent.name[-3:]),'success':res['physical_success'],'sim_s':res['sim_s'],'metrics':metrics,'input_audit':audit,'raw_proof':proof})
    summary={'schema':'ugrp.grasp_act.search9_causes.v1','raw_root':str(ROOT),'source_sha':'86367b4b78a14c772f6194f6b36d524a0f934afe','near_goal_margin_threshold_m':.05,'scope':'visible input ledger comparison; no successful JPEG locally available; no physics or rendering','rows':rows}
    for kind in ('cargo','wall'):
     summary[kind+'_near_success_indices']=[r['episode'] for r in rows if r['success'] and any(s[kind+'_min_m'] is not None and s[kind+'_min_m']<.05 for s in r['metrics'].values())]
     summary[kind+'_blocked_success_indices']=[r['episode'] for r in rows if r['success'] and any(s[kind+'_block_ticks'] for s in r['metrics'].values())]
    summary['reacquired_success_indices']=[r['episode'] for r in rows if r['success'] and any(b[2]>=.5 and b[3] for s in r['metrics'].values() for b in s['lost_bouts'])]
    a.out.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},indent=2))


if __name__=="__main__":main()
