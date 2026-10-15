"""Read completed GCP2 ACT16a artifacts, never run a policy/optimizer."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

from harness.grasp_act_data import read_rows, read_json, sha256, write_json
from scripts.analyze_grasp_act_act16a import require_cpu, existing, errors, stats, summarize_errors, reversal_events
from scripts.analyze_grasp_act_act14 import recount

STAGES=('approach','alignment','grasp','lift_confirmation')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();host=require_cpu();a.output.mkdir(parents=True,exist_ok=False)
    jobs=read_json(a.batch/'batch-summary.json')['results']
    phases=defaultdict(lambda:defaultdict(list)); refresh=defaultdict(lambda:defaultdict(list))
    copies=[]; events=[]; masks=[]; runs=[]; rejected=[]
    for job in sorted(jobs,key=lambda r:r['seed']):
        raw=Path(job['raw']);s=read_json(raw/'summary.json')
        if job['status']!='complete' or not s.get('complete'):
            runs.append({'seed':job['seed'],'status':'HOST_ERROR','raw':str(raw)});continue
        obs=read_rows(raw/'student-inputs.jsonl');cmd=read_rows(raw/'commands.jsonl');labels=read_rows(raw/'shadow-labels.jsonl')
        query_ids={r['sample_id'] for r in read_rows(raw/'chunk-predictions.jsonl')}
        ev=read_rows(raw/'eval-only.jsonl');funnel=recount(ev)
        assert len(obs)==len(cmd)==len(labels)==len(ev)
        assert funnel['first_pass_sim_t']==s['first_pass_sim_t']
        invalid=0;rows=[]
        for o,u,l in zip(obs,cmd,labels):
            valid=l['label_valid'] and l['teacher_command'] is not None
            row=dict(t=o['t'],phase=l['teacher_phase'],valid=valid,act=u['command'],persistence=o['issued'][-1],target=l['teacher_command'])
            rows.append(row)
            if not valid:invalid+=1;continue
            for policy in ('act','persistence'):
                err=errors(row[policy],row['target']);phases[l['teacher_phase']][policy].append(err);phases['ALL'][policy].append(err)
                if o['sample_id'] in query_ids:
                    refresh[l['teacher_phase']][policy].append(err);refresh['ALL'][policy].append(err)
            sa,sp,sy=map(np.sign,(row['act']['wheels'],row['persistence']['wheels'],row['target']['wheels']))
            needed=sy!=sp
            copies.append(dict(phase=l['teacher_phase'],query=o['sample_id'] in query_ids,n=4,agree=int((sa==sp).sum()),corrective=int(needed.sum()),
                               copied=int(((sa==sp)&needed).sum()),correct=int(((sa==sy)&needed).sum())))
        run_events=reversal_events(rows)
        events.extend(dict(seed=job['seed'],**r) for r in run_events)
        mask=read_rows(Path(job['offline'][-1])/'mask-rows.jsonl');masks.extend(mask)
        failed=next((k for k in STAGES if not funnel['cumulative_run_pass'][k]),None)
        contacts=[v for r in ev for v in r['external_contacts']]
        contact=min(contacts,key=lambda r:r['gap_m']) if contacts else None
        gap=min(r['target_finger_min_gap_m'] for r in ev)
        rej=dict(category=failed+'_not_passed' if failed else 'completed' if s['physical_success'] else 'completion_not_passed',
            blocking_object=contact['object'] if contact else 'none_observed',
            minimum_gap_m=contact['gap_m'] if contact else gap,
            minimum_gap_pair='external contact pair' if contact else 'target to nearest finger; no external contact',
            target_object=read_json(raw/'plan.json')['item_id'],target_finger_min_gap_m=gap,
            scope='evaluation-only observed gap/contact, not a proven collision cause',seed=job['seed'],raw=str(raw),
            reproduce_argv=job['rollout'])
        if not s['physical_success']:rejected.append(rej)
        shadow=read_json(raw/'shadow-progress.json')
        original=read_json(Path(__file__).resolve().parents[1]/'experiments/2026-10-15-act-train/act15-summary.json')
        old=next(r for r in original['primary_runs'] if r['seed']==job['seed'])
        record=dict(seed=job['seed'],status='complete',raw=str(raw),first_failed_gate=failed,
            funnel=funnel,done_times=s['done_times'],termination=s['termination'],cap_end=s['cap_end'],
            physical_success=s['physical_success'],stable_lift=s['lift_success'],input_audit=s['input_audit'],
            shadow_input_audit=shadow['input_audit'],teacher_actions_executed=shadow['teacher_actions_executed'],
            valid_expert_rows=len(rows)-invalid,invalid_expert_rows=invalid,wall_s=s['wall_s'],sim_s=s['sim_s'],
            policy_calls=s['inference_latency_s']['n'],rejection=rej,
            outcome_matches_original_summary=all([old['completed']==s['physical_success'],old['cap_end']==s['cap_end'],old['first_failed_gate']==failed]),
            original_manifest_hash=old['hash_manifest'],
            raw_hashes={str(f.relative_to(raw)):sha256(f) for f in raw.rglob('*') if f.is_file()})
        # Full raw hash map remains on GCP2, summary is intentionally compact.
        write_json(a.output/f'run-{job["seed"]}-integrity.json',record)
        record.pop('raw_hashes');runs.append(record)
    write_json(a.output/'reversal-events.json',events)
    copy={p:{'wheel_rows':sum(r['n'] for r in copies if p=='ALL' or r['phase']==p),
        **{k:sum(r[k] for r in copies if p=='ALL' or r['phase']==p) for k in ('agree','corrective','copied','correct')}}
        for p in ('ALL','start','fold','approach','align','relook')}
    refresh_copy={p:{'wheel_rows':sum(r['n'] for r in copies if r['query'] and (p=='ALL' or r['phase']==p)),
        **{k:sum(r[k] for r in copies if r['query'] and (p=='ALL' or r['phase']==p)) for k in ('agree','corrective','copied','correct')}}
        for p in ('ALL','start','fold','approach','align','relook')}
    errors_report={p:{policy:summarize_errors(v) for policy,v in data.items()} for p,data in phases.items()}
    metrics=dict(host=host,completed_runs=sum(r['status']=='complete' for r in runs),
        errors_by_phase=errors_report,copycat=copy,
        refresh_only_errors={p:{policy:summarize_errors(v) for policy,v in data.items()} for p,data in refresh.items()},
        refresh_only_copycat=refresh_copy,
        reversal={'events':len(events),**{policy:{'matched':sum(r[policy+'_delay_s'] is not None for r in events),
            'censored':sum(r[policy+'_delay_s'] is None for r in events),
            'matched_delay_s':stats([r[policy+'_delay_s'] for r in events if r[policy+'_delay_s'] is not None])} for policy in ('act','persistence')}},
        reversal_requiring_response={'events':sum(r['requires_response'] for r in events),
            'target_dwell_s':stats([r['target_dwell_s'] for r in events if r['requires_response']]),
            **{policy:{'matched':sum(r['requires_response'] and r[policy+'_delay_s'] is not None for r in events),
                'censored':sum(r['requires_response'] and r[policy+'_delay_s'] is None for r in events),
                'matched_delay_s':stats([r[policy+'_delay_s'] for r in events if r['requires_response'] and r[policy+'_delay_s'] is not None])} for policy in ('act','persistence')}},
        mask=dict(queries=len(masks),h0_delta=summarize_errors([r['h0_delta'] for r in masks]),
            done_flips=sum(r['done_flip'] for r in masks),
            max_stored_chunk_error=max(r['stored_chunk_max_abs_error'] for r in masks),
            h0_original_error=summarize_errors([r['h0_original_error'] for r in masks if r['label_valid']]),
            h0_masked_error=summarize_errors([r['h0_masked_error'] for r in masks if r['label_valid']])),
        caveats=['Only valid pre-hover expert labels; no expert actions executed.',
                 'Masking is post-hoc OOD sensitivity, not a causal or retrained ablation.',
                 'Persistence lag is on fixed ACT trajectory, not a persistence rollout.'])
    write_json(a.output/'metrics.json',metrics)
    cohorts={}
    for name,condition in [('same20',lambda s:s<91500),('new20',lambda s:s>=91500)]:
        group=[r for r in runs if condition(r['seed']) and r['status']=='complete'];prior=len(group);gates=[];frame_gates=[]
        frame_prior=sum(r['funnel']['counts']['evaluation_frames'] for r in group)
        for stage in STAGES:
            n=sum(r['funnel']['cumulative_run_pass'][stage] for r in group)
            gates.append(dict(gate=stage,received=prior,passed=n,rejected=prior-n));prior=n
            frames=sum(r['funnel']['counts'].get(stage,0) for r in group)
            frame_gates.append(dict(gate=stage,received=frame_prior,passed=frames,rejected=frame_prior-frames));frame_prior=frames
        rej=[r for r in rejected if condition(r['seed'])]
        cohorts[name]=dict(N=len(group),candidate_gate=dict(received=20,passed=len(group),rejected=20-len(group)),
            gate_events=gates,frame_events=frame_gates,
            completion_gate=dict(received=prior,passed=sum(r['physical_success'] for r in group),rejected=prior-sum(r['physical_success'] for r in group)),
            cap_end=sum(r['cap_end'] for r in group),student_done=sum(r['termination']=='student_done' for r in group),
            rejection_distribution=dict(Counter(r['category'] for r in rej)),rejections=rej)
    original_path=Path(__file__).resolve().parents[1]/'experiments/2026-10-15-act-train/act15-funnel.json'
    old=read_json(original_path)
    old_compact={k:{field:value for field,value in v.items() if field!='runs'} for k,v in old['cohorts'].items()}
    write_json(a.output/'rejection_table.json',dict(schema='ugrp.act16a.rejection_table.v2',
        pooling=False,original_gcp1=dict(source_path=str(original_path),sha256=sha256(original_path),cohorts=old_compact),
        regenerated_gcp2=dict(host=host,source_batch=str(a.batch),cohorts=cohorts),
        semantics='Sequential historical run attainment; frame events follow frozen ACT14 evaluator, never control input.',
        rejection_gap_scope='Names/gaps are observed contacts; absent contact uses nearest target-finger gap, not inferred collision cause.'))
    write_json(a.output/'runs.json',runs)
    print(json.dumps({'runs':len(runs),'cohorts':{k:[v['N']]+[r['passed'] for r in v['gate_events']] for k,v in cohorts.items()}},allow_nan=False))


if __name__=='__main__':main()
