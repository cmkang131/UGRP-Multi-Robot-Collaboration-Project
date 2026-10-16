"""Evaluator-only candidate decomposition of frozen search20 evidence. No physics."""
import argparse, hashlib, json, math
from collections import Counter
from copy import deepcopy
from pathlib import Path
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_search18 import read, KW
from scripts.replay_grasp_act_search17 import same
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher as Teacher
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search18 import Navigation, body_clearance
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_visible_route import constraints
from harness.static_keepouts import rect_distance
import sim.grasp_act_search19 as search19


def analyze(raw):
    names=['eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl','result.json','plan.json']
    data={n:read(raw/n) for n in names};plan=json.loads(data['plan.json']);res=json.loads(data['result.json'])
    ev=[json.loads(s) for s in data['eval-only.jsonl'].splitlines()]
    led={r:[json.loads(s) for s in data[f'teacher-{r}.jsonl'].splitlines()] for r in plan['roles']}
    modes={k:res.get(k,'off') for k in ALL_MODES}
    teachers={r:Teacher(r,e,led[r][0]['applied_command']['pwm'],**KW,**modes) for r,e in plan['roles'].items()}
    models={r:VisibleWorld(r,e,odometry=modes['search17_odometry']) for r,e in plan['roles'].items()}
    clocks={r:IssuedClock() for r in teachers};sync=GraspStartSync(plan['roles'],res['grasp_start_delays_s'])
    original=Teacher._plan_approach;original_body=search19.body_fallback;body_rows=set();captures={};details=[];mismatch=0
    def capture_body(t,w,now):
        selected,checked=original_body(t,w,now);body_rows.update(id(c) for c in checked);return selected,checked
    search19.body_fallback=capture_body
    def capture(t,w,now):
        captures[t.rid]=deepcopy(dict(w));return original(t,w,now)
    Teacher._plan_approach=capture
    try:
        for i,row in enumerate(ev):
            now=row['t'];worlds={r:m.observe(row['visible_measurements'][r],now) for r,m in models.items()}
            permits=sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now)
            for r,t in teachers.items():
                prev=led[r][max(0,i-1)]['applied_command'];skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                el=clocks[r].observe((skill,t.end,t.handoff),now,prev['pwm']);t.skill_started=now-el['skill_elapsed_s']
                old=len(t.goal_set_log);cmd,done=t.step(worlds[r],now,permit_pick=permits[r]);mismatch+=not same(cmd,done,t.phase,led[r][i])
                if len(t.goal_set_log)>old:
                    w=captures[r];start=ev[0]['robots'][r]['pose'];c,s=math.cos(start[2]),math.sin(start[2])
                    def anchor(p):
                        x,y=p[0]-start[0],p[1]-start[1];return [c*x+s*y,-s*x+c*y]
                    nav=Navigation(w,r,t.end,t.sink.pwm,t.bounds,rectangle=True);labels=[]
                    labels += [k for k in w['robots'] if k!=r]
                    labels += [k for k in w['objects'] if k!='beam_1']
                    labels += ['beam:'+str(j) for j in range(5)] if w['beam'] else []
                    true_ds=[];obstacles=[]
                    for label,d in zip(labels,nav.discs):
                        if label.startswith('beam:'):
                            j=int(label.split(':')[1]);bp=row['beam']['pose'];a=bp[2];delta=(-.27,-.135,0,.135,.27)[j];xy=anchor([bp[0]+delta*math.cos(a),bp[1]+delta*math.sin(a)])
                        elif label in row['objects']:xy=anchor(row['objects'][label]['xy'])
                        else:xy=anchor(row['robots'][label]['pose'])
                        true_ds.append((*xy,d[2]));obstacles.append({'name':label,'estimate':d[:2],'truth_eval_only':xy,'xy_error_mm':1000*math.dist(d[:2],xy),'seen_t':w['visibility'][r]['observations'].get(label,{}).get('seen_t')})
                    def gaps(p,ds):
                        a=[(body_clearance(p,[d],[]),label) for d,label in zip(ds,labels)]
                        a += [(body_clearance(p,[],[rect]),'wall:'+str(j)) for j,rect in enumerate(nav.rects)]
                        a += [(body_clearance(p,[],[],bounds=t.bounds),'bounds')]
                        return sorted(a)
                    radius,circle_ds,circle_rs=constraints(w,r,t.folded_ready)
                    candidates=[]
                    for decision in t.goal_set_log[old:]:
                        for k,cr in enumerate(decision['candidates']):
                            heading=geometry(w,r,t.end,(math.radians(cr['offset_deg']),cr['distance_m']))[2];p=(*cr['goal'],heading)
                            est=gaps(p,nav.discs);true=gaps(p,true_ds)
                            body=id(cr) in body_rows
                            circle_gaps=[(math.dist(cr['goal'],d[:2])-d[2]-radius,label) for d,label in zip(circle_ds,labels)]
                            circle_gaps += [(rect_distance(cr['goal'],rect)-radius,'wall:'+str(j)) for j,rect in enumerate(circle_rs)]
                            rejected=[{'name':label,'gap_mm':1000*g} for g,label in (est if body else circle_gaps) if g < (.14 if body else 0.)]
                            candidates.append({**cr,'index':k,'filter':'search20_body_admission_140mm' if body else 'legacy_disc_inflation',
                                'actual_goal_blockers':rejected if cr['reason']=='blocked_goal' else [],
                                'body_gap_mm':est[0][0]*1000,'nearest':est[0][1],
                                'below_140mm':[{'name':label,'gap_mm':1000*g} for g,label in est if g<.14],
                                'same_candidate_truth_gap_mm':1000*true[0][0],'same_candidate_truth_nearest':true[0][1]})
                    true_pose=anchor(row['robots'][r]['pose']);wp=w['robots'][r]['pose'];dyaw=wp[2]-(row['robots'][r]['pose'][2]-start[2])
                    details.append({'rid':r,'t':now,'sim_s':now-ev[0]['t'],'pose_error_mm':1000*math.dist(wp[:2],true_pose),
                        'yaw_error_rad':math.atan2(math.sin(dyaw),math.cos(dyaw)),
                        'obstacles':obstacles,'world_visible_issued_only':w,'pwm':t.sink.pwm,'path':deepcopy(t.path),'choice':t.approach_choice,'candidates':candidates,
                        'reasons':dict(Counter(x['reason'] for x in candidates))})
                t.remember_applied(led[r][i]['applied_command']);models[r].issue(led[r][i]['applied_command'])
                if done:t.done_recorded=True
    finally:
        Teacher._plan_approach=original;search19.body_fallback=original_body
    return {'seed':plan['seed'],'raw':str(raw),'physical_success':res['physical_success'],'audit':res['input_audit'],
        'scope':'frozen replay; all truth is evaluator-only; same-candidate truth gaps hold estimated goals fixed',
        'baseline_mismatch_ticks':mismatch,'decoded_sha256':{n:hashlib.sha256(d).hexdigest() for n,d in data.items()},'decisions':details}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    report=analyze(a.raw);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='decisions'}))
    for d in report['decisions']:
        print(d['rid'],round(d['sim_s'],2),d['reasons'],'pose_mm',d['pose_error_mm'],'gaps',dict(Counter(x['nearest'] for x in d['candidates'])))
