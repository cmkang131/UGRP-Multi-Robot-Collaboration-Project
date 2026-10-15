"""Finite20-case run-first queue. User requires all15 failures +5 successes.

Known teacher failures are collected through this one diagnostic cohort;
HOST_ERROR or failed speed admission stops further submissions. No new gate is
submitted unless all20 pass raw recount. Leases remain through retrieval.
"""
import datetime,hashlib,json,os,shutil,signal,statistics,subprocess,sys,time
from pathlib import Path
ROOT=Path('/home/ugrp/ugrp-sim'); OPS=ROOT/'ops-reviews/beampair9'; PY=ROOT/'ugrp/.venv-sim/bin/python'
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def read(p):
    if p.exists():return json.loads(p.read_bytes())
    z=Path(str(p)+'.zst')
    return json.loads(subprocess.check_output(['zstd','-qdc',str(z)])) if z.exists() else None
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
    cfg=read(Path(sys.argv[1]));src=ROOT/'src'/cfg['source_sha'];batch=OPS/cfg['batch']
    assert sys.platform=='linux' and cfg['max_parallel']<=16
    assert Path(cfg['rejection_table']).is_file()
    assert hashlib.sha256(Path(cfg['rejection_table']).read_bytes()).hexdigest()==cfg['rejection_table_sha256']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=src,text=True).strip()==cfg['source_sha']
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=src)
    batch.mkdir(exist_ok=False);(batch/'diagnostic').mkdir()
    write(batch/'batch-plan.json',dict(source_sha=cfg['source_sha'],planned_N=len(cfg['runs']),host='gcp2',config=cfg))
    lease=ROOT/'leases/beampair9.json';lease_value=read(lease);assert lease_value['task']=='beampair9'
    lease_value.update(pid=os.getpid(),stage=cfg['batch'],concurrency=cfg['max_parallel'],source_sha=cfg['source_sha']);write(lease,lease_value)
    env={**os.environ,'MUJOCO_GL':'osmesa','PYTHONPATH':str(src),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1','LP_NUM_THREADS':'1'}
    pending=list(cfg['runs']);running=[];completed=[];stopped=None;speed_checked=False
    def launch(r):
        other=[read(p) for p in lease.parent.glob('*.json') if p!=lease]
        reserved=sum((v or {}).get('concurrency',0) for v in other)
        if reserved+len(running)+1>40:return False
        if shutil.disk_usage(ROOT).free<cfg['disk_floor_bytes']:raise RuntimeError('disk budget floor')
        d=batch/'diagnostic'/f"episode-{r['episode']:03d}";d.mkdir()
        cmd=['timeout','--signal=INT','8h',str(PY),'-m','scripts.run_beampair1',
            '--plan',cfg['plan'],'--episode',str(r['episode']),'--out',str(d/'raw'),
            '--dependency-root',str(ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'),
            '--mode','beampair1_v1','--candidate',cfg['candidate'],'--cap-s','60',
            '--rendezvous','peer_rendezvous_v2','--approach-repair','beampair_approach_v2',
            '--wall-layer','beampair_wall_clear_v1','--peer-yield','beampair_peer_yield_v1',
            '--box-geometry','beampair_box_geometry_v1','--planning-boundary','beampair_checks_only_v1']
        log=(d/'log.txt').open('w');p=subprocess.Popen(cmd,cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        write(d/'PROCESS.json',dict(pid=p.pid,command=cmd,source_sha=cfg['source_sha'],started=now()))
        write(d/'RUN_META.json',{'class':'dev','task':'beampair9','stage':cfg['batch'],'sha':cfg['source_sha']})
        running.append(dict(p=p,d=d,log=log,r=r,at=time.monotonic()))
        write(batch/'admission-latest.json',dict(other_leases=other,reserved_concurrency=reserved,own=len(running),loadavg=os.getloadavg(),free_bytes=shutil.disk_usage(ROOT).free))
        return True
    try:
        while pending or running:
            while pending and len(running)<cfg['max_parallel'] and stopped is None and (speed_checked or len(completed)+len(running)<cfg['max_parallel']):
                if not launch(pending[0]):break
                pending.pop(0)
            for item in running[:]:
                code=item['p'].poll()
                if code is None:continue
                item['log'].close();d=item['d'];result=read(d/'raw/result.json')
                ok=bool(code==0 and result and result.get('status')=='complete' and result.get('physical_success'))
                category='success' if ok else 'HOST_ERROR' if not result or code or result.get('status')=='HOST_ERROR' else 'cap_end' if result.get('cap_end') else 'teacher_failure'
                entry=dict(**item['r'],raw=str(d/'raw'),category=category,exit=code,wall_s=time.monotonic()-item['at'],
                    sim_s=(result or {}).get('sim_s'),first30=read(d/'raw/first30-speed.json'))
                completed.append(entry);write(d/'EXIT.json',entry);running.remove(item)
                if category=='HOST_ERROR':stopped=dict(reason='HOST_ERROR',seed=item['r']['seed'])
                write(batch/'progress.json',dict(completed=completed,running=[x['r'] for x in running],pending=pending,stop=stopped))
            if not speed_checked and len(completed)>=cfg['max_parallel'] and not running:
                values=[r['first30']['wall_per_sim'] for r in completed if r.get('first30')]
                median=statistics.median(values) if values else None
                # Runs completing before30SIMs are complete measurements, not
                # missing host results. Record their total ratio separately.
                short=[r['wall_s']/r['sim_s'] for r in completed if not r.get('first30') and r.get('sim_s')]
                all_values=values+short
                admission=statistics.median(all_values) if all_values else None
                write(batch/'first30-speed.json',dict(exact_first30_N=len(values),exact_first30_median=median,
                    short_completed_N=len(short),short_total_ratios=short,admission_median=admission,
                    short_scope='complete finite runs below30SIMs use total wall/SIM; no interpolated30s result'))
                if admission is None or admission>6.:stopped=dict(reason='SPEED_GATE_FAIL',median=admission)
                speed_checked=True
            if stopped and not running:break
            time.sleep(.5)
    finally:
        for item in running:
            if item['p'].poll() is None:
                os.killpg(item['p'].pid,signal.SIGINT)
                item['p'].wait();item['log'].close()
        write(batch/'DONE.json',dict(completed=completed,not_started=pending,stop=stopped,source_sha=cfg['source_sha'],finished=now()))
        value=read(lease);value.update(stage='analysis',concurrency=0,finished_batch=cfg['batch']);write(lease,value)
    print(json.dumps(dict(N=len(completed),categories={k:sum(r['category']==k for r in completed) for k in ('success','teacher_failure','cap_end','HOST_ERROR')},not_started=len(pending),stop=stopped)))
if __name__=='__main__':main()
