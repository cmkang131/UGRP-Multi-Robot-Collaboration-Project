"""Saved-input decision replay only; stops at the first issued-command difference.

No simulator construction, physics, rendering or remote execution. Source
geometry is used ONLY in the separate feasibility audit, never fed to replay.
"""
import argparse, hashlib, json, math, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.grasp_act_visible_world import VisibleWorld
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_contract import IssuedClock
from scripts.run_crate_teacher import make_grasp_teacher
from sim.cargo_teacher_profile import CRATE

RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
HERE=Path(__file__).parent

def read(p):
    p=Path(p)
    if not p.exists():p=Path(str(p)+'.zst')
    b=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
    return b

def js(p):return json.loads(read(p))
def lines(p):return [json.loads(l) for l in read(p).splitlines()]

def replay(name,mode):
    raw=RAW/name/'raw';res=js(raw/'result.json');plan=js(raw/'plan.json')
    rows=[r for r in lines(raw/'eval-only.jsonl') if r['stage']=='grasp']
    roles=res['prefix']['assigned'];labs={r:lines(raw/f'teacher-{r}.jsonl')[:len(rows)] for r in roles}
    options={k:res.get(k,'off') for k in ('teacher_stability','teacher_search','approach_goal_set','crate_lift_pose','crate_approach_recovery')}
    if mode in ('pulse','bundle'):options.update(crate_approach_recovery='crate_approach_recovery_v1',crate_pulse_safety='crate_no_closer_v1')
    if mode=='bundle':options.update(crate_wall_footprint='crate_footprint_v1',crate_stances='crate_stances_v1')
    ts={r:make_grasp_teacher(r,e,labs[r][0]['applied_command']['pwm'],**options) for r,e in roles.items()}
    ms={r:VisibleWorld(r,e,profile=CRATE,static_walls='persistent_walls_v1' if mode in ('walls','bundle') else 'off') for r,e in roles.items()}
    clocks={r:IssuedClock() for r in roles}
    sync=GraspStartSync(tuple(roles),res['grasp_start_delays_s']);lift=GraspStartSync(tuple(roles),{r:0. for r in roles})
    first=None;checked=0;wall_retained=[];pulses=[]
    for i,row in enumerate(rows):
        now=row['t'];ws={r:ms[r].observe(row['visible_measurements'][r],now) for r in roles}
        permits=sync.tick({r:t.prepare_signal(ws[r],now) for r,t in ts.items()},now)
        lifts=lift.tick({r:t.lift_ready() for r,t in ts.items()},now)
        differences=[]
        for r,t in ts.items():
            previous=labs[r][max(0,i-1)]['applied_command']
            skill='wait' if ((t.phase=='ready' and not permits[r]) or (t.phase=='closed' and not lifts[r])) else 'grasp'
            c=clocks[r].observe((skill,t.end,t.handoff),now,previous['pwm']);t.skill_started=now-c['skill_elapsed_s']
            command,done=t.step(ws[r],now,permit_pick=permits[r],permit_lift=lifts[r])
            expected=labs[r][i]['clean_teacher_command']
            same=all(command[k]==expected[k] for k in ('t','wheels','pwm')) and max(abs(a-b) for a,b in zip(command['duration_s'],expected['duration_s']))<=1e-10
            same=same and done==labs[r][i]['done'] and t.phase==labs[r][i]['teacher_phase']
            checked+=int(same)
            if not same:differences.append({'robot':r,'phase':t.phase,'old_phase':labs[r][i]['teacher_phase'],
                'old_wheels':expected['wheels'],'new_wheels':command['wheels'],
                'old_duration_s':expected['duration_s'],'new_duration_s':command['duration_s'],
                'recoveries':[x for x in t.crate_recovery_log if x['t']==now],
                'goal_set':t.goal_set_log[-1] if t.goal_set_log else None})
            if mode=='walls' and i in (114,117,123) and r=='r1':
                wall_retained.append({'tick':i,'elapsed_s':round(now-rows[0]['t'],4),
                    'walls':{k:round(now-m['seen_t'],4) for k,m in ms[r].memory.items() if m['kind']=='wall'}})
            t.remember_applied(labs[r][i]['applied_command']);ms[r].issue(labs[r][i]['applied_command'])
        if differences:
            first={'tick':i,'elapsed_s':round(now-rows[0]['t'],4),'differences':differences}
            break
    files=['plan.json','result.json','eval-only.jsonl',*(f'teacher-{r}.jsonl' for r in roles)]
    hashes={f:hashlib.sha256(read(raw/f)).hexdigest() for f in files}
    return {'run':name,'source_sha':res['source_sha'],'mode':mode,'checked_matching_robot_commands':checked,
            'first_difference':first,'complete_ledger_match':first is None,'wall_retained':wall_retained,
            'raw':str(raw),'uncompressed_input_sha256':hashes,
            'scope':'same saved inputs valid only through first command difference; physical effect UNVERIFIED; RGB assignment/release/lookaround NOT replayed'}


def feasibility():
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import keepout_rects,pose_clear,rect_distance
    from sim.crate_navigation_v12 import FOOTPRINT,PAD_M,ANGLES_DEG,DISTANCES_M,stance_grasp_valid
    from sim.crate_antipodal import visible_grasp
    from sim.crate_cartesian_lift import STATION_M
    from sim.grasp_act_goal_set import geometry
    data=js(HERE/'crate11-summary.json');out=[]
    for saved in data['table2_seed_geometry_eval_only']:
        if not saved['near_wall_flag']:continue
        p=js(RAW/saved['run']/'raw/plan.json');static,_,_=resolve(p['map_id']);rects=keepout_rects(static,perimeter=True)
        ends={r:[*v['lug_xy'],.024] for r,v in ((v['end'],v) for v in saved['robots'].values())}
        row={'run':saved['run'],'seed':p['seed'],'sha8':saved['sha8'],'robots':{}}
        for rid,v in saved['robots'].items():
            w={'beam':{'pose':[*saved['crate_xy'],math.radians(saved['crate_yaw_deg'])],'ends':ends},
               'robots':{rid:{'pose':[0.,0.,0.]}},'visibility':{rid:{'visible_probes':15}}}
            counts={};best={}
            for mode in ('old','footprint_only','expanded_only','both'):
                angles=(0,-15,15) if mode in ('old','footprint_only') else ANGLES_DEG
                distances=(STATION_M,) if mode in ('old','footprint_only') else tuple(dict.fromkeys((STATION_M,*DISTANCES_M)))
                n=0;legal=0;bestclear=-math.inf
                for a in angles:
                    for d in distances:
                        _,_,heading,g=geometry(w,rid,v['end'],(math.radians(a),d));pose=(*g,heading)
                        if not (visible_grasp(w,rid,v['end'],pose=pose)['valid'] if mode in ('old','footprint_only') else stance_grasp_valid(w,rid,v['end'],pose)):continue
                        legal+=1
                        clear=(pose_clear(pose,FOOTPRINT,rects,bounds=static['bounds_m'],margin=PAD_M)
                               if mode in ('footprint_only','both') else all(rect_distance(g,r)>=.17 for r in rects))
                        if clear:n+=1
                counts[mode]={'legal_grasp_candidates':legal,'wall_free_candidates':n}
            row['robots'][rid]=counts
        row['both_robots_wall_feasible']={m:all(v[m]['wall_free_candidates']>0 for v in row['robots'].values()) for m in ('old','footprint_only','expanded_only','both')}
        out.append(row)
    return {'scope':'EVALUATION ONLY saved initial geometry; wall-free antipodal IK/load candidates, not route/physical success',
            'N_run_instances':len(out),'N_unique_seeds':len({r['seed'] for r in out}),
            'feasible_n':{m:sum(r['both_robots_wall_feasible'][m] for r in out) for m in ('old','footprint_only','expanded_only','both')},'runs':out}


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    failures=js(HERE/'crate11-summary.json')['table1_failures']
    names=list(dict.fromkeys(r['run'] for r in failures if r['sha8'] in ('bf31840f','49d11b8e')))
    result={'schema':'ugrp.crate12.offline.v1','physical_runs':0,'replays':[]}
    for name in names:
        for mode in ('off','walls','pulse','bundle'):
            r=replay(name,mode);result['replays'].append(r)
            print(name,mode,'MATCH' if r['first_difference'] is None else r['first_difference']['tick'],flush=True)
    result['near_wall']=feasibility()
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print('near_wall',result['near_wall']['feasible_n'],'/',result['near_wall']['N_run_instances'],flush=True)
if __name__=='__main__':main()
