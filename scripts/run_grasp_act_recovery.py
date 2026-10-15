"""GCP-only opt-in adapter around the existing pinned solo teacher.

No copied grasp path. Missing dependency modules are loaded from an explicit
clean teacher checkout; the pair (ACT SHA, teacher SHA) identifies this build.
Every recorded noisy state receives the original teacher's clean label.
"""
import argparse
from contextlib import contextmanager
import importlib
import json
from pathlib import Path
import platform
import subprocess

from harness.grasp_act_data import read_json, sha256, write_json
from harness.grasp_act_dart import MODE, WheelNoise, recovery_hooks
from harness.grasp_act_recovery_gate import verify_gate
from scripts.grasp_act_training_guard import source_sha

TEACHER_SHA='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'


@contextmanager
def dependency_modules(root):
    root=Path(root).resolve()
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if actual!=TEACHER_SHA or subprocess.check_output(['git','status','--porcelain'],cwd=root):
        raise ValueError('clean pinned solo teacher dependency required')
    packages=[]
    for name in ('harness','sim','scripts'):
        package=importlib.import_module(name);path=str(root/name)
        package.__path__.append(path);packages.append((package,path))
    try:yield
    finally:
        for package,path in packages:package.__path__.remove(path)


def run(plan, out, *, dependency_root, noise_path, mode='off', training_rgb=False, gate_receipt=None, cap_s=90.):
    # Refuse on Mac before importing a simulation runner or contacting metadata.
    if platform.system()!='Linux':raise RuntimeError('GCP Linux only; Mac execution forbidden')
    if mode not in ('off',MODE):raise ValueError('unknown recovery toggle')
    if mode=='off' and training_rgb:raise ValueError('use original teacher for default-off recordings')
    source=source_sha();noise_hash=sha256(noise_path) if mode!= 'off' else None
    model=json.loads(Path(noise_path).read_text()) if mode!='off' else None
    with dependency_modules(dependency_root):
        from scripts.grasp_act_host import identity
        host=identity('gcp1')
        if host['instance']!='ugrp-sim-gcp1' or host['machine_type']!='n4-highcpu-64':
            raise ValueError('ACT6 requires gcp1 n4-highcpu-64')
        # Gate matching uses the runner's exact host schema, including CPU count.
        approval=None
        if training_rgb:
            if gate_receipt is None:raise ValueError('38/40 gate required before any training RGB')
            approval=verify_gate(gate_receipt,source=source,dependency=TEACHER_SHA,
                noise_hash=noise_hash,host=host,recording_seeds=[plan['seed']])
        teacher=importlib.import_module('sim.grasp_act_solo_teacher')
        recording=importlib.import_module('harness.grasp_act_solo_recording')
        runner=importlib.import_module('scripts.run_solo_grasp_act_teacher')
        noise=WheelNoise(model,seed=plan['seed'],mode=mode)
        out=Path(out)
        if out.exists():raise FileExistsError(out)
        out.parent.mkdir(parents=True,exist_ok=True)
        ledger_path=out.parent/'recovery-commands.jsonl'
        report=None
        try:
            with ledger_path.open('x') as ledger, recovery_hooks(teacher,recording,noise,ledger):
                # The original pilot writer grants no admission. Our stricter
                # gate check above also covers the very first recording.
                report=runner.run(plan,out,execution_host='gcp1',profile='solo_visible_only_v1',
                    hidden=True,look=True,cap_s=cap_s,teacher_stability='align_relook_v1',
                    reach_mode='pad_window_v2',rgb_lift_mode='solo_lift_lookback_v1',
                    solo_lift_lookback_margin_v1=True,solo_truth_free_lookaround_v1=True,
                    training_rgb=training_rgb,recording_stage='pilot')
        finally:
            p=out/'result.json'
            if not p.exists() and (out/'result.json.zst').exists():
                p=out/'result.json.zst'
            if p.exists():
                report=read_json(p)
                report.update(source_sha=source,teacher_dependency_sha=TEACHER_SHA,noise_sha256=noise_hash,
                    recovery={'mode':mode,'seed':plan['seed'],'applied_history_clean_targets':mode!= 'off',
                              'ledger':str(ledger_path),'sha256':sha256(ledger_path)},
                    recovery_gate=approval,data_admitted=False)
                if training_rgb:
                    report.update(training_candidate=bool(report.get('physical_success') and approval),
                                  training_include=False,training_exclusion_reason='awaiting dataset admission')
                if p.suffix=='.zst':
                    encoded=(json.dumps(report,indent=2,allow_nan=False)+'\n').encode()
                    packed=subprocess.check_output(['zstd','-q','-c'],input=encoded)
                    if subprocess.check_output(['zstd','-qdc'],input=packed)!=encoded:
                        raise ValueError('recovery result compression mismatch')
                    p.write_bytes(packed)
                else:write_json(p,report)
                meta=out/'RUN_META.json';m=json.loads(meta.read_text());m.update(sha=source,pr=504,
                     branch='claude/act-train',teacher_dependency_sha=TEACHER_SHA);write_json(meta,m)
            # Preserve a finite compressed ledger; originals are not overwritten.
            if ledger_path.exists():
                from scripts.run_grasp_act_teacher import compress_logs
                compress_logs(out.parent)
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('plan','out','dependency-root','noise'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--recovery-mode',choices=('off',MODE),default='off')
    p.add_argument('--training-rgb',action='store_true');p.add_argument('--gate-receipt',type=Path)
    p.add_argument('--episode',type=int,required=True);p.add_argument('--cap-s',type=float,default=90.)
    a=p.parse_args();plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    run(plan,a.out,dependency_root=a.dependency_root,noise_path=a.noise,mode=a.recovery_mode,
        training_rgb=a.training_rgb,gate_receipt=a.gate_receipt,cap_s=a.cap_s)


if __name__=='__main__':main()
