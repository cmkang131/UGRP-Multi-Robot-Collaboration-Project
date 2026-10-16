from pathlib import Path
import datetime as dt,fcntl,hashlib,json,os,socket,subprocess,time
r=Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/warp8';sha='175281c8922453465f8bf32707e22988e78b8812';src=r/'src'/sha
assert socket.gethostname().split('.')[0]=='ugrp-act-l4-gcp3'
plan=json.loads((ops/'release-batch-plan-current.json').read_text());group=next(g for g in plan['groups'] if g['tag']=='releaseA-s1-r1');assert plan['source_sha']==sha and group['N']==len(group['indices'])==14
session=json.loads((ops/'release-host-start.json').read_text());assert session['source_sha']==sha and session['max_run_duration_s']==28800 and dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(session['cleanup_deadline'])
lock=(r/'leases/.warp9-claim.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
 assert not list((r/'leases').glob('*.json'))
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
 assert subprocess.run(['pgrep','-f','[n]vidia-cuda-mps'],capture_output=True).returncode==1
 assert subprocess.check_output(['systemctl','is-active','ugrp-idle-guard.timer'],text=True).strip()=='active'
 assert subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()==sha
 assert not subprocess.check_output(['git','-C',str(src),'status','--porcelain','--untracked-files=no'])
 for pid in (1743,1745):
  p=Path('/proc',str(pid),'cmdline')
  assert not p.exists() or b'beam40-r2' not in p.read_bytes()
 table=Path(plan['rejection_table']);assert table.is_absolute() and table.is_file()
 refs=Path(group['references']);assert hashlib.sha256(refs.read_bytes()).hexdigest()==group['references_sha256']
 cases=Path(plan['cases']);assert hashlib.sha256(cases.read_bytes()).hexdigest()==plan['cases_sha256']
 old=ops/'host-start.json';archive=ops/'host-start.beam-session.json'
 with archive.open('xb') as f:f.write(old.read_bytes())
 temp=ops/'host-start.new.json';temp.write_text(json.dumps(session,indent=2)+'\n');temp.replace(old)
 tag=group['tag'];assert not (r/'runs/warp8'/tag).exists()
 cmd=['python3',str(src/'experiments/2026-10-16-warp8/run_batch.py'),'--source-sha',sha,'--tag',tag,'--flow','release','--cases',str(cases),'--indices',','.join(map(str,group['indices'])),'--references',str(refs),'--canonical-xml',group['canonical_xml'],'--rejection-table',str(table),'--full-active-dof-workspace-v1']
 with (ops/(tag+'.driver.log')).open('x') as log:child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 lease=r/'leases'/('warp8-'+tag+'.json')
 # Resource-only launch handshake, bounded by the existing driver's10s monitor interval.
 until=time.monotonic()+10
 while not lease.exists() and child.poll() is None and time.monotonic()<until:time.sleep(.1)
 assert lease.exists() and child.poll() is None
 result={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'group':group,'session':session,'driver_PID':child.pid,'lease':json.loads(lease.read_text()),'GPU_before_launch':'none','MPS':'off','source_sha':sha,'actual_command':cmd,'submitter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'archive_original_host_start':str(archive)}
 (ops/'release-first-submit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
finally:fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
