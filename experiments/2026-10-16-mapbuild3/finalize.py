"""Finite gcp2 evidence reduction; no model calls, integration, or policy input."""
from pathlib import Path
from collections import Counter
import hashlib,json,sys,shutil
base=Path(sys.argv[1]);out=base/'delivery-final';out.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text())
write=lambda p,x:p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
raw=base/'gcp5-original-r2/capture-r1c';prep=base/'gcp5-original-r2/prepare-r1b';analysis=base/'analysis-r1'
for name in ('tracking-scores.json','command-phase-scale.json','map-scores.json','reproduce.json'):
    shutil.copyfile(analysis/name,out/name)
for source,target in [(raw/'summary.json','capture-summary.json'),(base/'capture-retrieval.json','capture-retrieval.json'),
                       (base/'obstacle-eval-r2.json','obstacle-evaluation.json'),(analysis/'playback/receipts.json','playback-receipts.json'),
                       (prep/'fixture.json','fixture.json'),(prep/'original-rejection-table.json','original-spawn-rejection-table.json'),
                       (prep/'spawn-rejection-table.json','spawn-rejection-table.json')]:shutil.copyfile(source,out/target)
cam=read(analysis/'camera-eval.json');write(out/'camera-summary.json',{k:v for k,v in cam.items() if k!='frames'})
audit=read(base/'audit-delivery-r3/audit-summary.json');funnel=read(analysis/'rejection_table.json')
rows=read(prep/'spawn-rejection-table.json')['rows'];joint={}
for row in rows:
    if row['candidate'].startswith('common-lattice-'):joint.setdefault(row['candidate'],[]).append(row['accepted'])
funnel['spawn']=dict(raw=str(prep),unit='shared XY candidate, both camera postures',stages=[
    dict(stage='tested_shared_starts',cumulative_pass_n=len(joint),rejected_n=0),
    dict(stage='both_postures_nonpenetrating',cumulative_pass_n=sum(all(x) for x in joint.values()),rejected_n=sum(not all(x) for x in joint.values()))],
    point_reasons=dict(Counter(k for row in rows for k in row['reasons'])),reason_fields='spawn-rejection-table.json rows[].rejections[]')
funnel['audit']=dict(raw=str(base/'audit-r3'),cohorts=audit['counts'])
funnel['map_cells']=[]
for name,score in read(analysis/'map-scores.json').items():
    total=score['observed_truth_cells']+score['out_of_truth_cells'];correct=score['observed_truth_cells']-score['wrong_free_cells']-score['occupied_fp']
    funnel['map_cells'].append(dict(candidate_sequence=name,unit='predicted_cell',stages=[
        dict(stage='predicted',cumulative_pass_n=total,rejected_n=0),dict(stage='inside_truth_domain',cumulative_pass_n=score['observed_truth_cells'],rejected_n=score['out_of_truth_cells']),
        dict(stage='correct_occupancy',cumulative_pass_n=correct,rejected_n=score['wrong_free_cells']+score['occupied_fp'])]))
write(out/'rejection_table.json',funnel)
write(out/'next-queue.json',dict(status='WITHHELD',ready=False,rejection_table=str(out/'rejection_table.json'),
    category='unqualified_camera_and_motion_model',reason='HIGH remains unknown; lateral issued/actual discrepancy; coverage1.27%; obstacle unobserved; warp10 reference NOT_READY',
    blocked_object='not_observed:contact clearance not measured',minimum_gap_m=None,gap_status='not_measured'))
summary=dict(schema='ugrp.mapbuild3.summary.v1',status='NOT_READY',simulation_host='ugrp-act-l4-gcp5',project='ugrp-sim-e-1016',
    analysis_host='ugrp-sim-gcp2',old_results_pooled=False,rounds=dict(physical_candidate=1,physical_cap_end_worlds=2,setup_host_errors_before_physics=2,
    audit_versions=3,audit_first_error='absolute mesh path; zero integration',tracking_candidates_same_capture=2),
    capture=read(raw/'summary.json'),camera=cam['summary'],tracking=read(analysis/'tracking-scores.json'),
    maps={k:{key:v[key] for key in ('coverage','total_truth_cells','observed_truth_cells','wrong_free_cells','occupied_tp','occupied_fp','unknown_truth_cells')} for k,v in read(analysis/'map-scores.json').items()},
    audit_counts=audit['counts'],rejection_table=str(out/'rejection_table.json'),
    gate4=funnel['gate4'],scope='fixed4SIMs, one map and shared clean XY, no long exploration/arrival/transport/E2E or real robot success')
write(out/'summary.json',summary)
write(out/'RUN_META.json',dict(**{'class':'milestone'},pr=556,branch='codex/mapbuild1',sha=summary['capture']['source_sha'],batch='mapbuild3',
    basis='selected version evidence, including failed attempts retained; not mission success'))
write(out/'SHA256SUMS.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()})
print(out)
