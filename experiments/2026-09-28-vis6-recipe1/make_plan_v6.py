#!/usr/bin/env python3
"""Writes the VIS6 candidate configs (configs/*.json) and the frozen plan (plan_v6.json). Deterministic; run once.

Refuses to overwrite: the committed files are the registration. Re-running into a fresh
directory (``--out``) must reproduce them byte for byte (tests/test_vision_loc_v6.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026-09-26-vision-loc'))
import replay_v6
import vision_stall_v6
import vis6_metrics
BASE = {'infer_size': [480, 360], 'obs': {'refine_px': 6, 'consistency_px': 4},
        'measurement': {'settle_s': 0.2, 'effective_columns': 8, 'sigma_px': 2.5}, 'robust': {}}
ETAS = {'eta050': .5, 'eta025': .25, 'eta0125': .125}
GATING = {f'd{d:02d}a{a}': {'min_d_m': d/100., 'min_yaw_rad': round(math.radians(a), 6), 'min_servo_pulse': 10,
                            'mode': 'skip', 'max_interval_s': 2.}
          for d in (2, 5, 10) for a in (3, 6)}
STALL = vision_stall_v6.validate_stall({})          # vision_stall_v6.DEFAULT_STALL, fixed before any replay
FIT = ['vl-dev-s909', 'vl-dev-s910', 'vl-dev-s911', 'vl3-dev-s941', 'vl3-dev-s942', 'vl3-dev-s943']
VALIDATION = ['vl3-dev-s945', 'vl3-dev-s946', 'vl3-dev-s947']


def configs() -> dict:
    out = {'T0': {**BASE, 'vis6': {}}}
    for n, eta in ETAS.items():
        out[f'T1b_{n}'] = {**BASE, 'vis6': {'eta': eta}}
    out['T1c_inert'] = {**BASE, 'vis6': {'eta': 1., 'stall': {**STALL, 'min_pred_px': 100.,
                                                                          'min_points': 1000000, 'max_points': 1000000}}}
    out['T1c'] = {**BASE, 'vis6': {'stall': STALL}}
    for g, gc in GATING.items():
        out[f'T1ac_{g}'] = {**BASE, 'vis6': {'stall': STALL, 'gating': gc}}
        for n, eta in ETAS.items():
            out[f'T1abc_{g}_{n}'] = {**BASE, 'vis6': {'eta': eta, 'stall': STALL, 'gating': gc}}
    return out


def dump(obj) -> str:
    return json.dumps(obj, indent=1, sort_keys=True) + '\n'


def plan(cfg_hashes: dict) -> dict:
    return {
        'schema': 'ugrp.vision_loc.vis6.plan.v2',
        'revision': 2,
        'amendment': '재생 전 PR #253 적대적 검토 반영. 거짓 stall 탈출, 잡음 보존, 사건 분할 내성, 해시 대조를 수정해 재동결. 이전 계획과 설정은 pre_review_0687c620/에 보존.',
        'supersedes_plan_sha256': 'c339db6787324d1ec8bae2e2a9d6a7db9fa247ad3616ca04b3ed0db96ae96b04',
        'module_sha256': replay_v6.source_hashes(),
        'status': 'FROZEN_BEFORE_ANY_VIS6_REPLAY',
        'issue': 'https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/216',
        'source': 'outputs/lit-review-tagfree-localization-20260928.md section 6.1 (recipe #1: 1a gating, 1b eta, 1c stall)',
        'split': {'fit': FIT, 'validation': VALIDATION,
                  'note': 'same fit/validation split as VIS4/VIS5; validation was seen before (not an independent test)'},
        'inputs': {'obs': 'outputs/vision-loc-20260926/r3/obs-w6 (vision, checkpoint sha256 3485390...)',
                   'frames': 'render/<ep>/inputs/frames.jsonl + frames/*.jpg (1c classical image processing only)',
                   'calibration': 'experiments/2026-09-26-vision-loc/calibration_train.json',
                   'gt': 'render/<ep>/eval_only/frames_eval.jsonl, scoring only',
                   'nn_inference_frames': 0, 'test_episodes': 'none (refused by replay_v6.py)'},
        'seeds': {'selection_fit': [0, 1, 2], 'final_validation': [0, 1, 2, 3, 4],
                  'rule': 'index 0 = episode seed (VIS3/VIS4), k >= 1 = episode_seed*1000 + k'},
        'particles': 2000,
        'configs_sha256': cfg_hashes,
        'stages': [
            {'id': 'P0', 'what': '먼저 T0/T1c_inert fit 첫 회차 seed0: a1 및 서로의 xyyaw/std_xy_m/std_yaw_rad/measured 대조. 통과 뒤 나머지 T0 fit seed0-2'},
            {'id': 'S1', 'what': '1b eta on fit: select calibration over [T0, T1b_eta050, T1b_eta025, T1b_eta0125]'},
            {'id': 'S2', 'what': 'T1c fit 검출기 관문은 seed0 고유 프레임 쌍으로만 집계'},
            {'id': 'S3', 'what': '1a gating grid on fit at eta 1: door accuracy constraints, then lowest fit NLL over T1ac_* in order '
                                 'd02a3, d02a6, d05a3, d05a6, d10a3, d10a6 (ties to the earlier)'},
            {'id': 'S4', 'what': '1a+1b+1c: select calibration over [T1ac_<S3>, T1abc_<S3>_eta050, _eta025, _eta0125]'},
            {'id': 'F', 'what': 'validation seeds 0-4: T0 baseline vs T1b_<S1>, T1c, T1ac_<S3>, T1abc_<S4>; '
                                'validation_gate each; adopt the passing one with the lowest validation NLL'},
        ],
        'rules': {
            'coverage95_band': [.90, .99],
            'calibration_selection': 'eligible: fit seed-mean XY 95% ellipse coverage in band; choose lowest fit '
                                     'episode-equal XY NLL; ties to the earlier (larger eta) name; accuracy is not a '
                                     'selection criterion; none eligible -> the component is dropped',
            'gating_accuracy_worse_max': {'door_pos_p90_m': .003, 'door_lat_p99_m': .003, 'door_yaw_p90_deg': .2},
            'events': {'min_bad_frames': 5, 'merge_gap_s': 1., 'primary': 'event_frames (all bad frames, including short events)'},
            'detector_gate': {'min_positives': 20, 'min_precision': .80, 'min_recall': .30,
                              'positive': 'GT < 0.01 m/s AND < 0.02 rad/s; predicted > 0.05 m/s OR > 0.05 rad/s; seed0 only',
                              'correct_stall': 'both XY/yaw <= max(0.5 x predicted, still threshold x dt), with active translation or yaw prediction'},
            'validation': dict(vis6_metrics.DEFAULT_VALIDATION_RULE),
        },
        'stop_rules': [
            'P0 reproduce fails -> STOP before any comparison (code or data drift); record, no selection',
            'S2 detector gate fails -> 1c dropped; 1a is dropped with it (gating needs 1c); F compares T1b only',
            'S1, S3 or S4 with no eligible candidate -> that stage contributes no candidate',
            'no candidate passes F -> keep b0 (VIS3 a1 = T0); no re-tuning of grids, thresholds or rules in this '
            'cohort; a new idea needs a new plan',
            'host: AC power only; ENOSPC or a killed run -> HOST_ERROR, rerun the whole unit into a new root; '
            'evaluate refuses partial sets',
            'budget: stop after the running stage when the cohort passes 40 CPU-hours; report what finished',
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(HERE))
    args = ap.parse_args(argv)
    out = Path(args.out)
    cdir = out/'configs'
    cdir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, cfg in configs().items():
        p = cdir/f'{name}.json'
        if p.exists():
            raise SystemExit(f'refusing to overwrite {p}')
        text = dump(cfg)
        p.write_text(text)
        hashes[name] = hashlib.sha256(text.encode()).hexdigest()
    p = out/'plan_v6.json'
    if p.exists():
        raise SystemExit(f'refusing to overwrite {p}')
    p.write_text(dump(plan(hashes)))
    print(f'{len(hashes)} configs, plan {hashlib.sha256(p.read_bytes()).hexdigest()}')


if __name__ == '__main__':
    main()
