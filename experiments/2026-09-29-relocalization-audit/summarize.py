"""Stage tables of structure-pixel fractions from audit_run.py output (frames.jsonl.gz). Read-only.

usage: python summarize.py <frames.jsonl.gz> <summary.json>
"""
import gzip
import json
import sys
from collections import defaultdict

import numpy as np

GROUPS = [
    # (key, label, predicate)
    ('align_start', '정렬 시작', lambda r: r['stage'] == 'align' and r['phase'] == 'align_start'),
    ('align_relook', '정렬 중 재확인 스윕(보조)', lambda r: r['stage'] == 'align' and r['phase'] == 'align_relook'),
    ('align_body', '정렬 진행(보조)', lambda r: r['stage'] == 'align' and r['phase'] == 'align_body'),
    ('pregrasp', '파지 직전 접근(보조)', lambda r: r['stage'] == 'grasp_lift' and r['phase'] in ('pregrasp', 'grasp_close')),
    ('lift_done', '들기 직후', lambda r: r['stage'] == 'grasp_lift' and r['phase'] == 'lift_done'),
] + [
    (f'carry_L{k}', f'운반 L{k}', (lambda k: lambda r: r['stage'] == 'carry' and r['phase'] == 'carry' and r['leg'] == k)(k))
    for k in range(8)
] + [
    ('carry_all', '운반 전체(L0-L7)', lambda r: r['stage'] == 'carry' and r['phase'] == 'carry'),
    ('carry_door', '문 통과 구간(운반 중, |x-2.2|<0.6 & -0.45<y<0.55)',
     lambda r: r['stage'] == 'carry' and r['phase'] == 'carry' and r['door_zone']),
    ('carry_leg_end', '운반 leg 끝(내려놓기 대기)', lambda r: r['stage'] == 'carry' and r['phase'] == 'carry_leg_end'),
    ('setdown_lowering', '내려놓는 중(보조)', lambda r: r['stage'] == 'setdown' and r['phase'] == 'setdown_lowering'),
    ('setdown_after_lower', '내려놓기 직후(빔 바닥, 그립퍼 닫힘)', lambda r: r['stage'] == 'setdown' and r['phase'] == 'setdown_after_lower'),
    ('open_0_2s', '그립퍼 연 뒤 0-2 s', lambda r: r['stage'] == 'setdown' and r['phase'] == 'open_0_2s'),
    ('open_2s_plus', '그립퍼 연 뒤 2 s 이후(후진·둘러보기)', lambda r: r['stage'] == 'setdown' and r['phase'] == 'open_2s_plus'),
]


def stat(x, scale=100.):
    x = np.asarray(x, float)
    if not len(x):
        return None
    return {'median': round(float(np.median(x)) * scale, 2), 'p10': round(float(np.percentile(x, 10)) * scale, 2),
            'min': round(float(x.min()) * scale, 2), 'mean': round(float(x.mean()) * scale, 2)}


def summarize(rows, robots=('r1', 'r2')):
    out = {}
    for key, label, pred in GROUPS:
        sel = [r for r in rows if pred(r) and r['robot'] in robots]
        if not sel:
            out[key] = {'label': label, 'n_frames': 0}
            continue
        d = {'label': label, 'n_frames': len(sel), 'n_cases': len({(r['run'], r['case']) for r in sel}),
             'V_pct': stat([r['V'] for r in sel]), 'G_pct': stat([r['G'] for r in sel]), 'R_pct': stat([r['R'] for r in sel]),
             'V_post_pct': stat([r['V_post'] for r in sel]), 'tag_geom_pct': stat([r['tag_geom'] for r in sel]),
             'beam_pct': stat([r['beam'] for r in sel]), 'dark_pct': stat([r['dark'] for r in sel]),
             'cols_V': {'median': float(np.median([r['cols_V'] for r in sel])), 'p10': float(np.percentile([r['cols_V'] for r in sel], 10)),
                        'min': float(min(r['cols_V'] for r in sel))},
             'frac_V_lt_1pct': round(float(np.mean([r['V'] < .01 for r in sel])), 3),
             'frac_V_ge_3pct': round(float(np.mean([r['V'] >= .03 for r in sel])), 3),
             'frac_V_ge_5pct': round(float(np.mean([r['V'] >= .05 for r in sel])), 3)}
        # per-case medians (each case = one independent staging), guards against long cases dominating
        cm = defaultdict(list)
        for r in sel:
            cm[(r['run'], r['case'], r['robot'])].append(r['V'])
        d['V_case_median_pct'] = stat([np.median(v) for v in cm.values()])
        d['n_case_robots'] = len(cm)
        d['by_robot_V_median_pct'] = {rid: (stat([r['V'] for r in sel if r['robot'] == rid]) or {}).get('median') for rid in robots}
        out[key] = d
    return out


def by_pan(rows):
    """Unloaded-look phases: V by issued pan pulse (rounded to 50 PWM ~ 4.5 deg)."""
    out = {}
    for key in ('align_start', 'align_relook', 'open_0_2s', 'open_2s_plus'):
        g = defaultdict(list)
        for r in rows:
            if r['phase'] == key and r['stage'] in ('align', 'setdown') and r.get('servo') and '6' in r['servo']:
                g[int(round(r['servo']['6'] / 100.) * 100)].append(r['V'])
        out[key] = {str(k): {'n': len(v), 'V_median_pct': round(float(np.median(v)) * 100, 2), 'V_p10_pct': round(float(np.percentile(v, 10)) * 100, 2)}
                    for k, v in sorted(g.items()) if len(v) >= 20}
    return out


def main(frames, dest):
    rows = [json.loads(l) for l in gzip.open(frames, 'rt')]
    default = [r for r in rows if r['profile'] is None]
    alt = [r for r in rows if r['profile'] is not None]
    res = {'schema': 'ugrp.relocalization_audit.summary.v1', 'rows_total': len(rows), 'rows_default_profile': len(default),
           'rows_floor_light_v1': len(alt), 'default_profile': summarize(default), 'floor_light_v1_sensitivity': summarize(alt), 'by_pan_default_profile': by_pan(default)}
    json.dump(res, open(dest, 'w'), indent=1)
    for k, v in res['default_profile'].items():
        if v['n_frames']:
            print(f"{k:20s} n={v['n_frames']:6d} cases={v['n_cases']:4d} V med {v['V_pct']['median']:5.2f} p10 {v['V_pct']['p10']:5.2f} min {v['V_pct']['min']:5.2f} | G med {v['G_pct']['median']:5.2f} | R med {v['R_pct']['median']:5.2f} | cols med {v['cols_V']['median']:.0f}")
        else:
            print(k, 'no frames')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
