"""Audit saved localization decisions and replay availability; never run MuJoCo.

This replays finalize() on recorded detections, NOT RGB detection or improved
localization. The 80-case denominator is the last saved decision of 40 x 2 robots.
Evaluation truth is read only for explicitly labelled error statistics.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from PIL import Image
from sim.lookaround_localization import LookaroundLocalizer


def stats(values):
    return {"n": len(values), "min": min(values), "median": statistics.median(values),
            "max": max(values)} if values else {"n": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path,
                        default=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs'))
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name('release-localization-audit.json'))
    args = parser.parse_args()
    evidence, manifests = [], {}

    def verified(path):
        run = path.relative_to(args.raw_root).parts[0]
        if run not in manifests:
            m = args.raw_root / run / 'SHA256SUMS'
            manifests[run] = dict((line.split(maxsplit=1)[1], line.split(maxsplit=1)[0])
                                  for line in m.read_text().splitlines() if line.strip())
            evidence.append({'path': str(m), 'sha256': hashlib.sha256(m.read_bytes()).hexdigest(),
                             'kind': 'retrieved_source_manifest'})
        blob = path.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        remote = '/home/ugrp/ugrp-sim/runs/' + str(path.relative_to(args.raw_root))
        if manifests[run].get(remote) != digest:
            raise ValueError(f'SOURCE_HASH_MISMATCH {path}')
        evidence.append({'path': str(path), 'sha256': digest, 'bytes': len(blob),
                         'source_manifest_verified': True})
        return blob

    reasons, skips, totals = Counter(), Counter(), Counter()
    priors = [[], [], []]
    before, after, images = [], [], []
    replayed = accepted = gate_records = map_known = views_count = 0
    for index in range(40):
        run = args.raw_root / f'release-command-gate-{index:02d}-cdace35e'
        path = run / 'raw/result.json.zst'
        blob = verified(path)
        result = json.loads(subprocess.check_output(['zstd', '-dc'], input=blob))
        if set(result['lookaround_result']) != {'r1', 'r2'}:
            raise ValueError(f'ROBOT_DENOMINATOR {run.name}')
        for rid, item in result['lookaround_result'].items():
            saved = item['localizer']
            # finalize's unknown-map path requires only these recorded fields.
            # Do not initialize a map pose or construct a simulator/camera.
            if saved['map_pose_known']:
                raise ValueError(f'UNEXPECTED_KNOWN_MAP {run.name} {rid}')
            localizer = LookaroundLocalizer.__new__(LookaroundLocalizer)
            localizer.map_pose_known = saved['map_pose_known']
            localizer.views = saved['views']
            decision = localizer.finalize()
            if decision != saved['decision']:
                raise ValueError(f'DECISION_REPLAY_MISMATCH {run.name} {rid}')
            replayed += 1
            accepted += bool(decision['accepted'])
            reasons[decision['reason']] += 1
            map_known += bool(saved['map_pose_known'])
            for view in saved['views']:
                views_count += 1
                skips[view.get('update_skipped', 'not_recorded')] += 1
                gate_records += 'gate' in view
                for key in ('wall_points', 'floor_lines', 'doors'):
                    totals[key] += view[key]
                for axis, sigma in enumerate(view['prior_sigma']):
                    priors[axis].append(sigma)
            ev = item['evaluation']
            before.append(ev['before']['error_xy_m'])
            if ev.get('after'):
                after.append(ev['after']['error_xy_m'])
    for run in sorted(args.raw_root.glob('release-command-*-cdace35e')):
        for path in sorted(run.glob('raw/eval-*/**/*.jpg')):
            verified(path)
            with Image.open(path) as frame:
                size = list(frame.size)
            images.append({'run': run.name, 'path': str(path), 'size': size,
                           'role': 'own' if 'eval-own' in path.parts else 'overview'})
    own = [p for p in images if p['role'] == 'own']
    source = {}
    for name in ('sim/lookaround_localization.py', 'scripts/run_grasp_act_release.py'):
        source[name] = hashlib.sha256((REPO / name).read_bytes()).hexdigest()
    summary = {
        'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'raw_source_sha': 'cdace35e0c5bd94d0c1d348e17cd470a773cb270',
        'scope': 'saved-detection terminal-decision replay and image inventory; no RGB replay, simulation, rendering, model, or modified localizer',
        'run_count': 40, 'last_decision_replayed': replayed, 'last_decision_accepted': accepted,
        'last_decision_reasons': dict(reasons), 'map_pose_known_count': map_known,
        'view_count_all_sweeps': views_count, 'update_skipped': dict(skips),
        'detection_totals_repeated_not_unique': dict(totals),
        'gate_records': gate_records, 'map_correspondence_residual': None,
        'gate_status': 'not reached; map_pose_unknown returns before _gate and _grid_update',
        'configured_but_unused_gates': {'wall_chi2_1': 6.63, 'joint_chi2_3': 11.34,
                                      'floor_m': .2, 'floor_deg': 10., 'door_m': .3},
        'prior_sigma_command_frame': {'x_m': stats(priors[0]), 'y_m': stats(priors[1]),
                                      'yaw_deg': stats([math.degrees(v) for v in priors[2]])},
        'evaluation_only_error': {'frame': 'arbitrary command origin aligned with evaluation-only spawn; NOT map localization',
                                  'before_m': stats(before), 'after_m': stats(after),
                                  'map_error_before_m': None, 'map_error_after_m': None},
        'images': {'all': len(images), 'runs': len(set(p['run'] for p in images)),
                   'own': len(own), 'own_sizes': dict(Counter('x'.join(map(str, p['size'])) for p in own)),
                   'overview': len(images)-len(own),
                   'native_own_640x480': sum(p['size'] == [640, 480] for p in own),
                   'gate_runs_represented': len(set(p['run'] for p in own if '-gate-' in p['run'])),
                   'exact_input_rgb_replay_available': False},
        'verification': {'result_hashes': 40, 'image_hashes': len(images), 'source_files': source},
        'improved_localizer': {'implemented': False, 'accepted': None, 'error_improvement': None},
    }
    detail_path = args.out.with_name(args.out.stem + '-inputs.json.zst')
    detail = json.dumps({'files': evidence, 'images': images}, ensure_ascii=False, indent=2).encode()
    detail_path.write_bytes(subprocess.check_output(['zstd', '-q', '-c'], input=detail))
    summary['evidence'] = {'path': detail_path.name, 'sha256': hashlib.sha256(detail_path.read_bytes()).hexdigest()}
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
