"""Offline: replay one robot's own saved startup frames+commands through the PF,
with and without the v6 recovery localizer (posterior_relook). No MuJoCo, no GT.

usage: replay_bootstrap.py <run_dir> <robot_id> <seed> <until_s>
"""
import json, sys
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.owncam_pose_source import OwnCamPoseSource
from harness.owncam_recovery_v6 import enable_provider

run, rid, seed, until = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
static = json.loads((run / 'inputs/static.json').read_text())
cmds = [c for c in map(json.loads, open(run / 'commands.jsonl')) if c['robot_id'] == rid and c.get('t', 0) <= until]
frames = sorted((json.loads(p.read_text()) for p in (run / 'inputs' / rid).glob('*.json')), key=lambda f: f['sim_time'])
frames = [f for f in frames if f['sim_time'] <= until]
out = {}
for mode in ('v5h', 'recovery_v6'):
    src = OwnCamPoseSource(static['map'], static['calibration']['params'], seed=seed)
    if mode == 'recovery_v6':
        enable_provider(src)
    events = sorted([(c['t'], 0, c) for c in cmds] + [(f['sim_time'], 1, f) for f in frames], key=lambda e: (e[0], e[1]))
    rows = []
    for t, kind, row in events:
        if kind == 0:
            src.on_command(row); continue
        bgr = cv2.imread(str(run / row['image_file']))
        rep = src.on_frame(t, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        q = rep.observation_quality or {}
        rows.append({'t': round(t, 3), 'frame_id': row['frame_id'], 'init': rep.initialized,
                     'std_xy_m': None if rep.std_xy_m is None else round(rep.std_xy_m, 4),
                     'std_yaw_rad': None if rep.std_yaw_rad is None else round(rep.std_yaw_rad, 4),
                     'n_tags': ((rep.last_valid_obs or {}).get('n_tags') if (rep.last_valid_obs or {}).get('t') == round(t, 4) else 0),
                     'inlier_fraction': q.get('inlier_fraction'), 'informative': q.get('informative'),
                     'saturated': q.get('saturated'), 'reason': q.get('reason')})
    out[mode] = {'frames': len(rows), 'first': rows[:3], 'last': rows[-3:],
                 'min_std_xy_m': min((r['std_xy_m'] for r in rows if r['std_xy_m'] is not None), default=None),
                 'frames_with_tags': sum(1 for r in rows if r['n_tags']),
                 'informative_frames': sum(1 for r in rows if r['informative'])}
print(json.dumps({'run': str(run), 'robot': rid, 'seed': seed, 'until_s': until, 'result': out}, indent=1))
