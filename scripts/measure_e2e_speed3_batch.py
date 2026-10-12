"""Six concurrent old/dt1/dt2 DEV cells, finite 60 SIM seconds; no cohort restart."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from scripts.run_e2e_azure_batch import prepare_native
from harness.e2e_result_writer import write


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--pr',type=int,required=True)
    p.add_argument('--repeat',type=int,default=1)
    a=p.parse_args()
    if sys.platform!='linux' or not a.run_root.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):
        raise ValueError('AZURE_PERSISTENT_ONLY')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=a.expected_source_sha:
        raise ValueError('COMMITTED_SHA_REQUIRED')
    a.run_root.mkdir(exist_ok=False)
    write(a.run_root/'RUN_META.json',{'class':'dev','pr':a.pr,'branch':'codex/e2e-speed3','sha':a.expected_source_sha,'batch':a.run_root.name})
    write(a.run_root/'speed-gate-override.json',dict(reason='User-authorized old/new speed characterization; finite 60 SIM seconds, no research cohort start'))
    write(a.run_root/'native.json',prepare_native())
    common=['--expected-source-sha',a.expected_source_sha,'--driver-profile','study_gemma4_31b_v1',
        '--relay-receipt',str(a.relay_receipt),'--e2e-live','--event-driven-llm','--compact-prompt',
        '--setdown-only-when-relook','on_v1','--decider','off','--exploration-progress','frontier_progress_v1',
        '--pose-fix','innovation','--path-follow','rpp_v1','--dev-light','--mapping-budget','case_cap_v1',
        '--wall-cap-s','1800','--stall-recovery','off','--stall-noise','off','--boundary-views','candidate_views_v1',
        '--b-marker-detect','contrast_v1','--stall-odometry','rgb_vo_us_v1','--ultrasonic-front','on_v1',
        '--vo-floor-mask','homography_v1','--vo-rotation-policy','no_ransac_v1','--explore-deadlock','replan_v1',
        '--boundary-association','extent_v1','--boundary-retry','navigation_v1','--boundary-coverage','native_v1',
        '--runtime-registration','reviewed_v1','--measure-sim-s','60','--rbpf-audit-hash','none','--execute']
    env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
    jobs=[]
    for seed in (61001,61002,61003):
        for variant in ('base','adaptive'):
            name=f'e2e-speed3-{variant}-s{seed}-r{a.repeat}'
            target=a.run_root/name;target.mkdir()
            write(target/'RUN_META.json',{'class':'dev','pr':a.pr,'branch':'codex/e2e-speed3','sha':a.expected_source_sha,'batch':a.run_root.name,'variant':variant,'seed':seed})
            workflow='e2e-boundary-native-v213' if variant=='base' else 'e2e-speed3-v215'
            cmd=[sys.executable,'-m','scripts.sim_cli','workflow','run',workflow,'--timeout','1800','--',*common,
                 '--seed',str(seed),'--output',str(target/'raw')]
            if variant!='base':cmd+=['--speed3',variant+'_v1']
            log=(target/'launch.log').open('x')
            command=[sys.executable,'-m','scripts.remote_run_finish','--source',os.getcwd(),'--run',str(target),'--',*cmd]
            process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            jobs.append((target,process,log))
            write(target/'submitted.json',dict(command=cmd,pid=process.pid,started_unix=time.time(),loadavg=os.getloadavg()))
    try:
        while any(p.poll() is None for _,p,_ in jobs):time.sleep(2)
    finally:
        for target,process,log in jobs:
            if process.poll() is None:
                import signal
                os.killpg(process.pid,signal.SIGINT)
            process.wait();log.close()
    write(a.run_root/'batch-result.json',dict(runs=[dict(name=t.name,exit=p.returncode) for t,p,_ in jobs]))


if __name__=='__main__':main()
