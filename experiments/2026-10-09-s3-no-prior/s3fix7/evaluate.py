"""GT-only evaluation of sealed saved input outputs; never imported by control."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess

from harness.pf_resampling_diversity import OPTIONS
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

HERE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs')


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--replays',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('prior_eval',HERE.parent/'s3fix6/evaluate.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    value=bind(old.evaluate,OPTIONS=OPTIONS)(a.replays)
    eligible=[op for op,r in value['selection'].items() if r['eligible']]
    def pooled_rmse(op):
        rows=value['table'][op].values()
        return math.sqrt(sum(r['frames']*r['xy_rmse_m']**2 for r in rows)/sum(r['frames'] for r in rows))
    value['smoke_option']=min(eligible,key=lambda op:(value['selection'][op]['pooled_over_3sigma'],
        pooled_rmse(op),OPTIONS.index(op))) if eligible else 'off'
    receipts={}
    for op in OPTIONS:
        for case in ('55001','55002','v149','v150'):
            key=case+'-'+op;folder=a.replays/key
            result=read(folder/'result.json')
            assert result.get('failure') is None and result.get('error') is None
            receipts[key]=dict(result_path=str((folder/'result.json').resolve()),
                result_sha256=sha(folder/'result.json'),frames=result['frames'])
            if op=='off':
                previous=RAW/'s3fix6-20261010/replays-v4'/key
                old_result=read(previous/'result.json')
                fields=(('poses_sha256','original_frontend_equal','original_proposals_equal') if case.startswith('550')
                        else ('generated_sha256','state_sha256'))
                same={k:result[k]==old_result[k] for k in fields}
                assert all(same.values()),(key,same)
                receipts[key]['baseline_admission']=dict(previous=str(previous.resolve()),
                    previous_receipt_sha256=sha(previous/'result.json'),equal=same,
                    scope='same prior admitted finite-pose replay; original NaN exception remains documented in s3fix6')
    source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    files=source_closure(Path.cwd(),['harness/zone_s3_recovery_runtime.py'])
    value.update(source_sha=source,physics_runs=0,replay_receipts=receipts,
        preregistration_sha256=sha(HERE/'README.md'),
        runtime_source_sha256={p:sha(Path(p)) for p in sorted(files)})
    with a.output.open('x') as f:f.write(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(selected=value['smoke_option'],checks=value['selection']),indent=2))


if __name__=='__main__':main()
