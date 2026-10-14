"""Replay exact archived own RGB and own commands, never synthesize evidence.

Run again after operations retrieves fetch-requests/crate4.txt. Missing images
remain unverified in the fixed 8/24/8 denominators. No simulator is imported.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from PIL import Image
from sim.crate_rgb_lift import confirm_v2, confirm_v3

A = (77208, 77209, 77212, 77213, 77224, 77225, 77228, 77229)
B = (77204, 77207, 77210, 77216, 77218, 77221, 77231, 77234)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def issued_lift_commands(records, start, stop):
    """Release rows share the final capture time but are not observer inputs."""
    return [r['applied_command'] for r in records
            if r['skill'] != 'release' and start-1e-8 <= r['t'] <= stop+1e-8]


def pair_verdict(verdicts):
    """Match the two-confirmation release rule; missing evidence stays unknown."""
    if len(verdicts) == 2 and all(v == 'confirmed' for v in verdicts):
        return 'confirmed'
    if 'not_confirmed' in verdicts:
        return 'not_confirmed'
    return 'undetermined'


def counts(verdicts):
    return {'N': len(verdicts), **{v: verdicts.count(v) for v in
            ('confirmed', 'not_confirmed', 'undetermined')}}


def verify_fetch_request(path, root):
    """Verify hash rows; retain operator completion notes separately."""
    verified, notes = [], []
    for line in path.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        if not re.match(r'^[0-9a-f]{64}\s+', line):
            notes.append(line)
            continue
        sha, remote = line.split(None, 1)
        rel = Path(remote).relative_to('/home/ugrp/ugrp-sim/runs')
        local = root/rel
        if not local.is_file() or digest(local) != sha:
            raise ValueError(f'fetch hash mismatch or missing: {local}')
        verified.append({'relative_path': str(rel), 'sha256': sha})
    if not verified:
        raise ValueError('empty fetch request')
    return {'request': str(path), 'request_sha256': digest(path), 'N': len(verified),
            'matched': len(verified), 'operator_notes': notes, 'files': verified}


def replay_negative_controls(path):
    """Separate older 0.9 kg failed lifts, sampled at recorded review times."""
    rows = json.loads(path.read_text())
    for row in rows:
        raw = Path(row['raw'])
        result = json.loads((raw/'result.json').read_text())
        manifest = json.loads((raw/'manifest.json').read_text())
        if digest(raw/'result.json') != manifest['result.json']['sha256']:
            raise ValueError('negative result hash mismatch')
        if result['prefix']['held_sim_s'] is not None:
            raise ValueError('negative control is not an evaluation-failed lift')
        row['robots'] = {}
        for rid, refs in row['frames'].items():
            cell = {'missing': [r['path'] for r in refs.values() if not (raw/r['path']).exists()]}
            row['robots'][rid] = cell
            if cell['missing']:
                continue
            frames = {}
            for tag, ref in refs.items():
                if digest(raw/ref['path']) != ref['sha256'] or ref['sha256'] != manifest[ref['path']]['sha256']:
                    raise ValueError('negative image hash mismatch')
                frames[tag] = np.array(Image.open(raw/ref['path']).convert('RGB'))
            log = raw/f'teacher-{rid}.jsonl.zst'
            if digest(log) != manifest[log.name]['sha256']:
                raise ValueError('negative command hash mismatch')
            records = [json.loads(s) for s in subprocess.check_output(['zstd', '-dc', str(log)], text=True).splitlines()]
            commands = issued_lift_commands(records, refs['before_lift']['t'], refs['settled_hold']['t'])
            cell['verdict'] = confirm_v3(frames['before_lift'], frames['lift_complete'],
                result['prefix']['assigned'][rid], commands=commands, settled=frames['settled_hold'])
        row['replayed'] = len(row['robots']) == 2 and all('verdict' in c for c in row['robots'].values())
        row['pair_verdict'] = pair_verdict([c.get('verdict', {}).get('verdict', 'undetermined')
                                           for c in row['robots'].values()])
        row['pair_confirmed'] = row['pair_verdict'] == 'confirmed'
    return {'planned_N': len(rows), 'replayed_N': sum(r['replayed'] for r in rows),
            'false_positives': sum(r['pair_confirmed'] for r in rows), 'rows': rows,
            'pair_counts': counts([r['pair_verdict'] for r in rows]),
            'robot_counts': counts([c.get('verdict', {}).get('verdict', 'undetermined')
                                    for r in rows for c in r['robots'].values()]),
            'scope': 'older 0.9 kg negative controls; never pool gate success rates; N=0 is unverified'}


def replay(root):
    rows = []
    for seed in range(77200, 77240):
        raw = root/f'crate-gate-{seed}-6f312f74/raw'
        result = json.loads((raw/'result.json').read_text())
        manifest = json.loads((raw/'manifest.json').read_text())
        prefix = result['prefix']
        source = {}
        for name in ('result.json', 'teacher-r1.jsonl.zst', 'teacher-r2.jsonl.zst', 'eval-only.jsonl.zst'):
            h = digest(raw/name)
            if h != manifest[name]['sha256']:
                raise ValueError(f'hash mismatch: {raw/name}')
            source[name] = h
        row = {'seed': seed, 'family': 'A' if seed in A else 'B' if seed in B else 'success',
               'raw': str(raw), 'sha256': source, 'evaluation_held': prefix['held_sim_s'] is not None,
               'max_stable_hold_s': prefix['max_stable_hold_s'], 'search_handoff': result['search_handoff'],
               'robots': {}, 'v3_pair_confirmed': False, 'exact_rgb_replayed': False}
        for rid, end in prefix['assigned'].items():
            original = prefix['rgb_lift']['per_robot'][rid]
            refs = prefix['rgb_lift']['frames'][rid]
            t = prefix['teachers'][rid]
            cell = {'old_recorded': original, 'frames': refs, 'missing': [],
                    'outcome': t['outcome'], 'visibility': t['visibility_counts'],
                    'planner_calls': t['planner_calls'], 'blocked_goal_calls': t['blocked_goal_calls'],
                    'events': t['events']}
            row['robots'][rid] = cell
            if set(refs) != {'before_lift', 'lift_complete', 'settled_hold'}:
                cell['status'] = 'no_lift_frame_sequence'; continue
            frames = {}
            for tag, ref in refs.items():
                path = raw/ref['path']
                if not path.exists():
                    cell['missing'].append(ref['path']); continue
                if digest(path) != ref['sha256'] or ref['sha256'] != manifest[ref['path']]['sha256']:
                    raise ValueError(f'image hash mismatch: {path}')
                frames[tag] = np.array(Image.open(path).convert('RGB'))
            if cell['missing']:
                cell['status'] = 'awaiting_original_images'; continue
            records = [json.loads(line) for line in subprocess.check_output(
                ['zstd', '-dc', str(raw/f'teacher-{rid}.jsonl.zst')], text=True).splitlines()]
            commands = issued_lift_commands(records, refs['before_lift']['t'], refs['settled_hold']['t'])
            args = (frames['before_lift'], frames['lift_complete'], end)
            kw = {'commands': commands, 'settled': frames['settled_hold']}
            cell['v2_replay'] = confirm_v2(*args, **kw)
            if cell['v2_replay'] != original:
                raise ValueError(f'v2 replay does not match {seed}/{rid}')
            cell['v3_replay'] = confirm_v3(*args, **kw)
            # Counterfactual stalled view: retain real issued lift commands,
            # replace BOTH post-lift images with the archived pre-lift frame.
            # This is a negative image control, not another physical episode.
            cell['prelift_control'] = confirm_v3(frames['before_lift'], frames['before_lift'], end,
                commands=commands, settled=frames['before_lift'])
            cell['status'] = 'exact_rgb_replayed'
        row['exact_rgb_replayed'] = all(c['status'] == 'exact_rgb_replayed' for c in row['robots'].values())
        row['v3_pair_confirmed'] = row['exact_rgb_replayed'] and all(
            c['v3_replay']['verdict'] == 'confirmed' for c in row['robots'].values())
        row['v3_pair_verdict'] = pair_verdict([c.get('v3_replay', {}).get('verdict', 'undetermined')
                                              for c in row['robots'].values()])
        rows.append(row)
    groups = {}
    for label in ('B', 'success', 'A'):
        rs = [r for r in rows if r['family'] == label]
        groups[label] = {'N': len(rs), 'exact_rgb_replayed': sum(r['exact_rgb_replayed'] for r in rs),
                         'v3_confirmed': sum(r['v3_pair_confirmed'] for r in rs),
                         'pair_counts': counts([r['v3_pair_verdict'] for r in rs]),
                         'robot_counts': counts([c.get('v3_replay', {}).get('verdict', 'undetermined')
                                                for r in rs for c in r['robots'].values()])}
    controls = [r for r in rows if r['family'] in ('B', 'success')]
    control_pairs = [pair_verdict([c.get('prelift_control', {}).get('verdict', 'undetermined')
                                  for c in r['robots'].values()]) for r in controls]
    negatives = [r for r in rows if not r['evaluation_held'] and r['exact_rgb_replayed']]
    return {'schema': 'crate4.offline.v2', 'baseline_sha': '6f312f74f25e284f9339a18de901e24667c17a31',
            'host': 'gcp1 n4-highcpu-64', 'groups': groups,
            'prelift_controls': {'planned_N': len(controls),
                'replayed_N': sum(r['exact_rgb_replayed'] for r in controls),
                'false_positives': control_pairs.count('confirmed'), 'pair_counts': counts(control_pairs),
                'robot_counts': counts([c.get('prelift_control', {}).get('verdict', 'undetermined')
                                       for r in controls for c in r['robots'].values()]),
                'scope': 'all 32 attempted lifts; both post frames replaced by own before_lift; real commands unchanged; image controls, not physical runs'},
            'false_positives': {'n': sum(r['v3_pair_confirmed'] for r in negatives), 'N': len(negatives),
                                'scope': 'only exact attempted-lift RGB sequences; no claim when N=0'},
            'rows': rows, 'new_gcp_runs': 0, 'simulation_steps': 0, 'render_calls': 0}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--negative-sequences', type=Path)
    p.add_argument('--fetch-request', type=Path)
    p.add_argument('--require-ready', action='store_true', help='exit 2 unless every requested exact replay/control passed')
    args = p.parse_args()
    result = replay(args.root)
    if args.negative_sequences:
        result['negative_controls'] = replay_negative_controls(args.negative_sequences)
    if args.fetch_request:
        result['fetch_verification'] = verify_fetch_request(args.fetch_request, args.root)
    result['analysis_source'] = {str(p): digest(p) for p in
                                (Path(__file__), Path('sim/crate_rgb_lift.py'))}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k in ('groups', 'false_positives', 'prelift_controls')}))
    if args.require_ready:
        positive = all(result['groups'][group]['v3_confirmed'] == result['groups'][group]['N']
                       for group in ('B', 'success'))
        negative = result.get('negative_controls', {})
        control = result['prelift_controls']
        if not (positive and negative.get('replayed_N', 0) > 0 and
                negative['replayed_N'] == negative['planned_N'] and negative['false_positives'] == 0 and
                control['replayed_N'] == control['planned_N'] and control['false_positives'] == 0):
            raise SystemExit(2)


if __name__ == '__main__':
    main()
