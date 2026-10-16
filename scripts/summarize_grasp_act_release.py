"""Finite release cohort summary; evaluation only, including missing/HOST_ERROR."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


def summarize(plan, runs_root, prefix, sha):
    rows=[]
    for i,episode in enumerate(plan['episodes']):
        raw=Path(runs_root)/f'{prefix}-{i:02d}-{sha[:8]}'/'raw'
        path=raw/'result.json'
        if not path.exists():path=raw/'result.json.zst'
        if not path.exists():
            rows.append({'index':i,'seed':episode['seed'],'status':'missing','raw':str(raw)})
            continue
        content=path.read_bytes()
        result=json.loads(subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else content)
        rows.append({'index':i,'seed':episode['seed'],'raw':str(raw),'result_path':str(path),
            'result_sha256':hashlib.sha256(content).hexdigest(),'status':result.get('status','unknown'),
            'source_sha':result.get('source_sha'),'prefix_held':result.get('prefix_held'),
            'profile_match':all(result.get(k)==v for k,v in plan.get('execution_profile',{}).items()),
            'release_success':result.get('release_success'),'outcome':result.get('release_outcome'),
            'failure_reasons':result.get('release_failure_reasons'),
            'center_distance_m':result.get('evaluation_position_error',{}).get('center_distance_m'),
            'input_audit':{k:result.get('input_audit',{}).get(k) for k in ('held_world_reads','invisible_measurements')}})
    distances=[r['center_distance_m'] for r in rows if isinstance(r.get('center_distance_m'),(int,float)) and math.isfinite(r['center_distance_m'])]
    complete=sum(r['status']=='complete' for r in rows)
    eligible=sum(r.get('prefix_held') is True for r in rows)
    passed=sum(r.get('release_success') is True for r in rows)
    source_ok=all(r.get('source_sha')==sha for r in rows)
    audit_ok=all(all(r.get('input_audit',{}).get(k)==0 for k in ('held_world_reads','invisible_measurements')) for r in rows)
    return {'scope':'evaluation only; queued/missing results are never complete','planned':len(rows),
        'complete':complete,'release_eligible':eligible,'release_success':passed,
        'gate_pass':len(rows)==len(distances)==40 and complete==eligible==40 and passed>=38 and source_ok and audit_ok and all(r.get('profile_match') for r in rows),
        'source_sha_match':source_ok,'audit_pass':audit_ok,
        'center_distance_m':{'n':len(distances),'median':statistics.median(distances) if distances else None,
            'max':max(distances) if distances else None,'scope':'all available finite final distances, successes AND failures'},
        'runs':rows}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--runs-root',type=Path,required=True)
    p.add_argument('--prefix',required=True);p.add_argument('--sha',required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=summarize(json.loads(a.plan.read_text()),a.runs_root,a.prefix,a.sha)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='runs'},ensure_ascii=False))


if __name__=='__main__':main()
