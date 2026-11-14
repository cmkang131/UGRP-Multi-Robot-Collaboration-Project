"""Finite marker-only two-robot UTC check; SSH prompts stay in the user's console."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
if (Path(__file__).resolve().parents[1]/'harness').is_dir():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from harness.utc_clock import NtpUtcClock,SCHEMA,ClockError
except ModuleNotFoundError:
    from utc_clock import NtpUtcClock,SCHEMA,ClockError

def receive(stream,out):
    for line in stream:
        try:out.put(json.loads(line))
        except ValueError:out.put({'phase':'ERROR','error':'Non-JSON agent output'})
    out.put({'phase':'ERROR','error':'SSH agent closed'})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-directory',type=Path,required=True)
    parser.add_argument('--identity-file',required=True)
    parser.add_argument('--source-revision',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    module=root/'utc_clock.py'
    if not module.exists():module=root.parent/'harness'/'utc_clock.py'
    check='utc-check-'+uuid.uuid4().hex
    out=args.run_directory/check;out.mkdir()
    binary=Path(os.environ['SystemRoot'])/'System32'/'OpenSSH'
    peers=[('ras1','192.168.137.186'),('ugrp1','192.168.137.218')]
    sessions=[];result={'status':'running','marker_only':True,'robot_motion_commands':0,'events':[],
        'source_revision':args.source_revision,'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [module,root/'utc_reservation_agent.py',root/'masterpi_control.py',Path(__file__)]}}
    try:
        for name,address in peers:
            remote=f'/home/{name}/ugrp_clock_logs/{args.run_directory.name}'
            opts=['-o','StrictHostKeyChecking=yes','-o',f'HostKeyAlias={name}.local','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3','-o','IdentitiesOnly=yes','-i',args.identity_file]
            print('Copy reservation support to '+name+'; enter SSH password if asked.',flush=True)
            p=subprocess.run([str(binary/'scp.exe'),*opts,str(module),str(root/'utc_reservation_agent.py'),str(root/'masterpi_control.py'),f'{name}@{address}:{remote}/'])
            if p.returncode:raise ClockError('Failed to deploy support to '+name)
            print('Connect reservation agent '+name,flush=True)
            proc=subprocess.Popen([str(binary/'ssh.exe'),*opts,'-T',f'{name}@{address}',f"python3 -u '{remote}/utc_reservation_agent.py' --participant '{name}' --output '{remote}/{check}'"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
            mailbox=queue.Queue();threading.Thread(target=receive,args=(proc.stdout,mailbox),daemon=True).start()
            session=(name,proc,mailbox,remote,opts);sessions.append(session)
            event=mailbox.get(timeout=120);result['events'].append(event)
            if event.get('phase')!='WELCOME':raise ClockError('Agent not ready: '+json.dumps(event))
        clock=NtpUtcClock()
        try:result['coordinator_clock']=clock.synchronize()
        finally:result['coordinator_ntp_samples']=list(clock.samples)
        target=clock.now()+10
        prepare={'schema':SCHEMA,'phase':'PREPARE','action_id':check,'participants':[x[0] for x in peers],'execute_at_utc_s':target}
        for name,proc,mailbox,remote,opts in sessions:
            proc.stdin.write(json.dumps(prepare)+'\n');proc.stdin.flush()
        readies=[]
        for name,proc,mailbox,remote,opts in sessions:
            event=mailbox.get(timeout=4);result['events'].append(event)
            if event.get('phase')!='READY':raise ClockError('Preparation failed')
            if event.get('participant')!=name or event.get('action_id')!=check or event.get('execute_at_utc_s')!=target:raise ClockError('Readiness mismatch')
            readies.append(name)
        commit={**prepare,'phase':'COMMIT','ready_participants':readies}
        for name,proc,mailbox,remote,opts in sessions:
            proc.stdin.write(json.dumps(commit)+'\n');proc.stdin.flush()
        fired=[]
        for name,proc,mailbox,remote,opts in sessions:
            event=mailbox.get(timeout=20);result['events'].append(event)
            if event.get('phase')!='FIRED':raise ClockError('Reserved marker failed: '+json.dumps(event))
            fired.append(event);print(json.dumps(event),flush=True)
        result['status']='reserved_markers_completed'
        result['execute_at_utc_s']=target
        result['reported_utc_issue_difference_ms']=abs(fired[0]['issued_at_utc_s']-fired[1]['issued_at_utc_s'])*1000
        result['physical_simultaneity_verified']=False
        result['limitations']='Local UTC logs do not measure true physical simultaneity; each clock retains NTP error.'
    except Exception as exc:
        result['status']='failed';result['error']=str(exc);print('UTC CHECK FAILED: '+str(exc),flush=True)
    finally:
        for name,proc,mailbox,remote,opts in sessions:
            if proc.poll() is None:
                try:proc.stdin.write(json.dumps({'phase':'ABORT'})+'\n');proc.stdin.flush()
                except (OSError,ValueError):pass
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=3)
            if proc.stdin:proc.stdin.close()
            if proc.stdout:proc.stdout.close()
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Saved: '+str(out),flush=True)
    return 0 if result['status']=='reserved_markers_completed' else 1

if __name__=='__main__':raise SystemExit(main())
