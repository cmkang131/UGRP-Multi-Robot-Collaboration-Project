"""Finite gcp2 L4 recording warm/pilot; never admits data or trains."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

BASE = Path('/home/ugrp/ugrp-sim')
QUALIFIED = BASE/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
TEACHER = BASE/'src/warp1-teacher-snapshot-6f057f7e'
class ResourceCap(RuntimeError):
    pass

API = BASE/'src/0362037280c6cbc4677f70366db43b9892b23690'
C = BASE/'runs/simalt3/c-env/bin/python'
WARP = BASE/'runs/simalt3/warp-env/bin/python'

def write(path, value):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)+'\n'); tmp.replace(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--deadline-utc',required=True);p.add_argument('--whole-control-graph-v1',action='store_true')
    p.add_argument('--cap-s',type=float,default=3);p.add_argument('--seed',type=int,default=86820)
    p.add_argument('--kind',choices=['cyan','red','green','yellow'],default='cyan')
    p.add_argument('--lease-name',default='act16w');a=p.parse_args()
    if not 0<a.cap_s<=90 or not a.lease_name.startswith('act16w'):p.error('finite existing90SIM cap and own lease required')
    sys.path.insert(0,str(API/'scripts'))
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    if host['instance']!='ugrp-act-l4-gcp2': raise RuntimeError('exact qualified L4 host required')
    a.root.mkdir(parents=True,exist_ok=False)
    lease=BASE/'leases'/(a.lease_name+'.json')
    report={'status':'running','host':host,'started_utc':datetime.now(timezone.utc).isoformat(),
            'training_include':False,'data_admitted':False,'cap_sim_s':a.cap_s,'seed':a.seed,'kind':a.kind,'raw':str(a.root)}
    deadline=datetime.fromisoformat(a.deadline_utc).timestamp();start=time.monotonic()
    with lease.open('x') as f:json.dump({'task':'act16w','pid':os.getpid(),'start':report['started_utc'],
        'expected_end':a.deadline_utc,'stage':'recording_pilot' if a.cap_s>3 else 'recording_warm3SIM','concurrency':1,'gpu_shared':True},f)
    env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    proc=None
    def run(name, args):
        nonlocal proc
        write(a.root/(name+'-argv.json'),args)
        with (a.root/(name+'.log')).open('x') as log:
            proc=subprocess.Popen(args,cwd=QUALIFIED,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            report['active_pid']=proc.pid;write(a.root/'summary.json',report)
            try:
                while proc.poll() is None and time.time()<deadline:
                    progress=a.root/'controller/progress.json'
                    if progress.exists() and not (a.root/'first30.json').exists():
                        try:
                            measured=json.loads(progress.read_text());sim_s=min(measured['ticks'])*.1
                            if sim_s>=30:
                                write(a.root/'first30.json',dict(sim_s=sim_s,loop_wall_s=measured['loop_wall_s'],wall_per_SIM=measured['loop_wall_s']/sim_s,threshold=6.,threshold_basis='AGENTS speed gate user flexible3.5; block only>6',timing=measured['timing']))
                        except (ValueError,KeyError):pass
                    time.sleep(1)
                if proc.poll() is None:raise subprocess.TimeoutExpired(args,deadline-time.time())
                result=proc.returncode
            except subprocess.TimeoutExpired:
                marker={'category':'cap_end','reason':'finite_stage_resource_deadline'}
                write(a.root/'SUPERVISOR_STOP.json',marker)
                if (a.root/'controller').exists():write(a.root/'controller/SUPERVISOR_STOP.json',marker)
                os.killpg(proc.pid,signal.SIGINT)
                try:proc.wait(timeout=45)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=15)
                raise ResourceCap('resource cap_end before recording stage completed')
            if result:raise RuntimeError(name+' exit '+str(result))
    try:
        # Frozen setup sampler only. No simulator/teacher action runs here.
        code="import sys,json;from collections import Counter;sys.path.insert(0,sys.argv[1]);from scripts.make_solo_teacher_plan import episode;from harness.grasp_act_seed_splits import check_range;check_range('train',int(sys.argv[3]),1);p=episode(0,sys.argv[4],int(sys.argv[3]),'train');p.update(episode_id='act16w-record-'+sys.argv[3],batch='act16w-resume2',pr=539,negative_probe=False,gate_eligible=False,training_eligible=False);open(sys.argv[2],'x').write(json.dumps({'episodes':[p]},indent=2)+'\\n')"
        run('plan',[str(C),'-c',code,str(TEACHER),str(a.root/'plan.json'),str(a.seed),a.kind])
        common=['--physics-backend','c_pilot_v1','--teacher-source',str(TEACHER),'--plan',str(a.root/'plan.json'),
                '--scene-v5-v1','--native-sleep-policy-compat-v1','--vm-hourly-usd','1.096']
        run('reference',[str(C),str(QUALIFIED/'scripts/run_warp_act_teacher.py'),*common,'--export-compiled-only','--out',str(a.root/'reference')])
        args=['--physics-backend','mjwarp_batch_v1','--teacher-source',str(TEACHER),'--plan',str(a.root/'plan.json'),
              '--cap-s',str(a.cap_s),'--vm-hourly-usd','1.096','--scene-v5-v1','--numpy-teacher-v1','--batch-sleep-v1',
              '--native-sleep-policy-compat-v1','--compiled-reference-v1',str(a.root/'reference/compiled-312.json'),
              '--compiled-geometry-312-v1',str(a.root/'reference/compiled-geometry312.npz'),'--out',str(a.root/'controller')]
        write(a.root/'runner-args.json',args)
        record_script=Path(__file__).resolve().parents[3]/'scripts/act16w_record.py' if a.whole_control_graph_v1 else API/'scripts/run_warp_act_record.py'
        graph_args=['--whole-control-graph-v1'] if a.whole_control_graph_v1 else []
        run('record',[str(WARP),'-u',str(record_script),*graph_args,'--enabled',
              '--qualified-source',str(QUALIFIED),'--teacher-source',str(TEACHER),
              '--qualification',str(BASE/'runs/warp3/teacher-gate-qualification-r1.json'),
              '--runner-args-json',str(a.root/'runner-args.json'),'--out',str(a.root/'capture')])
        controller=json.loads((a.root/'controller/summary.json').read_text())
        report.update(status='complete',controller_status=controller['status'],timing=controller['timing'],
              loop_wall_s=controller['loop_wall_s'],sim_s=controller['attempted_control_sim_s'],
              wall_per_SIM=controller['loop_wall_s']/controller['attempted_control_sim_s'])
    except ResourceCap as error:
        report.update(status='cap_end',resource_cap_end=True,error=repr(error));raise
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        report['wall_s']=time.monotonic()-start
        report['last_child_pid']=report.pop('active_pid',None);report['active_pid']=None
        report['foreign_leases_preserved']=[x.name for x in lease.parent.glob('*.json') if x!=lease]
        report['vm_stop_attempted']=False;write(a.root/'summary.json',report)
        if lease.exists() and json.loads(lease.read_text()).get('pid')==os.getpid():lease.unlink()

if __name__=='__main__':main()
