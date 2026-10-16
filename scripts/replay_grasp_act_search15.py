"""search14 versus bounded reobservation and pregrasp sampling on saved inputs; no simulator or renderer.

Every A command is checked against the retrieved ledger. After the first
candidate divergence, all observations AND applied commands still come from A;
these are shadow decisions, never new physical trajectories or successes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.replay_grasp_act_remaining import pinned
from scripts.replay_grasp_act_recovery import KW
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

SOURCE='abe63b9034b400c61314e76b382dea3c8f81c0ce'
BASELINE='8d9ad79a42a8a5486ce6cbf65aef87e78cd87f8e'
from sim.grasp_act_search15_modes import MODES
MODE='progress_view_recovery_v3'


def replay(raw, baseline):
    proof=[]
    plan=json.loads(verified(raw,'plan.json',proof));result=json.loads(verified(raw,'result.json',proof))
    assert result['source_sha']==SOURCE and result['approach_coordination']=='off'
    assert result['handoff_observation']=='visible_handoff_v1' and result['approach_recovery']==MODE
    assert result['self_pose_source']=='issued' and result['weld']=='off'
    labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl'+
            ('.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else ''),proof).splitlines()] for r in plan['roles']}
    inputs=[{'t':d['t'],'measurements':d['visible_measurements']}
            for l in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (d:=json.loads(l))]
    previous={r:labels[r][0]['applied_command'] for r in labels}
    models={r:VisibleWorld(r,e) for r,e in plan['roles'].items()}
    groups=[{r:cls(r,e,previous[r]['pwm'],**KW,approach_recovery=MODE,**modes)
             for r,e in plan['roles'].items()} for cls,modes in
             ((baseline,{}),(VisibleOnlyGraspTeacher,{}),(VisibleOnlyGraspTeacher,MODES))]
    clocks=[{r:IssuedClock() for r in labels} for _ in groups]
    syncs=[GraspStartSync(plan['roles'],result['grasp_start_delays_s']) for _ in groups]
    audit=new_input_audit(True,'issued');first=None;changes=0;maxdelta=0.;phase_changes=0
    digests=[hashlib.sha256() for _ in groups]
    for i,row in enumerate(inputs):
        now=row['t'];worlds={}
        for r in labels:
            audit_visible_input(audit,row['measurements'][r])
            worlds[r]=AuditedTeacherInput(models[r].observe(row['measurements'][r],now),audit)
        ticks=[]
        for j,teachers in enumerate(groups):
            permits=syncs[j].tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now);tick={}
            for r,t in teachers.items():
                skill='wait' if t.phase=='ready' and not permits[r] else 'grasp'
                elapsed=clocks[j][r].observe((skill,t.end,t.handoff),now,previous[r]['pwm'])
                t.skill_started=now-elapsed['skill_elapsed_s']
                cmd,done=t.step(worlds[r],now,permit_pick=permits[r]);tick[r]=(cmd,done,t.phase,t.outcome)
                digests[j].update(json.dumps(tick[r],sort_keys=True).encode())
                if j==0:
                    expected=labels[r][i]['clean_teacher_command']
                    delta=max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']));maxdelta=max(maxdelta,delta)
                    assert all(cmd[k]==expected[k] for k in ('t','wheels','pwm')) and delta<=1e-12,(raw,i,r,'baseline command')
                    assert done==labels[r][i]['done'] and t.phase==labels[r][i]['teacher_phase'],(raw,i,r,'baseline state')
                t.remember_applied(labels[r][i]['applied_command'])
                if done:t.done_recorded=True
            ticks.append(tick)
        assert ticks[0]==ticks[1],(raw,i,'OFF regression')
        changed=[r for r in labels if ticks[0][r][0]!=ticks[2][r][0]]
        changes+=len(changed)
        state_changed=[r for r in labels if ticks[0][r][1:]!=ticks[2][r][1:]];phase_changes+=len(state_changed)
        if first is None and (changed or state_changed):
            rs=sorted(set(changed+state_changed))
            first={'tick':i,'elapsed_sim_s':now-inputs[0]['t'],'robots':rs,
                'baseline':{r:ticks[0][r] for r in rs},'candidate':{r:ticks[2][r] for r in rs},
                'reason_events':{r:groups[2][r].events[-3:]+groups[2][r].recovery_log[-3:] for r in rs},
                'candidate_choices':{r:groups[2][r].approach_choice for r in rs}}
        for r in labels:
            previous[r]=labels[r][i]['applied_command'];models[r].issue(previous[r])
    diagnostics={r:t.diagnostic() for r,t in groups[2].items()}
    candidates=[c for d in diagnostics.values() for attempt in d['goal_set_log'] for c in attempt['candidates']]
    return {'episode':int(raw.parent.name[-3:]),'seed':plan['seed'],'saved_physical_success':result['physical_success'],
        'saved_handoff':result['approach_handoff'],'saved_sim_s':result['sim_s'],
        'saved_input_audit':result['input_audit'],'source_sha':SOURCE,
        'commands_verified':len(inputs)*len(labels),'off_changed_commands':0,
        'candidate_changed_commands':changes,'candidate_changed_states':phase_changes,'first_divergence':first,
        'input_audit':audit,'max_recorded_duration_delta_s':maxdelta,
        'command_sha256':[d.hexdigest() for d in digests],
        'candidate_goal_checks':len(candidates),
        'candidate_angle_distribution':dict(__import__('collections').Counter(str(round(c['offset_deg'],3)) for c in candidates)),
        'candidate_rejection_reasons':dict(__import__('collections').Counter(c['reason'] for c in candidates)),'candidate_goal_rejections':sum(c['reason']!='feasible' for c in candidates),
        'shadow_handoff_robots':sum(t.outcome in ('approach_blocked_handoff','search_timeout_handoff') for t in groups[2].values()),
        'shadow_diagnostics':diagnostics,'raw_proof':proof}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    baseline=pinned(BASELINE);rows=[]
    for i in range(13):
        row=replay(a.run/'diagnostic'/f'episode-{i:03d}'/'raw',baseline);rows.append(row)
        print(i,'changes',row['candidate_changed_commands'],'first',row['first_divergence'] and row['first_divergence']['elapsed_sim_s'],flush=True)
    normal=rows[:6]
    summary={'schema':'ugrp.grasp_act.search15_replay.v1','baseline_sha':BASELINE,'recorded_source_sha':SOURCE,'candidate_modes':MODES,
        'scope':'saved-input shadow replay; after divergence not a physical trajectory; no new physical results',
        'N':13,'saved_success_n':sum(r['saved_physical_success'] for r in rows),
        'saved_handoff_n':sum(r['saved_handoff'] for r in rows),'saved_host_error_n':0,
        'normal_commands':sum(r['commands_verified'] for r in normal),
        'normal_changed_commands':sum(r['candidate_changed_commands'] for r in normal),
        'normal_changed_states':sum(r['candidate_changed_states'] for r in normal),
        'normal_identical_episodes':sum(r['first_divergence'] is None for r in normal),
        'commands_verified':sum(r['commands_verified'] for r in rows),
        'invisible_measurements':sum(r['input_audit']['invisible_measurements'] for r in rows),
        'held_world_reads':sum(r['input_audit']['held_world_reads'] for r in rows),'rows':rows}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))
    assert summary['normal_identical_episodes']==6,'normal regression: inspect first branch before submission'


if __name__=='__main__':main()
