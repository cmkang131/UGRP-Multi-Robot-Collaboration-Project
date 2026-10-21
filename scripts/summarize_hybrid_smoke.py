"""Per-world table for a hybrid code-carry smoke (teacher near field + code carry + teacher place; not learned).

Reads only files the runner wrote: <run>/summary.json, world-XXX/raw/{result.json, carry-eval.json,
hybrid-drive.jsonl} (``.zst`` decoded). Answers HYBRID_RUN.md §8 risks 2-3 from the smoke itself:
does the code pass the door and reach zone B, does the beam/partner hide zone B, is the gate camera
projection right in the loaded pose. Counts are n/N per world list; nothing is pooled with other runs.

    python scripts/summarize_hybrid_smoke.py --run <smoke-dir> [--run ...] --out <dir>
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from collections import Counter
from pathlib import Path

SCHEMA = 'ugrp.pairact.hybrid_smoke_summary.v1'
LABEL = 'teacher 근거리 + 코드 운반, 학습 아님'


def read_bytes(path):
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    z = Path(str(path) + '.zst')
    if z.is_file():
        return subprocess.check_output(['zstd', '-qdc', str(z)])
    return None


def read_json(path):
    b = read_bytes(path)
    return None if b is None else json.loads(b)


def read_jsonl(path):
    b = read_bytes(path)
    return [] if b is None else [json.loads(x) for x in b.decode().splitlines() if x.strip()]


def _stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {'n': len(xs), 'median': statistics.median(xs), 'max': max(xs), 'min': min(xs)}


def world(run, entry):
    raw = run/f"world-{entry['world']:03d}"/'raw'
    res = read_json(raw/'result.json') or {}
    ev = read_json(raw/'carry-eval.json') or res.get('carry_eval') or {}
    hs = res.get('hybrid_smoke') or {}
    log = read_jsonl(raw/'hybrid-drive.jsonl')
    by_phase = {}
    for r in log:
        k = r.get('planner_phase') or r.get('segment')
        d = by_phase.setdefault(k, {'ticks': 0, 'zone_seen': 0, 'visible_frac': [], 'beam_blocked': [], 'in_fov': []})
        d['ticks'] += 1; d['zone_seen'] += bool(r.get('zone_seen'))
        occ = (r.get('eval_only') or {}).get('occlusion')
        if occ:
            d['visible_frac'].append(occ.get('visible_frac_of_fov'))
            d['beam_blocked'].append(occ['blocked_by_beam']/occ['in_fov'] if occ.get('in_fov') else None)
            d['in_fov'].append(occ.get('in_fov'))
    phases = {k: {'ticks': d['ticks'], 'zone_seen_frac': d['zone_seen']/d['ticks'],
                  'gt_visible_frac_of_fov': _stats(d['visible_frac']), 'gt_beam_blocked_frac': _stats(d['beam_blocked']),
                  'gt_zone_points_in_fov': _stats(d['in_fov'])} for k, d in by_phase.items()}
    mounts = [(r.get('eval_only') or {}).get('camera_mount') for r in log]
    proj = [(r.get('eval_only') or {}).get('projection') for r in log]
    funnel = ev.get('funnel') or {}
    return {'run': run.name, 'world': entry['world'], 'seed': entry.get('seed'), 'status': res.get('status'),
            'error_type': res.get('error_type'), 'grasp_success': bool(entry.get('success')),
            'code_started': hs.get('segment') not in (None, 'STUDENT_GRASP'),
            'code_outcome': (res.get('carry') or {}).get('code_outcome') or hs.get('outcome'),
            'handback_sim_s': hs.get('handback_sim_s'), 'code_segment_s': hs.get('code_segment_s'),
            'place_outcome': ((res.get('carry') or {}).get('place_teacher') or {}).get('outcome'),
            'carry_success': bool(ev.get('success')), 'carry_failure': ev.get('failure'),
            'through_door': funnel.get('door_passed'), 'in_zone': funnel.get('zone_inside_final'),
            'funnel': funnel, 'gt_inputs_to_code': hs.get('gt_inputs_to_code'),
            'calibration_values_sha256': hs.get('calibration_values_sha256'),
            'camera_height_m': _stats([m.get('height_m') for m in mounts if m]),
            'camera_pitch_down_deg': _stats([m.get('pitch_down_deg') for m in mounts if m]),
            'camera_yaw_rel_deg': _stats([m.get('yaw_rel_deg') for m in mounts if m]),
            'projection_error_m': _stats([p.get('error_m') for p in proj if p]),
            'camera_unavailable_ticks': sum(bool((r.get('eval_only') or {}).get('camera_unavailable')) for r in log),
            'phases': phases, 'code_ticks': len(log)}


def markdown(rep):
    L = [f'# hybrid 코드 운반 smoke 요약 ({LABEL})', '',
         f"- world {rep['n']}: 코드 운반 시작 {rep['counts']['code_started']}/{rep['n']}, 반환(handed_back) "
         f"{rep['counts']['handed_back']}/{rep['n']}, 문 통과 {rep['counts']['through_door']}/{rep['n']}, "
         f"운반 성공 {rep['counts']['carry_success']}/{rep['n']} (n/N, 합산 금지)",
         f"- 코드 결과: {dict(rep['code_outcomes'])}", '',
         '| world | seed | 파지 | 코드 결과 | 문 | zone | 성공/실패 | 코드 s | 카메라 높이 med | 피치 med | 투영 오차 med/max m | '
         'acquire zone 검출률 | acquire GT 가시율 med | 빔 가림 med |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    f = lambda s, k='median', d=3: '-' if not s else format(s[k], f'.{d}f')  # noqa: E731
    for w in rep['worlds']:
        a = w['phases'].get('acquire') or {}
        L.append(f"| {w['world']} | {w['seed']} | {w['grasp_success']} | {w['code_outcome']} | {w['through_door']} | "
                 f"{w['in_zone']} | {w['carry_success']}/{w['carry_failure']} | "
                 f"{'-' if w['code_segment_s'] is None else format(w['code_segment_s'], '.1f')} | "
                 f"{f(w['camera_height_m'])} | {f(w['camera_pitch_down_deg'], d=1)} | "
                 f"{f(w['projection_error_m'])}/{f(w['projection_error_m'], 'max')} | "
                 f"{'-' if not a else format(a['zone_seen_frac'], '.2f')} | "
                 f"{f(a.get('gt_visible_frac_of_fov'), d=2) if a else '-'} | {f(a.get('gt_beam_blocked_frac'), d=2) if a else '-'} |")
    L += ['', '판단 규칙(HYBRID_SMOKE.md §6): 문 검출기 없음 위험은 `through_door`와 `code_outcome`로, 빔 가림 위험은 '
          'acquire의 검출률·GT 가시율·빔 가림으로, 투영 위험은 투영 오차와 카메라 높이·피치로 봅니다.']
    return '\n'.join(L) + '\n'


def summarize(runs):
    worlds = []
    for run in runs:
        s = read_json(run/'summary.json')
        if s is None:
            raise SystemExit(f'MISSING_SUMMARY: {run}/summary.json')
        worlds += [world(run, e) for e in s.get('worlds') or []]
    n = len(worlds)
    counts = {'code_started': sum(w['code_started'] for w in worlds),
              'handed_back': sum(w['code_outcome'] == 'handed_back' for w in worlds),
              'through_door': sum(bool(w['through_door']) for w in worlds),
              'carry_success': sum(w['carry_success'] for w in worlds)}
    return {'schema': SCHEMA, 'label': LABEL, 'labels': ['teacher_near_field', 'code_carry', 'teacher_place',
                                                         'not_learned', 'not_pooled'],
            'n': n, 'counts': counts, 'code_outcomes': Counter(w['code_outcome'] for w in worlds), 'worlds': worlds}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run', type=Path, action='append', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    rep = summarize(a.run)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/'hybrid-smoke-summary.json').write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    (a.out/'hybrid-smoke-summary.md').write_text(markdown(rep))
    print(json.dumps({'n': rep['n'], **rep['counts']}, ensure_ascii=False))
    return rep


if __name__ == '__main__':
    main()
