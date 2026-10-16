"""Foreground read-only monitor on Mac; no VM starts, stops or task deadline."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ip', required=True)
    p.add_argument('--tag', required=True)
    p.add_argument('--history', type=Path, required=True)
    a = p.parse_args()
    assert Path(a.tag).name == a.tag and a.tag not in ('.', '..')
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ProxyCommand=none',
        '-o', 'HostName='+a.ip, '-o', 'HostKeyAlias=gcp3', '-o', 'StrictHostKeyChecking=yes', 'gcp3']
    command = 'python3 /home/ugrp/ugrp-sim/ops-reviews/warp8/watch_group-warp8b.py --tag ' + a.tag
    slow_since = None
    while True:
        try:
            output = subprocess.check_output(ssh + [command], text=True, stderr=subprocess.PIPE)
            sample = json.loads(output)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
            print(json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                monitor_error=type(error).__name__, detail=str(error))), flush=True)
            time.sleep(60)
            continue
        progress = sample['progress']
        speed = progress.get('per_world_wall_SIM')
        now = dt.datetime.fromisoformat(sample['utc'])
        slow_since = (slow_since or now) if speed is not None and speed > 9. else None
        if slow_since and (now-slow_since).total_seconds() >= 600:
            warning = dict(utc=sample['utc'], reason_category='SPEED_WARNING', blocked_object='host:gcp3',
                min_gap_m=None, continuous_over9_since=slow_since.isoformat(), sample=sample,
                action='record only; in-progress run preserved; no physics changes')
            a.history.with_suffix('.speed-warning.json').write_text(json.dumps(warning, indent=2)+'\n')
        with a.history.open('a') as f:
            f.write(json.dumps(sample)+'\n')
        print(json.dumps(dict(utc=sample['utc'], tag=a.tag, progress=progress,
            raw_statuses=sample['raw_statuses'], outcomes=sample['outcomes'], error=sample['error'],
            first30=sample['first30'], receipt=sample['receipt'])), flush=True)
        if sample['receipt'] is not None:
            return
        # Sampling interval only; it never limits planning, SIM time or VM uptime.
        time.sleep(60)


if __name__ == '__main__':
    main()
