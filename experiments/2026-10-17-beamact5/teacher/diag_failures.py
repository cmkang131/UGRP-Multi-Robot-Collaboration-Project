"""Read-only diagnostics for beamact5 teacher-gate failure worlds.

Runs on the run VM against the raw gate directory. Prints one compact JSON
object per world: outcome, per-role phase timeline, search/planning counters,
handoff/clearance evidence. No physics, no writes except stdout.
"""
import argparse
import json
import subprocess
from pathlib import Path

ZSTD = 'zstd -dc'


def raw_path(path):
    """Some worlds keep the artifact uncompressed; accept either form."""
    plain = Path(str(path)[:-4]) if str(path).endswith('.zst') else path
    if plain.is_file() and not Path(str(plain) + '.zst').is_file():
        return plain
    return Path(str(plain) + '.zst')


def load_zst(path):
    path = raw_path(path)
    if str(path).endswith('.zst'):
        out = subprocess.run(f'{ZSTD} {str(path)!r}', shell=True, check=True,
                             capture_output=True).stdout
        return json.loads(out)
    return json.loads(path.read_text())


def transitions(teacher):
    return [e for e in teacher.get('events', []) if 'to' in e]


def stage_counts(teacher):
    counts = {}
    for e in teacher.get('events', []):
        if 'stage' in e:
            key = f"{e['stage']}:{e.get('search', '')}"
            counts[key] = counts.get(key, 0) + 1
    return counts


def first_time(teacher, phase):
    for e in transitions(teacher):
        if e.get('to') == phase:
            return e.get('t')
    return None


def small(value, depth=0, max_depth=3):
    if depth >= max_depth:
        if isinstance(value, dict):
            return {'keys': sorted(value)[:20]}
        if isinstance(value, list):
            return {'n': len(value)}
    if isinstance(value, dict):
        return {k: small(v, depth + 1, max_depth) for k, v in value.items()
                if not isinstance(v, (list,)) or len(v) <= 6}
    if isinstance(value, list):
        if len(value) <= 6:
            return [small(v, depth + 1, max_depth) for v in value]
        return {'n': len(value), 'head': small(value[0], depth + 1, max_depth)}
    return value


RESULT_KEYS = [
    'teacher_search', 'approach_goal_set', 'nominal_blocked_handoff',
    'approach_progress', 'approach_recovery', 'approach_coordination',
    'handoff_observation', 'pregrasp_sampling', 'obstacle_reobserve',
    'peer_reobserve', 'search23', 'search24_budget', 'search25_budget',
    'search25_view', 'search25_inflation', 'search25_memory',
    'search_handoff', 'approach_handoff', 'start_nominal_goal_feasible',
    'cap_end', 'end_reason', 'criteria',
]


def world_summary(run_root, world):
    wdir = run_root / f'world-{world:03d}'
    data = load_zst(wdir / 'adapter' / 'beampair1-result.json.zst')
    result = data['result']
    summary = {
        'world': world,
        'end_reason': result.get('end_reason'),
        'sim_s': result.get('sim_s'),
        'wall_s': result.get('wall_s'),
        'cap_end': result.get('cap_end'),
        'physical_success': result.get('physical_success'),
        'peer_rendezvous': data.get('peer_rendezvous'),
        'peer_yield': data.get('peer_yield'),
        'first_close_t': data.get('first_close_t'),
        'teachers': {},
        'fields': {k: small(result.get(k)) for k in RESULT_KEYS},
    }
    for role in ('r1', 'r2'):
        t = result.get('teachers', {}).get(role, {})
        summary['teachers'][role] = {
            'phase': t.get('phase'), 'outcome': t.get('outcome'),
            'visibility': t.get('visibility_counts'),
            'max_unseen_before_pick_s': t.get('max_unseen_before_pick_s'),
            'ik_rejections': t.get('ik_rejections'),
            'first': {p: first_time(t, p)
                      for p in ('search', 'approach', 'align', 'ready', 'pick',
                                'complete')},
            'n_transitions': len(transitions(t)),
            'last_transitions': transitions(t)[-14:],
            'stage_counts': stage_counts(t),
        }
    # command ledger: phase durations and last rows
    ledger_path = raw_path(wdir / 'adapter' / 'beampair1-commands.jsonl.zst')
    rows = []
    if str(ledger_path).endswith('.zst'):
        stream = subprocess.Popen(f'{ZSTD} {str(ledger_path)!r}', shell=True,
                                  stdout=subprocess.PIPE, text=True).stdout
    else:
        stream = ledger_path.open()
    for line in stream:
        rows.append(json.loads(line))
    by_role = {}
    for role in ('r1', 'r2'):
        rr = [r for r in rows if r.get('robot_id') == role]
        if not rr:
            continue
        phase_time = {}
        for a, b in zip(rr, rr[1:]):
            dt = b['t'] - a['t']
            phase_time[a.get('phase_after')] = phase_time.get(a.get('phase_after'), 0.0) + dt
        by_role[role] = {
            'rows': len(rr),
            'visible_rows': sum(1 for r in rr if r.get('target_visible')),
            'phase_time_s': {k: round(v, 3) for k, v in sorted(phase_time.items())},
            'last': rr[-1],
        }
    summary['ledger'] = by_role
    # wall layer output
    wall_path = raw_path(wdir / 'adapter' / 'wall-layer.json.zst')
    if wall_path.is_file():
        summary['wall_layer'] = small(load_zst(wall_path), max_depth=2)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('run_root', type=Path)
    ap.add_argument('worlds', type=int, nargs='+')
    args = ap.parse_args()
    for world in args.worlds:
        print(json.dumps(world_summary(args.run_root, world), ensure_ascii=False))


if __name__ == '__main__':
    main()
