"""Results table + derived TensorBoard view for the executor smoke v2 (raw results are never modified).

Usage (worktree root, after both smoke-v2 episodes finished):
    python experiments/2026-09-26-zone-own-executor/build_results_v2.py <smoke-v2-dir> [--tensorboard <snapshot>]

Writes ``results_v2.json`` and ``raw_index_v2.json`` next to this file (gates E1-E7 of prereg_v2.json).
With ``--tensorboard`` it exports a NEW snapshot with the six v2 robot-episodes only; the v1 runs stay
in their own snapshot (``0926-zone-own-executor-smoke``) and are shown next to v2 through the view's
run filter (no duplicate conversion). v1 and v2 are separate cohorts and are never pooled.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from build_results import TB, derived, jsonl, robot_row, sha  # noqa: E402

from harness import m1_contract  # noqa: E402

EPISODES = ('smoke-v2-s700', 'smoke-v2-s701')
VERSION = 'v2'                  # build_results_v3.py sets 'v3' and its own EPISODES
EARLIER = {'v1': HERE / 'results.json'}


def gates(smoke):
    rows, per = {}, {}
    for ep in EPISODES:
        d = smoke / ep
        per[ep] = {'result': (d / 'result.json').exists(), 'failure': (d / 'failure.json').exists()}
        if not per[ep]['result']:
            continue
        per[ep].update(r=json.loads((d / 'result.json').read_text()), m=json.loads((d / 'manifest.json').read_text()),
                       events=jsonl(d / 'study' / 'events.jsonl'), api=jsonl(d / 'study' / 'api_calls.jsonl'))
    ok = [ep for ep in EPISODES if per[ep]['result']]
    both = len(ok) == 2
    rows['E1'] = {'pass': both and all(per[e]['r']['host_exception'] is None and not per[e]['failure'] for e in ok),
                  'detail': {e: {'result': per[e]['result'], 'failure_json': per[e]['failure']} for e in EPISODES}}
    e2 = {}
    for e in ok:
        accepted = [a['job_id'] for a in per[e]['api'] if a['accepted'] and a['api'] != 'abort']
        ev = per[e]['events']
        starts = {j: sum(1 for x in ev if x['job_id'] == j and x['event'] == 'job_started') for j in accepted}
        ends = {j: sum(1 for x in ev if x['job_id'] == j and x['event'] in ('job_done', 'job_failed')) for j in accepted}
        e2[e] = {'accepted_jobs': len(accepted), 'starts_ok': all(v == 1 for v in starts.values()),
                 'ends_ok': all(v == 1 for v in ends.values()),
                 'open_jobs_at_end': [j for j, v in ends.items() if v == 0],
                 'episode_end_terminals': sum(1 for x in ev if x['event'] == 'job_failed' and
                                              str(x['detail'].get('reason', '')).startswith('EPISODE_END')),
                 'every_robot_got_deliver': {a['robot_id'] for a in per[e]['api'] if a['accepted'] and
                                             a['api'] == 'deliver'} == {'r1', 'r2', 'r3'}}
    rows['E2'] = {'pass': both and all(v['starts_ok'] and v['ends_ok'] and v['every_robot_got_deliver'] for v in e2.values()),
                  'detail': e2}
    rows['E3'] = {'pass': both and all(rr['foreign_frames_fed'] == 0 and rr['executor_summary']['cameras_seen'] ==
                                       ['robot_cam'] for e in ok for rr in per[e]['r']['robots'].values()),
                  'detail': {e: {k: (v['foreign_frames_fed'], v['executor_summary']['cameras_seen'])
                                 for k, v in per[e]['r']['robots'].items()} for e in ok}}
    rows['E4'] = {'pass': both and all(rr['pose_sources_seen'] and all(s.startswith('owncam_pf_v2:') for s in
                                                                       rr['pose_sources_seen'])
                                       for e in ok for rr in per[e]['r']['robots'].values()),
                  'counts_as_m1_reported_only': {e: {k: v['counts_as_m1'] for k, v in per[e]['r']['robots'].items()}
                                                 for e in ok},
                  'detail': {e: {k: v['pose_sources_seen'] for k, v in per[e]['r']['robots'].items()} for e in ok}}
    rows['E5'] = {'pass': both and all(per[e]['r']['weld_max_eq_active'] == 0 and
                                       per[e]['r']['contact_profile']['noslip_iterations'] > 0 for e in ok),
                  'detail': {e: (per[e]['r']['weld_max_eq_active'], per[e]['r']['contact_profile']['noslip_iterations'])
                             for e in ok}}
    rows['E6'] = {'pass': both and all(per[e]['r']['false_confirmations'] == 0 for e in ok),
                  'detail': {e: per[e]['r']['false_confirmations'] for e in ok}}
    rows['E7'] = {'pass': both and all(not rr['guards']['confirmed_while_gate_uncertain']
                                       for e in ok for rr in per[e]['r']['robots'].values()),
                  'detail': {e: {k: v['guards']['confirmed_while_gate_uncertain'] for k, v in per[e]['r']['robots'].items()}
                             for e in ok}}
    return rows, per


def main():
    smoke = Path(sys.argv[1]).resolve()
    snapshot = sys.argv[sys.argv.index('--tensorboard') + 1] if '--tensorboard' in sys.argv else None
    rows, per = gates(smoke)
    robots = []
    for e in EPISODES:
        if not per[e]['result']:
            continue
        for rid, rr in sorted(per[e]['r']['robots'].items()):
            row = robot_row(e, rid, rr, per[e]['r'])
            row['guards'] = rr['guards']
            robots.append(row)
    earlier = {k: json.loads(p.read_text()) for k, p in EARLIER.items() if p.exists()}
    results = {'schema': f'ugrp.zone_own_executor_smoke_results.{VERSION}', 'smoke_dir': str(smoke),
               'source_sha': sorted({per[e]['m']['code']['sha'] for e in EPISODES if per[e]['result']}),
               'dirty': sorted({per[e]['m']['code']['dirty'] for e in EPISODES if per[e]['result']}),
               'gates': rows, 'smoke_pass': all(g['pass'] for g in rows.values()),
               'm1_style_success': f"{sum(r['m1_success'] for r in robots)}/{len(robots)}",
               'own_camera_confirmed': f"{sum(r['confirmation'] == 'own_camera_confirmed' for r in robots)}/{len(robots)}",
               **{f'{k}_for_reference_not_pooled': {x: v.get(x) for x in ('m1_style_success', 'own_camera_confirmed',
                                                                         'source_sha')} for k, v in earlier.items()},
               'robots': robots,
               'runs': {e: {'run': per[e]['r']['run'], 'wall_s': per[e]['m']['wall_s'],
                            'load_average': per[e]['m']['load_average']} for e in EPISODES if per[e]['result']}}
    (HERE / f'results_{VERSION}.json').write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str) + '\n')
    index = {str(p.relative_to(smoke)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(smoke.rglob('*')) if p.is_file() and p.suffix in ('.json', '.jsonl', '.log', '.txt')}
    (HERE / f'raw_index_{VERSION}.json').write_text(json.dumps({'root': str(smoke), 'note': 'local only, not a remote backup; '
                                                        'frames/*.jpg and scene.xml hashed in each manifest',
                                                        'files': index}, indent=1) + '\n')
    print(json.dumps({'smoke_pass': results['smoke_pass'], 'gates': {k: v['pass'] for k, v in rows.items()},
                      'm1_style': results['m1_style_success'], 'confirmed': results['own_camera_confirmed']}))
    if not snapshot:
        return
    view = smoke.parent / f'tensorboard-view-{smoke.name}'
    runs, conditions = [], {}
    for row in robots:
        e, rid = row['episode'], row['robot_id']
        rr = per[e]['r']['robots'][rid]
        name = f"exec{VERSION[1:]}-{e.split('-')[-1]}-{rid}"
        g = rr['guards']
        payload = {'derived_view_only': True, 'derived_from': str(smoke / e),
                   'source_result_sha256': sha(smoke / e / 'result.json'),
                   **{k: rr[k] for k in m1_contract.REQUIRED_OUTCOME_KEYS}, 'success': rr['m1_success'],
                   'stop_reason': row['deliver_outcome'], 'policy': f'zone_own_executor smoke {VERSION} (#221 guards) + M1 chain + skill v9',
                   'case': f"{e} {rid} {row['pickup_slot']}->{row['zone_slot']}",
                   'config': {'contact_profile': 'cargo_noslip_v1', 'robots': 3, 'scripted_no_llm': True,
                              'hold_before_deliver_s': per[e]['r']['scripted_jobs'][rid]['hold_s'], 'cohort': f'smoke-{VERSION}'},
                   'sim_s': row['deliver_duration_s'], 'wall_s': per[e]['m']['wall_s'], 'commands': row['commands'],
                   'model_calls': 0,
                   'evaluation': {'m1_success': rr['m1_success'], 'diagnostic_success': rr['diagnostic_success'],
                                  'counts_as_m1': rr['counts_as_m1'],
                                  'own_camera_confirmed': row['confirmation'] == 'own_camera_confirmed',
                                  'false_confirmation': rr['evaluation_only']['false_confirmation'],
                                  'pose_uncertain_events': g['pose_uncertain_events'],
                                  'stall_recoveries': g['stall_recoveries'], 'sweeps_restricted': g['sweeps_restricted'],
                                  'near_clip_retreats': g['near_clip_retreats'],
                                  'wall_contact_steps': rr['evaluation_only']['contact_steps'].get('wall', 0),
                                  'failed_checks': rr['m1_failed_checks']},
                   'offline_scalars': {'offline/pose_uncertain_events': g['pose_uncertain_events'],
                                       'offline/stall_recoveries': g['stall_recoveries'],
                                       'offline/sweeps_restricted': g['sweeps_restricted'] + g['m1_sweeps_restricted'],
                                       'offline/near_clip_retreats': g['near_clip_retreats'],
                                       'offline/wall_contact_steps': rr['evaluation_only']['contact_steps'].get('wall', 0)},
                   'offline_source': {'path': str(smoke / e / 'result.json'), 'sha256': sha(smoke / e / 'result.json')},
                   'offline_source_pointer': f'robots.{rid}.guards / robots.{rid}.evaluation_only.contact_steps',
                   'offline_scalar_scope': 'executor guard counters and eval-only wall contact steps of this robot-episode, '
                                           f'copied from the smoke-{VERSION} raw result.json; diagnostics, not task success or time',
                   'seed': per[e]['r']['seed'], 'source_sha': per[e]['m']['code']['sha']}
        runs.append(derived(view, name, payload))
        conditions[name] = f'executor smoke {VERSION} {e} robot {rid} (3 robots in one world, scripted, no LLM)'
    target = TB / snapshot
    if target.exists():
        raise SystemExit(f'{target} exists; snapshots are never overwritten')
    cmd = [sys.executable, str(ROOT / 'scripts/export_tensorboard.py'), '--output', str(target), '--max-images', '0']
    for name in runs:
        cmd += ['--source', str(view / name)]
    subprocess.run(cmd, check=True)
    collection = json.loads((target / 'collection.json').read_text())
    for entry in collection['exported']:
        short = Path(entry['source']).name
        old = target / entry['name']
        if old.exists() and entry['name'] != short:
            old.rename(target / short)
        entry['original_name'], entry['name'] = entry['name'], short
        d = json.loads((view / short / 'result.json').read_text())
        entry['condition'] = conditions[short] + f"; success=m1_success={d['m1_success']}, counts_as_m1={d['counts_as_m1']}"
    (target / 'collection.json').write_text(json.dumps(collection, indent=2) + '\n')
    print(json.dumps({'snapshot': str(target), 'runs': len(collection['exported']), 'failed': collection.get('failed')}))


if __name__ == '__main__':
    main()
