"""Markdown tables of the cohort for the README (reads analysis/results.json + consistency.json; prints to stdout).

usage: python report_tables.py <analysis_dir> [--summary]   (results.json in <analysis_dir> may be gzip-compressed: results.json.gz)
"""
import json
import sys
from pathlib import Path

LABELS = ['start', 'after_L0', 'after_L1', 'after_L2', 'after_L3', 'after_L4', 'after_L5', 'after_L6', 'after_L7']


def load(d):
    d = Path(d)
    if (d / 'results.json').exists():
        return json.loads((d / 'results.json').read_text())
    import gzip
    return json.loads(gzip.open(d / 'results.json.gz', 'rt').read())


def summary(d):
    r = load(d)
    print('| 구성 (프로필/관측/prior/자세) | 체크포인트 1..7 판정 | 7곳 판정 | 풀링 위치 p50/p90 (cm) | 풀링 방향 p50/p90 (deg) | 실패 | 표시 | 조용한 실패 |')
    print('|---|---|---|---|---|---:|---:|---:|')
    for key, e in r.items():
        m = e['pooled']['SY']['mid_checkpoints']
        tiers = ' '.join(e['checkpoints'][f'cp{k}'] for k in range(1, 8))
        print(f"| {key} | {tiers} | **{e['verdict_mid_checkpoints']}** | {100*m['pos_p50']:.1f} / {100*m['pos_p90']:.1f} | {m['yaw_p50']:.2f} / {m['yaw_p90']:.2f} | "
              f"{100*m['fail_rate']:.1f}% | {100*m['flagged_rate']:.1f}% | {100*m['silent_fail_rate']:.1f}% |")


def main(d):
    r = load(d)
    for key in ('default|vision|wide|p20', 'default|vision|wide|search', 'floor_light_v1|vision|wide|p20', 'floor_light_v1|vision|wide|search',
                'default|oracle|wide|p20', 'default|vision|tight|p20'):
        if key not in r:
            continue
        e = r[key]
        print(f'\n### {key}  (S+Y 48 runs per row; mid = checkpoints 1..7)\n')
        print('| cp | 지점 | 로봇 | 시작 오차 p90 (cm / deg) | 위치 p50 / p90 (cm) [p90 95% 구간] | 방향 p50 / p90 (deg) [p90 구간] | 실패 | 표시 | 조용한 실패 | σ_xy / σ_yaw 보고 | 판정 |')
        print('|---:|---|---|---|---|---|---:|---:|---:|---|---|')
        for cp in range(9):
            for rid in ('r1', 'r2'):
                s = e['groups'].get(f'SY|cp{cp}|{rid}')
                if not s:
                    continue
                print(f"| {cp} | {LABELS[cp]} | {rid} | {100*s['start_pos_p90']:.1f} / {s['start_yaw_p90']:.1f} | {100*s['pos_p50']:.1f} / {100*s['pos_p90']:.1f} [{100*s['pos_p90_ci95'][0]:.1f}–{100*s['pos_p90_ci95'][1]:.1f}] | "
                      f"{s['yaw_p50']:.2f} / {s['yaw_p90']:.2f} [{s['yaw_p90_ci95'][0]:.2f}–{s['yaw_p90_ci95'][1]:.2f}] | {100*s['fail_rate']:.0f}% | {100*s['flagged_rate']:.0f}% | {100*s['silent_fail_rate']:.0f}% | "
                      f"{100*s['std_xy_mean']:.1f} cm / {s['std_yaw_mean_deg']:.2f} | {s['tier']} |")
        print('\n체크포인트 판정(두 로봇 중 나쁜 쪽):', ', '.join(f'{k[2:]}={v}' for k, v in e['checkpoints'].items()), f"→ 운반 구간 사이 7곳 판정 **{e['verdict_mid_checkpoints']}**", e['n_mid_checkpoints_tier'])
        for pop in ('SY', 'S', 'Y', 'L'):
            if pop in e['pooled']:
                m = e['pooled'][pop]['mid_checkpoints']
                print(f"- 풀링 {pop}(7곳, n={m['n']}): 시작 오차 p90 {100*m['start_pos_p90']:.1f} cm / {m['start_yaw_p90']:.2f}° → 위치 p50/p90/p99/최대 {100*m['pos_p50']:.1f}/{100*m['pos_p90']:.1f}/{100*m['pos_p99']:.1f}/{100*m['pos_max']:.1f} cm, "
                      f"방향 p50/p90/p99/최대 {m['yaw_p50']:.2f}/{m['yaw_p90']:.2f}/{m['yaw_p99']:.2f}/{m['yaw_max']:.2f}°, RMS {100*m['pos_rms']:.2f} cm / {m['yaw_rms']:.2f}°, 실패 {100*m['fail_rate']:.1f}%, 표시 {100*m['flagged_rate']:.1f}%, 조용한 실패 {100*m['silent_fail_rate']:.1f}%")
        print('- pan 프레임 수별(S+Y, 7곳) 위치 p90 / 방향 p90 / 실패:', '; '.join(f"{k}장 {100*v['pos_p90']:.1f} cm / {v['yaw_p90']:.2f}° / {100*v['fail_rate']:.0f}%" for k, v in e['sweep_length_mid_checkpoints_SY'].items()))


if __name__ == '__main__':
    summary(sys.argv[1]) if '--summary' in sys.argv else main(sys.argv[1])
