"""Default-off finite SSH reconnect loop; relay lifetime is independent of SSH."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import time
import signal
from harness.s4_live_transport import MAX_RELAY_SECONDS


def command(seconds, *, host='oracle-x86',dual_model=False):
    if host not in ('oracle-x86','azure'):raise ValueError('registered SSH host required')
    return ['ssh', '-T', '-n', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ForwardAgent=no',
        '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
        '-R', '127.0.0.1:18391:127.0.0.1:18392',
        *(['-R','127.0.0.1:18393:127.0.0.1:18394'] if dual_model else []),host,f'sleep {seconds}']


def supervise(deadline, output, *, reconnect=False, popen=subprocess.Popen,
              clock=time.time, sleep=time.sleep,host='oracle-x86',dual_model=False):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    count = 0
    with (output/'ssh.log').open('x') as log, (output/'events.jsonl').open('x') as events:
        while clock() < deadline:
            count += 1
            proc = popen(command(max(1, int(deadline-clock())),host=host,dual_model=dual_model), stdout=log, stderr=subprocess.STDOUT)
            def record(event, **extra):
                events.write(json.dumps(dict(event=event, unix=clock(), attempt=count,
                    pid=proc.pid, reconnect=reconnect, deadline_unix=deadline, **extra))+'\n')
                events.flush()
            record('START')
            try:
                while proc.poll() is None and clock() < deadline:
                    sleep(1)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            record('EXIT', returncode=proc.returncode)
            if not reconnect: break
            sleep(min(10, max(0, deadline-clock())))
    return count


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--deadline-utc', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reconnect', action='store_true')
    p.add_argument('--host',choices=('oracle-x86','azure'),default='oracle-x86')
    p.add_argument('--dual-model',action='store_true')
    a = p.parse_args()
    deadline = datetime.fromisoformat(a.deadline_utc.replace('Z', '+00:00'))
    if deadline.tzinfo is None or not 0 < deadline.timestamp()-time.time() <= MAX_RELAY_SECONDS:
        raise ValueError('explicit timezone and finite <=8h session required')
    def stop(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    supervise(deadline.timestamp(), a.output, reconnect=a.reconnect,host=a.host,dual_model=a.dual_model)


if __name__ == '__main__': main()
