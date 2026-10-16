"""Two approved TRAIN pilots -> converter/loader canary, never ACT16 D0.

No teacher rollout, optimizer update or student action. Full40 admission remains
unchanged. Only these TRAIN observations are opened; no validation/final seeds.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from act16w_runtime import require_gcp2,frozen_source,sha256,ACT_SHA
B=Path('/home/ugrp/ugrp-sim')


def read(p):return json.loads(p.read_text()) if p.exists() else json.loads(subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    host=require_gcp2();source=frozen_source(ROOT);ACT=B/'src'/ACT_SHA;frozen_source(ACT,ACT_SHA)
    a.out.mkdir(parents=True,exist_ok=False);views=a.out/'views';views.mkdir()
    for seed in (86821,86822):
        original=B/f'runs/act16w-resume2-pilot-{seed}';audit=read(original/'native-pilot-check.json')
        if not audit['passed'] or not all(w['physical_success'] and w['command_complete'] and not w['cap_end'] for w in audit['worlds']):raise ValueError('complete approved native pilot required')
        raw=original/'capture/world-000';controller=original/'controller/world-000';view=views/str(seed);dest=view/'raw';dest.mkdir(parents=True)
        for name in ('student-r1.jsonl','teacher-r1.jsonl','student-camera.json','rgb'):
            path=raw/name
            if not path.exists():name+='.zst';path=raw/name
            if path.is_dir():
                for f in path.rglob('*'):
                    if f.is_file():target=dest/name/f.relative_to(path);target.parent.mkdir(parents=True,exist_ok=True);os.link(f,target)
            else:os.link(path,dest/name)
        os.link(controller/'plan.json',dest/'plan.json');result=read(controller/'result.json')
        write(dest/'result.json',{**result,'training_rgb':True,'recording_mode':'training','student_execution':False,'import_view':'DEV converter canary only; not research data admission','original_controller_training_rgb':result['training_rgb'],'original_controller_result':str(controller/'result.json'),'native_audit_sha256':sha256(original/'native-pilot-check.json')})
        (view/'SOURCE_SHA').write_text('0362037280c6cbc4677f70366db43b9892b23690\n');(view/'EXIT').write_text('0\n')
    protocol=dict(teacher_sha='f0db6b1abb842ea65b71c433738210254f300a7c',train_seeds=[86821,86822],validation_seeds=[],run_pattern='{seed}',transport_sha_by_seed={str(s):'0362037280c6cbc4677f70366db43b9892b23690' for s in (86821,86822)},done_label='last_local_row_v1',include_initial_approach_v1=True,run_class='dev',not_for_research_training=True,admission='two approved native pilots; converter/loader plumbing only; full40 gate not replaced')
    sys.path.insert(0,str(ACT))
    import numpy as np
    from harness.grasp_act_data import convert,GraspDataset,assert_tensor_keys
    from harness.grasp_act_loss import completion_priors
    manifest=convert(views,protocol,a.out/'dataset');data=GraspDataset(a.out/'dataset','train');probe=data[0];assert_tensor_keys(probe,training=True)
    horizons=[int((~shard['action_is_pad']).sum()) for shard in data.shards]
    if any(np.any(s['action_is_pad'][:,0]) for s in data.shards):raise ValueError('invalid current target in native canary')
    summary=dict(status='complete',passed=True,host=host,source_sha=source,ACT_source=ACT_SHA,raw=str(a.out),TRAIN_seeds=[86821,86822],validation_or_final_samples_opened=0,research_data_admitted=False,actual_ACT16_optimizer_steps=0,optimizer_updates=0,student_actions=0,rows=len(data),valid_horizons=horizons,tensor_shapes={k:list(v.shape) for k,v in probe.items()},input_keys=sorted(probe),done_priors=completion_priors(data),manifest_sha256=sha256(a.out/'dataset/manifest.json'),full_D0_normalization_changed=False,full40_gate_replaced=False)
    write(a.out/'summary.json',summary);print(json.dumps(summary))


if __name__=='__main__':main()
