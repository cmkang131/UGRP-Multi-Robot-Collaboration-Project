"""Offline, evaluation-only contact labels and legacy RGB diagnostic replay.

Never imports S4's model client or feeds labels to any controller. The actual
S4 LLM classifier cannot be replayed without a model call; its scores stay null.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
import hashlib
import importlib.abc
import json
from pathlib import Path
import re
import socket
import sys


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def finger_sides(row, rid):
    sides = set()
    for c in row['contacts']:
        a, b = c['geom1'], c['geom2']
        if a.startswith('cargo_beam_1__'):
            a, b = b, a
        if b.startswith('cargo_beam_1__') and c['dist_m'] <= 0:
            for side in ('left', 'right'):
                if a == f'{rid}__{side}_finger':
                    sides.add(side)
    return sorted(sides)


def contact_labels(contacts, commands, rid):
    """Contact proxy, not force closure or lift success; zero before grasp != loss.

    An episode ends at any opening command (>1500), missing command history, or
    contact gap >0.25 s. Commands at exactly capture time apply AFTER the frame.
    No label interpolation: caller joins by exact rounded-nanosecond timestamp.
    """
    grip = []
    for c in commands:
        if c['kind'] == 'initial_servo_command' and '1' in c.get('pulses', {}):
            grip.append((c['t'], c['pulses']['1']))
        elif c['kind'] == 'arm' and c.get('servo_id') == 1:
            grip.append((c['t'], c['pulse']))
    grip.sort(key=lambda p: p[0])
    times = [p[0] for p in grip]
    seen_held, lost, previous = False, False, None
    labels, episodes = {}, []
    for i, c in enumerate(contacts):
        t = round(c['t'], 9)
        if t in labels or (previous is not None and t <= previous):
            raise ValueError('duplicate/nonmonotonic contact timestamp')
        ci = bisect_left(times, t - 1e-8) - 1
        pulse = grip[ci][1] if ci >= 0 else None
        if pulse != 1500 or (previous is not None and t - previous > .25 + 1e-8):
            seen_held, lost = False, False
        sides = finger_sides(c, rid)
        if len(sides) == 2:
            label, seen_held, lost = 'held_contact', True, False
        elif sides:
            label = 'partial_contact'
        elif seen_held and pulse == 1500:
            label = 'lost_contact'
            if not lost:
                episodes.append({'robot_id': rid, 'onset_t': t, 'contact_line': i + 1})
            lost = True
        else:
            label = 'not_held'
        labels[t] = dict(label=label, finger_sides=sides, contact_line=i + 1,
                         closed_command=pulse == 1500)
        previous = t
    return labels, episodes


def inventory(root):
    result = []
    # Fixed scope: do not silently add the concurrently growing s3fix16 outputs.
    for top in sorted(root.iterdir()):
        if not re.match(r'^s3fix1[0-5](?:-|$)', top.name) or not top.is_dir():
            continue
        for cp in sorted(top.rglob('eval_only/contacts.jsonl')):
            raw = cp.parent.parent
            bp = raw / 'bundle.json'
            if not bp.exists():
                raise ValueError(f'missing bundle: {raw}')
            b = json.loads(bp.read_text())
            rp = raw / 'result.json'
            r = json.loads(rp.read_text()) if rp.exists() else {}
            excluded = ('cyan_task' if b.get('case') != 'pair' or
                        r.get('grid', {}).get('robot') == 'r3' else None)
            files = [cp, bp]
            if rp.exists():
                files.append(rp)
            for rid in ('r1', 'r2'):
                files += [p for n in ('frames.jsonl', 'commands.jsonl')
                          if (p := raw / f'robots/{rid}/{n}').exists()]
            result.append(dict(raw=str(raw.relative_to(root)), excluded=excluded,
                               source_sha=b['source_sha'], model_calls=b['model_calls'],
                               weld=b['weld'], seed=b['seed'],
                               files={str(f.relative_to(raw)): sha(f) for f in files}))
    return dict(schema='ugrp.s4grip.inventory.v1', root=str(root.resolve()), runs=result)


def block_external_work():
    class Block(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in {'mujoco', 'torch', 'torchvision', 'requests', 'httpx'}:
                raise RuntimeError(f'forbidden offline import: {fullname}')
    sys.meta_path.insert(0, Block())
    def deny(*a, **kw):
        raise RuntimeError('network/model connection forbidden in offline evaluation')
    socket.socket.connect = deny
    socket.socket.connect_ex = deny


def evaluate(manifest, output):
    block_external_work()
    import cv2
    from harness.zone_pair_highpose_grip import relation
    cv2.setNumThreads(1)
    cv2.ocl.setUseOpenCL(False)
    root = Path(manifest['root'])
    output.mkdir(parents=True, exist_ok=False)
    totals, summary, all_episodes = Counter(), [], []
    with (output / 'eval-only-frames.jsonl').open('w') as dest:
        for run in manifest['runs']:
            if run['excluded']:
                continue
            raw = root / run['raw']
            for name, digest in run['files'].items():
                if sha(raw / name) != digest:
                    raise ValueError(f'changed source: {raw / name}')
            if run['model_calls'] != 0 or run['weld'] != 'off':
                raise ValueError('scope expects recorded model_calls=0, weld=off')
            contacts = lines(raw / 'eval_only/contacts.jsonl')
            counts = Counter()
            errors = []
            for rid in ('r1', 'r2'):
                commands_path = raw / f'robots/{rid}/commands.jsonl'
                try:
                    labels, episodes = contact_labels(contacts, lines(commands_path), rid)
                except ValueError as exc:
                    errors.append(dict(robot_id=rid, error=str(exc)))
                    counts['excluded_ambiguous_contact_series'] += 1
                    continue
                counts.update({'contact_' + x: n for x, n in
                               Counter(v['label'] for v in labels.values()).items()})
                fp = raw / f'robots/{rid}/frames.jsonl'
                frames = lines(fp) if fp.exists() else []
                frame_times = []
                for row in frames:
                    if row['robot_id'] != rid or row['camera'] != 'robot_cam':
                        raise ValueError('not an own RGB frame')
                    path = raw / row['path']
                    if not path.resolve().is_relative_to((raw / f'robots/{rid}/rgb').resolve()):
                        raise ValueError('foreign frame path')
                    if sha(path) != row['sha256']:
                        raise ValueError(f'image hash mismatch: {path}')
                    t = round(row['sim_time'], 9)
                    gt = labels.get(t, dict(label='unmatched', finger_sides=[], contact_line=None))
                    frame_times.append((t, gt['label']))
                    # Only RGB and own issued commands enter this function. No GT.
                    servo = {int(k): v for k, v in row['commanded_servo'].items()}
                    pred = relation(path.read_bytes(), servo)
                    counts['frames'] += 1
                    counts['frame_' + gt['label']] += 1
                    counts['cv_' + gt['label'] + ('_ok' if pred['ok'] else '_reject')] += 1
                    record = dict(scope='eval_only', raw=run['raw'], robot_id=rid,
                                  frame_id=row['frame_id'], sim_time=t, image_path=row['path'],
                                  image_sha256=row['sha256'], commanded_servo=row['commanded_servo'],
                                  ground_truth=gt, legacy_relation=pred, s4_llm_prediction=None)
                    dest.write(json.dumps(record, ensure_ascii=False) + '\n')
                for ep in episodes:
                    ep.update(raw=run['raw'], own_rgb_at_onset=any(
                        abs(t-ep['onset_t']) < 1e-8 for t, _ in frame_times),
                        # No S4 provider prediction exists; delay is never zero-filled.
                        s4_detection_delay_frames=None)
                counts['contact_loss_episodes'] += len(episodes)
                counts['rgb_series'] += bool(frames)
                all_episodes.extend(episodes)
            totals.update(counts)
            summary.append(dict(raw=run['raw'], source_sha=run['source_sha'], seed=run['seed'],
                                counts=dict(counts), errors=errors))
            print(run['raw'], counts['frames'], flush=True)
    source = Path(__file__).resolve().parents[1]
    module_hashes = {str(p.relative_to(source)): sha(p) for m in list(sys.modules.values())
                     if (f := getattr(m, '__file__', None)) and
                     (p := Path(f).resolve()).is_relative_to(source) and p.suffix == '.py'}
    for name in ['scripts/evaluate_s4_grip_raw.py', 'harness/s4_pair_stage.py',
                 'harness/s4_pair_handshake.py']:
        module_hashes[name] = sha(source / name)
    result = dict(schema='ugrp.s4grip.offline.v1', research_result=False, evaluation_only=True,
                  physics_runs=0, render_calls=0, model_calls=0,
                  current_s4_detector='LLM own RGB judgement; no recorded predictions in S3',
                  s4_eligible_predictions=0, s4_precision=None, s4_recall=None,
                  s4_false_positive_rate=None, s4_delay_frames=None,
                  diagnostic='unchanged log-only relation; false means lost OR unobservable',
                  counts=dict(totals), runs=summary, contact_loss_episodes=all_episodes,
                  module_sha256=module_hashes,
                  dataset_sha256=sha(output / 'eval-only-frames.jsonl'))
    write(output / 'summary.json', result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inventory-root', type=Path)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    if a.inventory_root:
        if a.manifest.exists():
            raise FileExistsError(a.manifest)
        write(a.manifest, inventory(a.inventory_root))
    else:
        if a.output is None:
            p.error('--output required for evaluation')
        evaluate(json.loads(a.manifest.read_text()), a.output)


if __name__ == '__main__':
    main()
