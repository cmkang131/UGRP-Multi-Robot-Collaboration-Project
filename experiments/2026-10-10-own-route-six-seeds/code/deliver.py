"""Completed JSON packaging only; no physics, estimator replay, or source tuning."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,statistics,subprocess,sys

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
PRIMARY=Path('/Users/changmin/projects/ugrp')

def read(p):return json.loads(p.read_text())
def write(p,r):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def aggregate(scores):
    result={}
    for profile in ('baseline','a','b','c'):
        rows=[r for r in scores if r['profile']==profile]
        measured=[r for r in rows if r.get('samples',0)>0]
        errors=[r['final_error_m'] for r in measured]
        result[profile]=dict(registered=len(rows),recorded=sum(r['status']=='RECORDED' for r in rows),
            measured=len(measured),blocked=sum(r['status'].startswith('BLOCKED') for r in rows),
            host_errors=sum('HOST' in r['status'] for r in rows),
            frames=sum(r['samples'] for r in measured),over3_frames=sum(r['over_3sigma'] for r in measured),
            end_over3=sum(r['final_error_sigma']>3 for r in measured),
            error_median_m=statistics.median(errors) if errors else None,error_max_m=max(errors) if errors else None,
            B=sum(r['B_arrived'] for r in measured),returned=sum(r['returned'] for r in measured),
            false_declarations=sum(r['false_declarations'] for r in measured),
            contact_runs=sum(sum(r['contacts'].values())>0 for r in measured),
            contacts={k:sum(r['contacts'][k] for r in measured) for k in ('wall','robot')})
    return result


def gates(scores,prepared):
    by={(r['seed'],r['profile']):r for r in scores};out={}
    for p in ('a','b','c'):
        complete=len(prepared)>=2 and all(by.get((s,q),{}).get('status')=='RECORDED' and by[s,q].get('samples',0)>0 for s in prepared for q in ('baseline',p))
        g={'complete_pairs':complete}
        if complete:
            a=[by[s,p] for s in prepared];b=[by[s,'baseline'] for s in prepared]
            avg=lambda rows,k:statistics.mean(r[k] for r in rows)
            total=lambda rows,k:sum(r[k] for r in rows)
            g.update(overconfidence=avg(a,'over_3sigma_rate')<=.9*avg(b,'over_3sigma_rate') and avg(a,'over_3sigma_rate')<avg(b,'over_3sigma_rate'),
              position=avg(a,'final_error_m')<=1.2*avg(b,'final_error_m'),B=total(a,'B_arrived')>=total(b,'B_arrived'),
              returned=total(a,'returned')>=total(b,'returned'),false=total(a,'false_declarations')==0,
              contacts=sum(sum(r['contacts'].values()) for r in a)<=sum(sum(r['contacts'].values()) for r in b))
        out[p]=g
    return out


def main():
    parser=argparse.ArgumentParser();parser.add_argument('batch',type=Path);parser.add_argument('--smoke',type=Path,required=True);a=parser.parse_args()
    spec=importlib.util.spec_from_file_location('old_delivery',ROOT/'experiments/2026-10-10-own-route-particle-stages/code/deliver.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    verified=old.verify([a.batch,a.smoke])
    jobs=read(a.batch/'batch-status.json');scores=read(a.batch/'scores.json');plan=read(a.batch/'batch-plan.json')
    preparations=[];audits=[]
    for j in jobs:
        local=a.batch/Path(j['output']).name
        if j['mode']=='prepare':
            r=read(local/'result.json') if (local/'result.json').exists() else {}
            preparations.append({**j,'result':r})
        if (local/'frontend-grid.json').exists():
            audits.append(dict(seed=j['seed'],profile=j['profile'],mode=j['mode'],**read(local/'frontend-grid.json').get('candidate_audit',{})))
    prepared=[p['seed'] for p in preparations if p['status']=='RECORDED' and 'saved_checkpoint' in p['result']]
    result=dict(host='oracle-x86',source_sha=plan['source_sha'],registered_seeds=6,valid_preparations=len(prepared),
        registered_stage_slots=24,preparations=preparations,summary=aggregate(scores),gates=gates(scores,prepared),scores=scores,
        audits=audits,verified_files=verified,hash_mismatches=[],source_hashes={n:sha(a.batch/n) for n in ('scores.json','batch-status.json','batch-plan.json','paired-plan.json')},
        full_runs=0,thresholds_changed=False,raw=str(a.batch))
    target=EXP/'results/comparison.json';write(target,result)
    views=PRIMARY/'outputs/egomap63-delivery/views';sources=[]
    keymap={'over_3sigma_rate':'over_3sigma_fraction','over_3sigma':'over_3sigma_frames','final_error_m':'final_error_m',
            'final_sigma_m':'final_sigma_m','final_error_sigma':'final_error_sigma','B_arrived':'B_arrived','returned':'returned',
            'false_declarations':'false_declarations','samples':'samples','occupied_cells':'occupied_cells',
            'tube_wall_samples':'tube_wall_samples','tube_covered_samples':'tube_covered_samples'}
    for r in scores:
        name=f"{r['profile']}-{r['seed']}";source=views/name
        metrics={'offline/blocked':int(r['status'].startswith('BLOCKED')),'offline/registered':1,'offline/measured':int(r.get('samples',0)>0)}
        for k,label in keymap.items():
            if r.get(k) is not None:metrics['offline/'+label]=int(r[k]) if isinstance(r[k],bool) else r[k]
        if 'tube' in r:
            for key in ('precision_015','wall_coverage','wall_error_rmse_m'):
                if r['tube'].get(key) is not None:metrics['offline/'+key]=r['tube'][key]
            for key,value in r['contacts'].items():metrics['offline/'+key+'_contacts']=value
        view=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,offline_source=dict(path=str(target),sha256=sha(target)),
            offline_scalars=metrics,offline_scalar_scope='oracle-x86 paired DEV120s; registered6seeds; missing/blocked kept, no full mission claim',
            family='egomap63',policy=r['profile'],case=name,condition='oracle-x86',seed=r['seed'],source_sha=plan['source_sha'],
            outcome=r['status'],model_calls=0,hparam_metrics=list(metrics),evaluation=r)
        for key in ('wall_s','sim_s'):
            if r.get(key) is not None:view[key]=r[key]
        write(source/'result.json',view);sources.append(source)
    snapshot=PRIMARY/'outputs/tensorboard/1010-egomap63'
    cmd=[sys.executable,str(ROOT/'scripts/export_offline_audit.py')]
    for source in sources:cmd+=['--source',str(source)]
    subprocess.run(cmd+['--output',str(snapshot)],check=True)
    print(json.dumps({'summary':result['summary'],'prepared':prepared,'verified_files':verified,'snapshot':str(snapshot)},indent=2))

if __name__=='__main__':main()
