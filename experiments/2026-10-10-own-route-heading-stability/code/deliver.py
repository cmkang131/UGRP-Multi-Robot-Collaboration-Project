"""Post-hoc egomap65 delivery; saved JSON and hashes only, no replay."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,statistics,subprocess,sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];EXP=Path(__file__).resolve().parents[1]
PRIMARY=Path('/Users/changmin/projects/ugrp')
def read(p):return json.loads(p.read_text())
def write(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def aggregate(scores):
    output={}
    for profile in ('baseline','a'):
        for heading in ('off','filtered_hysteresis_v1'):
            rows=[r for r in scores if r['profile']==profile and r['heading_stability']==heading]
            measured=[r for r in rows if r.get('samples',0)];n=sum(r['samples'] for r in measured)
            counts=Counter()
            for r in measured:counts.update(r['command_audit']['counts'])
            errors=[r['final_error_m'] for r in measured]
            output[f'{profile}/{heading}']=dict(registered=len(rows),measured=len(measured),statuses=dict(Counter(r['status'] for r in rows)),
                B=sum(r['B_arrived'] for r in measured),returned=sum(r['returned'] for r in measured),
                false_declarations=sum(r['false_declarations'] for r in measured),
                wall_contacts=sum(r['contacts']['wall'] for r in measured),robot_contacts=sum(r['contacts']['robot'] for r in measured),
                over3_frames=sum(r['over_3sigma'] for r in measured),frames=n,
                over3_rate=sum(r['over_3sigma'] for r in measured)/n if n else None,
                end_over3=sum(r['final_error_sigma']>3 for r in measured),
                final_error_median=statistics.median(errors) if errors else None,final_error_max=max(errors) if errors else None,
                counts=dict(counts),turn_fraction=counts['turn']/sum(counts.values()) if counts else None,
                forward_fraction=counts['forward']/sum(counts.values()) if counts else None,
                turn_moving_fraction=counts['turn']/(sum(counts.values())-counts['hold']) if sum(counts.values())>counts['hold'] else None,
                reversals=sum(r['command_audit']['turn_sign_reversals'] for r in measured),
                within_reversals=sum(r['command_audit']['within_alignment_reversals'] for r in measured),
                B_nearest_m=[dict(seed=r['seed'],distance=r.get('B_nearest_boundary_distance_m')) for r in measured])
    return output

def verify_subset(root):
    found=missing=0;bad=[]
    for manifest in root.rglob('artifacts.sha256.json'):
        for name,digest in read(manifest).items():
            p=manifest.parent/name
            if not p.exists():missing+=1;continue
            found+=1
            if sha(p)!=digest:bad.append(str(p))
    if bad:raise ValueError(('LOCAL_HASH_MISMATCH',bad))
    return dict(local_verified_files=found,local_unretrieved_files=missing,mismatches=bad,scope='Only retrieved files verified locally; original RGB/large maps remain on oracle-x86, not a Mac backup.')

def main():
    p=argparse.ArgumentParser();p.add_argument('batch',type=Path);p.add_argument('--smoke',type=Path,required=True);p.add_argument('--recovery',type=Path);a=p.parse_args()
    scores=read(a.batch/'scores.json');original_scores=list(scores);plan=read(a.batch/'batch-plan.json');retry_scores=[]
    if a.recovery:
        retry_scores=read(a.recovery/'scores.json')
        key=lambda r:(r['seed'],r['profile'],r['heading_stability'])
        replacements={key(r):r for r in retry_scores}
        for r in original_scores:
            if key(r) in replacements and (r.get('samples',0) or r['status']!='HOST_ERROR_NO_RESULT'):raise ValueError('CANNOT_REPLACE_PHYSICAL_RESULT')
        scores=[replacements.get(key(r),r) for r in original_scores]
    result=dict(host='oracle-x86',source_sha=plan['source_sha'],registered=24,summary=aggregate(scores),scores=scores,
        attempts=original_scores+retry_scores,attempts_n=len(original_scores)+len(retry_scores),
        retry_reason='five zero-physics input-loss jobs restored byte-for-byte' if a.recovery else None,
        recovery_files=verify_subset(a.recovery) if a.recovery else None,
        jobs=read(a.batch/'batch-status.json'),recovery_jobs=read(a.recovery/'batch-status.json') if a.recovery else [],batch_files=verify_subset(a.batch),smoke_files=verify_subset(a.smoke),
        server_verification=read(a.batch/'server-verification.json'),thresholds_changed=False,
        source_hashes={n:sha(a.batch/n) for n in ('scores.json','batch-plan.json','batch-status.json')})
    prefixes=[];oldroot=PRIMARY/'outputs/oracle-runs/egomap64-batch/data'
    for r in scores:
        if r['heading_stability']!='off':continue
        name=f"egomap65-{r['seed']}-{r['profile']}-off"
        current=(a.recovery/name) if a.recovery and (a.recovery/name/'own-controller.jsonl').exists() else a.batch/name
        old=oldroot/f"stage-{r['seed']}-{r['profile']}"
        if not (current/'own-controller.jsonl').exists():continue
        start=read(old/'result.json')['start_sim_s']
        traces=[[line for line in (folder/'own-controller.jsonl').read_text().splitlines() if start<=json.loads(line)['t']<start+60] for folder in (old,current)]
        prefixes.append(dict(seed=r['seed'],profile=r['profile'],frames=[len(x) for x in traces],identical=sum(x==y for x,y in zip(*traces)),all_identical=traces[0]==traces[1]))
    result['old_heading_first60s_prefix']=prefixes
    target=EXP/'results/comparison.json';write(target,result)
    sources=[]
    for r in scores:
        label='old' if r['heading_stability']=='off' else 'stable'
        name=f"{r['profile']}-{label}-{r['seed']}";source=PRIMARY/'outputs/egomap65-delivery/views'/name
        metrics=dict(registered=1,measured=int(r.get('samples',0)>0))
        for k in ('B_arrived','returned','false_declarations','over_3sigma','over_3sigma_rate','final_error_m','final_sigma_m','final_error_sigma','samples','B_nearest_boundary_distance_m','approach_sim_s','return_sim_s'):
            if r.get(k) is not None:metrics[k]=int(r[k]) if isinstance(r[k],bool) else r[k]
        if r.get('command_audit'):
            for k in ('turn_fraction','forward_fraction','turn_moving_fraction','turn_sign_reversals','within_alignment_reversals'):metrics[k]=r['command_audit'][k]
            for k,v in r['contacts'].items():metrics[k+'_contacts']=v
        metrics={'offline/'+k:v for k,v in metrics.items()}
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,offline_source=dict(path=str(target),sha256=sha(target)),
            offline_scalars=metrics,offline_scalar_scope='24 preregistered paired DEV conditions, same six checkpoints; failures retained',family='egomap65',
            policy=r['profile']+'-'+label,case=name,condition='oracle-x86',seed=r['seed'],source_sha=plan['source_sha'],outcome=r['status'],
            model_calls=0,hparam_metrics=list(metrics),evaluation=r)
        for k in ('wall_s','sim_s'):
            if r.get(k) is not None:view[k]=r[k]
        write(source/'result.json',view);sources.append(source)
    cmd=[sys.executable,str(ROOT/'scripts/export_offline_audit.py')]
    for source in sources:cmd+=['--source',str(source)]
    subprocess.run(cmd+['--output',str(PRIMARY/'outputs/tensorboard/1010-egomap65')],check=True)
    print(json.dumps(result['summary'],indent=2))
if __name__=='__main__':main()
