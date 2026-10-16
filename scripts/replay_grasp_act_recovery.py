"""Exact saved-input regression; stop candidate at its first divergent command.

All baseline commands are checked. A divergent prefix is a new decision only:
subsequent saved images belong to the old trajectory, not to a candidate run.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import ModuleType
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

BASELINE='86367b4b78a14c772f6194f6b36d524a0f934afe'
ROOT=Path(__file__).resolve().parents[1]
KW=dict(bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',
        approach_goal_set='approach_goal_set_v1',nominal_blocked_handoff='nominal_blocked_handoff_v1',approach_progress='approach_progress_v1')


def replay(raw,baseline):
    proof=[];plan=json.loads(verified(raw,'plan.json',proof));result=json.loads(verified(raw,'result.json',proof))
    assert result['source_sha']==BASELINE and result['input_audit']['invisible_measurements']==0
    assert result['self_pose_source']=='issued' and result['weld']=='off'
    labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl'+('.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else ''),proof).splitlines()] for r in plan['roles']}
    inputs=[{'t':d['t'],'measurements':d['visible_measurements']} for l in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (d:=json.loads(l))]
    models={r:VisibleWorld(r,e) for r,e in plan['roles'].items()};previous={r:labels[r][0]['clean_teacher_command'] for r in plan['roles']}
    old={r:baseline(r,e,previous[r]['pwm'],**KW) for r,e in plan['roles'].items()}
    new={r:VisibleOnlyGraspTeacher(r,e,previous[r]['pwm'],**KW,approach_recovery='approach_recovery_v1') for r,e in plan['roles'].items()}
    clocks=[{r:IssuedClock() for r in old} for _ in range(2)];syncs=[GraspStartSync(plan['roles'],result['grasp_start_delays_s']) for _ in range(2)]
    audit=new_input_audit(True,'issued');first=None;identical=0;maximum=0.;digest=hashlib.sha256()
    for i,row in enumerate(inputs):
        now=row['t'];worlds={}
        for r in old:
            audit_visible_input(audit,row['measurements'][r]);worlds[r]=AuditedTeacherInput(models[r].observe(row['measurements'][r],now),audit)
        ticks=[]
        for k,teachers in enumerate((old,new) if first is None else (old,)):
            permits=syncs[k].tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now);tick={}
            for r,t in teachers.items():
                skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                elapsed=clocks[k][r].observe((skill,t.end,t.handoff),now,previous[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
                cmd,done=t.step(worlds[r],now,permit_pick=permits[r]);tick[r]=(cmd,done,t.phase)
                if k==0:
                    expected=labels[r][i]['clean_teacher_command'];dt=max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']));maximum=max(maximum,dt)
                    assert all(cmd[x]==expected[x] for x in ('t','wheels','pwm')) and dt<=1e-12,(raw,i,r,'baseline command')
                    assert done==labels[r][i]['done'] and t.phase==labels[r][i]['teacher_phase'],(raw,i,r,'baseline phase')
                    digest.update(json.dumps(cmd,sort_keys=True).encode())
                t.remember_applied(cmd)
                if done:t.done_recorded=True
            ticks.append(tick)
        if first is None:
            changed=[r for r in old if ticks[0][r]!=ticks[1][r]]
            if changed:
                first={'tick':i,'elapsed_sim_s':now-inputs[0]['t'],'robots':changed,
                       'baseline':{r:ticks[0][r] for r in changed},'candidate':{r:ticks[1][r] for r in changed},
                       'decisions':{r:new[r].diagnostic() for r in changed}}
            else:identical+=len(old)
        for r in old:previous[r]=labels[r][i]['applied_command'];models[r].issue(previous[r])
    return {'episode':int(raw.parent.name[-3:]),'seed':plan['seed'],'saved_success':result['physical_success'],
            'baseline_commands_verified':len(inputs)*len(old),'baseline_command_sha256':digest.hexdigest(),
            'saved_libm_max_duration_delta_s':maximum,'candidate_identical_commands':identical,
            'first_divergence':first,'input_audit':audit,'raw_proof':proof,
            'candidate_outcomes_at_last_compared_tick':{r:t.outcome for r,t in new.items()}}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    source=subprocess.check_output(['git','show',f'{BASELINE}:sim/grasp_act_teacher_v3.py'],cwd=ROOT,text=True)
    module=ModuleType('pinned_86367b4b');exec(compile(source,'86367b4b/grasp_act_teacher_v3.py','exec'),module.__dict__)
    rows=[]
    for raw in sorted(a.run.glob('cohort-*/episode-*/raw')):
        row=replay(raw,module.VisibleOnlyGraspTeacher);rows.append(row)
        print(json.dumps({k:row[k] for k in ('episode','saved_success','candidate_identical_commands')}),flush=True)
    assert len(rows)==40 and sum(r['saved_success'] for r in rows)==34
    summary={'schema':'ugrp.grasp_act.recovery_replay.v1','baseline_sha':BASELINE,'rows':rows,
             'baseline_commands_verified':sum(r['baseline_commands_verified'] for r in rows),
             'successful_unchanged_indices':[r['episode'] for r in rows if r['saved_success'] and r['first_divergence'] is None],
             'successful_changed_indices':[r['episode'] for r in rows if r['saved_success'] and r['first_divergence'] is not None],
             'failed_changed_indices':[r['episode'] for r in rows if not r['saved_success'] and r['first_divergence'] is not None],
             'invisible_measurements':sum(r['input_audit']['invisible_measurements'] for r in rows),
             'held_world_reads':sum(r['input_audit']['held_world_reads'] for r in rows),
             'scope':'no World, physics, rendering, model or remote execution; baseline all commands, candidate only valid prefix through first divergence; no new physical success claim'}
    a.out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))

if __name__=='__main__':main()
