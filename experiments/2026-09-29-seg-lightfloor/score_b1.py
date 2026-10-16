"""Per-checkpoint score of B1-protocol runs (numpy).  Pre-fixed pass criterion of this task (per checkpoint, both robots):
position p90 <= 5 cm AND yaw p90 <= 2 deg (S+Y start errors, 48 runs per robot).  B1's own tier (A/B/X, which also needs fail <= 10 % and
silent <= 5 %) is printed next to it.

usage: score_b1.py <runs.jsonl> [<runs.jsonl> ...] [--json out.json] [--look p20]
"""
import argparse, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'experiments' / '2026-09-29-carry-relocalization-b1'))
import analyze  # noqa: E402  (B1, unchanged)
import numpy as np


def score(paths, look='p20'):
    runs = analyze.load_runs(paths)
    res = analyze.summarize([r for r in runs if r['look'] == look])
    out = {}
    for key, e in res.items():
        cps = {}
        for cp in sorted({int(k.split('|')[1][2:]) for k in e['groups'] if k.startswith('SY|')}):
            g = [e['groups'][f'SY|cp{cp}|{rid}'] for rid in ('r1', 'r2') if f'SY|cp{cp}|{rid}' in e['groups']]
            pos = max(x['pos_p90'] for x in g); yaw = max(x['yaw_p90'] for x in g)
            cps[cp] = {'pos_p90_cm': round(100 * pos, 2), 'yaw_p90_deg': round(yaw, 2), 'fail_rate': max(x['fail_rate'] for x in g),
                       'flagged_rate': max(x['flagged_rate'] for x in g), 'tier': e['checkpoints'][f'cp{cp}'], 'n': sum(x['n'] for x in g),
                       'pass': bool(pos <= 0.05 and yaw <= 2.0)}
        pooled = e['pooled']['SY']['mid_checkpoints']
        out[key] = {'checkpoints': cps, 'n_pass_all9': sum(c['pass'] for c in cps.values()), 'n_pass_mid7': sum(c['pass'] for k, c in cps.items() if 1 <= k <= 7),
                    'n_cp': len(cps), 'pooled_mid': {k: round(v, 4) if isinstance(v, float) else v for k, v in pooled.items() if k in ('n', 'pos_p50', 'pos_p90', 'yaw_p50', 'yaw_p90', 'fail_rate', 'flagged_rate', 'silent_fail_rate')}}
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('runs', nargs='+'); ap.add_argument('--json'); ap.add_argument('--look', default='p20')
    a = ap.parse_args()
    out = score(a.runs, a.look)
    for key, e in out.items():
        print(f'== {key}: pass {e["n_pass_all9"]}/{e["n_cp"]} (mid 1..7: {e["n_pass_mid7"]}/{sum(1 for k in e["checkpoints"] if 1 <= k <= 7)})  pooled mid pos p50/p90 {100*e["pooled_mid"].get("pos_p50",float("nan")):.1f}/{100*e["pooled_mid"].get("pos_p90",float("nan")):.1f} cm yaw p90 {e["pooled_mid"].get("yaw_p90",float("nan")):.2f} fail {100*e["pooled_mid"].get("fail_rate",float("nan")):.1f}% flagged {100*e["pooled_mid"].get("flagged_rate",float("nan")):.1f}%')
        for cp, c in e['checkpoints'].items():
            print(f'  cp{cp}: pos p90 {c["pos_p90_cm"]:5.1f} cm  yaw p90 {c["yaw_p90_deg"]:5.2f}  fail {100*c["fail_rate"]:3.0f}%  flagged {100*c["flagged_rate"]:3.0f}%  tier {c["tier"]}  {"PASS" if c["pass"] else "fail"}')
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
