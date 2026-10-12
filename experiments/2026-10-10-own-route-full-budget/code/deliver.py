"""Completed egomap64 JSON/artifact packaging; no simulation or replay."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,statistics,subprocess,sys
from collections import Counter
ROOT=Path(__file__).resolve().parents[3];EXP=Path(__file__).resolve().parents[1]
PRIMARY=Path('/Users/changmin/projects/ugrp')

def read(p):return json.loads(p.read_text())
def write(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n')
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def module(path):
    spec=importlib.util.spec_from_file_location('delivery_'+path.parent.parent.name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def aggregate(scores):
    old=module(ROOT/'experiments/2026-10-10-own-route-six-seeds/code/deliver.py')
    result={k:v for k,v in old.aggregate(scores).items() if k in ('baseline','a')}
    for p,r in result.items():
        measured=[x for x in scores if x['profile']==p and x.get('samples',0)]
        counts={k:sum(x['command_audit']['counts'][k] for x in measured) for k in ('turn','forward','backward','lateral','hold')}
        n=sum(counts.values());moving=n-counts['hold']
        r.update(both_arrived=sum(x['both_arrived'] for x in measured),command_counts=counts,
            turn_fraction=counts['turn']/n if n else None,forward_fraction=counts['forward']/n if n else None,
            turn_moving_fraction=counts['turn']/moving if moving else None,
            turn_sign_reversals=sum(x['command_audit']['turn_sign_reversals'] for x in measured),
            within_alignment_reversals=sum(x['command_audit']['within_alignment_reversals'] for x in measured),
            shared_heading_turns=sum(x['command_audit']['shared_heading_turns'] for x in measured))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('batch',type=Path);p.add_argument('--smoke',type=Path,required=True);a=p.parse_args()
    old=module(ROOT/'experiments/2026-10-10-own-route-particle-stages/code/deliver.py')
    old.sha=sha  # bounded-memory hash read; identical SHA-256
    verified=old.verify([a.batch,a.smoke]);scores=read(a.batch/'scores.json');plan=read(a.batch/'batch-plan.json')
    baseline_root=PRIMARY/'outputs/oracle-runs/egomap63-batch/data'
    prefix_checks=[]
    for row in scores:
        name=f"stage-{row['seed']}-{row['profile']}"
        paths=[baseline_root/name,a.batch/name]
        if not all((v/'result.json').exists() for v in paths):continue
        start=read(paths[0]/'result.json')['start_sim_s']
        traces=[]
        for v in paths:
            traces.append([line for line in (v/'own-controller.jsonl').read_text().splitlines()
                           if start<=json.loads(line)['t']<start+60.])
        same=sum(x==y for x,y in zip(*traces))
        prefix_checks.append(dict(seed=row['seed'],profile=row['profile'],frames=[len(t) for t in traces],
            identical_frames=same,all_identical=traces[0]==traces[1],
            expected_task_change=row['seed']==63004))
    comparison=dict(first60_prefix_checks=prefix_checks,host='oracle-x86',source_sha=plan['source_sha'],checkpoint_source_sha=plan['checkpoint_source_sha'],
        registered_slots=12,seeds=list(range(63001,63007)),summary=aggregate(scores),scores=scores,
        jobs=read(a.batch/'batch-status.json'),verified_files=verified,hash_mismatches=[],
        source_hashes={n:sha(a.batch/n) for n in ('scores.json','batch-status.json','batch-plan.json')},
        thresholds_changed=False,raw=str(a.batch),approach_budget_s=270,return_budget_s=270)
    # Extra status breakdown uses saved JSON only, never changes commands.
    for row in scores:
        local=a.batch/f"stage-{row['seed']}-{row['profile']}"
        if not row.get('samples'):continue
        start=read(local/'result.json')['start_sim_s']
        trace=[json.loads(line) for line in (local/'own-controller.jsonl').read_text().splitlines()]
        turning=[x for x in trace if x['t']>=start and x['command'].get('turn',0)]
        row['turn_status_counts']=dict(Counter(x.get('status','unknown') for x in turning))
        row['turn_pulse_reason_counts']=dict(Counter(x.get('pulse',{}).get('reason','unknown') for x in turning))
    target=EXP/'results/comparison.json';write(target,comparison)
    sources=[];views=PRIMARY/'outputs/egomap64-delivery/views-v2'
    for r in scores:
        name=f"{r['profile']}-{r['seed']}";source=views/name
        metrics={'offline/registered':1,'offline/blocked':int(r['status'].startswith('BLOCKED')),
                 'offline/measured':int(r.get('samples',0)>0)}
        for k in ('over_3sigma_rate','over_3sigma','final_error_m','final_sigma_m','final_error_sigma','B_arrived','returned',
                  'both_arrived','false_declarations','samples','occupied_cells','tube_wall_samples','tube_covered_samples',
                  'B_initial_boundary_distance_m','B_nearest_boundary_distance_m','approach_sim_s','return_sim_s','final_return_distance_m'):
            if r.get(k) is not None:metrics['offline/'+k]=int(r[k]) if isinstance(r[k],bool) else r[k]
        if 'command_audit' in r:
            for k in ('turn_fraction','forward_fraction','turn_moving_fraction','turn_sign_reversals','within_alignment_reversals','shared_heading_turns'):
                if r['command_audit'].get(k) is not None:metrics['offline/commands/'+k]=r['command_audit'][k]
            for k,v in r['contacts'].items():metrics['offline/'+k+'_contacts']=v
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,offline_source=dict(path=str(target),sha256=sha(target)),
            offline_scalars=metrics,offline_scalar_scope='oracle-x86 six paired DEV checkpoints; approach270/return270; all registered slots retained',
            family='egomap64',policy=r['profile'],case=name,condition='oracle-x86',seed=r['seed'],source_sha=plan['source_sha'],
            outcome=r['status'],model_calls=0,hparam_metrics=list(metrics),evaluation=r)
        for k in ('wall_s','sim_s'):
            if r.get(k) is not None:view[k]=r[k]
        write(source/'result.json',view);sources.append(source)
    cmd=[sys.executable,str(ROOT/'scripts/export_offline_audit.py')]
    for source in sources:cmd+=['--source',str(source)]
    snapshot=PRIMARY/'outputs/tensorboard/1010-egomap64-v2'
    subprocess.run(cmd+['--output',str(snapshot)],check=True)
    print(json.dumps(dict(summary=comparison['summary'],verified_files=verified,snapshot=str(snapshot)),indent=2))
if __name__=='__main__':main()
