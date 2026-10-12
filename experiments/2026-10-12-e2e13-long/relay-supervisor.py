"""Own finite Mac relay and VM2 tunnel; Keychain credentials remain in memory."""
from pathlib import Path
import argparse,datetime,json,os,signal,subprocess,sys,time

p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);a=p.parse_args()
out=a.state;out.mkdir(parents=True,exist_ok=True);children=[];logs=[]
deadline=datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=7.5)
seconds=int((deadline-datetime.datetime.now(datetime.timezone.utc)).total_seconds())
def stop(*_):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
    children.append(subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())]))
    log=(out/'relay.log').open('x');logs.append(log)
    children.append(subprocess.Popen([sys.executable,'-m','scripts.s4_proxy_relay',
        '--output',str(out/'relay'),'--seconds',str(seconds),'--session-profile','e2e13_7h_v1',
        '--idempotent','--listen-port','18396','--remote-port','18393',
        '--driver-profile','study_gemma4_31b_v1','--upstream','openrouter_v1',
        '--gemma-state',str(out/'upstream'),'--decider','off'],stdout=log,stderr=subprocess.STDOUT))
    log=(out/'tunnel-supervisor.log').open('x');logs.append(log)
    children.append(subprocess.Popen([sys.executable,'-m','scripts.remote_reverse_tunnel',
        '--host','azure2','--remote-port','18393','--local-port','18396',
        '--deadline-utc',deadline.isoformat(),'--max-session-hours','7.5',
        '--output',str(out/'tunnel'),'--reconnect'],stdout=log,stderr=subprocess.STDOUT))
    (out/'relay-processes.json').write_text(json.dumps(dict(owner_pid=os.getpid(),children=[p.pid for p in children],
        deadline_utc=deadline.isoformat(),host='azure2',local_port=18396,remote_port=18393),indent=2)+'\n')
    while all(p.poll() is None for p in children) and datetime.datetime.now(datetime.timezone.utc)<deadline:time.sleep(1)
finally:
    for p in children:
        if p.poll() is None:p.terminate()
    for p in children:
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:p.kill();p.wait()
    for stream in logs:stream.close()
