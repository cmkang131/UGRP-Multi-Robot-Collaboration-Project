"""Fresh public download and pinned-source CPU loading, without inference.

Run after the study VM is stopped. The source checkout stays untouched.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


SOURCE = '3c9337d5f5c9deefd49139b26ae7117022e3d5cc'
WEIGHTS = '8263ad3f135048fea46d5cb85fee1d70910bdc399babbd1f2f20d92c2fbea271'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    row = json.loads(args.manifest.read_text())
    assert row['source_sha'] == SOURCE
    weight = next(item for item in row['files'] if item['path'] == 'actor/model.safetensors')
    assert weight['sha256'] == WEIGHTS
    assert not args.destination.exists(), 'fresh download destination required'
    assert not args.proof.exists(), 'new verification receipt required'
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.source,text=True).strip()
    dirty = subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],
                                    cwd=args.source,text=True).strip()
    assert head == SOURCE and not dirty
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.dont_write_bytecode = True
    sys.path.insert(0,str(args.source))
    from scripts import model_artifacts
    downloaded = model_artifacts.fetch(row,args.destination)
    before = model_artifacts.verify_directory(row,args.destination)
    import torch
    torch.set_num_threads(1)
    forward_calls = 0

    def forbid_forward(module, inputs):
        nonlocal forward_calls
        forward_calls += 1
        raise RuntimeError('forward/inference is outside artifact-loading verification')

    hook = torch.nn.modules.module.register_module_forward_pre_hook(forbid_forward)
    try:
        from harness.pairact_r1 import PairActActor
        actor = PairActActor.load(args.destination/'actor',device='cpu')
    finally:
        hook.remove()
    state_entries = len(actor.policy.state_dict())
    parameter_count = sum(value.numel() for value in actor.policy.parameters())
    devices = sorted({value.device.type for value in actor.policy.state_dict().values()})
    sim_imports = sorted(name for name in sys.modules if name == 'sim' or name.startswith('sim.'))
    assert state_entries == 239 and parameter_count == 51818398
    assert devices == ['cpu'] and not torch.cuda.is_initialized()
    assert forward_calls == 0 and not sim_imports
    after = model_artifacts.verify_directory(row,args.destination)
    assert before['verified_files'] == after['verified_files'] == 13
    with (args.destination/'actor/model.safetensors').open('rb') as stream:
        actual_weights = hashlib.file_digest(stream,'sha256').hexdigest()
    assert actual_weights == WEIGHTS
    proof = {'schema':'ugrp.baseline.fresh-source-model-load.v1',
        'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status':'PASS','source_sha':head,'source_tracked_clean':not dirty,
        'public_url':row['release']['url'],'archive':row['archive'],
        'download':downloaded,'full_inventory_before':before,'full_inventory_after':after,
        'weights_sha256':actual_weights,'state_entries':state_entries,
        'parameter_count':parameter_count,'state_devices':devices,
        'cuda_initialized':torch.cuda.is_initialized(),'policy_forward_calls':forward_calls,
        'sim_imports':sim_imports,'training_steps':0,'checkpoint_reselected':False,
        'scope':'Public artifact integrity and strict pinned-source CPU loading only; no physical task or speed claim'}
    with args.proof.open('x') as stream: json.dump(proof,stream,indent=2)
    print(json.dumps(proof,indent=2))


if __name__ == '__main__':
    main()
