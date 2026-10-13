"""Paired saved-map route-only replay; never imports/starts a simulator or provider."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from harness.e2e_route_stage_probe import replay,evaluate,SCHEMA


def read(path):
    path=Path(path)
    raw=path.read_bytes()
    data=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else raw
    return json.loads(data),hashlib.sha256(raw).hexdigest()


def run(manifest):
    if len({c['case_id'] for c in manifest['cases']}) != len(manifest['cases']):
        raise ValueError('DUPLICATE_STAGE_CASE_ID')
    rows=[]
    for case in manifest['cases']:
        try:
            state,sha=read(case['snapshot'])
            if sha!=case['sha256']:raise ValueError('SNAPSHOT_FILE_HASH_MISMATCH')
            if state['schema']!=SCHEMA:raise ValueError('SNAPSHOT_SCHEMA_MISMATCH')
        except (OSError,ValueError,subprocess.CalledProcessError) as exc:
            rows.append(dict(case_id=case['case_id'],seed=case['seed'],subset=case.get('subset','all'),status='HOST_ERROR',reason=str(exc)))
            continue
        for option in ('off','frontier_v1'):
            start=time.perf_counter();result=replay(state,option)
            row=dict(case_id=case['case_id'],seed=case['seed'],subset=case.get('subset','all'),
                status='COMPLETE',snapshot=case['snapshot'],snapshot_file_sha256=sha,
                planner_wall_s=time.perf_counter()-start,**result)
            # Exact same saved input, seed label and SHA for both arms. Eval reads only AFTER planning.
            if case.get('evaluation'):
                ev,evsha=read(case['evaluation'])
                if evsha!=case['evaluation_sha256']:raise ValueError('EVALUATION_FILE_HASH_MISMATCH')
                row['evaluation']=evaluate(result,state,ev);row['evaluation_file_sha256']=evsha
            rows.append(row)
    metrics={}
    for subset in ['all']+sorted({c.get('subset','all') for c in manifest['cases']}-{'all'}):
        metrics[subset]={}
        for option in ('off','frontier_v1'):
            selected=[r for r in rows if (subset=='all' or r['subset']==subset) and r.get('option')==option]
            n=sum(r['generated'] for r in selected)
            times=[r['input_sim_s'] for r in selected if r['generated']]
            evals=[r['evaluation']['collision_free'] for r in selected if r.get('evaluation',{}).get('collision_free') is not None]
            metrics[subset][option]=dict(generated_n=n,attempted_N=len(selected),
                expected_N=sum(subset=='all' or c.get('subset','all')==subset for c in manifest['cases']),
                observed_complete_n=sum(r['observed_complete'] for r in selected),
                ready_at_saved_sim_s_median=statistics.median(times) if times else None,
                ready_at_saved_sim_s_max=max(times) if times else None,
                collision_free_n=sum(evals),collision_evaluated_N=len(evals),
                physical_pass_n=0,physical_evaluated_N=0,online_generation_sim_s=None)
    return dict(schema='ugrp.e2e_route_stage_results.v1',rows=rows,metrics=metrics,
                scope='paired offline saved snapshots; ready-at times are NOT online candidate latency',
                input_manifest=manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=run(json.loads(a.manifest.read_text()))
    a.output.mkdir(parents=True,exist_ok=False)
    data=json.dumps(result,indent=2,allow_nan=False).encode()
    if len(data)>65536:
        packed=subprocess.check_output(['zstd','-q','-c'],input=data)
        if subprocess.check_output(['zstd','-q','-d','-c'],input=packed)!=data:raise ValueError('ZSTD_ROUNDTRIP')
        target=a.output/'results.json.zst';target.write_bytes(packed)
    else:
        target=a.output/'results.json';target.write_bytes(data)
    summary=dict(metrics=result['metrics'],scope=result['scope'],raw=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                 host_errors=sum(r['status']=='HOST_ERROR' for r in result['rows']))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
