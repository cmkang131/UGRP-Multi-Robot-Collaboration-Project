"""crate11: verify every saved file the analysis read against each run's top-level SHA256SUMS. Usage: crate11_hashcheck.py <runs.txt> <extra_frames.json...>"""
import hashlib, json, sys
from pathlib import Path

RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
NAMES = ('plan.json', 'result.json', 'result.json.zst', 'scene.xml', 'eval-only.jsonl.zst', 'teacher-r1.jsonl.zst', 'teacher-r2.jsonl.zst')


def sums(run):
    out = {}
    for line in (RAW / run / 'SHA256SUMS').read_text().splitlines():
        h, p = line.split(None, 1)
        out[p.strip().split(f'/runs/{run}/', 1)[-1]] = h
    return out


def main(runs, frame_jsons):
    runs = list(dict.fromkeys(runs))
    checked = 0; bad = []; missing_sums = []
    per_run = {}
    for run in runs:
        s = sums(run); n = 0
        for name in NAMES:
            p = RAW / run / 'raw' / name
            if not p.exists():
                continue
            key = f'raw/{name}'
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if key not in s:
                missing_sums.append((run, key))
            elif s[key] != h:
                bad.append((run, key))
            n += 1; checked += 1
        per_run[run] = n
    frames_checked = 0
    for fj in frame_jsons:
        d = json.loads(Path(fj).read_text()); run = d['run']; s = sums(run)
        for fr in d['frames']:
            for k in ('overview', 'own'):
                rel = fr[k]['path'].split(f'{run}/', 1)[-1]
                if s.get(rel) != fr[k]['sha256']:
                    bad.append((run, rel))
                frames_checked += 1
    print(json.dumps({'runs': len(runs), 'files_checked': checked, 'frames_checked': frames_checked, 'mismatch': bad, 'not_in_sums': missing_sums, 'per_run_files': per_run}))


if __name__ == '__main__':
    main(Path(sys.argv[1]).read_text().split(), sys.argv[2:])
