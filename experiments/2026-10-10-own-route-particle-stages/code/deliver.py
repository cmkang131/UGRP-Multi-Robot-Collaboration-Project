"""Lightweight result/TensorBoard packaging only; no physics or replay."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
PRIMARY=Path('/Users/changmin/projects/ugrp')


def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(roots):
    errors=[];verified=0
    manifests=sorted({m for root in roots for m in root.rglob('artifacts.sha256.json')})
    if not manifests:raise ValueError('NO_RAW_MANIFESTS')
    for manifest in manifests:
        for name,digest in read(manifest).items():
            verified+=1
            p=manifest.parent/name
            if not p.is_file() or sha(p)!=digest:errors.append(str(p))
    if errors:raise ValueError(errors)
    return verified


def main():
    p=argparse.ArgumentParser();p.add_argument('batch',type=Path)
    p.add_argument('--artifact-root',type=Path,action='append',required=True);a=p.parse_args()
    scores=read(a.batch/'scores.json');selection=read(a.batch/'selection.json')
    jobs=read(a.batch/'batch-status.json');plan=read(a.batch/'batch-plan.json')
    verified=verify(a.artifact_root)
    summary=dict(host='oracle-x86',source_sha=plan['source_sha'],registered_seed_count=2,
        available_seed_count=1,registered_slots=8,executed_stage_slots=sum(not j['status'].startswith('BLOCKED') for j in jobs),
        blocked_slots=sum(j['status'].startswith('BLOCKED') for j in jobs),full_runs=0,thresholds_changed=False,
        scores=scores,selection=selection,verified_files=verified,hash_mismatches=[],host_interruptions=4,
        host_retry_plan=read(PRIMARY/'outputs/egomap60-delivery/reboot-retry-plan.json'),
        raw=str(a.batch),source_hashes={name:sha(a.batch/name) for name in ['scores.json','selection.json','batch-plan.json','batch-status.json']})
    target=EXP/'results/comparison.json';write(target,summary)
    views=PRIMARY/'outputs/egomap60-delivery/views';sources=[]
    keymap={'over_3sigma_rate':'over_3sigma_fraction','final_error_m':'final_error_m','final_sigma_m':'final_sigma_m',
        'final_error_sigma':'final_error_sigma','B_arrived':'B_arrived','returned':'returned',
        'false_declarations':'false_declarations','samples':'samples','occupied_cells':'occupied_cells',
        'tube_wall_samples':'tube_wall_samples','tube_covered_samples':'tube_covered_samples'}
    for r in scores:
        name=f"{r['profile']}-{r['seed']}";source=views/name
        metrics={'offline/blocked':int(r['status'].startswith('BLOCKED'))}
        for key,label in keymap.items():
            if key in r and r[key] is not None:metrics['offline/'+label]=int(r[key]) if isinstance(r[key],bool) else r[key]
        if 'tube' in r:
            for key in ['precision_015','wall_coverage','wall_error_rmse_m']:
                if r['tube'].get(key) is not None:metrics['offline/'+key]=r['tube'][key]
            metrics['offline/wall_contacts']=r['contacts']['wall'];metrics['offline/robot_contacts']=r['contacts']['robot']
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
            offline_source=dict(path=str(target),sha256=sha(target)),offline_scalars=metrics,
            offline_scalar_scope='oracle-x86 resumed DEV: 60s B approach +60s return; one available seed of two, no full mission success claim',
            family='egomap60',policy=r['profile'],case=name,condition='oracle-x86',seed=r['seed'],source_sha=plan['source_sha'],
            outcome=r['status'],model_calls=0,hparam_metrics=list(metrics),evaluation=r,
            limits='60011 B unseen within150s; all four slots blocked. No threshold change or full runs.')
        for key in ('wall_s','sim_s'):
            if r.get(key) is not None:view[key]=r[key]
        write(source/'result.json',view);sources.append(source)
    snapshot=PRIMARY/'outputs/tensorboard/1010-egomap60'
    command=[sys.executable,str(ROOT/'scripts/export_offline_audit.py')]
    for source in sources:command+=['--source',str(source)]
    command+=['--output',str(snapshot)]
    subprocess.run(command,check=True)
    print(json.dumps(dict(summary=str(target),snapshot=str(snapshot),runs=len(sources),verified_files=verified)))


if __name__=='__main__':main()
