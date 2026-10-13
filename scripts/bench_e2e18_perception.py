"""Mac-only offline benchmark of E2E18 perception functions (no simulation, no physics).

Feeds a handful of saved own-RGB JPEGs (frames.jsonl rows + bundle.json from one run)
through the real Robot._receive / observe_beam / ORB relook path and prints cProfile
top functions plus a JSON of outputs for before/after identity checks.
Usage: python scripts/bench_e2e18_perception.py IN_DIR [--profile] [--out out.json] [--toggle NAME ...]
"""
import argparse, base64, cProfile, hashlib, io, json, pstats, sys, time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(in_dir):
    rows = [json.loads(l) for l in (in_dir / 'frames_subset.jsonl').read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: r['frame_id'])
    frames = []
    for r in rows:
        data = (in_dir / f"f{r['frame_id']}.jpg").read_bytes()
        assert hashlib.sha256(data).hexdigest() == r['sha256']
        rgb = np.asarray(Image.open(io.BytesIO(data)).convert('RGB'))
        frames.append((r, base64.b64encode(data).decode(), rgb))
    return frames


def make_robot(bundle):
    from harness.e2e_live_mapping import Robot
    from harness.e2e_exact_speedups import Options as SpeedOptions
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.e2e_speed4 import Options as Speed4Options
    from harness.s4_event_policy import Options
    o = bundle['e2e_options']
    cov = json.loads((ROOT / 'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot = Robot('r1', bundle['seed'], cov, Options(**bundle['study_options']), beam_end_model=o.get('beam_end_model', 'off'),
                 beam_decode=o.get('beam_decode', 'off'), speed4=Speed4Options(**bundle.get('speed4', {})),
                 speed5=o.get('speed5', 'off'), relook=o['setdown_only_when_relook'], goal_geometry=o['goal_geometry'],
                 exploration_progress=o.get('exploration_progress', 'off'), pose_fix=o.get('pose_fix', 'off'),
                 path_follow=o.get('path_follow', 'off'),
                 stall_options=StallOptions(**{k: o.get(k, 'off') for k in ('stall_odometry', 'stall_recovery', 'stall_noise')}),
                 explore_deadlock=o.get('explore_deadlock', 'off'), boundary_association=o.get('boundary_association', 'off'),
                 boundary_retry=o.get('boundary_retry', 'off'), boundary_coverage=o.get('boundary_coverage', 'off'),
                 vo_floor_mask=o.get('vo_floor_mask', 'off'), vo_rotation_policy=o.get('vo_rotation_policy', 'off'),
                 mapping_budget_s=o.get('mapping_budget_s'), boundary_views=o.get('boundary_views', 'off'),
                 boundary_frame=o.get('boundary_frame', 'off'), b_marker_detect=o.get('b_marker_detect', 'off'),
                 b_partial_accept=o.get('b_partial_accept', 'off'), exact_speedups=SpeedOptions(**o.get('exact_speedups', {})))
    g = robot.goal
    g.e2e_route_guard = o.get('route_guard', 'off'); g.e2e_beam_axis = o.get('beam_axis', 'off')
    g.e2e_route_coverage = o.get('route_coverage', 'off'); g.e2e_carrier_axes = o.get('carrier_axes', 'off')
    g.e2e_route_extent = o.get('route_extent', 'off'); g.e2e_record_scalars = o.get('record_scalars', 'off')
    from harness.e2e_route_cost import configure as cost_configure
    cost_configure(g, o.get('route_cost', 'off'))
    from harness.e2e_pose_guard import configure as pose_guard_configure
    pose_guard_configure(g, o.get('pose_guard', 'off'))
    robot.perception_settle = o.get('perception_settle', 'off'); robot.landmark_cache = o.get('landmark_cache', 'off')
    robot.pregrasp_acquire = o.get('pregrasp_acquire', 'off'); robot.camera_load = o.get('camera_load', 'off')
    from harness.e2e_observation_cadence import configure as cadence_configure
    cadence_configure(g, o.get('observation_cadence', 'off'), bundle.get('speed3_profile', {}).get('observation_period_s', .2))
    return robot


def run(frames, bundle, repeat=1):
    """Returns per-frame wall (s) and a digest of outputs."""
    out = []
    robot = make_robot(bundle)
    t0 = None
    for r, b64, rgb in frames:
        robot.servo = {int(k): v for k, v in r['commanded_servo'].items()}
        obs = dict(frame_id=r['frame_id'], sim_time=r['sim_time'] - 1.3, sha256=r['sha256'], image=b64)
        s = time.perf_counter()
        from harness.e2e_camera_settle import receive as settled_receive
        trace = settled_receive(robot, obs, rgb, obs['sim_time'], lambda *a, **k: None)
        out.append(dict(frame_id=r['frame_id'], wall_s=time.perf_counter() - s,
                        pose=[round(float(x), 9) for x in robot.goal.explorer.local_pose],
                        beam=json.dumps(robot.beam_observation['result'], sort_keys=True, default=str),
                        command=json.dumps(robot.nav_command, sort_keys=True, default=str)))
    return out


def isolated(frames):
    """Direct ORB / match timings on the saved views (relook inner loop)."""
    from harness.e2e_rgb_gate import features, geometric_match
    stored = [f for f in frames if f[0]['frame_id'] < 1370]
    probe = [f for f in frames if f[0]['frame_id'] >= 1370]
    t = time.perf_counter(); feats = {f[0]['frame_id']: features(f[2]) for f in frames}
    orb_s = (time.perf_counter() - t) / len(frames)
    res, t = [], time.perf_counter()
    for s in stored:
        for p in probe:
            res.append((s[0]['frame_id'], p[0]['frame_id'], geometric_match(feats[s[0]['frame_id']], feats[p[0]['frame_id']])))
    match_s = (time.perf_counter() - t) / max(1, len(res))
    return dict(orb_s_per_frame=orb_s, match_s_per_pair=match_s, pairs=len(res),
                keypoints={k: len(v['points']) for k, v in feats.items()},
                matches=[(a, b, r.get('accepted'), r.get('reason'), r.get('matches'), r.get('inliers')) for a, b, r in res])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('in_dir'); ap.add_argument('--profile', action='store_true'); ap.add_argument('--out')
    ap.add_argument('--top', type=int, default=25); ap.add_argument('--perception-fast', default='off')
    a = ap.parse_args()
    in_dir = Path(a.in_dir)
    bundle = json.loads((in_dir / 'bundle.json').read_text())
    frames = load(in_dir)
    from harness.e2e_perception_fast import install
    install(a.perception_fast)
    result = dict(isolated=isolated(frames))
    pr = cProfile.Profile() if a.profile else None
    if pr: pr.enable()
    result['frames'] = run(frames, bundle)
    if pr:
        pr.disable()
        st = pstats.Stats(pr).sort_stats('cumulative'); st.print_stats(a.top)
        pstats.Stats(pr).sort_stats('tottime').print_stats(a.top)
    result['mean_receive_s'] = float(np.mean([f['wall_s'] for f in result['frames']]))
    if a.out: Path(a.out).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != 'frames'}, default=str)[:1500])
    print([round(f['wall_s'], 3) for f in result['frames']])
