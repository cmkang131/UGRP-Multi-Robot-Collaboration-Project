"""Compact per-start acquisition table for the beamact5 wide-start gate."""
import argparse
import json
import subprocess
from pathlib import Path


def load_json(path):
    path = Path(path)
    if str(path).endswith('.zst'):
        return json.loads(subprocess.run(['zstd', '-dc', str(path)], check=True,
                                         capture_output=True).stdout)
    return json.loads(path.read_text())


def result_path(world_dir):
    zst = world_dir / 'raw' / 'result.json.zst'
    return zst if zst.is_file() else world_dir / 'raw' / 'result.json'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_root', type=Path)
    ap.add_argument('plan', type=Path)
    ap.add_argument('--seed0', type=int, default=8420000)
    args = ap.parse_args()
    plan = load_json(args.plan)
    by_seed = {ep['seed']: ep for ep in plan['episodes']}
    rows = []
    for world in range(40):
        seed = args.seed0 + world
        ep = by_seed[seed]
        d = load_json(result_path(args.run_root / f'world-{world:03d}'))
        r = d.get('result', d)
        for role in ('r1', 'r2'):
            t = r['teachers'][role]
            tr = [e for e in t.get('events', []) if 'to' in e]
            seen = [e for e in tr if e.get('to') == 'approach' and e.get('t', 0) > 2.0]
            ready = [e for e in tr if e.get('to') == 'ready']
            start = ep['start_layers'][role]
            rows.append({
                'world': world, 'role': role, 'end': ep['roles'][role],
                'layer': start['layer'],
                'distance_m': start['target_distance_m'],
                'yaw_bin': start['yaw_bin']['index'],
                'phase': t.get('phase'), 'outcome': t.get('outcome'),
                'visibility': t.get('visibility_counts'),
                'max_unseen_before_pick_s': t.get('max_unseen_before_pick_s'),
                'first_approach_after_search_s': seen[0]['t'] if seen else None,
                'first_ready_s': ready[0]['t'] if ready else None,
                'n_transitions': len(tr),
                'search_log_n': len(t.get('search_log') or []),
                'recovery_log_n': len(t.get('recovery_log') or []),
                'recovery_log_tail': (t.get('recovery_log') or [])[-4:],
            })
    print(json.dumps({'run': str(args.run_root), 'rows': rows}, ensure_ascii=False))


if __name__ == '__main__':
    main()
