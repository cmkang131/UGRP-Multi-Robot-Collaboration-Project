"""Finite C16 warm supervisor; no foreign computation in a qualified window."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback


def foreign(owned):
    found=[]
    owned=set(owned)
    # Session manager/timeout ancestors and renderer/compressor descendants are
    # our own finite job, not foreign research load.
    parents={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            text=path.joinpath('stat').read_text();parents[int(path.name)]=int(text[text.rfind(')')+2:].split()[1])
        except (FileNotFoundError,PermissionError,ValueError):pass
    cur=os.getpid()
    while cur>1 and cur in parents:owned.add(cur);cur=parents[cur]
    changed=True
    while changed:
        add={pid for pid,parent in parents.items() if parent in owned}-owned
        changed=bool(add);owned.update(add)
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or int(path.name) in owned: continue
        try:
            if path.stat().st_uid != os.getuid(): continue
            args=path.joinpath('cmdline').read_bytes().split(b'\0')
            if args and any(x in args[0].lower() for x in (b'python',b'mujoco',b'ffmpeg')):
                found.append(dict(pid=int(path.name),executable=args[0].decode()))
        except (FileNotFoundError,PermissionError): pass
    return found


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enabled',action='store_true')
    for key in ('python','qualified-source','teacher-source','plan','compiled-reference','compiled-geometry','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--hourly-usd-estimate',type=float,required=True)
    a=p.parse_args()
    if not a.enabled or sys.platform!='linux':p.error('explicit Linux opt-in required')
    a.out.mkdir(parents=True,exist_ok=False);barrier=a.out/'barrier';barrier.mkdir()
    children=[];logs=[];samples=[];owned={os.getpid(),os.getppid()}
    report=dict(status='running',qualified_unshared=False,nworld=16,replicas_are_load=True,independent_gate_episodes=0)
    try:
        initial=foreign(owned);report['foreign_before']=initial
        if initial:report['status']='HOLD_FOREIGN_LOAD';return
        for i in range(16):
            folder=a.out/f'c-{i:02d}'
            cmd=[str(a.python),'-u',str(Path(__file__).with_name('warp_act_warm.py')),'--enabled','--backend','c_pilot_v1',
                 '--qualified-source',str(a.qualified_source),'--teacher-source',str(a.teacher_source),
                 '--plan',str(a.plan),'--compiled-reference',str(a.compiled_reference),'--compiled-geometry',str(a.compiled_geometry),
                 '--hourly-usd-estimate',str(a.hourly_usd_estimate),'--barrier',str(barrier),'--out',str(folder)]
            log=(a.out/f'c-{i:02d}.log').open('x');logs.append(log)
            child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT);children.append(child);owned.add(child.pid)
        while len(list(barrier.glob('*.READY.json')))<16:
            if any(x.poll() is not None for x in children):raise RuntimeError('C worker exited before warm barrier')
            time.sleep(.2)
        report['foreign_at_go']=foreign(owned)
        if report['foreign_at_go']:raise RuntimeError('foreign load appeared before timing')
        (barrier/'GO.json').write_text('{}\n')
        while len(list(barrier.glob('*.DONE.json')))<16:
            if any(x.poll() is not None for x in children):raise RuntimeError('C worker exited during timing')
            samples.append(dict(monotonic=time.monotonic(),foreign=foreign(owned)))
            time.sleep(.2)
        rows=[json.loads(p.read_text()) for p in sorted(barrier.glob('*.DONE.json'))]
        wall=max(r['timed_monotonic_end'] for r in rows)-min(r['timed_monotonic_start'] for r in rows)
        report.update(timed_wall_s=wall,aggregate_timed_sim_s=48.,sim_s_per_wall_s=48./wall,
            sim_s_per_usd=48./wall*3600/a.hourly_usd_estimate,
            hourly_usd_estimate=a.hourly_usd_estimate,price_basis='inherited estimate, not actual billing',
            foreign_during=samples,foreign_after=foreign(owned),worker_timing=[{k:r[k] for k in ('timed_wall_s','interval_median','interval_p90','host')} for r in rows])
        (barrier/'FINALIZE.json').write_text('{}\n')
        for child in children:
            if child.wait(timeout=90):raise RuntimeError('C finalization failed')
        report.update(status='complete',qualified_unshared=not any(x['foreign'] for x in samples) and not report['foreign_after'],
                      cap_end=16,HOST_ERROR=0,scope='same fixed source case, normal teacher SIM3..6 after3SIMs warmup; no model inference or full-mission extrapolation')
    except BaseException as error:
        report.update(status='HOST_ERROR',HOST_ERROR=1,error=repr(error),traceback=traceback.format_exc());raise
    finally:
        for child in children:
            if child.poll() is None:child.send_signal(signal.SIGINT)
        for child in children:
            if child.poll() is None:
                try:child.wait(timeout=20)
                except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=10)
        for log in logs:log.close()
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
