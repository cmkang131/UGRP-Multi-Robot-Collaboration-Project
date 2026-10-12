"""Finite serial offline cohort with shared timing lock and immutable split seal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from scripts import agent_lock


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--split', choices=['development', 'confirmation'], required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = ROOT/'tests/fixtures/rgb_communication_audit/source_manifest.json'
    source = json.loads(manifest.read_text())['additional_bundles']['self-map-own-prob-v1']['files_sha256']
    for file, expected in source.items():
        if hashlib.sha256((ROOT/file).read_bytes()).hexdigest() != expected:
            raise ValueError('SOURCE_NOT_FROZEN: '+file)
    seal = out/'development_fixed.json'
    if args.split == 'confirmation':
        fixed = json.loads(seal.read_text())
        if fixed['source_sha'] != sha or fixed['files_sha256'] != source:
            raise ValueError('DEVELOPMENT_SEAL_MISMATCH')
    lock = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='claude/ego-wall-map',
                              purpose='PR405 offline probabilistic map replay timing', pid=os.getpid(),
                              expected_minutes=120, timing_sensitive=True)
    rows = []
    try:
        seeds = (911,) if args.split == 'development' else (912, 913)
        for condition in ('prob', 'rbpf30', 'rbpf100'):
            for seed in seeds:
                for robot in ('r1', 'r2'):
                    name = f's{seed}-{robot}'
                    cmd = [sys.executable, str(HERE/'own_map_prob_replay.py'), '--case', name,
                           '--condition', condition, '--output', str(out)]
                    started = time.time()
                    print(f'START {condition} {name}', flush=True)
                    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=1800)
                    row = {'condition': condition, 'case': name, 'command': cmd, 'exit_code': result.returncode,
                           'started_unix': started, 'process_wall_s': time.time()-started,
                           'stdout': result.stdout, 'stderr': result.stderr}
                    rows.append(row)
                    (out/f'{args.split}_execution.json').write_text(json.dumps({'lock': lock, 'runs': rows}, indent=2)+'\n')
                    print(result.stdout, end='', flush=True)
                    if result.returncode:
                        print(result.stderr, file=sys.stderr, flush=True)
                        raise RuntimeError(f'OFFLINE_CASE_FAILED: {condition}/{name}')
        if args.split == 'development':
            seal.write_text(json.dumps({'source_sha': sha, 'files_sha256': source, 'conditions': ['prob','rbpf30','rbpf100'],
                                       'particles': [30,100], 'seed': 20261006, 'criteria': 'README 17.1 unchanged',
                                       'completed': rows, 'tuning': 'none; same fixed configuration for confirmation'}, indent=2)+'\n')
    finally:
        agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')


if __name__ == '__main__':
    main()
