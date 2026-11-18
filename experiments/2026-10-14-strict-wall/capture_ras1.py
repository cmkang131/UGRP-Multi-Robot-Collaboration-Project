import base64,hashlib,json,signal,socket,sys,threading,time,urllib.request
from pathlib import Path
import masterpi_control as c
name=sys.argv[1]
if not name.startswith('strictwall-') or not name.replace('-','').isalnum():raise ValueError('Invalid recording ID')
root=Path(name);root.mkdir(exist_ok=False)
expected={1:2000,3:858,4:2320,5:1320,6:1900}
lease=c.acquire_actuator_lease(owner='codex:ras1-strict-wall');motors=c.MotorTransport();c._active_motor_transport=motors
signal.signal(signal.SIGINT,c._signal_handler);signal.signal(signal.SIGTERM,c._signal_handler);signal.signal(signal.SIGHUP,c._signal_handler)
def timeout(*_):raise TimeoutError('45 second finite capture budget')
signal.signal(signal.SIGALRM,timeout);signal.alarm(45)
stop=threading.Event();errors=[];frames=[];commands=[];lock=threading.Lock()
emit_lock=threading.Lock()
def emit(v):
 with emit_lock:print('EVENT '+json.dumps(v),flush=True)
def sampler():
 try:
  while not stop.is_set():
   start=time.monotonic()
   with urllib.request.urlopen('http://127.0.0.1:8080/snapshot',timeout=3) as f:raw=f.read()
   if not raw.startswith(b'\xff\xd8'):raise RuntimeError('Invalid JPEG')
   with lock:
    index=len(frames)+1;name=f'frame-{index:03d}.jpg';t=time.monotonic()
    (root/name).write_bytes(raw)
    row=dict(physical_host=socket.gethostname(),frame_id=index,image=name,monotonic_s=t,wall_time_s=time.time(),commanded_pose=c.load_pose_state(),sha256=hashlib.sha256(raw).hexdigest())
    frames.append(row)
    with (root/'frames.jsonl').open('a') as out:out.write(json.dumps(row)+'\n')
   # Images stay on-device until the finite capture completes; no large JSON transport.
   pass
   stop.wait(max(0.,.15-(time.monotonic()-start)))
 except BaseException as error:errors.append(repr(error));stop.set()
worker=threading.Thread(target=sampler,daemon=True)
try:
 c.stop_all(motors,context='strict-initial')
 if c.load_pose_state()!=expected:raise RuntimeError('Unexpected camera posture')
 samples=[];probe=None
 for _ in range(12):
  try:
   candidate=c.probe_hardware()
   if any(abs(candidate['battery_mv']-v['battery_mv'])<=500 for v in samples):probe=candidate;break
   samples.append(candidate)
  except Exception:pass
  time.sleep(.03)
 if probe is None:raise RuntimeError('No consistent valid battery readings')
 emit(dict(kind='begin',probe=probe,pose=expected))
 worker.start();time.sleep(1.)
 plan=['left']*6+['right']*12+['left']*6
 for i,direction in enumerate(plan):
  if errors or c.load_pose_state()!=expected:raise RuntimeError('Camera or sampler state changed '+str(errors))
  began=time.monotonic()
  receipt=dict(index=i+1,started_monotonic_s=began,direction=direction,speed=35,duration_s=.06,command=dict(kind='mecanum',forward=0.,left=.35 if direction=='left' else -.35,turn=0.,duration_s=.06))
  c._run_motion(motors,c.drive_speeds(direction,35),.06)
  receipt['stopped_monotonic_s']=time.monotonic();commands.append(receipt)
  with (root/'commands.jsonl').open('a') as out:out.write(json.dumps(receipt)+'\n')
  emit(dict(kind='command',row=receipt));time.sleep(.22)
 time.sleep(1.)
finally:
 c.stop_all(motors,context='strict-finally');stop.set()
 if worker.is_alive():worker.join(timeout=4)
 signal.alarm(0);lease.close()
 result=dict(physical_host=socket.gethostname(),frames=len(frames),commands=len(commands),errors=errors,stopped=True,pose=c.load_pose_state())
 (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');emit(dict(kind='stopped',result=result))
