"""Finite Mac SSH/cloud relay for this authorized A/B only; no local ML/GUI.

No credentials are copied. Never stops a VM or peer. Automatic restart is
allowed only for the known8h lifetime termination, with fresh budget evidence.
"""
from datetime import datetime,timezone,timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
RECORD=HERE/'controller-state.json'
ALERT=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/ops-alert.md')
PROJECT='ugrp-sim-b-1014';ACCOUNT='changmin5781@gmail.com';ZONE='asia-northeast3-a'
TRAIN_SOURCE='4747c4144a972e348a9ae4c7bbcc769ad116106d'
ANALYSIS_SOURCE='e62e73f62'  # resolved to a full imported SHA at launch
BASE='/home/ugrp/ugrp-sim';OUT=BASE+'/ops-reviews/beamact3'
PY=BASE.replace('/ugrp-sim','/ugrp-rl1b-act-env')+'/bin/python'
START='2026-10-16T02:09:00Z'
state={'task':'beamact3','status':'running','started':datetime.now(timezone.utc).isoformat(),
       'training_source':TRAIN_SOURCE,'arms':{},'events':[],'vm_stop_performed':False}
initial=time.monotonic();last_budget=0.;last_cloud=0.;info=None;gpu_ip=None


def save():
    tmp=RECORD.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(RECORD)


def event(kind,**data):
    row=dict(t=datetime.now(timezone.utc).isoformat(),kind=kind,**data)
    state['events'].append(row);save();print(json.dumps(row),flush=True)


def run(argv,**kw):
    return subprocess.run(argv,text=True,capture_output=True,check=True,timeout=60,**kw).stdout


def cloud(args):
    return json.loads(run(['gcloud',*args,'--account',ACCOUNT,'--project',PROJECT,'--format=json']))


def budget(force=False):
    global last_budget
    if not force and time.monotonic()-last_budget<300:return
    rows=cloud(['logging','read','resource.type="cloud_run_revision" AND resource.labels.service_name="budget-stop" AND timestamp>="'+START+'"','--limit=20'])
    last_budget=time.monotonic()
    parsed=[]
    for r in rows:
        data=r.get('jsonPayload',{})
        if data:parsed.append(dict(timestamp=r.get('timestamp'),payload=data))
        cost=data.get('costAmount');limit=data.get('budgetAmount')
        fired=(isinstance(cost,(int,float)) and isinstance(limit,(int,float)) and cost>=limit>0)
        fired=fired or 'stop_all' in json.dumps(data) or 'stop_all' in r.get('textPayload','')
        if fired:
            state['status']='BUDGET';event('BUDGET',evidence=r)
            with ALERT.open('a') as f:f.write('\nbeamact3: BUDGET | 새 실행·재시작 중단 | '+json.dumps(parsed[-1:] or [dict(timestamp=r.get('timestamp'))])+'\n')
            raise RuntimeError('BUDGET_STOP fired: no new execution or restart')
    if parsed:
        state['latest_budget_evidence']=parsed[0];save()
    else:
        # Logs may simply have no update since task start. Fetch the latest
        # actual billing notification, and fail closed if evidence unavailable.
        older=cloud(['logging','read','resource.type="cloud_run_revision" AND resource.labels.service_name="budget-stop" AND jsonPayload.costAmount:*','--limit=1'])
        if not older:raise RuntimeError('no budget evidence; do not submit/restart')
        state['latest_budget_evidence']=dict(timestamp=older[0].get('timestamp'),payload=older[0].get('jsonPayload'));save()


def instance(force=False):
    global info,last_cloud,gpu_ip
    if force or info is None or time.monotonic()-last_cloud>120:
        budget()
        info=cloud(['compute','instances','describe','ugrp-act-l4-gcp2','--zone',ZONE])
        gpu_ip=info.get('networkInterfaces',[{}])[0].get('accessConfigs',[{}])[0].get('natIP')
        last_cloud=time.monotonic()
        if int(info['scheduling']['maxRunDuration']['seconds'])!=28800:
            raise RuntimeError('L4 lifetime guard changed; no execution')
    return info


def ssh(host):
    if host=='gpu':return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-i','/Users/changmin/.ssh/ugrp_gcp2','ugrp@'+gpu_ip]
    return ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','gcp2']


def query(host,code):
    return json.loads(run([*ssh(host),'python3 -'],input=code))


def available_gpu():
    current=instance(force=True)
    if current['status']=='RUNNING':return
    if current['status'] in ('STOPPING','STAGING','PROVISIONING'):
        time.sleep(30);return available_gpu()
    if current['status']!='TERMINATED':raise RuntimeError('unexpected L4 lifecycle state')
    budget(force=True)
    boot=datetime.fromisoformat(current['lastStartTimestamp'])
    elapsed=(datetime.now(timezone.utc)-boot).total_seconds()
    # Runtime shutdown must coincide with the unchanged8h configured lifetime.
    # Early termination is ambiguous, including budget-stop: never restart it.
    if elapsed<28800:raise RuntimeError('early VM termination; no automatic restart')
    event('known_8h_host_interruption',last_start=current['lastStartTimestamp'],status=current['status'])
    if state.get('restart_count',0)>=2:raise RuntimeError('finite controller restart count exceeded')
    cloud(['compute','instances','start','ugrp-act-l4-gcp2','--zone',ZONE,'--quiet'])
    state['restart_count']=state.get('restart_count',0)+1
    time.sleep(30);instance(force=True)
    for _ in range(12):
        try:
            # Preserve and remove ONLY our stale leases after a known reboot.
            query('gpu',f'''import datetime,json,pathlib,os
b=pathlib.Path({BASE!r});m=b/'ops-reviews/beamact3/stale-leases';m.mkdir(exist_ok=True)
removed=[]
for p in (b/'leases').glob('beamact3-*.json'):
 d=json.loads(p.read_text());pid=d.get('pid',0)
 cmd=pathlib.Path('/proc')/str(pid)/'cmdline'
 if cmd.exists() and b'beamact3' in cmd.read_bytes():raise RuntimeError('own lease still active')
 dest=m/(p.stem+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'.json')
 p.rename(dest);removed.append(str(dest))
print(json.dumps(dict(own_stale_leases_preserved=removed,other_leases_untouched=[p.name for p in (b/'leases').glob('*.json')])) )
''')
            return
        except subprocess.CalledProcessError:time.sleep(10)
    raise RuntimeError('L4 not SSH-ready after start')


def wait_stage(arm,stage,attempt):
    last_print=0.
    while True:
        if time.monotonic()-initial>18*3600:raise TimeoutError('finite18h task controller')
        budget();current=instance()
        if current['status']!='RUNNING':
            available_gpu()
            return {'status':'HOST_LIFETIME_INTERRUPTION','complete':False}
        try:
            data=query('gpu',f'''import json,pathlib
r=pathlib.Path({OUT!r})/{arm!r};sup=r/{stage+'-attempt'+str(attempt)+'-supervisor.json'!r};s=r/{stage+'-attempt'+str(attempt)!r}/'summary.json'
x=json.loads(s.read_text()) if s.exists() else {{}}
z=json.loads(sup.read_text()) if sup.exists() else {{}}
print(json.dumps(dict(supervisor_status=z.get('status'),supervisor={{k:z.get(k) for k in ('status','wall_s','output','summary_sha256','complete','exit','source_sha')}} if z.get('status')!='running' else None,status=x.get('status'),complete=x.get('complete'),steps_completed=x.get('steps_completed'),readback_verified=x.get('readback_verified'),checkpoint=x.get('last_checkpoint'),wall_s=x.get('wall_s'),timing=x.get('timing',{{}}).get('step_median_s'),lease_exists=(pathlib.Path({BASE!r})/'leases'/{'beamact3-'+arm+'.json'!r}).exists())))
''')
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired):
            instance(force=True);time.sleep(30);continue
        if time.monotonic()-last_print>60:
            print(datetime.now(timezone.utc).isoformat(),arm,stage,attempt,json.dumps({k:data.get(k) for k in ('supervisor_status','status','steps_completed','timing')}),flush=True);last_print=time.monotonic()
        if data['supervisor_status'] not in (None,'running') and not data['lease_exists']:
            if data['supervisor_status']=='HOST_ERROR':raise RuntimeError('remote stage HOST_ERROR '+json.dumps(data))
            return data
        time.sleep(30)


def launch(arm,stage,attempt,*,resume=None,smoke=None,model=None,source=TRAIN_SOURCE):
    available_gpu();budget(force=True);current=instance(force=True)
    boot=datetime.fromisoformat(current['lastStartTimestamp'])
    remaining=28800-(datetime.now(timezone.utc)-boot).total_seconds()
    if stage=='smoke':limit=1800
    else:
        # One measured complete smoke wall+its managed pre/post work is reserved
        # for checkpoint/readback/resource finalization. Resource guard only.
        smoke_wall=state['arms'][arm]['smoke']['wall_s']
        margin=math.ceil(smoke_wall+state['arms'][arm]['smoke_managed_overhead_s'])
        limit=min(21600,math.floor(remaining-margin))
        if limit<margin:
            event('wait_existing_VM_lifetime',arm=arm,remaining_s=remaining,measured_finalization_margin_s=margin)
            while instance(force=True)['status']=='RUNNING':budget();time.sleep(30)
            available_gpu()
            return launch(arm,stage,attempt,resume=resume,smoke=smoke,model=model,source=source)
    argv=[PY,'experiments/2026-10-16-beamact3/train_shared.py','--arm',arm,'--stage',stage,'--attempt',str(attempt),'--max-wall-s',str(limit)]
    if resume:argv+=['--resume',resume,'--smoke-summary',smoke]
    if model:argv+=['--model',model]
    src=BASE+'/src/'+source
    receipt=query('gpu',f'''import json,os,pathlib,subprocess
src={src!r};out=pathlib.Path({OUT!r})/{arm!r};out.mkdir(exist_ok=True)
env={{**os.environ,'PYTHONPATH':src,'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'4'}}
with (out/{stage+'-attempt'+str(attempt)+'-launch.log'!r}).open('x') as log:
 p=subprocess.Popen({argv!r},cwd=src,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
print(json.dumps(dict(pid=p.pid,source=src,argv={argv!r})))
''')
    event('stage_launch',arm=arm,stage=stage,attempt=attempt,limit_s=limit,receipt=receipt)


def final_training(arm):
    armstate=state['arms'].setdefault(arm,{})
    if arm=='B':launch(arm,'smoke',1)
    started=time.monotonic();smoke=wait_stage(arm,'smoke',1)
    if not(smoke.get('complete') and smoke.get('readback_verified') and smoke['steps_completed']==300):
        raise RuntimeError('matching smoke incomplete')
    armstate['smoke']=smoke
    sup=smoke['supervisor']
    armstate['smoke_managed_overhead_s']=max(0.,sup['wall_s']-smoke['wall_s'])
    event('smoke_readback_pass',arm=arm,steps=300,wall_s=smoke['wall_s'])
    checkpoint=smoke['checkpoint'];smokepath=OUT+'/'+arm+'/smoke-attempt1/summary.json'
    attempt=1;total_wall=0.
    while True:
        launch(arm,'main',attempt,resume=checkpoint,smoke=smokepath)
        result=wait_stage(arm,'main',attempt)
        if result['status']=='HOST_LIFETIME_INTERRUPTION':
            event('HOST_ERROR',arm=arm,stage='main',attempt=attempt,reason='configured8h host lifetime; incomplete attempt excluded')
            # Exact latest atomic checkpoint, not a model selected by outcomes.
            recovered=query('gpu',f'''import json,pathlib
r=pathlib.Path({OUT!r})/{arm!r};rows=[]
for p in r.glob('main-attempt*/step-*/resume.json'):
 if (p.parent/'actor/SHA256.json').exists() and (p.parent/'optimizer.pt').exists():rows.append((json.loads(p.read_text())['step'],str(p.parent)))
print(json.dumps(dict(latest=max(rows) if rows else None)))
''')
            if recovered['latest']:checkpoint=recovered['latest'][1]
            attempt+=1;continue
        armstate.setdefault('main_attempts',[]).append(result);total_wall+=result.get('wall_s') or 0.
        if total_wall>7*3600:raise RuntimeError('one-arm finite cumulative training budget exhausted')
        if result.get('complete') and result.get('readback_verified') and result['steps_completed']==20000:
            armstate['model']=result['checkpoint']+'/actor';armstate['training_summary']=OUT+'/'+arm+'/main-attempt'+str(attempt)+'/summary.json'
            event('fixed20000_complete',arm=arm,model=armstate['model'],attempts=attempt,train_wall_s=total_wall)
            return
        if result.get('status') not in ('WALL_CAP','interrupted') or not result.get('readback_verified'):
            raise RuntimeError('incomplete main without verified restart checkpoint')
        checkpoint=result['checkpoint'];attempt+=1
        event('resource_window_checkpoint',arm=arm,checkpoint=checkpoint,step=result['steps_completed'])


def transfer(arm):
    budget(force=True)
    target=OUT+'/'+arm+'/model-v1';model=state['arms'][arm]['model']
    # Only model+adapter, streamed through Mac memory; no dataset/raw transfer.
    run([*ssh('cpu'),'mkdir -p '+shlex.quote(OUT+'/'+arm)+' && test ! -e '+shlex.quote(target)+' && mkdir '+shlex.quote(target)])
    def relay_code(directory,send):
        return f'''import datetime,json,os,pathlib,subprocess
p=pathlib.Path({BASE!r})/'leases'/{'beamact3-'+arm+'-transfer.json'!r}
with p.open('x') as f:json.dump(dict(task='beamact3-{arm}-transfer',pid=os.getpid(),start=datetime.datetime.now(datetime.timezone.utc).isoformat(),expected_end='finite model stream',concurrency=0),f)
try:subprocess.run({['tar','-C',directory,'-cf' if send else '-xf','-','.']!r},check=True)
finally:p.unlink()
'''
    sender=subprocess.Popen([*ssh('gpu'),'python3 -c '+shlex.quote(relay_code(model,True))],stdout=subprocess.PIPE)
    receiver=subprocess.Popen([*ssh('cpu'),'python3 -c '+shlex.quote(relay_code(target,False))],stdin=sender.stdout)
    sender.stdout.close()
    if receiver.wait() or sender.wait():raise RuntimeError('model stream failed')
    result=query('cpu',f'''import hashlib,json,pathlib
r=pathlib.Path({target!r});h=json.loads((r/'SHA256.json').read_text());assert all(hashlib.sha256((r/k).read_bytes()).hexdigest()==v for k,v in h.items())
print(json.dumps(dict(files=len(h),model_sha256=h['model.safetensors'])))
''')
    state['arms'][arm]['cpu_model']=target;event('model_transfer_verified',arm=arm,**result)


def evaluate_cpu(arm):
    budget(force=True)
    src=state['analysis_cpu_source'];model=state['arms'][arm]['cpu_model'];dest=OUT+'/'+arm+'/heldout20-v1'
    command='cd '+shlex.quote(src)+' && PYTHONPATH=. '+BASE+'/ugrp/.venv-sim/bin/python experiments/2026-10-16-beamact3/run_eval.py --arm '+arm+' --model '+shlex.quote(model)+' --output '+shlex.quote(dest)
    log=(HERE/(arm+'-cpu-supervisor.log')).open('x')
    proc=subprocess.Popen([*ssh('cpu'),command],stdout=log,stderr=subprocess.STDOUT)
    state['arms'][arm]['cpu_relay_pid']=proc.pid;event('student20_launch',arm=arm,cpu_source=src)
    return proc,log


def offline(arm):
    # Same frozen head module; analysis source adds only paired role probes.
    launch(arm,'offline',1,model=state['arms'][arm]['model'],source=state['analysis_gpu_sha'])
    result=wait_stage(arm,'offline',1)
    if result['supervisor_status']!='complete':raise RuntimeError('offline incomplete')
    state['arms'][arm]['offline_summary']=OUT+'/'+arm+'/offline-attempt1/summary.json'
    event('offline_complete',arm=arm)


def main():
    p=__import__('argparse').ArgumentParser();p.add_argument('--analysis-sha',required=True);a=p.parse_args()
    state['analysis_gpu_sha']=a.analysis_sha;state['analysis_cpu_source']=BASE+'/src/'+a.analysis_sha
    save();budget(force=True);instance(force=True)
    cpu_jobs=[]
    for arm in ('A','B'):
        final_training(arm)
        offline(arm)
        transfer(arm)
        cpu_jobs.append((arm,*evaluate_cpu(arm)))
    for arm,proc,log in cpu_jobs:
        while proc.poll() is None:budget();save();time.sleep(30)
        log.close()
        if proc.returncode:raise RuntimeError('CPU evaluation failed for '+arm)
        result=query('cpu',f'''import json,pathlib
x=json.loads(pathlib.Path({OUT+'/'+arm+'/heldout20-v1/summary.json'!r}).read_text())
print(json.dumps({{k:x[k] for k in ('n','N','complete','funnel','reason_distribution','failure_stage_distribution')}}))
''')
        state['arms'][arm]['student20']=result;event('student20_recount',arm=arm,**result)
    state['status']='training_offline_student_complete';event('finite_controller_complete')


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        if state['status']!='BUDGET':state['status']='ERROR'
        event('controller_error',error_type=type(exc).__name__,error=str(exc));raise
