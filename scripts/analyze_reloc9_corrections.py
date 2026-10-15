"""Evaluator-only scoring of saved applied corrections, including partial ones."""
import argparse
import json
from pathlib import Path
import subprocess
from scripts.reloc9_metrics import correction_metrics, counts
from scripts.analyze_reloc9_rotation import RAW
import hashlib


def evaluate(runs):
    output=[]; sources=[]
    for run in runs:
        path=RAW/run/'raw/result.json'
        if not path.exists():path=Path(str(path)+'.zst')
        data=path.read_bytes()
        raw=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else data
        saved=json.loads(raw)
        sources.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),
                            decoded_sha256=hashlib.sha256(raw).hexdigest()))
        viewdata=saved.get('lookaround',{})
        views=viewdata.get('localizer',{}).get('localizer',{}).get('views',[])
        gt={round(r['t'],6):r['truth'] for r in viewdata.get('evaluation',{}).get('views',[]) if 'truth' in r}
        rows=[]
        for v in views:
            truth=gt.get(round(v['t'],6))
            if truth is None:continue
            accepted=v.get('fix_acceptance',{}).get('accepted',False)
            partial=v.get('partial_update',{}).get('applied',False)
            rows.append(dict(t=v['t'],accepted=accepted,partial=partial,
                evaluation_only=correction_metrics(v['prior'],v['posterior'],truth)))
        output.append(dict(run=run,status=saved['status'],source_sha=saved['source_sha'],views_N=len(views),
            evaluation_rows_N=len(rows), full=counts(rows,lambda d:d['accepted']),
            applied_including_partial=counts(rows,lambda d:d['accepted'] or d['partial']),rows=rows))
    return dict(schema='ugrp.reloc9_correction_evaluation.v1',runs=output,sources=sources,
        new_physics_runs=0,scope='saved applied corrections only; absolute risk and relative degradation are separate',
        selfmap_113_of_123='unchanged selfmap6 gate replay; regression only, NOT reloc8 evidence')


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); result=evaluate(a.runs)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps([dict(run=r['run'],full=r['full'],all_applied=r['applied_including_partial']) for r in result['runs']]))


if __name__=='__main__':main()
