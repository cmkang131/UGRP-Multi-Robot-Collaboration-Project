"""Actual GCP ledger replay and same-state search20 probes; no physics/render.

Recorded future observations/commands remain fixed even after a branch differs.
The persistent shadow is also a recorded-input diagnostic, not a new trajectory.
"""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_search18 import read, KW, clone_teacher
from scripts.replay_grasp_act_search17 import same
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_search15_modes import ALL_MODES
from sim.grasp_act_search19 import MODES as S19
from sim.grasp_act_search20 import MODES as S20
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher as Teacher
from sim.grasp_act_teacher import local, wrap

ROOT = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def replay(raw, output):
    names = ('eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl','result.json','plan.json')
    data = {n: read(raw/n) for n in names}
    rows = [json.loads(x) for x in data['eval-only.jsonl'].splitlines()]
    plan, result = (json.loads(data[n]) for n in ('plan.json','result.json'))
    led = {r:[json.loads(x) for x in data[f'teacher-{r}.jsonl'].splitlines()] for r in plan['roles']}
    prev = {r:led[r][0]['applied_command'] for r in led}
    modes = {k:result.get(k,'off') for k in ALL_MODES}
    teachers = {r:Teacher(r,e,prev[r]['pwm'],**KW,**modes) for r,e in plan['roles'].items()}
    models = {r:VisibleWorld(r,e,odometry=modes['search17_odometry']) for r,e in plan['roles'].items()}
    clocks = {r:IssuedClock() for r in led}
    sync = GraspStartSync(plan['roles'],result['grasp_start_delays_s'])
    audit = new_input_audit(True,'issued'); counts = Counter(); diffs=[]; timing=[]; snapshots=[]
    shadow = {r:Teacher(r,e,prev[r]['pwm'],**KW,**{**modes,**S19,**S20}) for r,e in plan['roles'].items()}
    shadow_sync = GraspStartSync(plan['roles'],result['grasp_start_delays_s'])
    shadow_clocks = {r:IssuedClock() for r in led}
    continuation={};continuation_rows=[]
    captures = {}; old_approach = Teacher._approach; old_plan = Teacher._plan_approach
    def capture(self,w,now):
        captures[id(self)] = deepcopy(dict(w))
        return old_approach(self,w,now)
    def capture_plan(self,w,now):
        captures[id(self)] = deepcopy(dict(w))
        return old_plan(self,w,now)
    Teacher._approach = capture; Teacher._plan_approach = capture_plan
    try:
        for i,row in enumerate(rows):
            now=row['t']; worlds={}
            for r in led:
                audit_visible_input(audit,row['visible_measurements'][r])
                worlds[r]=AuditedTeacherInput(models[r].observe(row['visible_measurements'][r],now),audit)
            permits=sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now)
            sp=shadow_sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in shadow.items()},now)
            for r,t in teachers.items():
                skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                elapsed=clocks[r].observe((skill,t.end,t.handoff),now,prev[r]['pwm'])
                t.skill_started=now-elapsed['skill_elapsed_s']; before=clone_teacher(t)
                cmd,done=t.step(worlds[r],now,permit_pick=permits[r])
                counts['baseline_mismatch_ticks']+=not same(cmd,done,t.phase,led[r][i])
                if modes.get('search19_footprint')!='off' and before.search19_body_active and now>=15.4-1e-6 and r not in continuation:
                    continuation[r]=clone_teacher(before);continuation[r].search15_modes.update(S20)
                c=clone_teacher(before);c.search15_modes.update({**S19,**S20})
                value,finished=c.step(deepcopy(worlds[r]),now,permit_pick=permits[r])
                changed=value!=cmd or finished!=done or c.phase!=t.phase or c.outcome!=t.outcome
                worse=((any(cmd['wheels']) and not any(value['wheels'])) or (done and not finished)
                       or (t.outcome is None and c.outcome is not None)
                       or c.no_path_calls-before.no_path_calls>t.no_path_calls-before.no_path_calls)
                counts.update(robot_ticks=1,changed=int(changed),worse=int(worse))
                timing.append(c.search20_compute)
                if changed and len(diffs)<24:
                    diffs.append({'rid':r,'t':now,'phase':[t.phase,c.phase],
                        'outcome':[t.outcome,c.outcome],'wheels':[cmd['wheels'],value['wheels']],
                        'search20':c.search20_log[-2:]})
                # Preserve the inherited search19 stance to isolate late jitter.
                if plan['seed']==8311709 and r=='r1' and any(abs(now-tt)<.015 for tt in (5.7,15.4,16.4,17.4,18.4,19.4)):
                    w=captures.get(id(t),dict(worlds[r]))
                    pose,point,heading,goal=t._geometry(w)
                    snapshots.append({'t':now,'world':w,'pwm':before.sink.pwm,
                        'choice':before.approach_choice,'path':before.path,'path_goal':before.path_goal,
                        'body_active':before.search19_body_active,'folded':before.folded_ready,
                        'baseline':{'valid':t.approach_plan_valid,'outcome':t.outcome,'wheels':cmd['wheels']},
                        'search20':{'valid':c.approach_plan_valid,'outcome':c.outcome,'wheels':value['wheels'],
                            'events':c.search20_log[-2:],'compute':c.search20_compute},
                        'goal':goal,'heading':heading})
                if r in continuation:
                    cc=continuation[r];cc.skill_started=t.skill_started
                    cv,cd=cc.step(deepcopy(worlds[r]),now,permit_pick=permits[r])
                    if any(abs(now-tt)<.015 for tt in (15.4,16.4,17.4,18.4,19.4)):
                        continuation_rows.append({'rid':r,'t':now,'valid':cc.approach_plan_valid,'outcome':cc.outcome,'wheels':cv['wheels'],'compute':cc.search20_compute,'events':cc.search20_log[-2:]})
                    cc.remember_applied(led[r][i]['applied_command'])
                s=shadow[r]
                skill='wait' if s.phase=='ready' and not sp[r] else 'grasp'
                el=shadow_clocks[r].observe((skill,s.end,s.handoff),now,prev[r]['pwm']);s.skill_started=now-el['skill_elapsed_s']
                sv,sd=s.step(deepcopy(worlds[r]),now,permit_pick=sp[r])
                counts['shadow_changed']+=sv!=cmd or sd!=done or s.phase!=t.phase or s.outcome!=t.outcome
                for obj in (t,s):
                    obj.remember_applied(led[r][i]['applied_command'])
                    if done:obj.done_recorded=True
            for r in led:
                prev[r]=led[r][i]['applied_command'];models[r].issue(prev[r])
    finally:
        Teacher._approach=old_approach;Teacher._plan_approach=old_plan
    summary={'seed':plan['seed'],'raw':str(raw),'source_sha':result['source_sha'],
        'original_success':result['physical_success'],'scope':'recorded-input decisions only; NOT physical success',
        **counts,'input_audit':audit,'decoded_sha256':{n:hashlib.sha256(x).hexdigest() for n,x in data.items()},
        'timing':{'max_s':max(x['elapsed_s'] for x in timing),'max_body_planning_s':max(x['body_planning_s'] for x in timing),'total_s':sum(x['elapsed_s'] for x in timing),
                  'budget_exhausted_ticks':sum(x['budget_exhausted'] for x in timing),
                  'max_checks':max(x['checks'] for x in timing),'cache_hits':sum(x['cache_hits'] for x in timing)},
        'shadow':{r:{'outcome':t.outcome,'phase':t.phase,'events':t.search20_log} for r,t in shadow.items()}}
    output.mkdir(parents=True,exist_ok=True)
    (output/f'{plan["seed"]}-detail.json').write_text(json.dumps({'summary':summary,'diffs':diffs,'snapshots':snapshots,'continuation':continuation_rows,'timing_ticks':timing},indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--cohorts',nargs='+',choices=('search18','search19'),default=['search18','search19'])
    p.add_argument('--seeds',nargs='*',type=int);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    runs=[]
    for cohort in a.cohorts:
        patterns = ['grasp-search19-repro4-gcp-06558d64'] if cohort=='search19' else ['grasp-search18-repro4-gcp-00620d7a','grasp-search18-novel12-gcp-00620d7a']
        for group in patterns:
            for raw in sorted((a.root/group).glob('diagnostic*/episode-*/raw')):
                seed=json.loads(read(raw/'plan.json'))['seed']
                if a.seeds and seed not in a.seeds:continue
                s=replay(raw,a.out/cohort);s['cohort']=cohort;runs.append(s)
                print(json.dumps({k:v for k,v in s.items() if k not in ('shadow','decoded_sha256')}),flush=True)
                (a.out/'summary.json').write_text(json.dumps({'runs':runs,'complete':False},indent=2)+'\n')
    src=['sim/grasp_act_search20.py','sim/grasp_act_search19.py','sim/grasp_act_teacher_v3.py','sim/grasp_act_pregrasp.py','scripts/replay_grasp_act_search20.py']
    summary={'scope':'recorded-input replay; no dynamics/render/model/remote execution',
        'complete':True,'runs':runs,'robot_ticks':sum(x['robot_ticks'] for x in runs),
        'baseline_mismatch_ticks':sum(x['baseline_mismatch_ticks'] for x in runs),
        'success_N':sum(x['original_success'] for x in runs),
        'success_changed_N':sum(bool(x['changed']) for x in runs if x['original_success']),
        'success_worse_N':sum(bool(x['worse']) for x in runs if x['original_success']),
        'source_hashes':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in src}}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':main()
