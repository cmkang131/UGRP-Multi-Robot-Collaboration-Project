"""Collect the already used actor only after a GPU cohort and cleanup close.

Copies the ten frozen inference/provenance files to Oracle for the required
immutable Release. No training, inference, selection or physics is performed.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ssh-config', type=Path, required=True)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--closed-arm', choices=('arm_c', 'arm_s'), required=True)
    args = parser.parse_args()
    plan = json.loads(Path(__file__).with_name('model-collection-plan.json').read_text())
    root = '/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z'
    probe = ("import json,subprocess;from pathlib import Path;"
        f"p=Path({root!r})/{(args.closed_arm+'.receipt.json')!r};"
        "assert p.is_file(),'cohort receipt absent';r=json.loads(p.read_text());"
        "assert r.get('ended_utc') and type(r.get('exit_code')) is int,'cohort not closed';"
        "g=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,process_name',"
        "'--format=csv,noheader'],text=True);assert not g.strip(),'GPU processes still active';"
        "print(json.dumps({'receipt':r,'GPU_compute_processes':g.strip()}))")
    closed = subprocess.check_output(['ssh','-F',str(args.ssh_config),'gcp6-baseline',
                                     shlex.join(['python3','-c',probe])],text=True)
    guard = json.loads(closed)
    args.stage.mkdir(parents=True,exist_ok=True)
    verified = []
    for item in plan['files_to_collect_after_gpu_cohort']:
        target = args.stage/item['path']
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            raise ValueError('refuse overwrite of model stage asset: '+str(target))
        subprocess.run(['scp','-q','-F',str(args.ssh_config),
                        'gcp6-baseline:'+item['source_path'],str(target)],check=True)
        with target.open('rb') as stream: digest = hashlib.file_digest(stream,'sha256').hexdigest()
        if target.stat().st_size != item['bytes'] or digest != item['sha256']:
            raise ValueError('frozen model provenance mismatch: '+str(target))
        verified.append({'path':item['path'],'bytes':item['bytes'],'sha256':digest})
    receipt = {'schema':'ugrp.baseline.model-collection.v1',
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'id':plan['id'],'closed_cohort_guard':guard,'files':verified,
        'frozen_files_match':True,'stage':str(args.stage),
        'policy_forward_calls':0,'training_steps':0,'checkpoint_reselected':False}
    with (args.stage.parent/'collection-receipt.json').open('x') as stream:
        json.dump(receipt,stream,indent=2)
    print(json.dumps({'id':plan['id'],'verified_files':len(verified),'all_match':True}))


if __name__ == '__main__':
    main()
