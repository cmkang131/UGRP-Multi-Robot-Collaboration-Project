from pathlib import Path
import subprocess,sys,time,signal,json,os
out=Path(__file__).resolve().parent;deadline=time.time()+27000;children=[];logs=[]
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
 log=(out/'relay.log').open('x');logs.append(log)
 cmd=[sys.executable,'-m','scripts.s4_proxy_relay','--output',str(out/'relay'),'--seconds','27000','--idempotent','--listen-port','18394','--remote-port','18393','--driver-profile','study_gemma4_31b_v1','--upstream','openrouter_v1','--gemma-state',str(out/'upstream')]
 children.append(subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,cwd=out/'relay-source'))
 (out/'relay-owner.json').write_text(json.dumps(dict(pid=os.getpid(),relay_pid=children[0].pid,deadline_unix=deadline,local_port=18394,remote_port=18393)))
 while time.time()<deadline and children[0].poll() is None:
  log=(out/'tunnel.log').open('a');logs.append(log)
  cmd=['ssh','-T','-n','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','ExitOnForwardFailure=yes','-o','ForwardAgent=no','-o','ControlMaster=no','-o','ControlPath=none','-R','127.0.0.1:18393:127.0.0.1:18394','azure3',f'sleep {max(1,int(deadline-time.time()))}']
  tunnel=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT);children.append(tunnel)
  with (out/'tunnel-events.jsonl').open('a') as f:f.write(json.dumps(dict(pid=tunnel.pid,unix=time.time(),deadline_unix=deadline))+'\n')
  while tunnel.poll() is None and time.time()<deadline and children[0].poll() is None:time.sleep(1)
  if tunnel.poll() is None:tunnel.terminate();tunnel.wait(timeout=10)
  time.sleep(3)
finally:
 for p in children:
  if p.poll() is None:p.terminate()
 for p in children:
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait()
 for f in logs:f.close()
