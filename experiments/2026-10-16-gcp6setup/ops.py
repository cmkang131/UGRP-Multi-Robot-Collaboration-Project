"""Recorded gcp6 setup commands; no tokens, private keys, or account files recorded."""
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence'
ACCOUNT = 'kcm5781kcm5781@gmail.com'
PROJECT = 'ugrp-sim-f-1016'


def cloud(name, *args, project=PROJECT):
    if project != PROJECT:
        raise ValueError('Only the gcp6 project is allowed')
    command = ['gcloud', *args, '--account', ACCOUNT, '--project', project, '--quiet', '--format=json']
    started = time.time()
    result = subprocess.run(command, capture_output=True, text=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    record = dict(command=command, started_utc=datetime.datetime.fromtimestamp(started, datetime.timezone.utc).isoformat(),
                  elapsed_s=time.time()-started, returncode=result.returncode, stderr=result.stderr)
    try:
        payload = json.loads(result.stdout)
        (EVIDENCE / (name+'.json')).write_text(json.dumps(payload, indent=2)+'\n')
    except json.JSONDecodeError:
        payload = result.stdout
        (EVIDENCE / (name+'.txt')).write_text(payload)
    (EVIDENCE / (name+'-command.json')).write_text(json.dumps(record, indent=2)+'\n')
    print(name, result.returncode, round(record['elapsed_s'], 2), flush=True)
    if result.returncode:
        print(result.stderr, flush=True)
        raise RuntimeError(name)
    return payload


if __name__ == '__main__':
    cloud(sys.argv[1], *sys.argv[2:])
