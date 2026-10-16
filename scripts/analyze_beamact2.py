"""GCP2 raw recount: every seed, ordered funnel, rejection table; no rollout."""
import argparse
from collections import Counter
from pathlib import Path

from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.beamact_pair_student import Funnel, STAGES
from harness.beamact_pair_score import assigned_forces
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import source_sha


def existing(path):
    return path if path.exists() else Path(str(path)+'.zst')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=False);analysis_source=source_sha()
    queue=read_json(a.root/'queue.json')
    runs=[];frame_pass=Counter();frame_reject=Counter();cumulative=Counter();reasons=Counter();failure_stages=Counter()
    for seed in range(8329000,8329020):
        out=a.root/f'seed-{seed}';path=out/'result.json'
        if not path.exists():
            runs.append(dict(seed=seed,status='NOT_STARTED',complete=False));continue
        r=read_json(path)
        row=dict(seed=seed,raw=str(out),result_sha256=sha256(path),status=r['status'],
            complete=r['complete'],cap_end=r['cap_end'],physical_success=False)
        if r['complete']:
            raw=existing(out/'eval-only.jsonl');evaluations=read_rows(raw)
            commands=read_rows(existing(out/'commands.jsonl'))
            inputs=read_rows(existing(out/'student-inputs.jsonl'))
            from harness.beamact_replay import replay
            protocol_replay=replay(inputs,commands,read_rows(existing(out/'chunk-predictions.jsonl')),
                read_json(out/'initial-issued.json'),read_json(out/'start-protocol.json'))
            # Revalidate ALL serialized actor inputs, not just inference calls.
            from harness.grasp_act_rollout import InputAudit, LiftScore
            from harness import grasp_act_contract as c
            audit=InputAudit()
            for obs in inputs:audit.accept(obs)
            f=Funnel();score=LiftScore();unrestricted=LiftScore();done={};counts=Counter()
            roles=read_json(out/'plan.json')['roles']
            for cmd in commands:
                c.command(cmd['command'])
                if cmd['done']:done.setdefault(cmd['robot'],cmd['t'])
                counts[cmd['robot']]+=1
            for e in evaluations:
                truth=e['truth']
                assigned=assigned_forces(e['target_finger_contact_rows'],truth['beam']['ends'],roles)
                assert assigned==e['assigned_contact_forces']
                forces=[v for rid in ('r1','r2') for v in assigned[rid]]
                score.add(e['t'],clearance=truth['beam']['min_z'],tilt=truth['beam']['tilt_deg'],forces=forces,weld=False)
                unrestricted.add(e['t'],clearance=truth['beam']['min_z'],tilt=truth['beam']['tilt_deg'],
                    forces=[v for rid in ('r1','r2') for v in truth['contacts'][rid]],weld=False)
                passed=dict(e['passed']);passed['lift_3s']=score.record()['lift_success']
                f.add(e['t'],passed)
            success=score.record()['lift_success'] and len(done)==2 and not r['cap_end']
            assert success==r['physical_success'] and f.record()==r['funnel']
            assert counts['r1']==counts['r2']==len(evaluations)
            assert len(inputs)==len(commands)==2*len(evaluations)
            assert all(v['invisible_measurements']==v['held_world_reads']==0 for v in r['input_audit'].values())
            assert r['teacher_actions']==r['truth_corrections']==0 and r['weld']=='off'
            category='success' if success else 'cap_end' if r['cap_end'] else f.record()['failure_stage'] or 'command_completion'
            reasons[category]+=1
            if not success:failure_stages[f.record()['failure_stage'] or 'command_completion']+=1
            cumulative.update(f.record()['cumulative_run_pass']);frame_pass.update(f.frames);frame_reject.update(f.rejected)
            row.update(physical_success=success,category=category,done_times=done,input_audit=audit.record,
                protocol_replay=protocol_replay,
                funnel=f.record(),raw_eval_sha256=sha256(raw),commands_sha256=sha256(existing(out/'commands.jsonl')),
                command_rows=len(commands),max_stable_hold_s=score.max_stable_s,
                max_unrestricted_stable_hold_s=unrestricted.max_stable_s,
                final_target_finger_min_gap_m=evaluations[-1]['target_finger_min_gap_m'],
                raw_independent_stage_frames={s:sum(e['passed'][s] for e in evaluations) for s in STAGES})
        else:
            row['category']='HOST_ERROR';reasons['HOST_ERROR']+=1
        runs.append(row)
    completed=sum(r['complete'] for r in runs);n=sum(r.get('physical_success',False) for r in runs)
    result=dict(schema='ugrp.beamact2.summary.v1',host=host,n=n,N=20,attempted=sum(r['status']!='NOT_STARTED' for r in runs),
        independent_joint_hold_n=sum(r.get('max_stable_hold_s',0.)>=3.-1e-8 for r in runs),
        unrestricted_joint_hold_n=sum(r.get('max_unrestricted_stable_hold_s',0.)>=3.-1e-8 for r in runs),
        complete=completed==20,completed=completed,not_started=20-sum(r['status']!='NOT_STARTED' for r in runs),
        analysis_source_sha=analysis_source,
        verdict='READY' if n==20 and completed==20 else 'NOT_READY',source_sha=queue['source_sha'],
        model_sha256=queue['model_sha256'],runs=runs,reason_distribution=dict(reasons),
        criteria=dict(lift=LiftScore.CRITERIA,contact_assignment='nearest authored colored end; ties ambiguous',
            both_student_done=True,cap_end=False),
        failure_stage_distribution=dict(failure_stages),
        funnel={s:dict(cumulative_runs=cumulative[s],frame_pass=frame_pass[s],frame_reject=frame_reject[s]) for s in STAGES},
        verification='raw eval/commands/all own-input rows recounted; no teacher results merged')
    write_json(a.root/'summary.json',result)
    write_json(a.root/'rejection_table.json',dict(source_sha=queue['source_sha'],funnel=result['funnel'],
        reasons=dict(reasons),failure_stages=dict(failure_stages),runs=[dict(seed=r['seed'],reason_category=r.get('category','not_started'),
            blocked_object='beam_1:target_not_inferred_blocker',min_gap_m=r.get('final_target_finger_min_gap_m'),
            gap_scope='evaluation-only target-finger signed gap; no obstruction cause inferred',raw=r.get('raw')) for r in runs],
        reproduce='python -m scripts.analyze_beamact2 --root '+str(a.root)))
    print('beamact2',n,'/20',result['verdict'],result['funnel'])


if __name__=='__main__':main()
