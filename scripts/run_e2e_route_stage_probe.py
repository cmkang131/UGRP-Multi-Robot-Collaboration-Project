"""Paired saved-map route-only replay; never imports/starts a simulator or provider."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import time
from collections import Counter
from harness.e2e_route_stage_probe import replay,evaluate,SCHEMA,LEGACY_SCHEMA
from harness.e2e_route_input_record import SCHEMA as RECORD_SCHEMA

OPTIONS=('off','frontier_v1','footprint_v2')


def recordings_manifest(roots, evaluation_dir=None):
    cases=[];runs=[]
    for root in roots:
        root=Path(root).resolve()
        summary=json.loads((root/'summary.json').read_text())
        rows=[json.loads(line) for line in (root/'index.jsonl').read_text().splitlines()] if (root/'index.jsonl').exists() else []
        for row in rows:
            if row['status']!='SAVED':continue
            case=dict(case_id=f'{root}:{row["attempt"]}',seed=summary['metadata'].get('seed'),
                snapshot=str(root/row['file']),sha256=row['sha256'],subset='generated_source' if row['generated'] else 'failed_source')
            if evaluation_dir:
                # Evaluation labels are joined by the private snapshot digest,
                # never passed to the planner or restored controller.
                from harness.pair_stage_probe import digest
                record,_=read(case['snapshot'])
                ev=Path(evaluation_dir)/(digest(record['snapshot'])+'.json')
                if ev.exists():case.update(evaluation=str(ev),evaluation_sha256=hashlib.sha256(ev.read_bytes()).hexdigest())
            cases.append(case)
        runs.append(dict(root=str(root),**summary))
    return dict(cases=cases,recording_runs=runs,options=list(OPTIONS))


def read(path):
    path=Path(path)
    raw=path.read_bytes()
    data=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else raw
    return json.loads(data),hashlib.sha256(raw).hexdigest()


def run(manifest):
    options=manifest.get('options',OPTIONS)
    if not options or set(options)-set(OPTIONS):raise ValueError('UNKNOWN_ROUTE_REPLAY_OPTION')
    if len({c['case_id'] for c in manifest['cases']}) != len(manifest['cases']):
        raise ValueError('DUPLICATE_STAGE_CASE_ID')
    rows=[]
    for case in manifest['cases']:
        try:
            state,sha=read(case['snapshot'])
            if sha!=case['sha256']:raise ValueError('SNAPSHOT_FILE_HASH_MISMATCH')
            original=state.get('result') if state['schema']==RECORD_SCHEMA else None
            if state['schema']==RECORD_SCHEMA:state=state['snapshot']
            if state['schema'] not in (SCHEMA,LEGACY_SCHEMA):raise ValueError('SNAPSHOT_SCHEMA_MISMATCH')
        except (OSError,ValueError,subprocess.CalledProcessError) as exc:
            rows.append(dict(case_id=case['case_id'],seed=case['seed'],subset=case.get('subset','all'),status='HOST_ERROR',reason=str(exc)))
            continue
        for option in options:
            start=time.perf_counter();result=replay(state,option)
            row=dict(case_id=case['case_id'],seed=case['seed'],subset=case.get('subset','all'),
                status='COMPLETE',snapshot=case['snapshot'],snapshot_file_sha256=sha,
                planner_wall_s=time.perf_counter()-start,**result)
            if original is not None and option==state['attrs'].get('route_recovery','off'):
                row['recorded_result_reproduced']=(result['generated']==original['generated'] and result['route']==original['route'] and result['failure']==(original['failure'] or {}).get('reason'))
            # Exact same saved input, seed label and SHA for both arms. Eval reads only AFTER planning.
            if case.get('evaluation'):
                try:
                    ev,evsha=read(case['evaluation'])
                    if evsha!=case['evaluation_sha256']:raise ValueError('EVALUATION_FILE_HASH_MISMATCH')
                    row['evaluation']=evaluate(result,state,ev);row['evaluation_file_sha256']=evsha
                except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as exc:
                    row['evaluation_error']=str(exc)
            rows.append(row)
    metrics={}
    for subset in ['all']+sorted({c.get('subset','all') for c in manifest['cases']}-{'all'}):
        metrics[subset]={}
        for option in options:
            selected=[r for r in rows if (subset=='all' or r['subset']==subset) and r.get('option')==option]
            n=sum(r['generated'] for r in selected)
            times=[r['input_sim_s'] for r in selected if r['generated']]
            evals=[r['evaluation']['collision_free'] for r in selected if r.get('evaluation',{}).get('collision_free') is not None]
            compute=[r['planner_compute_s'] for r in selected]
            metrics[subset][option]=dict(generated_n=n,attempted_N=len(selected),
                expected_N=sum(subset=='all' or c.get('subset','all')==subset for c in manifest['cases']),
                observed_complete_n=sum(r['observed_complete'] for r in selected),
                ready_at_saved_sim_s_median=statistics.median(times) if times else None,
                ready_at_saved_sim_s_max=max(times) if times else None,
                collision_free_n=sum(evals),collision_evaluated_N=len(evals),
                geometric_passable_n=sum(evals),geometric_evaluated_N=len(evals),
                compute_s_median=statistics.median(compute) if compute else None,compute_s_max=max(compute) if compute else None,
                failure_reasons=dict(Counter((r.get('diagnostics') or {}).get('reason') or r['failure'] or 'NO_PACKET' for r in selected if not r['generated'])),
                physical_pass_n=0,physical_evaluated_N=0,online_generation_sim_s=None)
    return dict(schema='ugrp.e2e_route_stage_results.v1',rows=rows,metrics=metrics,
                scope='paired offline saved snapshots; ready-at times are NOT online candidate latency',
                input_manifest=manifest)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--manifest',type=Path);group.add_argument('--recordings',type=Path,nargs='+')
    p.add_argument('--evaluation-dir',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=run(json.loads(a.manifest.read_text()) if a.manifest else recordings_manifest(a.recordings,a.evaluation_dir))
    a.output.mkdir(parents=True,exist_ok=False)
    data=json.dumps(result,indent=2,allow_nan=False).encode()
    if len(data)>65536:
        packed=subprocess.check_output(['zstd','-q','-c'],input=data)
        if subprocess.check_output(['zstd','-q','-d','-c'],input=packed)!=data:raise ValueError('ZSTD_ROUNDTRIP')
        target=a.output/'results.json.zst';target.write_bytes(packed)
    else:
        target=a.output/'results.json';target.write_bytes(data)
    summary=dict(metrics=result['metrics'],scope=result['scope'],raw=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                 host_errors=sum(r['status']=='HOST_ERROR' for r in result['rows']),
                 recording_source_attempts_N=sum(r['attempts'] for r in result['input_manifest'].get('recording_runs',[])),
                 recording_saved_N=sum(r['saved'] for r in result['input_manifest'].get('recording_runs',[])),
                 recording_budget_omitted_N=sum(r['dropped'] for r in result['input_manifest'].get('recording_runs',[])),
                 evaluation_errors=sum('evaluation_error' in r for r in result['rows']))
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
