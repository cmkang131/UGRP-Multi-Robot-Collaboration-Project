#!/usr/bin/env python3
"""Offline analysis for the render-profile A/B (experiments/2026-09-29-render-profile/README.md).

Reads finished ``run_pair_stage_probes`` output directories (raw is never modified) and computes the
metrics that README fixed before any run:

* frame gate (``harness.zone_pair_vision.valid_frame`` formula on the saved own JPEG) pass rate and which
  of its three criteria reject (V<8 fraction, 1-99 percentile contrast, V standard deviation);
* colour/tag detection rates with the existing, unchanged detectors (``owncam_pair_beam_v2``);
* PF error against ground truth (evaluation only, from ``result.json``) and sigma;
* case success / cause, wall and SIM time;
* ``/usr/bin/time -l`` CPU seconds and retired instructions parsed from the wrapper output.

Ground truth is read only from the evaluation fields the probe already stored; nothing here feeds a
controller. Frames of robots r1 and r2 (the carrying pair) are analysed; r3 is not part of the pair.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PAIR = ('r1', 'r2')
# Criteria of harness/zone_pair_vision.valid_frame, copied as constants so a change there is visible here.
GATE_LOW_V, GATE_LOW_FRAC, GATE_CONTRAST, GATE_STD = 8, .25, 15, 3
# Result fields that legitimately differ between two executions of the same case (host timing, paths).
VOLATILE_KEYS = {'wall_s', 'loadavg_case_start', 'loadavg_case_end', 'loadavg_case', 'render_profile'}


def frame_gate(jpeg: bytes) -> dict:
    """Same criteria as ``valid_frame`` on a saved own frame, with the reason for each rejection."""
    from harness.owncam_pair_beam_v2 import _valid
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None or frame.shape != (480, 640, 3):
        return {'ok': False, 'reasons': ['decode']}
    value = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2][_valid()]
    p1, p99 = np.percentile(value, [1, 99])
    low = float((value < GATE_LOW_V).mean())
    contrast = float(p99 - p1)
    std = float(value.std())
    reasons = [name for name, bad in (('dark_fraction', not low < GATE_LOW_FRAC),
                                      ('contrast', not contrast >= GATE_CONTRAST),
                                      ('std', not std >= GATE_STD)) if bad]
    return {'ok': not reasons, 'reasons': reasons, 'low_v_fraction': low, 'contrast': contrast,
            'v_std': std, 'mean_v': float(value.mean())}


def detect_frame(jpeg: bytes, pose) -> dict:
    """Existing detectors, unchanged: beam/band visibility, grip view, beam-colour pixels."""
    from harness import owncam_pair_beam_v2 as b2
    out = {}
    try:
        obs = b2.observe_beam(jpeg, {int(k): v for k, v in pose.items()})
        out['beam_visible'] = bool(obs.get('visible'))
        out['band_visible'] = obs.get('reason') == 'BAND_VISIBLE'
    except Exception as exc:                    # a detector failure is a data point, not a crash
        out['beam_visible'] = out['band_visible'] = False
        out['detector_error'] = type(exc).__name__
    try:
        out['grip_seen'] = bool(b2.grip_view(jpeg)['seen'])
    except Exception as exc:
        out['grip_seen'] = False
        out['detector_error'] = type(exc).__name__
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is not None and frame.shape == (480, 640, 3):
        valid = b2._valid()
        out['beam_colour_fraction'] = float((b2.beam_colour_mask(frame) & valid).sum() / valid.sum())
    return out


def _load(path: Path):
    return json.loads(path.read_text()) if path.is_file() else None


def analyze_case(case_dir: Path) -> dict:
    """Per-robot frame statistics of one case directory."""
    robots = (_load(case_dir / 'robots.json') or {})
    frames_dir = case_dir / 'frames'
    per_robot = {}
    for rid in PAIR:
        records = (robots.get(rid) or {}).get('frames', [])
        gate, det, tags = [], [], []
        for rec in records:
            path = frames_dir / rid / f'{rec["frame"]:05d}.jpg'
            if not path.is_file():
                continue
            jpeg = path.read_bytes()
            gate.append(frame_gate(jpeg))
            det.append(detect_frame(jpeg, rec.get('commanded_servo') or {}))
            report = rec.get('report') or {}
            last = report.get('last_valid_obs') or {}
            tags.append({'fresh': last.get('t') == report.get('t_est') and bool(last.get('n_tags')),
                         'n_tags': int(last.get('n_tags') or 0) if last.get('t') == report.get('t_est') else 0})
        n = len(gate)
        if not n:
            per_robot[rid] = {'frames': 0}
            continue
        rej = {k: sum(k in g['reasons'] for g in gate) for k in ('dark_fraction', 'contrast', 'std', 'decode')}
        per_robot[rid] = {
            'frames': n, 'gate_pass': sum(g['ok'] for g in gate), 'gate_reject_reasons': rej,
            'mean_v': float(np.mean([g['mean_v'] for g in gate if 'mean_v' in g])),
            'low_v_fraction_mean': float(np.mean([g['low_v_fraction'] for g in gate if 'low_v_fraction' in g])),
            'contrast_min': float(min(g['contrast'] for g in gate if 'contrast' in g)),
            'beam_visible': sum(d['beam_visible'] for d in det), 'band_visible': sum(d['band_visible'] for d in det),
            'grip_seen': sum(d['grip_seen'] for d in det),
            'beam_colour_fraction_mean': float(np.mean([d['beam_colour_fraction'] for d in det
                                                        if 'beam_colour_fraction' in d] or [0.])),
            'detector_errors': sum('detector_error' in d for d in det),
            'tag_fix_frames': sum(t['fresh'] for t in tags),
            'mean_tags': float(np.mean([t['n_tags'] for t in tags]))}
    return per_robot


def frame_hashes(case_dir: Path) -> dict:
    return {str(p.relative_to(case_dir / 'frames')): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((case_dir / 'frames').rglob('*.jpg'))}


def _strip(value):
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def compare_case_dirs(a: Path, b: Path) -> dict:
    """Stage 0: are two executions of the same case byte-identical in frames and equal in result?"""
    ha, hb = frame_hashes(a), frame_hashes(b)
    common = sorted(set(ha) & set(hb))
    diff = [k for k in common if ha[k] != hb[k]]
    ra, rb = _strip(_load(a / 'result.json')), _strip(_load(b / 'result.json'))
    rdiff = sorted(k for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))
    return {'frames_a': len(ha), 'frames_b': len(hb), 'frames_only_in_one': len(set(ha) ^ set(hb)),
            'frames_differing': len(diff), 'first_differing': diff[:5],
            'frames_identical': not diff and set(ha) == set(hb),
            'result_keys_differing': rdiff, 'result_equal': not rdiff}


def analyze_run(run_dir: Path, frames: bool = True) -> dict:
    """One probe output directory: rows plus (optionally) frame statistics per case."""
    rows = [json.loads(line) for line in (run_dir / 'cases.jsonl').read_text().splitlines() if line.strip()]
    manifest = _load(run_dir / 'manifest.json') or {}
    cases = {}
    for row in rows:
        cdir = run_dir / 'cases' / re.sub(r'[^A-Za-z0-9._+-]', '_', row['case_id'])
        if not cdir.is_dir():                       # directory naming follows the runner; fall back to a scan
            cdir = next((d for d in (run_dir / 'cases').iterdir()
                         if d.is_dir() and (_load(d / 'case.json') or {}).get('case_id') == row['case_id']), cdir)
        stage_s = row.get('stop_sim_s') if row.get('stop_sim_s') is not None else row.get('stage_sim_s')
        cases[row['case_id']] = {
            'stage': row['stage'], 'passed': bool(row['passed']), 'category': row['category'],
            'cause': row.get('cause'), 'first_failure': row.get('first_failure'),
            'wall_s': row.get('wall_s'), 'sim_s': stage_s,
            'wall_per_sim': (row['wall_s'] / stage_s) if row.get('wall_s') and stage_s else None,
            'loadavg_case': row.get('loadavg_case'), 'host_error': row.get('host_error'),
            'render_profile': (row.get('render_profile') or {}).get('name') if isinstance(row.get('render_profile'), dict)
            else row.get('render_profile'),
            'pf': {'est_vs_gt_at_ref': row.get('est_vs_gt_at_ref'), 'sigma_yaw_max': row.get('sigma_yaw_max'),
                   'std_xy_at_ref': {r: (v or {}).get('std_xy_m') for r, v in (row.get('own_at_ref') or {}).items()}},
            'frames': analyze_case(cdir) if frames and cdir.is_dir() else None}
    return {'dir': str(run_dir), 'render_profile': manifest.get('render_profile'),
            'environment': manifest.get('environment'), 'cases': cases}


def parse_time_l(text: str) -> dict:
    """Parse macOS ``/usr/bin/time -l`` output: user/sys CPU seconds, real, retired instructions."""
    out = {}
    m = re.search(r'([\d.]+)\s+real\s+([\d.]+)\s+user\s+([\d.]+)\s+sys', text)
    if m:
        out.update(real_s=float(m[1]), user_s=float(m[2]), sys_s=float(m[3]), cpu_s=float(m[2]) + float(m[3]))
    m = re.search(r'(\d+)\s+instructions retired', text)
    if m:
        out['instructions'] = int(m[1])
    m = re.search(r'(\d+)\s+cycles elapsed', text)
    if m:
        out['cycles'] = int(m[1])
    return out


def _rate(num: int, den: int):
    return round(num / den, 4) if den else None


def aggregate(runs: list[dict]) -> dict:
    """Pool the cases of runs (one arm) by stage: success, gate, detectors, PF, timing."""
    by_stage = {}
    for run in runs:
        for case_id, c in run['cases'].items():
            by_stage.setdefault(c['stage'], []).append((case_id, c))
    out = {}
    for stage, items in sorted(by_stage.items()):
        host_errors = sum(c['category'] == 'HOST_ERROR' for _, c in items)
        cs = [c for _, c in items if c['category'] != 'HOST_ERROR']   # host errors are re-run, not scored
        entry = {'cases': len(cs), 'host_errors_excluded': host_errors, 'passed': sum(c['passed'] for c in cs),
                 'causes': {}, 'wall_per_sim_median': None}
        for c in cs:
            entry['causes'][c['cause'] or c['category']] = entry['causes'].get(c['cause'] or c['category'], 0) + 1
        wps = [c['wall_per_sim'] for c in cs if c['wall_per_sim']]
        entry['wall_per_sim_median'] = round(statistics.median(wps), 3) if wps else None
        for rid in PAIR:
            fr = [c['frames'][rid] for c in cs if c.get('frames') and c['frames'].get(rid, {}).get('frames')]
            n = sum(f['frames'] for f in fr)
            entry[rid] = {
                'frames': n, 'gate_pass_rate': _rate(sum(f['gate_pass'] for f in fr), n),
                'reject_dark': sum(f['gate_reject_reasons']['dark_fraction'] for f in fr),
                'reject_contrast': sum(f['gate_reject_reasons']['contrast'] for f in fr),
                'reject_std': sum(f['gate_reject_reasons']['std'] for f in fr),
                'mean_v': round(float(np.mean([f['mean_v'] for f in fr])), 2) if fr else None,
                'beam_visible_rate': _rate(sum(f['beam_visible'] for f in fr), n),
                'band_visible_rate': _rate(sum(f['band_visible'] for f in fr), n),
                'grip_seen_rate': _rate(sum(f['grip_seen'] for f in fr), n),
                'tag_fix_rate': _rate(sum(f['tag_fix_frames'] for f in fr), n),
                'detector_errors': sum(f['detector_errors'] for f in fr)}
            errs = [(c['pf']['est_vs_gt_at_ref'] or {}).get(rid) for c in cs]
            errs = [e for e in errs if e]
            entry[rid]['pf_xy_err_m_mean'] = round(float(np.mean([e['xy_m'] for e in errs])), 4) if errs else None
            entry[rid]['pf_yaw_err_rad_mean_abs'] = (round(float(np.mean([abs(e['yaw_rad']) for e in errs])), 4)
                                                     if errs else None)
            sig = [(c['pf']['sigma_yaw_max'] or {}).get(rid) for c in cs]
            sig = [s for s in sig if s is not None]
            entry[rid]['sigma_yaw_max_mean'] = round(float(np.mean(sig)), 4) if sig else None
        out[stage] = entry
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run', action='append', default=[], metavar='ARM:NAME=DIR',
                   help='finished probe output dir, e.g. shadows_v1:S1=/abs/outputs/x/shadows-1')
    p.add_argument('--time', action='append', default=[], metavar='NAME=FILE',
                   help='/usr/bin/time -l output of the run NAME (repeatable)')
    p.add_argument('--compare', nargs=2, metavar=('CASE_DIR_A', 'CASE_DIR_B'),
                   help='stage 0: compare two executions of one case (frame bytes, result.json)')
    p.add_argument('--no-frames', action='store_true')
    p.add_argument('--out', type=Path)
    args = p.parse_args(argv)
    result = {'schema': 'ugrp.render_profile_ab_analysis.v1'}
    if args.compare:
        result['stage0'] = compare_case_dirs(Path(args.compare[0]), Path(args.compare[1]))
    runs, by_arm = {}, {}
    for spec in args.run:
        head, _, path = spec.partition('=')
        arm, _, name = head.partition(':')
        runs[name] = {'arm': arm, **analyze_run(Path(path), frames=not args.no_frames)}
        by_arm.setdefault(arm, []).append(runs[name])
    result['runs'] = runs
    result['by_arm'] = {arm: aggregate(rs) for arm, rs in by_arm.items()}
    timing = {}
    for spec in args.time:
        name, _, path = spec.partition('=')
        timing[name] = parse_time_l(Path(path).read_text())
    result['time_l'] = timing
    text = json.dumps(result, indent=1, ensure_ascii=False, default=str) + '\n'
    if args.out:
        args.out.write_text(text)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
