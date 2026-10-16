"""Replay delivered inputs against f932b02c; never instantiate a simulator.

Saved truth is discarded before either controller receives its input. The six
normal traces must match every saved command and the baseline byte for byte
(with <=1e-12 tolerance only across GCP/Mac libm pulse widths).
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import ModuleType
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.run_grasp_act_teacher import finalize_outcomes
from scripts.run_grasp_act_batch import handoff_only
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

BASELINE='f932b02c5074a7727aab57af1907b69332699c33'
NORMAL_SOURCE='a45645200e13f2bad9fbe882e8c9c15a439457c3'
ROOT=Path(__file__).resolve().parents[1]


def replay(raw,baseline,*,normal):
    proof=[];plan=json.loads(verified(raw,'plan.json',proof));result=json.loads(verified(raw,'result.json',proof))
    assert result['source_sha']==(NORMAL_SOURCE if normal else BASELINE)
    assert result['physical_success'] is normal and result['input_audit']['invisible_measurements']==0
    assert result['self_pose_source']=='issued' and result['weld']=='off'
    labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl.zst',proof).splitlines()] for r in plan['roles']}
    inputs=[{'t':row['t'],'measurements':row['visible_measurements']}
            for line in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (row:=json.loads(line))]
    models={r:VisibleWorld(r,e) for r,e in plan['roles'].items()}
    previous={r:labels[r][0]['clean_teacher_command'] for r in plan['roles']}
    kw={'bounds':(-20,20,-20,20),'teacher_stability':'align_relook_v1',
        'teacher_search':'search_body_scan_v2','approach_goal_set':'approach_goal_set_v1',
        'nominal_blocked_handoff':'nominal_blocked_handoff_v1'}
    old={r:baseline(r,e,previous[r]['pwm'],**kw) for r,e in plan['roles'].items()}
    new={r:VisibleOnlyGraspTeacher(r,e,previous[r]['pwm'],**kw,approach_progress='approach_progress_v1') for r,e in plan['roles'].items()}
    syncs=[GraspStartSync(plan['roles'],result['grasp_start_delays_s']) for _ in range(2)]
    clocks=[{r:IssuedClock() for r in plan['roles']} for _ in range(2)]
    count=0;digest=hashlib.sha256();delta=0.
    for i,row in enumerate(inputs):
        now=row['t'];worlds={r:models[r].observe(row['measurements'][r],now) for r in plan['roles']}
        ticks=[]
        for k,teachers in enumerate((old,new)):
            permits=syncs[k].tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now)
            tick={}
            for r,t in teachers.items():
                skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                elapsed=clocks[k][r].observe((skill,t.end,t.handoff),now,previous[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
                cmd,done=t.step(worlds[r],now,permit_pick=permits[r]);expected=labels[r][i]['clean_teacher_command']
                if k==0 or normal:
                    assert all(cmd[key]==expected[key] for key in ('t','wheels','pwm')),(raw,i,r,k)
                    dt=max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']));delta=max(delta,dt)
                    assert dt<=1e-12 and done==labels[r][i]['done'] and t.phase==labels[r][i]['teacher_phase'],(raw,i,r,k)
                tick[r]=(cmd,done,t.phase);t.remember_applied(cmd)
                if done:t.done_recorded=True
            ticks.append(tick)
        # Command equality is required up to and including the handoff tick.
        assert ticks[0]==ticks[1],(raw,i,'candidate changed command on saved-input trajectory')
        for r in plan['roles']:
            digest.update(json.dumps(ticks[1][r][0],sort_keys=True).encode());count+=1
        if any(t.outcome is not None for t in new.values()):
            assert not normal
            finalize_outcomes(new,strict=True,joint_held=False)
            report={'status':'complete','physical_success':False,'approach_handoff':True,
                    'teachers':{r:t.diagnostic() for r,t in new.items()}}
            assert handoff_only(report)
            assert all(not any(ticks[1][r][0]['wheels']) and ticks[1][r][0]['pwm']['1']==2000
                       and t.phase not in ('pick','complete') for r,t in new.items())
            return {'seed':plan['seed'],'normal':False,'clean_approach_handoff':True,
                    'handoff_sim_s':now-inputs[0]['t'],'commands_identical_before_handoff':count,
                    'teachers':report['teachers'],'raw_proof':proof}
        for r in plan['roles']:
            previous[r]=labels[r][i]['applied_command'];models[r].issue(previous[r])
    assert normal,'failure trace did not hand off'
    return {'seed':plan['seed'],'normal':True,'commands_compared':count,
            'command_sha256':digest.hexdigest(),'saved_gcp_max_duration_delta_s':delta,
            'progress_logs':{r:t.progress_log for r,t in new.items()},'raw_proof':proof}


def main():
    p=argparse.ArgumentParser();p.add_argument('--normal-run',type=Path,required=True)
    p.add_argument('--failed-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    source=subprocess.check_output(['git','show',f'{BASELINE}:sim/grasp_act_teacher_v3.py'],cwd=ROOT,text=True)
    module=ModuleType('pinned_f932b02c');exec(compile(source,'f932b02c/grasp_act_teacher_v3.py','exec'),module.__dict__)
    rows=[replay(a.normal_run/'diagnostic'/f'episode-{i:03d}'/'raw',module.VisibleOnlyGraspTeacher,normal=True) for i in range(6)]
    rows += [replay(a.failed_run/'cohort-000'/f'episode-{i:03d}'/'raw',module.VisibleOnlyGraspTeacher,normal=False) for i in (12,15)]
    summary={'schema':'ugrp.grasp_act.progress_replay.v1','baseline_sha':BASELINE,'normal_saved_source_sha':NORMAL_SOURCE,
             'normal_identical_n':6,'normal_N':6,'normal_commands_compared':sum(r.get('commands_compared',0) for r in rows),
             'failed_clean_handoff_n':2,'failed_N':2,'rows':rows,
             'baseline_candidate_commands':'exact equality including pulse durations until terminal handoff',
             'invisible_measurements':0,'held_world_reads':0,'evaluation_truth_delivered_to_teacher':False,
             'audit_scope':'replay only: whitelist measurements + issued pose; no simulator/world constructed',
             'physical_success_new':0,'scope':'offline replay; no physical, rendering, model or remote execution'}
    a.out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))


if __name__=='__main__':main()
