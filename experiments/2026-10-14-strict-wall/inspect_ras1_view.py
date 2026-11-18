"""Finite ras1 camera-only DEV inspection; no wheel movement command."""
import hashlib,json,signal,sys,time,urllib.request
from pathlib import Path
import masterpi_control as c

run_id=sys.argv[1]
if not run_id.startswith('viewcheck-') or not run_id.replace('-','').isalnum():raise ValueError('Invalid run id')
root=Path(run_id);root.mkdir(exist_ok=False)
lease=c.acquire_actuator_lease(owner='codex:ras1-camera-inspection')
motors=c.MotorTransport();c._active_motor_transport=motors
initial=c.load_pose_state();events=[];frames=[];errors=[];stopped=False
expected={1:2000,3:858,4:2320,5:1320,6:1900}
def emit(event):
 event['monotonic_s']=time.monotonic();events.append(event)
 with (root/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
 print('EVENT '+json.dumps(event),flush=True)
def interrupted(signum,frame):raise RuntimeError('Interrupted '+str(signum))
for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(sig,interrupted)
def move(servo,pulse):
 before=c.load_pose_state()
 if before[servo]==pulse:return
 if servo==6 and not(1100<=pulse<=1900 and abs(pulse-before[6])<=200):raise ValueError('Pan step out of bounds')
 if servo==3 and (pulse not in (740,858) or abs(pulse-before[3])>118):raise ValueError('Tilt step out of bounds')
 if servo not in (3,6):raise ValueError('Only camera joints')
 c.stop_all(motors,context='viewcheck-before-camera')
 c.ServoTransport().write_servo(servo,pulse,1.2)
 time.sleep(1.7)
 emit(dict(kind='camera_command',servo=servo,pulse=pulse,duration_s=1.2))
try:
 signal.alarm(90)
 if initial!=expected:raise ValueError('Unexpected initial posture: '+str(initial))
 c.stop_all(motors,context='viewcheck-stationary')
 probes=[];probe=None
 for _ in range(12):
  try:
   p=c.probe_hardware()
   if any(abs(p['battery_mv']-q['battery_mv'])<=500 for q in probes):probe=p;break
   probes.append(p)
  except Exception:pass
  time.sleep(.03)
 if probe is None:raise RuntimeError('No two consistent valid battery samples')
 emit(dict(kind='begin',physical_host='ras1',initial_pose=initial,probe=probe,chassis_motion='none'))
 # Two existing PR camera postures; incremental pan stays within poses.BASE_MIN/MAX.
 for tilt,pans in ((858,(1900,1700,1500,1300,1100)),(740,(1100,1300,1500,1700,1900))):
  move(3,tilt)
  for pan in pans:
   move(6,pan)
   for replicate in range(3):
    with urllib.request.urlopen('http://127.0.0.1:8080/snapshot',timeout=5) as response:raw=response.read()
    if not raw.startswith(b'\xff\xd8'):raise RuntimeError('Invalid JPEG')
    name=f'frame-{len(frames)+1:03d}.jpg';(root/name).write_bytes(raw)
    row=dict(frame_id=len(frames)+1,image=name,sha256=hashlib.sha256(raw).hexdigest(),monotonic_s=time.monotonic(),wall_time_s=time.time(),commanded_pose=c.load_pose_state(),replicate=replicate,physical_host='ras1',chassis_motion='none')
    frames.append(row)
    with (root/'frames.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    time.sleep(.2)
   emit(dict(kind='view',tilt_pulse=tilt,pan_pulse=pan,frames=len(frames)))
 move(3,initial[3])
except BaseException as error:
 errors.append(repr(error));emit(dict(kind='error',error=repr(error)))
finally:
 signal.alarm(0)
 try:c.stop_all(motors,context='viewcheck-finally');stopped=True
 finally:lease.close()
 result=dict(physical_host='ras1',frames=len(frames),errors=errors,stopped=stopped,initial_pose=initial,final_commanded_pose=c.load_pose_state(),chassis_motion='none',camera_angles_measured=False)
 (root/'result.json').write_text(json.dumps(result,indent=2)+'\n');emit(dict(kind='complete',**result))
if errors:raise SystemExit(1)
