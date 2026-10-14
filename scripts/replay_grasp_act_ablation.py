"""Search12 single-toggle and conditional saved-input shadow replay; no new views or physical evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_handoff import visible_local_sample
from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
from harness.grasp_act_start_sync import GraspStartSync,GraspApproachSync,GraspConditionalApproachSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.replay_grasp_act_remaining import pinned
from scripts.replay_grasp_act_recovery import BASELINE,KW
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
from sim.grasp_act_priority import MODE,OBSERVED_MODE


def replay(raw,baseline,*,require_unchanged=True):
    proof=[];p=json.loads(verified(raw,'plan.json',proof));result=json.loads(verified(raw,'result.json',proof))
    assert result['source_sha']==BASELINE and result['weld']=='off' and result['self_pose_source']=='issued'
    labels={r:[json.loads(l) for l in verified(raw,f'teacher-{r}.jsonl.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else f'teacher-{r}.jsonl',proof).splitlines()] for r in p['roles']}
    inputs=[{'t':v['t'],'measurements':v['visible_measurements']}
            for l in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (v:=json.loads(l))]
    previous={r:labels[r][0]['clean_teacher_command'] for r in labels};models={r:VisibleWorld(r,e) for r,e in p['roles'].items()}
    names=['baseline','off','gt_only','priority_only','both_old','conditional_with_gt']
    modes=['off','off','off',MODE,MODE,OBSERVED_MODE]
    groups=[{r:(baseline if j==0 else VisibleOnlyGraspTeacher)(r,e,previous[r]['pwm'],**KW,
        **({} if j==0 else {'approach_recovery':'off','approach_coordination':modes[j]}))
        for r,e in p['roles'].items()} for j in range(len(names))]
    syncs=[(GraspConditionalApproachSync if m==OBSERVED_MODE else GraspApproachSync if m==MODE else GraspStartSync)
           (p['roles'],result['grasp_start_delays_s']) for m in modes]
    clocks=[{r:IssuedClock() for r in labels} for _ in groups]
    audit=new_input_audit(True,'issued');count={n:0 for n in names[1:]};first={k:None for k in count}
    max_libm=0.;digests=[hashlib.sha256() for _ in groups];local_changed=0;first_label=None
    for i,row in enumerate(inputs):
        now=row['t'];worlds={}
        for r in labels:
            audit_visible_input(audit,row['measurements'][r]);worlds[r]=AuditedTeacherInput(models[r].observe(row['measurements'][r],now),audit)
        ticks=[]
        for j,teachers in enumerate(groups):
            if modes[j]==OBSERVED_MODE:
                requests={r:t.request_coordination(worlds[r],now) for r,t in teachers.items()}
                if syncs[j].request(requests,now):
                    for t in teachers.values():t.activate_coordination(now)
            permits=syncs[j].tick({r:t.prepare_signal(worlds[r],now) for r,t in teachers.items()},now);tick={}
            for r,t in teachers.items():
                waiting=j>0 and t.priority is not None and t.priority.waiting and (t.end=='teal' or t.priority.round==1)
                skill='wait' if (t.phase=='ready' and not permits[r]) or waiting else 'grasp'
                elapsed=clocks[j][r].observe((skill,t.end,t.handoff),now,previous[r]['pwm']);t.skill_started=now-elapsed['skill_elapsed_s']
                if j==2:
                    local_before,_=visible_local_sample(worlds[r],r,t.end,handed_off=t.handoff)
                    was_done=getattr(t,'done_recorded',False)
                cmd,done=t.step(worlds[r],now,permit_pick=permits[r]);tick[r]=(cmd,done,t.phase)
                digests[j].update(json.dumps(tick[r],sort_keys=True).encode())
                if j==0:
                    expected=labels[r][i]['clean_teacher_command']
                    delta=max(abs(a-b) for a,b in zip(cmd['duration_s'],expected['duration_s']));max_libm=max(max_libm,delta)
                    assert all(cmd[k]==expected[k] for k in ('t','wheels','pwm')) and delta<=1e-12,(raw,i,r,'baseline')
                    assert done==labels[r][i]['done'] and t.phase==labels[r][i]['teacher_phase']
                if j==2:
                    local_new=local_before and skill!='wait' and (t.phase!='complete' or not was_done)
                    label_changed=local_new!=labels[r][i]['local_skill_sample'];local_changed+=label_changed
                    if label_changed and first_label is None:first_label={'tick':i,'elapsed_s':now-inputs[0]['t'],'robot':r,'recorded':labels[r][i]['local_skill_sample'],'visible':local_new}
                t.remember_applied(labels[r][i]['applied_command'])
                if done:t.done_recorded=True
            ticks.append(tick)
        assert ticks[0]==ticks[1],(raw,i,'OFF differs from 86367b4b')
        assert ticks[0]==ticks[2],(raw,i,'GT-only changed control')
        if require_unchanged:assert ticks[0]==ticks[5],(raw,i,'conditional normal regression')
        assert ticks[3]==ticks[4],(raw,i,'GT toggle changed priority control')
        for j,key in enumerate(count,1):
            changed=[r for r in labels if ticks[0][r][0]!=ticks[j][r][0]];count[key]+=len(changed)
            if changed and first[key] is None:first[key]={'tick':i,'elapsed_s':now-inputs[0]['t'],'robots':changed,
                'baseline':{r:ticks[0][r] for r in changed},'candidate':{r:ticks[j][r] for r in changed},
                'reason':'coordination mode '+modes[j]}
        for r in labels:previous[r]=labels[r][i]['applied_command'];models[r].issue(previous[r])
    return {'episode':int(raw.parent.name[-3:]),'seed':p['seed'],'saved_success':result['physical_success'],
            'recorded_commands_verified':len(inputs)*len(labels),'off_identical_commands':len(inputs)*len(labels),
            'shadow_changed_commands':count,'first_divergence':first,'input_audit':audit,
            'visible_handoff_changed_training_labels':local_changed,'first_label_divergence':first_label,
            'conditional_protocol_events':syncs[-1].events,
            'conditional_request_events':{r:t.priority_request.events for r,t in groups[-1].items()},
            'max_recorded_libm_delta_s':max_libm,'command_sha256':[d.hexdigest() for d in digests],'raw_proof':proof}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    baseline=pinned(BASELINE);rows=[]
    for i in range(6):
        row=replay(a.run/'diagnostic'/f'episode-{i:03d}'/'raw',baseline);rows.append(row);print(i,row['shadow_changed_commands'],flush=True)
    assert sum(r['recorded_commands_verified'] for r in rows)==4664 and all(r['saved_success'] for r in rows)
    summary={'schema':'ugrp.grasp_act.search12_replay.v1','baseline_sha':BASELINE,
        'variants': ['off','gt_only','priority_only','both_old','conditional_with_gt'],'normal_N':6,'recorded_commands_verified':4664,'off_identical_commands':4664,
        'shadow_changed_commands':{k:sum(r['shadow_changed_commands'][k] for r in rows) for k in rows[0]['shadow_changed_commands']},
        'visible_handoff_changed_training_labels':sum(r['visible_handoff_changed_training_labels'] for r in rows),
        'invisible_measurements':sum(r['input_audit']['invisible_measurements'] for r in rows),
        'held_world_reads':sum(r['input_audit']['held_world_reads'] for r in rows),
        'scope':'same saved measurements and actual issued history; after first divergence counterfactual shadow outputs only; cannot generate new viewpoints or establish peer-block improvement; handoff labels do not remove episodes from gate',
        'rows':rows}
    a.out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))


if __name__=='__main__':main()
