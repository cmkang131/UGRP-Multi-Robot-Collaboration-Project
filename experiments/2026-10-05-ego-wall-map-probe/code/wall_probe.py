"""Offline measurement of height-free wall contact detection on recorded frames.

Refs #216. **Physical simulation runs: 0.** Reads recorded own-camera frames only and
never writes into a recorded episode directory.

Detection reads: own undistorted RGB, own commanded servo (extrinsics), fixed camera
calibration, own load state. Ground truth (map walls, robot pose) is read in this
scoring script only, never passed into the detector.

Outputs (raw, absolute path into the primary checkout ``outputs/``):
  per-frame CSV   one row per frame: load state, detections, segments, heights
  segments JSONL  one row per detected wall face with its geometry
  summary JSON    aggregate rates including the height-invariance comparison
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(ROOT / 'experiments/2026-10-05-ego-wall-map-probe/code'))

import markerless_probe as mp  # noqa: E402
import height_free_wall as hfw  # noqa: E402

# Elevation bias fitted offline on the VIS3 dev split (calibration_seed.json). Applied to
# both variants identically so the comparison is not a calibration effect.
SEED_BIAS = {'unloaded': -0.01868, 'loaded': -0.04579}

# Own-command load state. The load state selects the elevation-bias entry and the carried-object
# mask, so it has to be a signal the robot owns and that actually tracks carrying: the gripper
# servo (1) commanded closed. ``sim/masterpi_dynamics_v2`` maps servo 1 to closure
# (2000 - pulse)/500, so 1600 is >= 0.8 of full closure; the carry frames of the v98 dev episode
# command 1500. The earlier rule ``servo[3] >= 900`` is the wrist-pitch pulse, i.e. an *arm pose*:
# it marked the open-gripper search pose (3 = 1072) as loaded and gave it the carry bias.
LOADED_GRIPPER_PULSE_MAX = 1600


def is_loaded(servo) -> bool:
    """True when the own commanded gripper pulse is closed on a carried object."""
    pulse = servo.get(1, servo.get('1', 2000))
    return int(pulse) <= LOADED_GRIPPER_PULSE_MAX


# OPTION ``load_rule`` (default ``s3`` = the behaviour before #405):
#   ``s3``       servo[3] >= 900, the arm-pose rule every earlier tool used. Each tool read the key in its own
#                way and ``legacy_str_key`` reproduces that: ``servo.get('3', 0)`` on an int-keyed dict is always
#                0, i.e. never loaded (wall_probe.run, coverage, overlay, diag_rows); ``servo.get(3, 0)`` is the
#                int-key form (self_top_for, score_harness, cue_study, map2d, height_invariance).
#   ``gripper``  is_loaded(): the own commanded gripper pulse.
LOAD_RULES = ('s3', 'gripper')
LOAD_RULE_DEFAULT = 's3'
_load_rule = LOAD_RULE_DEFAULT


def set_load_rule(rule: str) -> None:
    """Process-wide default of the tools that read the load state through :func:`loaded_for`."""
    global _load_rule
    if rule not in LOAD_RULES:
        raise ValueError(f'load rule must be one of {LOAD_RULES}, got {rule!r}')
    _load_rule = rule


def loaded_for(servo, rule: str | None = None, legacy_str_key: bool = False) -> bool:
    """Own-command load state under ``rule`` (default: the process-wide rule, ``s3`` unless set)."""
    rule = _load_rule if rule is None else rule
    if rule == 'gripper':
        return is_loaded(servo)
    if rule == 's3':
        return servo.get('3' if legacy_str_key else 3, 0) >= 900
    raise ValueError(f'load rule must be one of {LOAD_RULES}, got {rule!r}')


def detector_bias(servo, loaded: bool, sag: bool = False) -> float:
    """Elevation bias of the detector's camera model for the commanded pose.

    OPTION ``sag`` (``--sag-comp``, default off = the behaviour before #405): the constant ``SEED_BIAS`` entry for
    the load state. On: ``sag_comp.bias_rad``, the command-only gravity-droop model (commanded pulses and the own
    gripper command only). The model has its own load class (``is_loaded``, the gripper command), whatever
    ``--load-rule`` says, because its load term was fitted on frames split that way.
    """
    if sag:
        import sag_comp
        return sag_comp.bias_rad(servo, is_loaded(servo))
    return mp.elevation_bias(SEED_BIAS['loaded' if loaded else 'unloaded'], servo)


# Frozen VIS3 detector parameters at the current final-environment wall height.
FROZEN_DETECTOR = {'wall_height_m': .40, 'columns': 96, 'strip_half_px': 2}


def free_joint_qaddr(scene_xml: Path, name: str):
    """(qpos address, nv address) of a free joint, from the recorded scene's joint order."""
    scene = ET.fromstring(scene_xml.read_text())
    world = scene.find('worldbody')
    nq, nv = 0, 0
    for node in world.iter():
        if node.tag not in ('joint', 'freejoint'):
            continue
        kind = node.get('type', 'free' if node.tag == 'freejoint' else 'hinge')
        if node.get('name') == name and kind == 'free':
            return nq, nv
        nq += {'free': 7, 'ball': 4}.get(kind, 1)
        nv += {'free': 6, 'ball': 3}.get(kind, 1)
    raise ValueError(f'free joint not found: {name}')


def yaw_from_quat(quat):
    w, x, y, z = quat
    return math.atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))


def wall_rects(static_map):
    """(cx, cy, hx, hy, height) of every wall footprint. Scoring only."""
    out = []
    for o in static_map['obstacles']:
        if o.get('kind') != 'wall':
            continue
        cx, cy = o['center_m']
        hx, hy = o['half_extents_m']
        out.append((float(cx), float(cy), float(hx), float(hy), float(o.get('height_m', .10))))
    return out


def dist_to_walls(pt, rects):
    """Shortest distance from a world point to any wall footprint (0 when inside)."""
    best = float('inf')
    x, y = pt
    for cx, cy, hx, hy, _ in rects:
        dx = max(abs(x - cx) - hx, 0.)
        dy = max(abs(y - cy) - hy, 0.)
        best = min(best, math.hypot(dx, dy))
    return best


def resolve_frames(ep_dir: Path, robot: str):
    """Recorded frame index. Two layouts exist in this repo's outputs."""
    for rel in (Path('inputs')/'frames.jsonl', Path('robots')/robot/'frames.jsonl'):
        if (ep_dir/rel).exists():
            rows = []
            for line in (ep_dir/rel).read_text().splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            return rows, rel
    raise FileNotFoundError(f'no frames.jsonl under {ep_dir}')


def frame_rows(ep_dir: Path, robot: str = 'r1'):
    return resolve_frames(ep_dir, robot)[0]


def load_state(servo, load_table):
    """Own-command load state. Falls back to the shoulder pulse table when available."""
    s3 = int(servo.get('3', 0))
    return load_table.get(s3, 'unloaded')


def self_top_for(und_bgr, cm, servo, load_rule=None):
    """Per-column carried-object occlusion ceiling for one frame. Own image + own servo only.

    The single way every runner gets ``self_top``: it delegates to
    ``height_free_wall.self_top_mask``, which delegates to :mod:`self_mask`, so the
    strip half-width is the detector's own and the mask is indexed by exactly the
    columns ``height_free_wall.detect`` uses. ``HEIGHT`` everywhere when nothing is
    carried or nothing occludes.

    The load state is :func:`loaded_for` under the ``load_rule`` option (default ``s3``: the earlier
    ``servo[3] >= 900``, an arm pose that also marks the open-gripper search pose as loaded; ``gripper``:
    the own commanded gripper pulse).
    """
    return hfw.self_top_mask(und_bgr, cm, loaded=loaded_for(servo, load_rule))


def run(args):
    ep_dir = Path(args.episode)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    static_map = json.loads((ep_dir/'inputs'/'static_map.json').read_text())
    rects = wall_rects(static_map)
    traj = [json.loads(l) for l in (ep_dir/'eval_only'/'trajectory.jsonl').read_text().splitlines() if l.strip()]
    qa, _ = free_joint_qaddr(ep_dir/'scene.xml', f'{args.robot}__base_free')
    poses = [(float(t['qpos'][qa]), float(t['qpos'][qa + 1]), yaw_from_quat(t['qpos'][qa + 3:qa + 7]))
             for t in traj]
    frames_all, frames_rel = resolve_frames(ep_dir, args.robot)
    t_of_frame = [float(r['sim_time']) for r in frames_all]

    def pose_at(t):
        i = int(np.searchsorted(t_of_frame, t))
        i = min(max(i, 0), len(poses) - 1)
        return poses[i]

    cols = mp.column_positions(FROZEN_DETECTOR['columns'], FROZEN_DETECTOR['strip_half_px'])
    step = max(1, int(args.every))
    rows = frames_all
    seg_out = open(out_dir/'segments.jsonl', 'w')
    csv_rows = []
    n_frames = 0
    for idx in range(0, len(rows), step):
        row = rows[idx]
        t = float(row['sim_time'])
        servo = {int(k): int(v) for k, v in row['commanded_servo'].items()}
        bgr = cv2.imread(str(ep_dir/row['path']), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        und = mp.undistort(bgr)
        loaded = loaded_for(servo, args.load_rule, legacy_str_key=True)
        b0 = mp.elevation_bias(SEED_BIAS['loaded' if loaded else 'unloaded'], servo)
        cm = mp.column_model(servo, b0, cols)

        # carried-object occlusion: OFF (baseline) and ON (self_mask on the undistorted frame)
        top_off = np.full(len(cols), hfw.HEIGHT, int)
        top_on = self_top_for(und, cm, servo)

        res = {}
        for tag, self_top in (('mask_off', top_off), ('mask_on', top_on)):
            scan = hfw.detect(und, cm, self_top=self_top)
            segs = hfw.link_segments(scan)
            res[tag] = (scan, segs)
        scan_frozen = mp.detect_boundaries(und, cm, FROZEN_DETECTOR, top_off)

        px, py, yaw = pose_at(t)
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        rec = {'frame_index': int(row.get('frame_id', idx)), 't': round(t, 3), 'loaded': bool(loaded)}
        for tag in ('mask_off', 'mask_on'):
            scan, segs = res[tag]
            xs, ys = [], []
            for s in segs:
                for rng, brg in ((s['range_first_m'], s['bearing_first_rad']),
                                 (s['range_last_m'], s['bearing_last_rad'])):
                    wx = px + rng*math.cos(brg)
                    wy = py + rng*math.sin(brg)
                    xs.append(wx)
                    ys.append(wy)
            d = [dist_to_walls((x, y), rects) for x, y in zip(xs, ys)] or [float('nan')]
            hit = [x <= args.hit_m for x in d]
            rec[f'{tag}_det_cols'] = int(np.isfinite(scan['vb'][:, 0]).sum())
            rec[f'{tag}_segments'] = len(segs)
            rec[f'{tag}_endpoint_hits'] = int(sum(hit))
            rec[f'{tag}_endpoints'] = len(hit)
            rec[f'{tag}_endpoint_hit_share'] = round(float(np.mean(hit)), 4) if hit else None
            rec[f'{tag}_min_wall_dist_m'] = round(float(np.nanmin(d)), 4) if d else None
            hs = scan['h'][np.isfinite(scan['h'])]
            rec[f'{tag}_height_med_m'] = round(float(np.median(hs)), 4) if hs.size else None
            for s in segs:
                seg_out.write(json.dumps({**s, 'tag': tag, 'frame_index': int(row.get('frame_id', idx)),
                                          't': round(t, 3), 'loaded': bool(loaded),
                                          'robot_x': round(px, 3), 'robot_y': round(py, 3),
                                          'robot_yaw': round(yaw, 4),
                                          'endpoint_wall_dist_m': round(min(
                                              dist_to_walls((px + s['range_first_m']*math.cos(s['bearing_first_rad']),
                                                             py + s['range_first_m']*math.sin(s['bearing_first_rad'])), rects),
                                              dist_to_walls((px + s['range_last_m']*math.cos(s['bearing_last_rad']),
                                                             py + s['range_last_m']*math.sin(s['bearing_last_rad'])), rects)), 4)}
                                         ) + '\n')
        rec['frozen_det_cols'] = int(scan_frozen.detected.sum())
        csv_rows.append(rec)
        n_frames += 1
        if n_frames % 200 == 0:
            print(f'{n_frames} frames', flush=True)
    seg_out.close()

    fields = list(csv_rows[0].keys())
    with open(out_dir/'per_frame.csv', 'w') as f:
        f.write(','.join(fields) + '\n')
        for r in csv_rows:
            f.write(','.join('' if r.get(k) is None else str(r.get(k)) for k in fields) + '\n')

    def agg(tag):
        seg = np.array([r[f'{tag}_segments'] for r in csv_rows], float)
        hit = np.array([r[f'{tag}_endpoint_hits'] for r in csv_rows], float)
        end = np.array([r[f'{tag}_endpoints'] for r in csv_rows], float)
        det = np.array([r[f'{tag}_det_cols'] for r in csv_rows], float)
        hm = [r[f'{tag}_height_med_m'] for r in csv_rows if r[f'{tag}_height_med_m'] is not None]
        return {'frames': len(csv_rows), 'mean_det_cols': float(det.mean()),
                'mean_segments': float(seg.mean()), 'frames_with_segment_share': float((seg > 0).mean()),
                'endpoint_hit_share': float(hit.sum()/max(end.sum(), 1)),
                'height_frames': len(hm),
                'height_median_m': float(np.median(hm)) if hm else None,
                'height_p10_m': float(np.percentile(hm, 10)) if hm else None,
                'height_p90_m': float(np.percentile(hm, 90)) if hm else None}

    summary = {'episode': str(ep_dir), 'robot': args.robot, 'frames': n_frames,
               'frames_jsonl': str(frames_rel),
               'step': step, 'map_id': static_map.get('map_id'),
               'gt_wall_heights_m': sorted({r[4] for r in rects}),
               'hit_threshold_m': args.hit_m, 'n_gt_walls': len(rects),
               'height_free_mask_off': agg('mask_off'), 'height_free_mask_on': agg('mask_on'),
               'frozen_vism3_detector_mean_cols': float(np.mean([r['frozen_det_cols'] for r in csv_rows])),
               'seed_bias_rad': SEED_BIAS, 'frozen_detector_params': FROZEN_DETECTOR,
               'height_free_params': hfw.recorded_params(),
               'gt_use': 'scoring only; detector inputs are own RGB, own servo, fixed calibration'}
    (out_dir/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', required=True)
    ap.add_argument('--every', type=int, default=2)
    ap.add_argument('--hit-m', type=float, default=.10)
    ap.add_argument('--load-rule', choices=LOAD_RULES, default=LOAD_RULE_DEFAULT,
                    help='own load state: s3 = the earlier servo[3] >= 900 (default), gripper = commanded gripper closed')
    run(ap.parse_args())