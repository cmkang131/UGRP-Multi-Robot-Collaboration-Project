#!/usr/bin/env python3
"""pairact-r1 P5 rows -> per-arm n/N_eff, funnel, correction audit and the registered hybrid switch.

Eval-only, CPU. Input rows come from scripts/pairact_p5_rows.py (root -r-c5). Writes one new JSON.

  python scripts/pairact_r1_p5_decide.py --prereg experiments/2026-10-21-pairact-r1/PAIRACT_R1_EVAL_PREREG_DRAFT.json \
    --rows RUN-report/p5-rows.jsonl [--freeze experiments/2026-10-21-pairact-r1/CHECKPOINT_FREEZE.json] \
    --out RUN-report/p5-decision.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import pairact_r1_plan as plan


def decide(prereg_path, rows_path, freeze_path=None):
    prereg = json.loads(Path(prereg_path).read_text())
    header, episodes = plan.read_rows(rows_path)
    sha = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
    if header.get('prereg_sha256') != sha:
        raise ValueError('rows header prereg_sha256 differs from --prereg')
    sd = prereg['seeds']
    seeds = list(range(int(sd['first']), int(sd['last']) + 1))
    arms = [a['id'] for a in prereg['arms']]
    counts = plan.p5_counts(header, episodes, seeds=seeds, arms=arms)
    out = dict(schema='ugrp.pairact_r1.p5_decision.v1', prereg_sha256=sha, prereg_status=prereg.get('status'),
               rows_sha256=hashlib.sha256(Path(rows_path).read_bytes()).hexdigest(), counts=counts,
               hybrid=plan.hybrid_decision(counts))
    if freeze_path is not None:
        fr = json.loads(Path(freeze_path).read_text())
        out['training_tier'] = plan.train_plan(fr['collect_decision'], fr.get('result_labels', ()),
                                               fr.get('limited_bins', ()))
    n = counts['n_eff']
    out['text'] = {a: f'{a} {r["success"]}/{n}' for a, r in counts['arms'].items()}
    if prereg.get('status') != 'FROZEN':
        out['label'] = 'DRAFT prereg: table only, no verdict'
    return out


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--prereg', type=Path, required=True)
    a.add_argument('--rows', type=Path, required=True)
    a.add_argument('--freeze', type=Path)
    a.add_argument('--out', type=Path, required=True)
    args = a.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f'{args.out} exists')
    rec = decide(args.prereg, args.rows, args.freeze)
    args.out.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(dict(text=rec['text'], hybrid=rec['hybrid']['decision']), ensure_ascii=False))


if __name__ == '__main__':
    main()
