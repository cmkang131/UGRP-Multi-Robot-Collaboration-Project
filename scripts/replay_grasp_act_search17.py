"""Saved-input teacher replay only (no World/render/host access).

Loader/clock/synchronization follow beam-gate-752b0cbb/scripts/{load,rp}.py.
Evaluation fields are used only for grouping; only visible_measurements enter
VisibleWorld. Observers integrate RECORDED commands after divergence: later
branches are forced-input diagnostics, never counterfactual physical outcomes.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_search15_modes import MODES
from sim.grasp_act_search17 import MODES as SEARCH17

KW=dict(bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',
        approach_goal_set='approach_goal_set_v1',nominal_blocked_handoff='nominal_blocked_handoff_v1',
        approach_progress='approach_progress_v1',approach_recovery='progress_view_recovery_v3',
        approach_coordination='off',**MODES)


def read(path):
    path=Path(path)
    if path.exists():return path.read_bytes()
    return subprocess.check_output(['zstd','-q','-dc',str(path)+'.zst'])


def load(root,ep):
    d=root/f'cohort-{ep//16*16:03d}'/f'episode-{ep:03d}'/'raw'
    ev=[json.loads(x) for x in read(d/'eval-only.jsonl').splitlines()]
    labels={r:[json.loads(x) for x in read(d/f'teacher-{r}.jsonl').splitlines()] for r in ('r1','r2')}
    return ev,labels,json.loads(read(d/'result.json')),json.loads(read(d/'plan.json'))


def same(cmd,done,phase,row):
    expected=row['clean_teacher_command']
    return (all(cmd[k]==expected[k] for k in ('t','wheels','pwm'))
        and max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']))<=1e-12
        and done==row['done'] and phase==row['teacher_phase'])


def replay(root,ep,modes,*,probes=False):
    ev,labels,result,plan=load(root,ep)
    inputs=[{'t':r['t'],'measurements':r['visible_measurements']} for r in ev]
    previous={r:labels[r][0]['applied_command'] for r in labels}
    models={r:VisibleWorld(r,e,odometry=modes.get('search17_odometry','off')) for r,e in plan['roles'].items()}
    teachers={r:VisibleOnlyGraspTeacher(r,e,previous[r]['pwm'],**KW,**modes) for r,e in plan['roles'].items()}
    clocks={r:IssuedClock() for r in labels}
    sync=GraspStartSync(plan['roles'],result['grasp_start_delays_s']);audit=new_input_audit(True,'issued')
    mismatch=0;first={};one_step=[]
    for i,row in enumerate(inputs):
        now=row['t'];worlds={}
        for r in labels:
            audit_visible_input(audit,row['measurements'][r])
            worlds[r]=AuditedTeacherInput(models[r].observe(row['measurements'][r],now),audit)
        permits=sync.tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now)
        for r,t in teachers.items():
            skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
            elapsed=clocks[r].observe((skill,t.end,t.handoff),now,previous[r]['pwm'])
            t.skill_started=now-elapsed['skill_elapsed_s']
            # Exact baseline-state counterfactual at original known branch times.
            if probes and ep in (25,40,47) and abs(now-inputs[0]['t']-{25:3.7,40:17.4,47:19.3}[ep])<.01 and r=={25:'r1',40:'r1',47:'r2'}[ep]:
                other=deepcopy(t);other.search15_modes.update({k:v for k,v in SEARCH17.items() if k!='search17_odometry'})
                value,done=other.step(deepcopy(worlds[r]),now,permit_pick=permits[r])
                one_step.append({'rid':r,'sim_s':round(now-inputs[0]['t'],3),'original':labels[r][i]['clean_teacher_command'],
                                 'new':value,'events':other.search17_log,'reobserve':other.reobserver.events[-3:]})
            cmd,done=t.step(worlds[r],now,permit_pick=permits[r])
            if not same(cmd,done,t.phase,labels[r][i]):
                mismatch+=1
                if r not in first:first[r]={'tick':i,'sim_s':round(now-inputs[0]['t'],3),'phase':t.phase,
                    'old':labels[r][i]['clean_teacher_command'],'new':cmd,'events':deepcopy(t.search17_log[-3:])}
            t.remember_applied(labels[r][i]['applied_command'])
            if done:t.done_recorded=True
        for r in labels:
            previous[r]=labels[r][i]['applied_command'];models[r].issue(previous[r])
    events={r:t.search17_log for r,t in teachers.items()}
    return {'ep':ep,'seed':plan['seed'],'original_success':result['physical_success'],'mismatch_ticks':mismatch,
            'robot_ticks':len(inputs)*2,'first_divergence':first,'events':events,'one_step_probes':one_step,
            'input_audit':audit,'scope':'saved visible inputs + recorded applied commands; physical effect unverified'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--episodes',type=int,nargs='+',default=list(range(16,56)))
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    modes={'off':{},'geometry':{k:v for k,v in SEARCH17.items() if k!='search17_odometry'},'full':SEARCH17}
    allrows=[]
    for ep in a.episodes:
        rows={name:replay(a.root,ep,values,probes=name=='off') for name,values in modes.items()}
        allrows.append(rows);(a.out/f'episode-{ep:03d}.json').write_text(json.dumps(rows,indent=2)+'\n')
        print(json.dumps({'ep':ep,**{k:{'mismatch_ticks':r['mismatch_ticks'],'first':{rid:v['sim_s'] for rid,v in r['first_divergence'].items()},'events':{rid:sorted(set(x['event'] for x in v)) for rid,v in r['events'].items()}} for k,r in rows.items()}}),flush=True)
    summary={'scope':'offline forced-input replay; no physical claim','source_base':'752b0cbbe25fb97d908c661e6fd00b5d6a3e44f3',
             'episodes':len(allrows),'baseline_mismatch_ticks':sum(r['off']['mismatch_ticks'] for r in allrows),
             'robot_ticks':sum(r['off']['robot_ticks'] for r in allrows),'profiles':{}}
    for name in ('geometry','full'):
        good=[r[name] for r in allrows if r[name]['original_success']]
        summary['profiles'][name]={'successes_N':len(good),'successes_with_command_divergence':sum(bool(r['first_divergence']) for r in good),
          'successes_with_geometry_branch':sum(any(r['events'].values()) for r in good),
          'geometry_branch_episodes':[r['ep'] for r in good if any(r['events'].values())],
          'failure_first_divergence':{r[name]['ep']:r[name]['first_divergence'] for r in allrows if not r[name]['original_success']}}
    summary['artifacts']=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(a.out.glob('episode-*.json'))]
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
