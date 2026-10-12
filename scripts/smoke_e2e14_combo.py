"""E2E14 combination smoke on saved frames (NOT a simulation, no physics/render).

Saved own RGB (the e2e11 selected windows) and the recorded issued commands are
pushed, in time order, through the real ``Robot`` built exactly as
``scripts/run_e2e_ownmap_live.run`` builds it from a bundle's ``e2e_options``.
Configurations: 12th-round A (pulse gate + recovery + noise), VO only, #443 views+marker only, and all
three on (the v202 bundle). Open loop: the robot's own navigation output is
recorded but never fed back, so every configuration sees byte-identical inputs.

Checks (interaction only, not a success measure):
- no exception in any configuration;
- per frame, the all-on trace carries ``boundary_view``/``boundary_diagnostics``
  (#443) and ``stall_odometry`` with option rgb_vo_v1 (#444); gate marker option
  is contrast_v1;
- VO is not perturbed by #443: VO rows (status/fusion/delta) and the own pose
  are identical between VO-only and all-on;
- #443 gate diagnostics are compared between views+marker-only and all-on and
  reported (they may differ because VO changes the own pose estimate).
Inputs: own RGB, own issued commands, fixed calibration. Simulator truth is not read.
"""
import argparse, base64, hashlib, json, subprocess, sys, time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONFIGS = {
    'a12': dict(stall_odometry='rgb_pulse_gate_v1', stall_recovery='backup_replan_v1', stall_noise='amcl_alpha_v1'),
    'vo_only': dict(stall_odometry='rgb_vo_v1'),
    'b443_only': dict(boundary_views='candidate_views_v1', b_marker_detect='contrast_v1'),
    'combo_v202': dict(stall_odometry='rgb_vo_v1', boundary_views='candidate_views_v1', b_marker_detect='contrast_v1'),
}


def rows(path):
    path = Path(path)
    data = path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path) + '.zst'])
    return [json.loads(x) for x in data.splitlines() if x]


def bundle_for(extra):
    from scripts.run_e2e_ownmap_live import bundle, Options
    return bundle('smoke', 61001, 'study_gemma4_31b_v1', enabled=True, relook='on_v1', options=Options(True, True, 'en'),
                  exploration_progress='frontier_progress_v1', pose_fix='innovation', path_follow='rpp_v1',
                  dev_light=True, stall_bundle=True, mapping_budget='case_cap_v1', wall_cap_s=25200., **extra)


def robot_for(b, rid, seed_offset):
    # Same argument mapping as scripts/run_e2e_ownmap_live.run.
    from harness.e2e_live_mapping import Robot
    from harness.e2e_exact_speedups import Options as SpeedOptions
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.s4_event_policy import Options
    o = b['e2e_options']
    cov = json.loads((ROOT / 'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    return Robot(rid, b['seed'] + seed_offset, cov, Options(**b['study_options']), relook=o['setdown_only_when_relook'],
                 goal_geometry=o['goal_geometry'], exploration_progress=o.get('exploration_progress', 'off'),
                 pose_fix=o.get('pose_fix', 'off'), path_follow=o.get('path_follow', 'off'),
                 stall_options=StallOptions(**{k: o.get(k, 'off') for k in ('stall_odometry', 'stall_recovery', 'stall_noise')}),
                 mapping_budget_s=o.get('mapping_budget_s'),
                 boundary_views=o.get('boundary_views', 'off'), b_marker_detect=o.get('b_marker_detect', 'off'),
                 exact_speedups=SpeedOptions(**o.get('exact_speedups', {})))


def replay(raw, images, rid, b, seed_offset, limit):
    frames = rows(raw / f'robots/{rid}/frames.jsonl')
    origin = frames[0]['sim_time']
    commands = [{**r, 't': round(r['t'] - origin, 8)} for r in rows(raw / f'robots/{rid}/commands.jsonl')
                if r['kind'] != 'initial_servo_command']
    saved = [f for f in frames if (images / f['path']).exists()]
    if limit: saved = saved[:limit]
    robot = robot_for(b, rid, seed_offset)
    from harness.active_camera import SEARCH
    for sid, pwm in SEARCH.items():  # runner start: own SEARCH pose issued at t=0
        robot.commanded(dict(kind='look', pan_pulse=pwm) if sid == 6 else dict(kind='arm', servo_id=sid, pulse=pwm), 0.)
    cursor = 0; out = []
    while cursor < len(commands) and commands[cursor]['t'] <= 0. + 1e-8:
        cursor += 1  # recorded SEARCH commands at t=0 already issued above
    for f in saved:
        t = round(f['sim_time'] - origin, 8)
        while cursor < len(commands) and commands[cursor]['t'] < t - 1e-8:
            c = commands[cursor]; robot.commanded({k: v for k, v in c.items() if k != 't'}, c['t']); cursor += 1
        data = (images / f['path']).read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        if sha != f['sha256']: raise ValueError('SAVED_RGB_HASH_MISMATCH')
        rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        trace = robot.receive(dict(frame_id=f['frame_id'], sim_time=t, sha256=sha, image=base64.b64encode(data).decode()), rgb)
        so = trace.get('stall_odometry') or {}
        bv = trace.get('boundary_view')
        out.append(dict(frame_id=f['frame_id'], t=t, pose=[round(x, 9) for x in robot.goal.explorer.local_pose.tolist()],
                        command=robot.nav_command,
                        vo=None if not so or so.get('options', {}).get('stall_odometry') != 'rgb_vo_v1' else
                        dict(status=so.get('status'), fusion=so.get('fusion'),
                             applied_delta=[round(x, 9) for x in so.get('applied_delta', [])]),
                        boundary_view=bv, has_boundary_diag='boundary_diagnostics' in trace,
                        boundary_diag_sha=hashlib.sha256(json.dumps(trace.get('boundary_diagnostics'), sort_keys=True,
                                                                     default=str).encode()).hexdigest()
                        if 'boundary_diagnostics' in trace else None,
                        marker_detect=robot.goal.e2e_gate.marker_detect))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--outputs', type=Path, default=Path('/Users/changmin/projects/ugrp/outputs'))
    p.add_argument('--limit', type=int, default=0, help='saved frames per robot (0 = all)')
    p.add_argument('--summary-out', type=Path, required=True)
    a = p.parse_args()
    sel = a.outputs / 'e2e11-stall-odometry/selected-frames'
    result = dict(kind='saved_frame_fixed_replay_smoke', simulation=False, physics=False, render=False,
                  note='Open-loop interaction smoke; not a run, not a success or accuracy measure.', cases={}, errors=[])
    bundles = {k: bundle_for(v) for k, v in CONFIGS.items()}
    result['bundle_ids'] = {k: v['execution_bundle_id'] for k, v in bundles.items()}
    started = time.monotonic()
    for run_dir in sorted(sel.iterdir()):
        raw = a.outputs / 'azure-runs' / run_dir.name / 'raw'
        for i, rid in enumerate(('r1', 'r2')):
            key = f'{run_dir.name}:{rid}'; per = {}
            for name, b in bundles.items():
                try:
                    per[name] = replay(raw, run_dir / 'raw', rid, b, i, a.limit)
                except Exception as e:  # recorded, not hidden
                    result['errors'].append(dict(case=key, config=name, error=f'{type(e).__name__}: {e}'))
            c = per.get('combo_v202', []); v = per.get('vo_only', []); g = per.get('b443_only', [])
            result['cases'][key] = dict(
                frames={k: len(x) for k, x in per.items()},
                combo_boundary_view_frames=sum(r['boundary_view'] is not None for r in c),
                combo_boundary_diag_frames=sum(r['has_boundary_diag'] for r in c),
                combo_vo_frames=sum(r['vo'] is not None for r in c),
                combo_vo_measured=sum(bool(r['vo']) and r['vo']['status'] == 'measured' for r in c),
                combo_vo_replaced=sum(bool(r['vo']) and r['vo']['fusion'] == 'vo_replaced' for r in c),
                combo_marker_contrast_frames=sum(r['marker_detect'] == 'contrast_v1' for r in c),
                vo_rows_equal_vo_only=[r['vo'] for r in c] == [r['vo'] for r in v],
                pose_equal_vo_only=[r['pose'] for r in c] == [r['pose'] for r in v],
                boundary_diag_equal_b443_only=sum(x['boundary_diag_sha'] == y['boundary_diag_sha'] for x, y in zip(c, g)),
                boundary_view_phase_equal_b443_only=sum(x['boundary_view'] == y['boundary_view'] for x, y in zip(c, g)),
                a12_vo_frames=sum(r['vo'] is not None for r in per.get('a12', [])),
                a12_boundary_view_frames=sum(r['boundary_view'] is not None for r in per.get('a12', [])))
            print(key, json.dumps(result['cases'][key]), flush=True)
    result['wall_s'] = round(time.monotonic() - started, 1)
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result['source_head'] = sha
    a.summary_out.parent.mkdir(parents=True, exist_ok=True)
    a.summary_out.write_text(json.dumps(result, indent=1, sort_keys=True) + '\n')
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
