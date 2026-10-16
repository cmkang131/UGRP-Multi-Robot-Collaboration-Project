"""Copies the small, reviewable artefacts of the cohort into the experiment folder (raw renders/runs stay in outputs/).

  render_hashes_<profile>.tsv   sha256 of every rendered JPEG (raw frames stay local)
  montage_<profile>_p20.jpg     one contact sheet: per checkpoint r1/r2 at pan 1500 and pan 2030 (look `p20`), 240x180 tiles
  runs_hashes.tsv               sha256 + line count of every cohort runs file
  analysis/                     results.json (gzip), budget.json, consistency.json copied from the analysis dir

usage: python export_small.py <cohort_dir> <experiment_dir>
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(cohort: str, exp: str):
    cohort, exp = Path(cohort), Path(exp)
    for rd in sorted(cohort.glob('render_*')):
        man = json.loads((rd / 'render_manifest.json').read_text())
        prof = man['render_profile']
        (exp / f'render_hashes_{prof}.tsv').write_text('name\tsha256\n' + ''.join(f"{r['name']}\t{r['sha256']}\n" for r in man['rows']))
        by = {r['name']: r for r in man['rows']}
        tiles = []
        for k in sorted({r['checkpoint'] for r in man['rows']}):
            row = []
            for rid, pan in (('r1', 1500), ('r1', 2030), ('r2', 1500), ('r2', 2030)):
                im = cv2.imread(str(rd / by[f'cp{k}_{rid}_p20_{pan}']['file']))
                im = cv2.resize(im, (240, 180), interpolation=cv2.INTER_AREA)
                cv2.putText(im, f'cp{k} {rid} pan{pan}', (4, 16), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1, cv2.LINE_AA)
                row.append(im)
            tiles.append(np.hstack(row))
        cv2.imwrite(str(exp / f'montage_{prof}_p20.jpg'), np.vstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 80])
    lines = ['file\tsha256\tlines\n']
    for p in sorted(cohort.glob('runs_*.jsonl')):
        lines.append(f'{p.name}\t{sha(p)}\t{sum(1 for _ in open(p))}\n')
    (exp / 'runs_hashes.tsv').write_text(''.join(lines))
    (exp / 'analysis').mkdir(exist_ok=True)
    src = cohort / 'analysis'
    with open(src / 'results.json', 'rb') as f, gzip.open(exp / 'analysis' / 'results.json.gz', 'wb', 9) as g:
        shutil.copyfileobj(f, g)
    for name in ('budget.json', 'consistency.json'):
        shutil.copy(src / name, exp / 'analysis' / name)


if __name__ == '__main__':
    main(*sys.argv[1:3])
