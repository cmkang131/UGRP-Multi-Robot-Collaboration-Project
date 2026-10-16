"""Finite exclusive-GPU queue for N64/N256; never stops foreign tasks or VMs."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback


def gpu_pids():
    text=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True)
    return {int(x.strip()) for x in text.splitlines() if x.strip().isdigit()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for key in ('python','qualified-source','teacher-source','plan','compiled-reference','compiled-geometry','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--deadline-utc',required=True,help='administrative resource deadline, no planning wall budget')
    p.add_argument('--hourly-usd-estimate',type=float,required=True)
    a=p.parse_args()
    if not a.enabled or sys.platform!='linux':p.error('default OFF, Linux gcp2 only')
    from warp_act_warm import identity
    from warp_act_c16_warm import foreign as foreign_compute
    host=identity()
    if host['instance'] not in ('ugrp-act-l4-gcp2','ugrp-act-l4-gcp2b'):p.error('explicit gcp2 L4 main/b only')
    end=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00')).timestamp()
    a.out.mkdir(parents=True,exist_ok=False);child=None;log=None
    report=dict(status='running',host=host,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                cases=[],attempts=[],deadline_utc=a.deadline_utc,scope='same qualified teacher SIM3..6; replicas load only')
    lease=Path('/home/ugrp/ugrp-sim/leases/warp3.json')
    def load(owned):
        # Account for CPU-side rendering/teacher work on the same L4 VM too.
        # Existing system daemons are outside this user and never stopped.
        return gpu_pids()-owned, foreign_compute(owned)
    def write_status(stage,**extra):
        value=dict(stage=stage,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**extra)
        (a.out/'progress.json').write_text(json.dumps(value,indent=2)+'\n')
        if lease.exists():
            d=json.loads(lease.read_text())
            if d.get('task')!='warp3':raise RuntimeError('own lease lost')
            d.update(pid=os.getpid(),active_pids=[os.getpid()]+([child.pid] if child and child.poll() is None else []),
                     stage=stage,exclusive_gpu_requested=True,concurrency=0 if stage=='WAIT_FOREIGN_GPU' else 1)
            lease.write_text(json.dumps(d,indent=2)+'\n')
    try:
        for n in (64,256):
            attempt=0
            while time.time()<end:
                foreign,cpu=load({os.getpid()})
                if foreign or cpu:
                    write_status('WAIT_FOREIGN_GPU',nworld=n,foreign_gpu_pids=sorted(foreign),foreign_compute=cpu);time.sleep(20);continue
                attempt+=1;folder=a.out/f'n{n}-attempt{attempt:02d}';barrier=a.out/f'barrier-n{n}-attempt{attempt:02d}';barrier.mkdir()
                cmd=[str(a.python),'-u',str(Path(__file__).with_name('warp_act_warm.py')),'--enabled','--backend','mjwarp_batch_v1',
                     '--nworld',str(n),'--qualified-source',str(a.qualified_source),'--teacher-source',str(a.teacher_source),
                     '--plan',str(a.plan),'--compiled-reference',str(a.compiled_reference),'--compiled-geometry',str(a.compiled_geometry),
                     '--hourly-usd-estimate',str(a.hourly_usd_estimate),'--barrier',str(barrier),'--out',str(folder)]
                log=(a.out/f'n{n}-attempt{attempt:02d}.log').open('x');child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
                own={os.getpid(),child.pid};seen=set();cpu_seen={};samples=[];write_status('WARMUP',nworld=n,worker_pid=child.pid)
                while not list(barrier.glob('*.READY.json')):
                    if time.time()>=end:raise TimeoutError('resource deadline during warmup')
                    if child.poll() is not None:raise RuntimeError('GPU worker exited before warm barrier')
                    foreign,cpu=load(own);seen.update(foreign);cpu_seen.update({x['pid']:x for x in cpu});time.sleep(.2)
                foreign,cpu=load(own);seen.update(foreign);cpu_seen.update({x['pid']:x for x in cpu})
                if seen or cpu_seen:
                    # Only our worker is interrupted; foreign jobs are preserved.
                    child.send_signal(signal.SIGINT);child.wait(timeout=60);log.close();log=None
                    report['attempts'].append(dict(nworld=n,attempt=attempt,status='unqualified_shared_warmup',
                        category='foreign_compute_load',reason='foreign compute appeared during warmup',blocking_object=sorted(seen|set(cpu_seen)),minimum_gap_m=None,
                        minimum_gap_status='resource contention, not geometry',raw=str(folder)))
                    child=None;continue
                write_status('TIMED',nworld=n);(barrier/'GO.json').write_text('{}\n')
                while not list(barrier.glob('*.DONE.json')):
                    if time.time()>=end:raise TimeoutError('resource deadline during timing')
                    if child.poll() is not None:raise RuntimeError('GPU worker exited during timing')
                    foreign,cpu=load(own);seen.update(foreign);cpu_seen.update({x['pid']:x for x in cpu})
                    samples.append(dict(monotonic=time.monotonic(),foreign=sorted(foreign),foreign_compute=cpu));time.sleep(.2)
                foreign,cpu=load(own);seen.update(foreign);cpu_seen.update({x['pid']:x for x in cpu})
                write_status('FINALIZING',nworld=n);(barrier/'FINALIZE.json').write_text('{}\n')
                if child.wait(timeout=300):raise RuntimeError('GPU worker finalization failed')
                log.close();log=None;child=None
                full=json.loads((folder/'summary.json').read_text())
                logtext=(a.out/f'n{n}-attempt{attempt:02d}.log').read_text()
                middle=logtext.split('WARM_MEASURE_BEGIN',1)[-1].split('WARM_MEASURE_END',1)[0]
                compiled='(compiled)' in middle
                qualified=full['status']=='complete' and not seen and not cpu_seen and not compiled
                row={k:full[k] for k in ('backend','host','nworld','source_sha','controller_source','teacher_source','seed',
                    'scenario','warmup_sim_s','timed_sim_range','timed_wall_s','aggregate_timed_sim_s','sim_s_per_wall_s',
                    'sim_s_per_usd','hourly_usd_estimate','price_basis','interval_median','interval_p90','first10_median',
                    'last10_median','timed_components','cap_end','HOST_ERROR')}
                row.update(qualified_unshared=qualified,foreign_gpu_pids=sorted(seen),foreign_samples=samples,
                    foreign_compute=list(cpu_seen.values()),
                    compiled_during_timing=compiled,raw=str(folder),summary_sha256=hashlib.sha256((folder/'summary.json').read_bytes()).hexdigest())
                report['attempts'].append(row)
                if not qualified:continue
                # Verify the complete raw file manifest independently.
                for rel,sha in full['raw_sha256'].items():
                    if hashlib.sha256((folder/rel).read_bytes()).hexdigest()!=sha:raise RuntimeError('warm raw hash mismatch')
                row['raw_hash_files']=len(full['raw_sha256']);row['raw_hash_mismatch']=0
                report['cases'].append(row);break
            else:raise TimeoutError('resource deadline while waiting for exclusive GPU')
        report['status']='complete';write_status('COMPLETE')
    except BaseException as error:
        report.update(status='cap_end' if isinstance(error,TimeoutError) else 'HOST_ERROR',reason=repr(error),traceback=traceback.format_exc());raise
    finally:
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT)
            try:child.wait(timeout=60)
            except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=20)
        if log:log.close()
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
