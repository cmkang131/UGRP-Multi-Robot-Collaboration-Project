"""One read-only status sample on gcp3; no process control or simulator imports."""
import argparse
from collections import Counter
import datetime as dt
import json
from pathlib import Path
import socket
import subprocess


def read(path, default=None):
    try:
        if path.exists():
            return json.loads(path.read_text())
        if path.with_name(path.name + '.zst').exists():
            return json.loads(subprocess.check_output(['zstd', '-qdc', str(path) + '.zst']))
        return default
    except (FileNotFoundError, subprocess.CalledProcessError):
        return default


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--tag', required=True)
    a = p.parse_args()
    assert Path(a.tag).name == a.tag and a.tag not in ('.', '..')
    assert socket.gethostname().split('.')[0] == 'ugrp-act-l4-gcp3'
    root = Path('/home/ugrp/ugrp-sim')
    run = root / 'runs/warp8' / a.tag
    progress = read(run / 'progress.json', {})
    summary = read(run / 'summary.json', {})
    progress.pop('world_sim_s', None)
    progress.pop('timing', None)
    statuses, outcomes, phases = Counter(), Counter(), Counter()
    audits = []
    for folder in sorted(run.glob('world-*')):
        if not folder.is_dir():
            continue
        raw = read(folder / 'raw/result.json', {})
        statuses[raw.get('status', 'missing')] += 1
        outcomes[str(raw.get('release_outcome'))] += 1
        if raw.get('status') == 'complete':
            audits.append(dict(world=folder.name, input_audit=raw.get('input_audit'),
                release_success=raw.get('release_success'), outcome=raw.get('release_outcome')))
        for trace in (folder / 'raw').glob('teacher-*.jsonl*'):
            if trace.suffix == '.zst':
                if trace.with_suffix('').exists():
                    continue
                lines = subprocess.check_output(['zstd', '-qdc', str(trace)]).splitlines()
            else:
                with trace.open('rb') as f:
                    f.seek(max(0, trace.stat().st_size - 65536))
                    lines = f.read().splitlines()
            try:
                row = json.loads(lines[-1])
                phases[str(row.get('teacher_phase') or row.get('phase') or row.get('teacher', {}).get('phase'))] += 1
            except (IndexError, json.JSONDecodeError):
                phases['unflushed'] += 1
    print(json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), tag=a.tag,
        progress=progress, status=summary.get('status'), error_type=summary.get('error_type'),
        error=summary.get('error'), receipt=read(run.with_suffix('.receipt.json')),
        first30=read(run / 'first30-speed.json'), raw_statuses=statuses, outcomes=outcomes,
        last_teacher_phases=phases, terminal_world_audits=audits,
        leases={p.name:read(p) for p in (root / 'leases').glob('*.json')},
        GPU=subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,utilization.gpu',
            '--format=csv,noheader,nounits'], text=True).strip(),
        disk_free_bytes=__import__('shutil').disk_usage(root).free)))


if __name__ == '__main__':
    main()
