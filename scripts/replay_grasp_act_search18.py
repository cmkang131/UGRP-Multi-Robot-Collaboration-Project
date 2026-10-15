"""Replay saved search17 inputs, and branch from the same state for search18.

Recorded visible measurements and applied commands only enter the teacher.
All probes are one-step counterfactual decisions, NOT physical trajectories.
Free-space history is accumulated on the recorded camera/command history.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.run_grasp_act_teacher import audit_visible_input
from scripts.replay_grasp_act_search17 import same
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_search15_modes import MODES as S15
from sim.grasp_act_search17 import MODES as S17
from sim.grasp_act_search18 import MODES as S18
import sim.grasp_act_search18 as sa
from sim.grasp_act_free_space import FreeSpace

KW=dict(bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',
        approach_goal_set='approach_goal_set_v1',nominal_blocked_handoff='nominal_blocked_handoff_v1',
        approach_progress='approach_progress_v1',approach_recovery='progress_view_recovery_v3',approach_coordination='off')
STAGES={'repro3':'grasp-search17-repro3-gcp-4fdf7f84','novel12':'grasp-search17-novel12-gcp-4fdf7f84'}


def read(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-q','-dc',str(path)+'.zst'])


def clone_teacher(t):
    # Histories do not steer these branches. Avoid copying their ever-growing
    # diagnostic payloads, while preserving every controller state variable.
    histories=('events','goal_set_log','search17_log','search18_log','recovery_log','progress_log','search_log','search19_log','search20_log')
    memo={id(getattr(t,k)):[] for k in histories}
    memo[id(t.reobserver.events)]=[]
    return deepcopy(t,memo)


def replay(root,stage,ep,variants,shadow=()):
    raw=root/STAGES[stage]/'diagnostic'/f'episode-{ep:03d}'/'raw'
    files={name:read(raw/name) for name in ('eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl','result.json','plan.json')}
    rows=[json.loads(x) for x in files['eval-only.jsonl'].splitlines()]
    led={r:[json.loads(x) for x in files[f'teacher-{r}.jsonl'].splitlines()] for r in ('r1','r2')}
    result=json.loads(files['result.json']);plan=json.loads(files['plan.json'])
    prev={r:led[r][0]['applied_command'] for r in led}
    models={r:VisibleWorld(r,e,odometry=S17['search17_odometry']) for r,e in plan['roles'].items()}
    teachers={r:VisibleOnlyGraspTeacher(r,e,prev[r]['pwm'],**KW,**S15,**S17) for r,e in plan['roles'].items()}
    clocks={r:IssuedClock() for r in led};spaces={r:FreeSpace() for r in led}
    # Persistent shadow controllers: same recorded observations/applied commands, own state.
    shadow_names=[v for v in variants if '@' not in v and v in shadow]
    shadows={v:{r:VisibleOnlyGraspTeacher(r,e,led[r][0]['applied_command']['pwm'],**KW,**S15,**S17) for r,e in plan['roles'].items()} for v in shadow_names}
    for v in shadow_names:
        for t in shadows[v].values():t.search15_modes.update(S18 if v=='bundle' else {v:S18[v]})
    trace={};wait_ticks={v:Counter() for v in ['baseline',*shadow_names]};shadow_first={v:{} for v in shadow_names};shadow_cmd_first={v:{} for v in shadow_names}
    sync=GraspStartSync(plan['roles'],result['grasp_start_delays_s']);audit=new_input_audit(True,'issued')
    stats={v:Counter() for v in variants};first={v:{} for v in variants};diffs={v:[] for v in variants};probes=[];mismatch=0
    for i,row in enumerate(rows):
        now=row['t'];worlds={};empty_world={}
        for r in led:
            audit_visible_input(audit,row['visible_measurements'][r])
            worlds[r]=AuditedTeacherInput(models[r].observe(row['visible_measurements'][r],now),audit)
        permits=sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now)
        for r,t in teachers.items():
            skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
            elapsed=clocks[r].observe((skill,t.end,t.handoff),now,prev[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
            before=clone_teacher(t)
            # Independent negative-evidence history, fed ONLY the baseline's
            # actual issued camera posture. No hypothetical future views.
            proxy=clone_teacher(t);empty_world[r]=spaces[r].update(worlds[r],proxy,now)
            cmd,done=t.step(worlds[r],now,permit_pick=permits[r])
            mismatch+=not same(cmd,done,t.phase,led[r][i])
            sim=round(now-rows[0]['t'],4)
            for variant in variants:
                c=clone_teacher(before)
                name,_,mm=variant.partition('@')
                modes=S18 if name=='bundle' else {name:S18[name]}
                sa.MARGIN_M=float(mm)/1000. if mm else sa.REQUIRED_MARGIN_M;sa.ANALYSIS_OVERRIDE=bool(mm)
                c.search15_modes.update(modes)
                if 'search18_free_space' in modes:c.search18_space=deepcopy(spaces[r])
                value,finished=c.step(deepcopy(worlds[r]),now,permit_pick=permits[r])
                changed=(value!=cmd or finished!=done or c.phase!=t.phase or c.outcome!=t.outcome)
                old_block=t.blocked_goal_calls-before.blocked_goal_calls
                new_block=c.blocked_goal_calls-before.blocked_goal_calls
                old_no=t.no_path_calls-before.no_path_calls;new_no=c.no_path_calls-before.no_path_calls
                regress=(new_block>old_block or new_no>old_no or (t.outcome is None and c.outcome is not None)
                         or (any(cmd['wheels']) and not any(value['wheels'])) or (done and not finished))
                stats[variant].update(ticks=1,changed=int(changed),worse_decisions=int(regress),
                    new_blocks=max(0,new_block-old_block),new_no_path=max(0,new_no-old_no),
                    relaxed_blocks=max(0,old_block-new_block),resolved_no_path=max(0,old_no-new_no),
                    footprint_rejects=sum(e['event']=='footprint_pulse_reject' for e in c.search18_log))
                if changed and r not in first[variant]:first[variant][r]={'sim_s':sim,'phase':c.phase,'outcome':c.outcome,'events':c.search18_log}
                if changed and len(diffs[variant])<12:
                    diffs[variant].append({'rid':r,'sim_s':sim,'phase':[t.phase,c.phase],'wheels':[cmd['wheels'],value['wheels']],
                        'keys':sorted(k for k in value if value[k]!=cmd.get(k)),'peer_wait':[sorted(t.peer_wait_ids),sorted(c.peer_wait_ids)],
                        'blocked_since':[t.approach_blocked_since,c.approach_blocked_since]})
                targets={315709:(('r1',3.7),('r1',16.4)),8311709:(('r1',3.3),),8311702:(('r1',7.6),('r1',16.6)),8311711:(('r2',13.8),('r2',25.8))}
                if any(r==rr and abs(sim-ss)<.01 for rr,ss in targets.get(plan['seed'],())):
                    nav=c._navigation(worlds[r]);radius,discs,rects=c._constraints(worlds[r]);pose,g,heading,goal=c._geometry(worlds[r])
                    probes.append({'variant':variant,'rid':r,'sim_s':sim,'old_outcome':t.outcome,'new_outcome':c.outcome,
                        'old_no_path':old_no,'new_no_path':new_no,'old_block':old_block,'new_block':new_block,
                        'old_wheels':cmd['wheels'],'new_wheels':value['wheels'],'events':c.search18_log,
                        'actual_start_free':nav.free(pose[:2],discs,rects,radius),'goal_free':nav.free(goal,discs,rects,radius),
                        'retained_path_valid':bool(nav.retained_path(pose[:2],before.path,goal,discs,rects,radius)),
                        'free_space_status':spaces[r].last_status,'free_space_cleared':spaces[r].cleared})
            if t.phase=='approach' and t.peer_wait_ids:wait_ticks['baseline'][r]+=1
            for v in shadow_names:
                sh=shadows[v][r];sh.skill_started=t.skill_started
                if sh.outcome is None:
                    sh.prepare_signal(deepcopy(worlds[r]),now)
                    sv,sd=sh.step(deepcopy(worlds[r]),now,permit_pick=permits[r])
                    if sh.phase=='approach' and sh.peer_wait_ids:wait_ticks[v][r]+=1
                    trace.setdefault((v,r),[]).append([sim,sh.phase,sh.outcome,any(sv['wheels']),sh.approach_plan_valid,sh.approach_blocked_since,sorted(sh.peer_wait_ids),sh.peer_wait_since,sh.planner_calls,sh.no_path_calls,sh.blocked_goal_calls])
                    if sv['wheels']!=cmd['wheels']:shadow_cmd_first[v].setdefault(r,sim)
                    if sh.phase!=t.phase or sh.outcome!=t.outcome:shadow_first[v].setdefault(r,{'sim_s':sim,'baseline_phase':t.phase,'shadow_phase':sh.phase,'shadow_outcome':sh.outcome})
                sh.remember_applied(led[r][i]['applied_command'])
            t.remember_applied(led[r][i]['applied_command'])
            if done:t.done_recorded=True
        for r in led:prev[r]=led[r][i]['applied_command'];models[r].issue(prev[r])
    sa.MARGIN_M=sa.REQUIRED_MARGIN_M;sa.ANALYSIS_OVERRIDE=False
    return {'stage':stage,'episode':ep,'seed':plan['seed'],'original_success':result['physical_success'],
        'raw':str(raw),'sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
        'robot_ticks':len(rows)*2,'baseline_mismatch_ticks':mismatch,'variants':stats,'first_change':first,'diffs':diffs,'shadow_trace':{f'{v}/{r}':x for (v,r),x in trace.items()},'shadow_wait_ticks':{v:dict(c) for v,c in wait_ticks.items()},'shadow_first_divergence':shadow_first,'shadow_first_command_divergence':shadow_cmd_first,'probes':probes,
        'free_space_events':{r:s.events for r,s in spaces.items()},'input_audit':audit}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seeds',nargs='*',type=int)
    p.add_argument('--variants',nargs='*',default=[*S18,'bundle']);p.add_argument('--shadow',nargs='*',default=[*S18,'bundle']);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    results=[]
    for stage,n in [('repro3',3),('novel12',12)]:
        for ep in range(n):
            plan=json.loads(read(a.root/STAGES[stage]/'diagnostic'/f'episode-{ep:03d}'/'raw/plan.json'))
            if a.seeds and plan['seed'] not in a.seeds:continue
            r=replay(a.root,stage,ep,a.variants,a.shadow);results.append(r)
            (a.out/f'{stage}-{ep}.json').write_text(json.dumps(r,indent=2)+'\n')
            print(json.dumps({'seed':r['seed'],'success':r['original_success'],'mismatch':r['baseline_mismatch_ticks'],'variants':r['variants']}),flush=True)
    summary={'scope':'one-step same-state counterfactual decisions on recorded observations/commands; not physical results',
        'runs':results,'robot_ticks':sum(r['robot_ticks'] for r in results),
        'baseline_mismatch_ticks':sum(r['baseline_mismatch_ticks'] for r in results),
        'success_N':sum(r['original_success'] for r in results),
        'success_runs_with_worse_decisions':{v:sum(r['variants'][v]['worse_decisions']>0 for r in results if r['original_success']) for v in a.variants}}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
