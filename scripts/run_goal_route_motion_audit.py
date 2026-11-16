"""egomap59: calibrated-command audit and PR422 shared heading; same P1 gates."""
from pathlib import Path
import argparse,json,os,signal,subprocess
from harness.active_camera import bind
from scripts import run_goal_route_preflight as previous
from sim.goal_route_assets import OPTION,ASSETS,geometry,directory,xml_preflight
from sim.zone_masterpi_v3_scene import static_map

ROOT=previous.ROOT
EXP=ROOT/'experiments/2026-10-09-goal-route-motion-audit'
RAW=Path('/Users/changmin/projects/ugrp/outputs/goal-route-motion-audit-v1')
SEEDS=previous.SEEDS


def bundle(seed,source):
    b=previous.bundle(seed,source)
    b['execution_bundle_id']=f'egomap59-goal-route-{seed}-v1'
    b['heading_contract']['command_contract_source']='6ffa74dfcf004458e450fde5a897dc343bd13e1b'
    b['heading_contract']['command_contract']='single_axis_0.10_to_0.80_s'
    b['motion_audit']=dict(startup_correction='off',mean_model='unchanged v122+rotL measured response curve',
        reason='forward pulses 1.010 expected/actual; startup-loss hypothesis not supported',
        retrospective_evaluation_only=True,calibration_refit=False)
    return b


run=bind(previous.run,bundle=bundle)
source_check=bind(previous.source_check,EXP=EXP)


def preflight(seed,source):
    receipt=source_check(source)
    # No backend/lock/model construction can occur before this succeeds.
    b=bundle(seed,source);r,xml=xml_preflight(b,seed)
    receipt['xml_preflight']=r
    return receipt,xml


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,choices=SEEDS,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    assert a.output.resolve()==RAW/f'seed{a.seed}' and not a.output.exists()
    receipt,xml=preflight(a.seed,a.expected_source_sha)
    RAW.mkdir(parents=True,exist_ok=True)
    previous.previous.base.dump(RAW/f'preflight-{a.seed}.json',receipt)
    (RAW/f'preflight-{a.seed}.xml').write_text(xml)
    if not a.execute:return 0
    assert int(subprocess.check_output(['ps','-o','ni=','-p',str(os.getpid())]))==0,'NICE_MUST_BE_ZERO'
    queue=json.loads((RAW/'queue-admission.json').read_text())
    assert queue['s3fix_completed'] and queue['approved_ego_next']
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=acquire(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',purpose=f'egomap59 {a.seed} P1 DEV',pid=os.getpid(),expected_minutes=60)
    try:
        def timeout(*_):raise TimeoutError('HOST_BUDGET_60_MINUTES')
        signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,3600)
        from sim.goal_route_assets import PhysicsBackend
        result=run(a.output,a.expected_source_sha,a.seed,PhysicsBackend)
        previous.previous.base.dump(a.output/'source-admission.json',receipt);previous.previous.base.dump(a.output/'lock.json',lock)
        previous.previous.base.dump(a.output/'queue-admission.json',queue)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
