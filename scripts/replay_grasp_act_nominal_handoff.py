"""Replay delivered measurements and issued commands; never construct a World.

Normal traces must match both the pinned baseline and every saved command.
The blocked trace terminates at a clean map handoff before any alternative.
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
from scripts.run_grasp_act_teacher import finalize_outcomes
from scripts.run_grasp_act_batch import handoff_only
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

BASELINE='a45645200e13f2bad9fbe882e8c9c15a439457c3'
ROOT=Path(__file__).resolve().parents[1]


def verified(raw,name,proof):
    path=raw/name;entry=json.loads((raw/'manifest.json').read_text())[name]
    data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=entry['sha256']:raise ValueError('raw hash mismatch: '+str(path))
    if name.endswith('.zst'):
        data=subprocess.check_output(['zstd','-dc',str(path)])
        if hashlib.sha256(data).hexdigest()!=entry['decoded_sha256']:
            raise ValueError('decoded hash mismatch: '+str(path))
    proof.append({'path':str(path),'sha256':digest,'decoded_sha256':hashlib.sha256(data).hexdigest()})
    return data.decode()


def replay(raw,baseline,*,normal):
    proof=[];plan=json.loads(verified(raw,'plan.json',proof))
    result=json.loads(verified(raw,'result.json',proof))
    if result['source_sha']!=BASELINE:raise ValueError('replay source mismatch')
    if normal and result['physical_success'] is not True:raise ValueError('normal trace did not succeed')
    labels={rid:[json.loads(line) for line in verified(raw,f'teacher-{rid}.jsonl.zst',proof).splitlines()]
            for rid in plan['roles']}
    # Discard evaluator truth before replay. Only the recorded delivered
    # measurement whitelist and time reach VisibleWorld and the teachers.
    inputs=[{'t':row['t'],'measurements':row['visible_measurements']}
            for line in verified(raw,'eval-only.jsonl.zst',proof).splitlines() if (row:=json.loads(line))]
    models={rid:VisibleWorld(rid,end) for rid,end in plan['roles'].items()}
    previous={rid:labels[rid][0]['clean_teacher_command'] for rid in plan['roles']}
    kw={'bounds':(-20,20,-20,20),'teacher_stability':'align_relook_v1',
        'teacher_search':'search_body_scan_v2','approach_goal_set':'approach_goal_set_v1'}
    old={rid:baseline(rid,end,previous[rid]['pwm'],**kw) for rid,end in plan['roles'].items()}
    new={rid:VisibleOnlyGraspTeacher(rid,end,previous[rid]['pwm'],**kw,
        nominal_blocked_handoff='nominal_blocked_handoff_v1') for rid,end in plan['roles'].items()}
    syncs=[GraspStartSync(plan['roles'],result['grasp_start_delays_s']) for _ in range(2)]
    clocks=[{rid:IssuedClock() for rid in plan['roles']} for _ in range(2)]
    digest=hashlib.sha256();count=0;max_duration_delta=0.
    for i,row in enumerate(inputs):
        now=row['t'];worlds={rid:models[rid].observe(row['measurements'][rid],now) for rid in plan['roles']}
        baseline_tick={};candidate_tick={}
        for k,teachers in enumerate((old,new) if normal else (new,)):
            ready={rid:t.prepare_signal(worlds[rid],now) for rid,t in teachers.items()}
            permits=syncs[k].tick(ready,now)
            for rid,t in teachers.items():
                label=labels[rid][i]
                skill='wait' if t.phase=='ready' and not permits[rid] else 'grasp'
                elapsed=clocks[k][rid].observe((skill,t.end,t.handoff),now,previous[rid]['pwm'])
                t.skill_started=now-elapsed['skill_elapsed_s']
                issued,done=t.step(worlds[rid],now,permit_pick=permits[rid])
                if teachers is new:candidate_tick[rid]=issued
                if not normal and t.outcome is None:
                    expected=label['clean_teacher_command']
                    assert all(issued[key]==expected[key] for key in ('t','wheels','pwm'))
                    assert max(abs(a-b) for a,b in zip(issued['duration_s'],expected['duration_s']))<=1e-12
                    assert done==label['done'] and t.phase==label['teacher_phase']
                if normal:
                    expected=label['clean_teacher_command']
                    delta=max(abs(a-b) for a,b in zip(issued['duration_s'],expected['duration_s']))
                    max_duration_delta=max(max_duration_delta,delta)
                    # GCP x86 -> Mac libm can differ below 1e-15 in pulse
                    # duration. The old/new pair below must still be exact.
                    if (any(issued[key]!=expected[key] for key in ('t','wheels','pwm'))
                            or delta>1e-12 or done!=label['done'] or t.phase!=label['teacher_phase']):
                        raise AssertionError(f'{raw.parent.name} tick={i} {rid} baseline={k==0}: actual={issued,done,t.phase}; expected={label["clean_teacher_command"],label["done"],label["teacher_phase"]}')
                    if k==0:baseline_tick[rid]=(issued,done,t.phase)
                    if k==1:
                        assert (issued,done,t.phase)==baseline_tick[rid], 'candidate differs from a4564520'
                        digest.update(json.dumps(issued,sort_keys=True).encode());count+=1
                t.remember_applied(issued)
                if done:t.done_recorded=True
        if not normal and any(t.outcome is not None for t in new.values()):
            finalize_outcomes(new,strict=True,joint_held=False)
            handoff={'status':'complete','physical_success':False,
                     'teachers':{rid:t.diagnostic() for rid,t in new.items()}}
            assert handoff_only(handoff)
            assert any(t.outcome=='approach_blocked_handoff' for t in new.values())
            assert not any(t.goal_set_log for t in new.values())
            assert all(t.phase not in ('pick','complete') and not any(candidate_tick[rid]['wheels'])
                       and candidate_tick[rid]['pwm']['1']==2000 for rid,t in new.items())
            return {'seed':plan['seed'],'clean_approach_handoff':True,'handoff_sim_s':now-inputs[0]['t'],
                    'commands_compared':0,'teachers':handoff['teachers'],'raw_proof':proof}
        for rid in plan['roles']:
            previous[rid]=labels[rid][i]['applied_command'];models[rid].issue(previous[rid])
    assert normal, 'hard replay did not hand off'
    return {'seed':plan['seed'],'normal':True,'commands_compared':count,'command_sha256':digest.hexdigest(),
            'sim_s':inputs[-1]['t']-inputs[0]['t'],'saved_gcp_max_duration_delta_s':max_duration_delta,'raw_proof':proof}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();source=subprocess.check_output(['git','show',f'{BASELINE}:sim/grasp_act_teacher_v3.py'],cwd=ROOT,text=True)
    module=ModuleType('pinned_grasp_teacher');exec(compile(source,'a4564520/grasp_act_teacher_v3.py','exec'),module.__dict__)
    rows=[replay(a.run/'diagnostic'/f'episode-{i:03d}'/'raw',module.VisibleOnlyGraspTeacher,normal=i<6) for i in range(7)]
    summary={'schema':'ugrp.grasp_act.nominal_handoff_replay.v1','baseline_sha':BASELINE,
        'normal_identical_n':6,'normal_N':6,'hard_clean_handoff_n':1,'hard_N':1,
        'commands_compared':sum(r['commands_compared'] for r in rows),'rows':rows,
        'baseline_candidate_commands':'exact equality including all pulse durations',
        'saved_gcp_duration_tolerance_s':1e-12,'saved_gcp_other_command_fields':'exact equality',
        'scope':'offline replay only; no new physical success, rendering, model calls or remote submission',
        'evaluation_truth_delivered_to_teacher':False}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))


if __name__=='__main__':main()
