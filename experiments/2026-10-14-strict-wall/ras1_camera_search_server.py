"""Camera-only NDJSON hardware adapter; all chassis commands are stop."""
import hashlib,json,signal,sys,time,urllib.request
from pathlib import Path
import masterpi_control as c

POSTURES={'ahead':{1:2000,3:858,4:2320,5:1320},'up':{1:2000,3:960,4:2410,5:1215},'down':{1:2000,3:740,4:2320,5:1320}}
run_id=sys.argv[1]
if not run_id.startswith('activeview-') or not run_id.replace('-','').isalnum():raise ValueError('Invalid run id')
root=Path(run_id);root.mkdir(exist_ok=False);lease=c.acquire_actuator_lease(owner='codex:ras1-active-wall-camera');motors=c.MotorTransport();c._active_motor_transport=motors
initial=c.load_pose_state();frames=[];errors=[];stopped=False;count=0
expected={1:2000,3:858,4:2320,5:1320,6:1900}
def emit(event):
 event['monotonic_s']=time.monotonic()
 with (root/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
 print('EVENT '+json.dumps(event),flush=True)
def interrupt(signum,frame):raise RuntimeError('signal '+str(signum))
for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupt)
def servo(s,p):
 current=c.load_pose_state()
 if current.get(s)==p:return
 if s==1 or not 500<=p<=2500:raise ValueError('Unexpected joint command')
 c.stop_all(motors,context='active-view-camera-only')
 c.ServoTransport().write_servo(s,p,1.0);time.sleep(1.3)
 emit(dict(kind='servo',servo=s,pulse=p))
def pan(target):
 current=c.load_pose_state()[6]
 while current!=target:
  current+=max(-250,min(250,target-current));servo(6,current)
def posture(target):
 current=c.load_pose_state();order=(3,4,5) if target[3]<current[3] else (5,4,3)
 for s in order:servo(s,target[s])
try:
 signal.alarm(210)
 if initial!=expected:raise ValueError('Unexpected initial pose '+str(initial))
 c.stop_all(motors,context='active-view-begin');samples=[];probe=None
 for _ in range(12):
  try:
   p=c.probe_hardware()
   if any(abs(p['battery_mv']-q['battery_mv'])<=500 for q in samples):probe=p;break
   samples.append(p)
  except Exception:pass
  time.sleep(.03)
 if probe is None:raise RuntimeError('No consistent battery probe')
 emit(dict(kind='ready',physical_host='ras1',initial_pose=initial,probe=probe,chassis_motion='none'))
 for line in sys.stdin:
  request=json.loads(line)
  if request['kind']=='finish':break
  if request['kind']!='view' or count>=30:raise ValueError('Invalid request/budget')
  name=request['posture'];target=POSTURES[name];p=int(request['pan'])
  if not 500<=p<=2500:raise ValueError('Pan bounds')
  posture(target);pan(p);time.sleep(.2);count+=1;view_frames=[]
  for replicate in range(2):
   with urllib.request.urlopen('http://127.0.0.1:8080/snapshot',timeout=4) as response:raw=response.read()
   if not raw.startswith(b'\xff\xd8'):raise RuntimeError('Invalid JPEG')
   image=f'frame-{len(frames)+1:03d}.jpg';(root/image).write_bytes(raw)
   row=dict(image=image,view=count,posture=name,commanded_pose=c.load_pose_state(),physical_host='ras1',monotonic_s=time.monotonic(),wall_time_s=time.time(),sha256=hashlib.sha256(raw).hexdigest(),replicate=replicate,chassis_motion='none')
   frames.append(row);view_frames.append(row)
   with (root/'frames.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   time.sleep(.18)
  emit(dict(kind='view',count=count,frames=view_frames))
 # Restore the known folded posture before finishing, always with wheels stopped.
 posture(initial);pan(initial[6])
except BaseException as e:errors.append(repr(e));emit(dict(kind='error',error=repr(e)))
finally:
 signal.alarm(0)
 try:c.stop_all(motors,context='active-view-finally');stopped=True
 finally:lease.close()
 result=dict(physical_host='ras1',views=count,frames=len(frames),errors=errors,stopped=stopped,initial_pose=initial,final_pose=c.load_pose_state(),chassis_motion='none')
 (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');emit(dict(kind='complete',**result))
if errors:raise SystemExit(1)
