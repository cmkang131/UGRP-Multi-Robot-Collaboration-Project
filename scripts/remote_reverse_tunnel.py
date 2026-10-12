"""Finite, default-off SSH reconnect compatible with S4 Mac relay ports."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import signal
import subprocess
import time
import re


def command(host, seconds, remote_port=18391, local_port=18392):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', host) or host.startswith('-'):
        raise ValueError('Invalid SSH host')
    return ['ssh', '-T', '-n', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-o', 'ExitOnForwardFailure=yes', '-o', 'ForwardAgent=no',
        '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
        '-R', f'127.0.0.1:{remote_port}:127.0.0.1:{local_port}', host, f'sleep {seconds}']


def supervise(host, deadline, output, *, reconnect=False, remote_port=18391, local_port=18392):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    count = 0
    with (output/'ssh.log').open('x') as log, (output/'events.jsonl').open('x') as events:
        while time.time() < deadline:
            count += 1
            proc = subprocess.Popen(command(host, max(1, int(deadline-time.time())), remote_port, local_port),
                                    stdout=log, stderr=subprocess.STDOUT)
            def record(event, **extra):
                events.write(json.dumps(dict(event=event, unix=time.time(), attempt=count,
                    pid=proc.pid, reconnect=reconnect, deadline_unix=deadline, host=host, **extra))+'\n')
                events.flush()
            record('START')
            try:
                while proc.poll() is None and time.time() < deadline:
                    time.sleep(1)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            record('EXIT', returncode=proc.returncode)
            if not reconnect:
                break
            time.sleep(min(10, max(0, deadline-time.time())))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='oracle-x86')
    parser.add_argument('--deadline-utc', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reconnect', action='store_true')
    parser.add_argument('--remote-port', type=int, default=18391)
    parser.add_argument('--local-port', type=int, default=18392)
    args = parser.parse_args()
    deadline = datetime.fromisoformat(args.deadline_utc.replace('Z', '+00:00'))
    if deadline.tzinfo is None or not 0 < deadline.timestamp()-time.time() <= 14400:
        raise ValueError('Explicit timezone and finite <=4h session required')
    if not all(1024 <= port <= 65535 for port in (args.remote_port, args.local_port)):
        raise ValueError('Ports must be in 1024..65535')
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    supervise(args.host, deadline.timestamp(), args.output, reconnect=args.reconnect,
              remote_port=args.remote_port, local_port=args.local_port)


if __name__ == '__main__':
    main()
