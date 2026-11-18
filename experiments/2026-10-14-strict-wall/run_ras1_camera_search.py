from pathlib import Path
import json,hashlib,os,sys,subprocess,time,shlex,threading,tarfile,shutil
import argparse
SRC=Path(__file__).resolve().parents[2];sys.path.insert(0,str(SRC))
p=argparse.ArgumentParser(description='Finite ras1 multi-axis camera search; requires PR405 runtime and localhost ustreamer.')
p.add_argument('--host',default='ras1@ras1.local');p.add_argument('--output',type=Path,required=True)
p.add_argument('--runtime',default='/home/ras1/MasterPi/tools/.ugrp_versions/strict-wall-20261014')
p.add_argument('--pans',type=int,nargs='+',default=[500,750,1000,1250,1500,1750,2000,2250,2500])
p.add_argument('--max-views',type=int,default=30)
p.add_argument('--lock-root',type=Path,default=Path.home()/'projects/ugrp/outputs/agent-locks');args=p.parse_args()
from scripts import agent_lock
from harness.wall_camera_search import WallCameraSearch
runid='activeview-'+time.strftime('%Y%m%d-%H%M%S');out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
ssh=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=ras1.local','-o','ConnectTimeout=5','-o','ServerAliveInterval=3','-o','ServerAliveCountMax=2',args.host];runtime=args.runtime;helper=SRC/'experiments/2026-10-14-strict-wall/ras1_camera_search_server.py'
try:
 if not 1<=args.max_views<=30:raise ValueError('Hardware adapter permits at most30 views')
 pre=subprocess.check_output(ssh+['hostname; cd '+shlex.quote(runtime)+' && sha256sum masterpi_control.py poses.py && curl -fsS --max-time 5 http://127.0.0.1:8080/state'],text=True,timeout=12)
except Exception as error:
 (out/'RUN_META.json').write_text(json.dumps(dict(classification='dev',outcome='HOST_ERROR',stage='preflight',frames=0,camera_commands_issued=False,chassis_commands_issued=False,error=repr(error)),indent=2)+'\n')
 raise
assert all(s in pre for s in ('ras1','ba7e8c36d92539c8393f3e4f4976f75fde6e5635de06c4d5ad3f411721809b15','91a8876714171a0fcabbd40cbfb49d7d83fb91ad0cc50e7a15d10ae18491cc4e','encoder'))
(out/'preflight.txt').write_text(pre)
subprocess.run(ssh+['cat > '+shlex.quote(runtime+'/camera_search_server.py')],input=helper.read_bytes(),check=True,timeout=8)
sha=subprocess.check_output(ssh+['sha256sum '+shlex.quote(runtime+'/camera_search_server.py')],text=True,timeout=5).split()[0];assert sha==hashlib.sha256(helper.read_bytes()).hexdigest()
lockroot=args.lock_root;lock=agent_lock.acquire(lockroot,owner='codex',branch='codex/strict-wall-motion-ras1',purpose='ras1 multi-axis wall camera search',pid=os.getpid(),expected_minutes=4);(out/'lock.json').write_text(json.dumps(lock,indent=2)+'\n')
streamlog=(out/'stream.log').open('wb');encoderlog=(out/'encoder.log').open('wb');remoteerr=(out/'remote-stderr.log').open('w');stream=encoder=remote=None;worker=None;errors=[]
try:
 stream=subprocess.Popen(ssh+['curl -sfN --max-time 240 http://127.0.0.1:8080/stream'],stdout=subprocess.PIPE,stderr=streamlog)
 encoder=subprocess.Popen(['/opt/homebrew/bin/ffmpeg','-hide_banner','-loglevel','warning','-nostdin','-use_wallclock_as_timestamps','1','-f','mpjpeg','-i','pipe:0','-an','-vf','setpts=PTS-STARTPTS,fps=15','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-movflags','+faststart',str(out/'camera-raw.mp4')],stdin=subprocess.PIPE,stderr=encoderlog)
 first=threading.Event()
 def copy():
  total=0
  try:
   with (out/'camera-source.mjpeg').open('wb') as f:
    while True:
     b=stream.stdout.read1(65536)
     if not b:break
     total+=len(b)
     if total>100*1024*1024:raise RuntimeError('100 MiB capture budget')
     f.write(b);encoder.stdin.write(b);encoder.stdin.flush();first.set()
  except Exception as e:errors.append(repr(e))
  finally:encoder.stdin.close()
 worker=threading.Thread(target=copy,daemon=True);worker.start()
 if not first.wait(8):raise RuntimeError('No real camera')
 remote=subprocess.Popen(ssh+['cd '+shlex.quote(runtime)+' && python3 camera_search_server.py '+shlex.quote(runid)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=remoteerr,text=True)
 planner=WallCameraSearch(start_pan=1900,pans=tuple(args.pans),max_views=args.max_views)
 def dispatch():
  # A rotation-only image does not establish triangulated walls. Continue
  # search until actual verifier evidence or the finite coverage budget ends.
  view=planner.next_view(confirmed=False,observed_floor_support=0)
  command=dict(kind='finish') if view is None else dict(kind='view',posture=view.posture,pan=view.pan)
  remote.stdin.write(json.dumps(command)+'\n');remote.stdin.flush()
 with (out/'events-local.jsonl').open('w') as log:
  for line in remote.stdout:
   if not line.startswith('EVENT '):continue
   event=json.loads(line[6:]);log.write(json.dumps(event)+'\n');log.flush()
   if event['kind']=='ready':print(json.dumps(event),flush=True);dispatch()
   elif event['kind']=='view':
    row=event['frames'][0];raw=subprocess.check_output(ssh+['cat '+shlex.quote(runtime+'/'+runid+'/'+row['image'])],timeout=8);assert hashlib.sha256(raw).hexdigest()==row['sha256'];(out/row['image']).write_bytes(raw)
    print(json.dumps(dict(view=event['count'],posture=row['posture'],pan=row['commanded_pose']['6'],image=row['image'])),flush=True);dispatch()
   elif event['kind'] in ('error','complete'):print(json.dumps(event),flush=True)
 assert remote.wait(timeout=5)==0,'Remote adapter failed'
 with (out/'remote-capture.tar').open('wb') as f:subprocess.run(ssh+['tar -C '+shlex.quote(runtime+'/'+runid)+' -cf - .'],stdout=f,stderr=subprocess.PIPE,check=True,timeout=15)
 extracted=out/'remote';extracted.mkdir()
 with tarfile.open(out/'remote-capture.tar') as t:t.extractall(extracted,filter='data')
 for p in extracted.iterdir():
  if p.is_file():
   target=out/p.name
   if target.exists():assert target.read_bytes()==p.read_bytes()
   else:shutil.copy2(p,target)
 rows=[json.loads(s) for s in (out/'frames.jsonl').read_text().splitlines()]
 for r in rows:assert hashlib.sha256((out/r['image']).read_bytes()).hexdigest()==r['sha256']
 result=json.loads((out/'result.json').read_text());assert result['stopped'] and not result['errors'],result
except BaseException as error:
 (out/'RUN_META.json').write_text(json.dumps(dict(classification='dev',outcome='HOST_ERROR',stage='capture_or_retrieval',complete=False,error=repr(error)),indent=2)+'\n')
 raise
finally:
 try:
  if remote and remote.poll() is None:
   try:remote.stdin.write('{"kind":"finish"}\n');remote.stdin.flush();remote.wait(timeout=25)
   except Exception:remote.terminate()
  subprocess.run(ssh+['python3 '+shlex.quote(runtime+'/masterpi_control.py')+' stop'],capture_output=True,check=True,timeout=8)
 finally:
  if stream:
   stream.terminate()
   try:stream.wait(timeout=4)
   except subprocess.TimeoutExpired:stream.kill();stream.wait()
  if worker:worker.join(timeout=5)
  if encoder:
   try:encoder.wait(timeout=10)
   except subprocess.TimeoutExpired:encoder.kill();encoder.wait()
  streamlog.close();encoderlog.close();remoteerr.close();agent_lock.release(lockroot,owner='codex')
meta=dict(classification='dev',source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SRC,text=True).strip(),capture_code_sha256=sha,physical_host='ras1',chassis_motion='none',views=result['views'],frames=len(rows),stopped=result['stopped'],errors=errors,wall_confirmation_claimed=False)
(out/'RUN_META.json').write_text(json.dumps(meta,indent=2)+'\n');print('CAPTURE_OUTPUT '+str(out),flush=True)
