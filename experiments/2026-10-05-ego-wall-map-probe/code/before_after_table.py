"""Before / after table of ``score_harness.py`` runs (offline, reads only the runs' own outputs).

Refs #216. **Physical simulation runs: 0.** Reads ``summary.json``, ``per_frame.csv`` and
``columns.npz`` of each run and prints one markdown table plus a JSON file.

  python before_after_table.py --run legacy=<dir> --run scorer+load=<dir> --run +extent=<dir> --json out.json

Definitions (all on the ground-truth-VISIBLE columns of the ground-truth-VISIBLE frames, except FP):

  zero-recall frames   visible frames in which no visible column reports a contact
  column recall        contacts on visible columns / visible columns
  testable recall      the same over visible columns whose ground-truth contact has >= band_px rows above it
  correct              a contact on a visible column with |row error| <= row_tol_px (the detector window_px)
  precision            correct / contacts on visible columns
  correct recall       correct / visible columns
  row error            detector vb - ground-truth contact row, pixels. Positive = detector below the boundary.
                       'per-frame' = median per frame, then median and p10/p90 over frames
                       'per-column' = over every detected visible column
  range error          detector range - ground-truth range, metres (signed), same two views
  FP                   contacts on frames where ground truth says no wall contact is in view (never mixed with recall)
"""
from __future__ import annotations

import argparse
import csv
import json
import warnings
from pathlib import Path

import numpy as np


def pct(a, q):
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(np.percentile(a, q)) if a.size else float('nan')


def stat(a):
    return {'n': int(np.isfinite(np.asarray(a, float)).sum()), 'median': pct(a, 50), 'p10': pct(a, 10), 'p90': pct(a, 90)}


def summarize(run_dir: Path, variant: str):
    s = json.loads((run_dir/'summary.json').read_text())
    v = s['variants'][variant]
    per = list(csv.DictReader(open(run_dir/'per_frame.csv')))
    z = np.load(run_dir/'columns.npz')
    arr = z[variant]                                   # (frames, 4, columns): det row, det range, gt row, gt range
    det_row, det_rng, gt_row, gt_rng = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    vis = np.isfinite(gt_row)
    hit = vis & np.isfinite(det_row)
    row_err = np.where(hit, det_row - gt_row, np.nan)
    rng_err = np.where(hit & np.isfinite(det_rng) & np.isfinite(gt_rng), det_rng - gt_rng, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)          # frames without a detected visible column
        pf_row = np.nanmedian(row_err, axis=1)
        pf_rng = np.nanmedian(rng_err, axis=1)
    rec, cor, fp = v['recall'], v['correctness'], v['false_positives_invisible_frames']
    out = {
        'run': str(run_dir), 'variant': variant, 'gt_camera': s['gt_camera'], 'load_rule': s['load_rule'],
        'detector_params_override': s.get('detector_params_override'),
        'frames_scored': s['frames_scored'], 'visible_frames': rec['visible_frames'],
        'visible_columns': rec['gt_visible_columns'],
        'zero_recall_frames': rec['visible_frames_with_zero_recall'],
        'column_recall': rec['column_recall'],
        'testable_column_recall': v['recall_testable']['column_recall'],
        'contacts_on_visible': cor['detected_on_visible_columns'],
        'correct_on_visible': cor['correct_on_visible_columns'],
        'precision': cor['precision_on_visible_columns'], 'correct_column_recall': cor['correct_column_recall'],
        'zero_correct_frames': cor['visible_frames_with_zero_correct'],
        'fp_frames': fp['frames'], 'fp_contacts': fp['contacts'], 'fp_frames_with_contact': fp['frames_with_any_contact'],
        'fp_segments': fp['segments'], 'fp_frames_with_segment': fp['frames_with_any_segment'],
        'row_err_px_per_frame': stat(pf_row), 'row_err_px_per_column': stat(row_err),
        'range_err_m_per_frame': stat(pf_rng), 'range_err_m_per_column': stat(rng_err),
        'abs_row_err_px_per_column_median': pct(np.abs(row_err), 50),
        'abs_range_err_m_per_column_median': pct(np.abs(rng_err), 50),
        'frames_in_per_frame_csv': len(per),
    }
    return out


ROWS = (
    ('벽이 보이는 프레임', lambda o: f"{o['visible_frames']}"),
    ('0검출 프레임 (보이는 프레임 중)', lambda o: f"{o['zero_recall_frames']} ({o['zero_recall_frames']/o['visible_frames']:.1%})"),
    ('열 recall (보이는 열 중 접촉 보고)', lambda o: f"{o['column_recall']:.3f}"),
    ('열 recall, 시험 가능 열만 (정답 접촉 행 ≥ 10: 위쪽 band가 프레임에 들어가는 열)', lambda o: f"{o['testable_column_recall']:.3f}"),
    ('정확한 접촉(행 오차 절댓값 ≤ 3 px) 비율 = precision', lambda o: f"{o['precision']:.3f}"),
    ('정확 열 recall', lambda o: f"{o['correct_column_recall']:.3f}"),
    ('정확한 접촉이 0인 보이는 프레임', lambda o: f"{o['zero_correct_frames']}"),
    ('거짓 검출: 안 보이는 프레임 중 접촉이 있는 프레임 / 접촉 수', lambda o: f"{o['fp_frames_with_contact']}/{o['fp_frames']} 프레임, {o['fp_contacts']} 접촉"),
    ('거짓 검출: 면(segment) 수', lambda o: f"{o['fp_segments']}"),
    ('행 오차 px, 프레임 중앙값의 중앙값 (p10…p90)', lambda o: fmt(o['row_err_px_per_frame'], 2)),
    ('행 오차 px, 열 단위 (p10…p90)', lambda o: fmt(o['row_err_px_per_column'], 2)),
    ('거리 오차 m, 프레임 중앙값의 중앙값 (p10…p90)', lambda o: fmt(o['range_err_m_per_frame'], 3)),
    ('거리 오차 m, 열 단위 (p10…p90)', lambda o: fmt(o['range_err_m_per_column'], 3)),
)


def fmt(d, nd):
    return f"{d['median']:+.{nd}f} ({d['p10']:+.{nd}f} … {d['p90']:+.{nd}f}), n={d['n']}"


def markdown(runs):
    names = list(runs)
    lines = ['| 항목 | ' + ' | '.join(names) + ' |', '|---|' + '---|'*len(names)]
    for label, f in ROWS:
        lines.append(f'| {label} | ' + ' | '.join(f(runs[n]) for n in names) + ' |')
    return '\n'.join(lines)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', action='append', required=True, help='label=run_dir (repeat)')
    ap.add_argument('--variant', default='mask_on', choices=('mask_off', 'mask_on'))
    ap.add_argument('--json', default='')
    a = ap.parse_args()
    runs = {}
    for item in a.run:
        label, d = item.split('=', 1)
        runs[label] = summarize(Path(d), a.variant)
    print(markdown(runs))
    if a.json:
        Path(a.json).write_text(json.dumps(runs, indent=2))
