#!/usr/bin/env python3
"""VIS6 replay -> offline-audit derived views (one per candidate x split) for scripts/export_offline_audit.py.

Reads only the evaluate/select JSONs of a finished VIS6 output root (seed-mean metrics already computed by
``replay_v6.py evaluate``). Every scalar is copied from the hashed metrics JSON; nothing is recomputed.

  python3 build_tb_views.py --root /Users/changmin/projects/ugrp/outputs/vis6-recipe1-20260929 \
      --output <root>/tb-derived --source-sha <sha>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

KEYS = ('coverage95_xy', 'exceed3_xy', 'anees_xy', 'nll_xy', 'coverage95_yaw', 'anees_yaw', 'nll_yaw',
        'pos_p90_m', 'lost_frames', 'door_pos_p90_m', 'door_lat_p99_m', 'door_yaw_p90_deg',
        'sigma_xy_p90_m', 'sigma_xy_p90_loaded_m', 'sigma_xy_p90_unloaded_m', 'events', 'event_frames',
        'n_frames', 'n_door')
STALL = ('pairs', 'positives', 'stall_decisions', 'moving_decisions', 'unknown', 'precision', 'recall',
         'abstain_share_of_positives')
HP = ['offline/coverage95_xy', 'offline/exceed3_xy', 'offline/nll_xy', 'offline/pos_p90_m', 'offline/lost_frames',
      'offline/door_pos_p90_m', 'offline/door_lat_p99_m', 'offline/door_yaw_p90_deg', 'offline/event_frames']
SHORT = {'T1abc_': 'abc-', 'T1ac_': 'ac-', 'T1b_': 'b-', 'T1c': 'c', 'T0': 't0'}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def short(name: str) -> str:
    for k, v in SHORT.items():
        if name.startswith(k):
            return v + name[len(k):]
    return name


def finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--source-sha', required=True)
    a = ap.parse_args()
    root = a.root.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    final = json.loads((root/'select_F.json').read_text()) if (root/'select_F.json').exists() else None
    selections = {p.stem: json.loads(p.read_text()) for p in sorted(root.glob('select_*.json'))}
    index = []
    for mname, stage in (('metrics_fit_S1_S3.json', 'S1-S3'), ('metrics_fit_S4.json', 'S4'),
                         ('metrics_val_F.json', 'F'), ('SUPP_metrics_val_T0.json', 'SUPP')):
        mp = root/mname
        if not mp.exists():
            continue
        met = json.loads(mp.read_text())
        for cand, splits in met['candidates'].items():
            for split, block in splits.items():
                m = block['seed_mean']['mean']
                sd = block['seed_mean'].get('sd', {})
                scal = {f'offline/{k}': float(m[k]) for k in KEYS if finite(m.get(k))}
                scal.update({f'offline/sd/{k}': float(sd[k]) for k in KEYS if finite(sd.get(k))})
                diag = block.get('stall_diagnostic') or {}
                scal.update({f'offline/stall/{k}': float(diag[k]) for k in STALL if finite(diag.get(k))})
                success, definition = None, None
                if stage == 'F' and final and cand in final.get('results', {}):
                    r = final['results'][cand]
                    success = bool(r['pass'])
                    scal['gate/validation_pass'] = float(success)
                    scal['gate/validation_failures'] = float(len(r['failures']))
                    definition = ('VIS6 validation gate (plan_v6 rules.validation) vs T0 on validation seeds 0-4; '
                                  'offline localization gate, NOT robot task success')
                s1, s2, s3 = (selections.get(k, {}) for k in ('select_S1', 'select_S2', 'select_S3'))
                if stage == 'S1-S3' and cand in s1.get('table', {}):
                    scal['gate/S1_eligible'] = float(cand in s1.get('eligible', []))
                if stage == 'S1-S3' and cand == 'T1c' and 'pass' in s2:
                    scal['gate/S2_detector_pass'] = float(bool(s2['pass']))
                if stage == 'S1-S3' and cand.startswith('T1ac_') and 'eligible' in s3:
                    scal['gate/S3_accuracy_eligible'] = float(cand in s3['eligible'])
                name = (f'v6-{short(cand)}-{split[:3]}' + ('' if stage != 'S4' or cand.startswith('T1abc') else '-s4')
                        + ('-supp' if stage == 'SUPP' else ''))
                d = a.output/name
                d.mkdir()
                view = {
                    'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True,
                    'offline_source': {'path': str(mp), 'sha256': sha(mp)},
                    'offline_source_pointer': f'candidates.{cand}.{split}.seed_mean',
                    'offline_scalar_scope': (('SUPPLEMENT outside the frozen plan (descriptive, not a selection input). '
                                              if stage == 'SUPP' else '') +
                                             f'VIS6 offline PF replay ({stage}), candidate {cand}, split {split}, '
                                             f'seed indices {block["seed_mean"]["seeds"]}: seed-mean (offline/*) and '
                                             'seed SD (offline/sd/*) from replay_v6.py evaluate; stall detector '
                                             'diagnostic from seed0. Dev episodes only (validation is seen dev, '
                                             'not an independent test). Not closed-loop, not task success.'),
                    'offline_scalars': scal,
                    'family': 'vis6-replay', 'policy': cand, 'case': stage, 'split': split,
                    'seed': '+'.join(str(s) for s in block['seed_mean']['seeds']),
                    'source_sha': a.source_sha, 'run_id': name,
                    'outcome': ('adopted' if final and final.get('chosen') == cand else
                                'gate_pass' if success else 'gate_fail' if success is False else
                                'baseline_b0_kept' if cand == 'T0' else 'not_adopted'),
                    'hparam_metrics': [t for t in HP if t in scal] + (['gate/validation_pass'] if success is not None else []),
                    'texts': {'evaluation/selections': {k: {kk: vv for kk, vv in v.items() if kk != 'table'}
                                                        for k, v in selections.items()}},
                    'limits': 'offline replay of teacher-driven dev renders; no physics stepping, no model calls',
                }
                if success is not None:
                    view['success'], view['success_definition'] = success, definition
                (d/'result.json').write_text(json.dumps(view, indent=1, ensure_ascii=False))
                index.append({'name': name, 'candidate': cand, 'split': split, 'stage': stage,
                              'metrics': str(mp), 'metrics_sha256': view['offline_source']['sha256'],
                              'scalars': scal})
    (a.output/'index.json').write_text(json.dumps(index, indent=1))
    print(f'{len(index)} views -> {a.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
