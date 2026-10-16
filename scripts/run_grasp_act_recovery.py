"""GCP-only opt-in adapter around the existing pinned solo teacher.

No copied grasp path. Teacher packages are isolated in an explicit clean
teacher checkout; the pair (ACT SHA, teacher SHA) identifies this build.
Every recorded noisy state receives the original teacher's clean label.
"""
import argparse
from contextlib import contextmanager
import importlib
from importlib.machinery import PathFinder
from importlib.util import module_from_spec
import json
import math
from pathlib import Path
import platform
import signal
import subprocess
import sys

from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.grasp_act_dart import MODE, PULSE_MODE, MODES, WheelNoise, recovery_hooks
from harness.grasp_act_recovery_gate import verify_gate
from harness.grasp_act_recovery_audit import evaluation_hook
from harness.grasp_act_perturb import PERTURB_MODE, PERTURB_MODES, RecoveryPerturb, recovery_statistics
from harness.grasp_act_search import SEARCH_MODE
from scripts.grasp_act_training_guard import source_sha

TEACHER_SHA='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
CALIBRATION_MODE='act8_yaw_gain_v1'


def rotation_gain(model, mode, recovery_mode):
    if mode == 'off':return 1.
    if mode != CALIBRATION_MODE or recovery_mode != SEARCH_MODE:
        raise ValueError('yaw calibration requires opt-in active search')
    calibration=model.get('rotation_calibration', {})
    gain=calibration.get('yaw_gain')
    if (calibration.get('mode') != mode or type(gain) not in (int,float)
            or not math.isfinite(gain) or not .1 <= gain <= 2.
            or calibration.get('fit_cohort') != 'act8'
            or calibration.get('validation_cohorts') != ['act9','act10']):
        raise ValueError('frozen ACT8 yaw calibration required')
    return gain


@contextmanager
def protected_runner(runner, teacher):
    """Protect marker-triggered AND signal-triggered cleanup from a second SIGINT.

    The pinned runner constructs KeyboardInterrupt on SUPERVISOR_STOP. Its
    module-local exception binding catches that path before its except block.
    Capture the actual audit instance, never reconstruct successful zero counts.
    The guard remains active through adapter finalization and compression.
    """
    state={'interrupted':False}
    previous=signal.getsignal(signal.SIGINT)
    missing=object(); old_interrupt=vars(runner).get('KeyboardInterrupt',missing)
    original=teacher.InputAudit
    class StopOnce(KeyboardInterrupt):
        def __init__(self,*args):
            signal.signal(signal.SIGINT,signal.SIG_IGN)
            state['interrupted']=True
            super().__init__(*args)
    def interrupt(signum,frame):raise StopOnce('SIGINT')
    def audit(*args,**kwargs):
        state['audit']=original(*args,**kwargs)
        return state['audit']
    runner.KeyboardInterrupt=StopOnce
    teacher.InputAudit=audit
    signal.signal(signal.SIGINT,interrupt)
    try:yield state
    finally:
        teacher.InputAudit=original
        if old_interrupt is missing:del runner.KeyboardInterrupt
        else:runner.KeyboardInterrupt=old_interrupt
        signal.signal(signal.SIGINT,previous)


def atomic_result(path, report):
    if path.suffix != '.zst':
        write_json(path,report)
        return
    encoded=(json.dumps(report,indent=2,allow_nan=False)+'\n').encode()
    packed=subprocess.check_output(['zstd','-q','-c'],input=encoded)
    if subprocess.check_output(['zstd','-qdc'],input=packed)!=encoded:
        raise ValueError('recovery result compression mismatch')
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(packed)
    temporary.replace(path)


def validate_dependency(root):
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if actual!=TEACHER_SHA or subprocess.check_output(['git','status','--porcelain'],cwd=root):
        raise ValueError('clean pinned solo teacher dependency required')


@contextmanager
def dependency_modules(root):
    """Single-run import scope: no ACT fallback, including cached submodules.

    Adapter references already held by the caller remain ACT objects. All
    imports made by the teacher resolve only inside the pinned dependency.
    Restore the caller's packages and search path even on an import/run error.
    This process-global scope is for the single-threaded CLI, not parallel runs.
    """
    root=Path(root).resolve()
    validate_dependency(root)
    names=('harness','sim','scripts')
    owned=lambda name: name.split('.')[0] in names
    saved={name:module for name,module in sys.modules.copy().items() if owned(name)}
    search_path=sys.path[:]
    try:
        for name in saved:del sys.modules[name]
        sys.path.insert(0,str(root))
        for name in names:
            spec=PathFinder.find_spec(name,[str(root)])
            if spec is None or spec.submodule_search_locations is None:
                raise ImportError(f'missing teacher package: {name}')
            package=module_from_spec(spec)
            sys.modules[name]=package
            if spec.loader is not None:spec.loader.exec_module(package)
            # Freeze namespace packages too: sys.path changes cannot add ACT.
            package.__path__=[str(root/name)]
        yield
    finally:
        for name in list(sys.modules):
            if owned(name):del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:]=search_path


def run(plan, out, *, dependency_root, noise_path, mode='off', training_rgb=False, gate_receipt=None, cap_s=90.,
        rotation_calibration='off'):
    # Refuse on Mac before importing a simulation runner or contacting metadata.
    if platform.system()!='Linux':raise RuntimeError('GCP Linux only; Mac execution forbidden')
    if mode not in MODES:raise ValueError('unknown recovery toggle')
    if mode == PULSE_MODE and training_rgb:
        raise ValueError('ACT8 is gate-only; no recording admission for the new mode')
    if mode=='off' and training_rgb:raise ValueError('use original teacher for default-off recordings')
    source=source_sha();noise_hash=sha256(noise_path) if mode!= 'off' else None
    model=json.loads(Path(noise_path).read_text()) if mode!='off' else None
    yaw_gain=rotation_gain(model,rotation_calibration,mode)
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
                noise_hash=noise_hash,host=host,recording_seeds=[plan['seed']],recovery_mode=mode,
                rotation_calibration=rotation_calibration, yaw_gain=yaw_gain)
        teacher=importlib.import_module('sim.grasp_act_solo_teacher')
        recording=importlib.import_module('harness.grasp_act_solo_recording')
        runner=importlib.import_module('scripts.run_solo_grasp_act_teacher')
        actuator=importlib.import_module('scripts.run_grasp_act_teacher')
        noise=(RecoveryPerturb(model,seed=plan['seed'],mode=mode) if mode in PERTURB_MODES
               else WheelNoise(model,seed=plan['seed'],mode=mode))
        out=Path(out)
        if out.exists():raise FileExistsError(out)
        out.parent.mkdir(parents=True,exist_ok=True)
        ledger_path=out.parent/'recovery-commands.jsonl'
        evaluation_path=out.parent/'recovery-eval-only.jsonl' if mode in (PULSE_MODE,*PERTURB_MODES) else None
        with protected_runner(runner,teacher) as stop_state:
            return run_protected(runner,teacher,recording,actuator,noise,plan,out,ledger_path,evaluation_path,
                source,noise_hash,approval,mode,training_rgb,cap_s,rotation_calibration,yaw_gain,stop_state)


def run_protected(runner,teacher,recording,actuator,noise,plan,out,ledger_path,evaluation_path,
                  source,noise_hash,approval,mode,training_rgb,cap_s,rotation_calibration,yaw_gain,stop_state):
    report=None; failure=None
    try:
        from contextlib import ExitStack
        with ExitStack() as stack:
            ledger=stack.enter_context(ledger_path.open('x'))
            evaluation=stack.enter_context(evaluation_path.open('x')) if evaluation_path else None
            stack.enter_context(recovery_hooks(teacher,recording,noise,ledger,yaw_gain=yaw_gain))
            stack.enter_context(evaluation_hook(actuator,evaluation,enabled=evaluation_path is not None))
            # The original pilot writer grants no admission. Our stricter
            # gate check above also covers the very first recording.
            report=runner.run(plan,out,execution_host='gcp1',profile='solo_visible_only_v1',
                hidden=True,look=True,cap_s=cap_s,teacher_stability='align_relook_v1',
                reach_mode='pad_window_v2',rgb_lift_mode='solo_lift_lookback_v1',
                solo_lift_lookback_margin_v1=True,solo_truth_free_lookaround_v1=True,
                training_rgb=training_rgb,recording_stage='pilot')
    except BaseException as error:
        failure=error
        raise
    finally:
        signal.signal(signal.SIGINT,signal.SIG_IGN)
        out.mkdir(parents=True,exist_ok=True)
        p=out/'result.json'
        if not p.exists() and (out/'result.json.zst').exists():
            p=out/'result.json.zst'
        try:
            if p.exists():report=read_json(p)
        except (ValueError,EOFError):
            report=None
        if report is None:
            report={'status':'running','training_rgb':training_rgb,'physical_success':None}
        if failure is not None or stop_state['interrupted'] or report.get('status')=='running':
            report.update(status='interrupted' if isinstance(failure,KeyboardInterrupt) or stop_state['interrupted'] else 'HOST_ERROR',
                error_type=type(failure).__name__ if failure else 'IncompleteRunner',
                error=str(failure) if failure else 'runner returned without a terminal result',
                physical_success=None,training_include=False,training_candidate=False)
        if 'audit' in stop_state:
            report['input_audit']=stop_state['audit'].record()
        else:
            report.setdefault('input_audit',None)
        report['input_audit_available']=report['input_audit'] is not None
        # Publish the terminal audit BEFORE processing potentially partial
        # recovery ledgers. A malformed last line cannot leave status=running.
        report.update(source_sha=source,teacher_dependency_sha=TEACHER_SHA,
                      noise_sha256=noise_hash,data_admitted=False)
        atomic_result(p,report)
        try:
            report.update(source_sha=source,teacher_dependency_sha=TEACHER_SHA,noise_sha256=noise_hash,
                recovery={'mode':mode,'seed':plan['seed'],'applied_history_clean_targets':mode!= 'off',
                          'ledger':str(ledger_path),'sha256':sha256(ledger_path) if ledger_path.exists() else None},
                recovery_gate=approval,data_admitted=False)
            if mode == SEARCH_MODE:
                report['recovery'].update(rotation_calibration=rotation_calibration,yaw_gain=yaw_gain)
            if mode in PERTURB_MODES:
                report['recovery']['audit']=recovery_statistics(read_rows(ledger_path))
                report['recovery']['perturbation_targets_excluded']=True
            if evaluation_path:
                report['recovery']['evaluation_only']={'path':str(evaluation_path),'sha256':sha256(evaluation_path),
                    'scope':'10 Hz command boundary contacts and wheel/base GT; never returned to teacher'}
            if training_rgb:
                report.update(training_candidate=bool(report.get('physical_success') and approval),
                              training_include=False,training_exclusion_reason='awaiting dataset admission')
            meta=out/'RUN_META.json';m=json.loads(meta.read_text()) if meta.exists() else {};m.update(sha=source,pr=504,
                 branch='claude/act-train',teacher_dependency_sha=TEACHER_SHA);write_json(meta,m)
        except Exception as error:
            report.update(recovery_finalization_error={'type':type(error).__name__,'error':str(error)},
                          training_candidate=False,training_include=False)
            if report.get('status')=='complete':
                report.update(status='HOST_ERROR',physical_success=None)
        finally:
            atomic_result(p,report)
        # Preserve a finite compressed ledger; originals are not overwritten.
        if ledger_path.exists():
            from scripts.run_grasp_act_teacher import compress_logs
            compress_logs(out.parent)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('plan','out','dependency-root','noise'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--recovery-mode',choices=MODES,default='off')
    p.add_argument('--rotation-calibration',choices=('off',CALIBRATION_MODE),default='off')
    p.add_argument('--training-rgb',action='store_true');p.add_argument('--gate-receipt',type=Path)
    p.add_argument('--episode',type=int,required=True);p.add_argument('--cap-s',type=float,default=90.)
    a=p.parse_args();plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    run(plan,a.out,dependency_root=a.dependency_root,noise_path=a.noise,mode=a.recovery_mode,
        training_rgb=a.training_rgb,gate_receipt=a.gate_receipt,cap_s=a.cap_s,rotation_calibration=a.rotation_calibration)


if __name__=='__main__':main()
