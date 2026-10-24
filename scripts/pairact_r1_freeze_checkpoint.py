#!/usr/bin/env python3
"""pairact-r1 P4 -> P5: freeze the checkpoint chosen by the validation offline gate.

Reads only: ``<offline>/selection.json`` + ``checkpoints.jsonl`` (scripts/pairact_r1_offline.py),
``<run>/step-<selected>/actor/SHA256.json``, the dataset manifest, the stage-target sidecar and the
train config. Writes one new file (refuses to overwrite). The file is committed before any heldout
rollout (PAIRACT_R1_EVAL_PREREG_DRAFT.json commit_before_run). No checkpoint is modified or copied.

  python scripts/pairact_r1_freeze_checkpoint.py --offline RUN/offline --run RUN/main \
    --dataset datasets/pairact-r1-<TS> --stage-targets datasets/pairact-r1-<TS>-stage/stage-targets.json \
    --config experiments/2026-10-21-pairact-r1/PAIRACT_R1_TRAIN_CONFIG_DRAFT.json \
    --collect-report RUNP3T/report.json --out experiments/2026-10-21-pairact-r1/CHECKPOINT_FREEZE.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = 'ugrp.pairact_r1.checkpoint_freeze.v1'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(offline, run, dataset, stage_targets, config, collect_report=None):
    offline, run = Path(offline), Path(run)
    sel = json.loads((offline / 'selection.json').read_text())
    if sel.get('split') != 'validation':
        raise ValueError('selection must come from the validation split')
    if sel.get('verdict') != 'SELECTED' or sel.get('selected_step') is None:
        raise ValueError(f'no checkpoint to freeze: verdict {sel.get("verdict")!r} (P5 does not run)')
    step = int(sel['selected_step'])
    if sel.get('dataset_manifest_sha256') != sha256(Path(dataset) / 'manifest.json'):
        raise ValueError('selection dataset manifest sha differs from --dataset')
    if sel.get('stage_targets_sha256') != sha256(stage_targets):
        raise ValueError('selection stage-targets sha differs from --stage-targets')
    rows = [json.loads(x) for x in (offline / 'checkpoints.jsonl').read_text().splitlines() if x.strip()]
    chosen = [r for r in rows if int(r['step']) == step]
    if len(chosen) != 1 or chosen[0].get('passed') is not True:
        raise ValueError(f'step {step}: exactly one passing gate row required')
    step_dir = run / f'step-{step:06d}'
    if not step_dir.is_dir():
        step_dir = run / f'step-{step}'
    actor = step_dir / 'actor'
    actor_sha = json.loads((actor / 'SHA256.json').read_text())
    if actor_sha != chosen[0]['actor_sha256']:
        raise ValueError(f'step {step}: actor SHA256.json differs from the gated checkpoint')
    out = dict(schema=SCHEMA, selected_step=step, actor_dir=str(actor), actor_sha256=actor_sha,
               actor_sha256_file_sha256=sha256(actor / 'SHA256.json'),
               selection_sha256=sha256(offline / 'selection.json'),
               checkpoints_jsonl_sha256=sha256(offline / 'checkpoints.jsonl'),
               dataset_manifest_sha256=sel['dataset_manifest_sha256'],
               stage_targets_sha256=sel['stage_targets_sha256'], train_config_sha256=sha256(config),
               gate=sel.get('gate'), checkpoints=sel.get('checkpoints'),
               heldout_access_before_freeze='none (asserted by the operator; P5 starts after this commit)')
    if collect_report is not None:
        rep = json.loads(Path(collect_report).read_text())
        d = rep.get('decision') or {}
        if d.get('decision') not in ('TRAIN', 'TRAIN_DATA_RANGE_LIMITED', 'TRAIN_SMALL_DATA'):
            raise ValueError(f'collection decision {d.get("decision")!r} is not trainable')
        out.update(collect_report_sha256=sha256(collect_report), collect_decision=d['decision'],
                   result_labels=d.get('labels', []),
                   limited_bins=[b['bin'] for b in d.get('limited_bins') or []])
    return out


def main(argv=None):
    a = argparse.ArgumentParser()
    for k in ('offline', 'run', 'dataset', 'stage-targets', 'config', 'out'):
        a.add_argument(f'--{k}', type=Path, required=True)
    a.add_argument('--collect-report', type=Path)
    args = a.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f'{args.out} exists; a freeze is written once')
    rec = freeze(args.offline, args.run, args.dataset, args.stage_targets, args.config, args.collect_report)
    args.out.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(dict(selected_step=rec['selected_step'], out=str(args.out)), indent=1))


if __name__ == '__main__':
    main()
