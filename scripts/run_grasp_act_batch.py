"""Finite VM3 teacher waves with the existing speed verdict and five-minute ledger."""
from __future__ import annotations
import argparse,hashlib,json,os,signal,subprocess,sys,time
from collections import Counter
from pathlib import Path
from scripts.azure_speed_gate import require_azure,verdict,SpeedWarning,kill_group,write


def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def summarize(rows,planned):
    completed=[r for r in rows if r.get('status')=='complete' and r.get('exit',0)==0]
    return {'object_kind':'long_beam','n':sum(r.get('physical_success') is True for r in completed),
        'N':len(completed),'planned_N':planned,'started_N':len(rows),
        'joint_held_n':sum(r.get('joint_held') is True for r in completed),
        'robots':{rid:{'n':sum(r.get('teachers',{}).get(rid,{}).get('outcome')=='success' for r in completed),
            'N':len(completed)} for rid in ('r1','r2')},
        'failure_reasons':dict(Counter(t['outcome'] for r in completed for t in r.get('teachers',{}).values() if t.get('outcome')!='success')),
        'host_errors':sum(r.get('status')=='HOST_ERROR' or (r.get('status')!='interrupted' and r.get('exit',0) not in (0,-2,130)) for r in rows),
        'interrupted':sum(r.get('status')=='interrupted' for r in rows),'rows':rows}


def wave(root,plan,indices,cap,*,probe,limit):
    jobs=[];reason=None;rows=[];monitored=0.;started=time.monotonic()
    parent=read(root.parents[0]/'RUN_META.json')
    env={**os.environ,**{k:'1' for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','LP_NUM_THREADS')}}
    try:
        for index in indices:
            target=root/f'episode-{index:03d}';target.mkdir(parents=True,exist_ok=False)
            write(target/'RUN_META.json',{**parent,'class':'dev','pr':484,'purpose':'speed_probe' if probe else 'teacher_gate'})
            command=[sys.executable,'-m','scripts.sim_cli','workflow','run','grasp-act-teacher','--',
                '--plan',str(plan),'--episode',str(index),'--out',str(target/'raw'),'--cap-s',str(cap)]
            if probe:command.append('--probe')
            log=(target/'log.txt').open('x');at=time.monotonic()
            proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
            write(target/'PROCESS.json',{'pid':proc.pid,'command':command,'started_unix':time.time()})
            jobs.append((index,target,proc,log,at,SpeedWarning(limit)))
        while any(p.poll() is None for _,_,p,_,_,_ in jobs):
            now=time.monotonic();states=[]
            for index,target,proc,_,at,warning in jobs:
                result=read(target/'raw/result.json');progress=read(target/'raw/progress.json')
                states.append({'index':index,'exit':proc.poll(),'progress':progress,'status':result.get('status')})
                if proc.poll() not in (None,0):reason='CHILD_HOST_ERROR';break
                if not probe and result.get('status')=='complete' and result.get('physical_success') is False:
                    reason='PHYSICAL_TEACHER_FAILURE';break
                if now-at > (max(300.,30*limit*3) if probe else max(600.,cap*limit*3)):
                    reason='WALL_TIMEOUT';break
                if proc.poll() is None:
                    value=warning.observe(now,float(progress.get('sim_s',0.)))
                    if value:write(target/'SPEED_GATE_WARNING.json',value)
            if now-monitored>=300 or reason:
                write(root/f'monitor-{int(now-started):06d}.json',{'unix':time.time(),'loadavg':os.getloadavg(),'states':states,'stop_reason':reason})
                monitored=now
            if reason:break
            time.sleep(2)
    except BaseException as error:
        reason=type(error).__name__+':'+str(error)
    finally:
        if reason:write(root/'SUPERVISOR_STOP.json',{'reason':reason,'unix':time.time(),'scope':'this teacher wave only'})
        for _,_,proc,_,_,_ in jobs:kill_group(proc)
        for index,target,proc,log,at,_ in jobs:
            try:code=proc.wait(timeout=45)
            except subprocess.TimeoutExpired:kill_group(proc,signal.SIGKILL);code=proc.wait()
            log.close();(target/'EXIT').write_text(str(code)+'\n')
            result=read(target/'raw/result.json') or {'status':'HOST_ERROR','error':'missing result'}
            # Preserve each standard workflow record as well as the raw episode.
            from scripts.remote_run_finish import collect
            collect(Path(__file__).resolve().parents[1],target)
            result.update(index=index,exit=code,raw=str(target/'raw'))
            if (target/'raw/result.json').is_file():result['result_sha256']=hashlib.sha256((target/'raw/result.json').read_bytes()).hexdigest()
            rows.append(result)
    write(root/'wave.json',{'reason':reason,'rows':rows})
    return rows,reason


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--concurrency',type=int,default=16);p.add_argument('--speed-gate-limit',type=float,default=3.5)
    p.add_argument('--cap-s',type=float,default=60.);p.add_argument('--probe-only',action='store_true');a=p.parse_args()
    root=a.root.resolve();require_azure(root);plan=a.plan.resolve();episodes=read(plan)['episodes']
    if not 1<=a.concurrency<=16 or len(episodes)<a.concurrency:raise ValueError('explicit 1..16 concurrency and enough plans required')
    if not 0<a.cap_s<=180:raise ValueError('finite simulation cap required')
    if os.getloadavg()[0]>=12.8:raise ValueError('AZURE_LOAD_ADMISSION')
    available=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))
    if available<6*1024**2+a.concurrency*512*1024:raise ValueError('AZURE_MEMORY_ADMISSION')
    write(root/'resource-admission.json',{'loadavg':os.getloadavg(),'memory_available_kib':available,
        'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest(),'concurrency':a.concurrency})
    rows,reason=wave(root/'speed',plan,range(a.concurrency),30.,probe=True,limit=a.speed_gate_limit)
    samples=[{'sim_s':r.get('sim_s'),'wall_s':r.get('wall_s'),'exit':r['exit'],
        'expected_stop':r.get('status')=='complete' and r.get('sim_s',0)>=30-1e-6,
        'finalization_complete':any((Path(r['raw'])/name).is_file() for name in ('manifest.json','manifest.json.zst')),'finalization_errors':[],
        'raw':r['raw']} for r in rows]
    gate=verdict(samples,a.concurrency,a.speed_gate_limit)
    if reason:gate.update(status='SPEED_GATE_FAIL',admitted=False,reason=reason)
    write(root/'speed-gate.json',gate)
    if not gate['admitted'] or a.probe_only:return
    all_rows=[]
    for start in range(0,len(episodes),a.concurrency):
        rows,reason=wave(root/f'cohort-{start:03d}',plan,range(start,min(start+a.concurrency,len(episodes))),a.cap_s,probe=False,limit=a.speed_gate_limit)
        all_rows.extend(rows);write(root/'teacher-gate.json',summarize(all_rows,len(episodes)))
        if reason:break


if __name__=='__main__':main()
