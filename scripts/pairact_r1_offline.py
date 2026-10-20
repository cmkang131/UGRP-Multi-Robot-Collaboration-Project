"""pairact-r1 offline gate + checkpoint selection on the VALIDATION split only (P4).

For each ``<run>/step-*/actor`` checkpoint: h0 stage argmax and done score on
every validation row, once with the recorded history (clean) and once with a
fixed-seed +-1..6 PWM dither on the own issued-PWM history (G5 copycat check).
Gate thresholds and the selection rule are ``harness.pairact_r1.GATE`` /
``select_checkpoint`` (OFFLINE_GATE.md). Heldout seeds are never loaded here:
the dataset must contain only train/validation splits. GPU or CPU; no simulator.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import beamact3
from harness import pairact_r1 as p
from harness.grasp_act_data import sha256, write_json

DITHER_SEED = 20261021


def evaluate(actor, data, *, dither, batch_size=64):
    import torch
    rng = np.random.default_rng(DITHER_SEED)
    mean, std = (np.asarray(data.stats[k], np.float32) for k in ('state_mean', 'state_std'))
    pred, target, segments, done_score, done_target = [], [], [], [], []
    rows = list(range(len(data)))
    offset = 0
    seg_global = []
    for shard_segments in data.segments:
        seg_global.extend(s + offset for s in shard_segments)
        offset += max(shard_segments) + 1
    for start in range(0, len(rows), batch_size):
        items = []
        for i in rows[start:start + batch_size]:
            item = data[i]
            if dither:
                j, r = data.index[i]
                raw = p.history_dither(data.shards[j]['state'][r], rng, 6, .5)
                item['observation.state'] = (raw - mean) / std
            items.append(item)
            j, r = data.index[i]
            target.append(int(data.targets[j][r, 0]))
            done_target.append(float(data.shards[j]['action'][r, 0, -1]))
        inputs = {k: torch.from_numpy(np.stack([x[k] for x in items])).to(actor.device)
                  for k in items[0] if k.startswith('observation.')}
        inputs = beamact3.transform_batch(inputs, 'A')
        with torch.inference_mode():
            values = actor.policy.predict_action_chunk(inputs).cpu().numpy()
        logits = actor.policy.model.action_head.stage_logits.detach().cpu().numpy()
        pred.extend(logits[:, 0].argmax(-1).tolist())
        done_score.extend(actor.beam3.decode_predictions(values)[:, 0, -1].tolist())
    segments = seg_global
    return p.offline_metrics(pred, target, segments, done_score, done_target)


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument('--run', type=Path, required=True, help='training output root with step-*/actor')
    a.add_argument('--dataset', type=Path, required=True)
    a.add_argument('--stage-targets', type=Path, required=True)
    a.add_argument('--output', type=Path, required=True)
    a.add_argument('--device', default='cuda')
    args = a.parse_args(argv)
    manifest = json.loads((args.dataset / 'manifest.json').read_text())
    if {e['split'] for e in manifest['episodes']} - {'train', 'validation'}:
        raise ValueError('heldout episodes must not be in the offline dataset')
    data = p.pair_dataset_class()(args.dataset, 'validation', stage_manifest=args.stage_targets)
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for folder in sorted(args.run.glob('step-*')):
        actor = p.PairActActor.load(folder / 'actor', device=args.device)
        clean = evaluate(actor, data, dither=False)
        dithered = evaluate(actor, data, dither=True)
        passed, reasons = p.gate(clean, dithered)
        row = dict(step=int(folder.name.removeprefix('step-')), passed=passed, reasons=reasons,
                   clean=clean, dithered=dithered,
                   actor_sha256=json.loads((folder / 'actor/SHA256.json').read_text()))
        rows.append(row)
        with (args.output / 'checkpoints.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
    selected = p.select_checkpoint(rows)
    write_json(args.output / 'selection.json', dict(
        split='validation', gate=p.GATE, selected_step=selected,
        verdict='SELECTED' if selected is not None else 'NOT_READY_NO_CHECKPOINT_PASSES',
        dataset_manifest_sha256=sha256(args.dataset / 'manifest.json'),
        stage_targets_sha256=sha256(args.stage_targets), checkpoints=len(rows),
        source_sha256=sha256(Path(__file__)), pairact_source_sha256=sha256(Path(p.__file__))))
    print(json.dumps(dict(selected_step=selected, checkpoints=len(rows)), indent=1))


if __name__ == '__main__':
    main()
