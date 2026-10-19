#!/usr/bin/env python3
"""Render-only preflight for the approved 2026-10-19 nav gate mode v230_fwd24.

Runs in the clean pushed-source clone (cwd must be the clone root so the scene
assets resolve) and builds the exact contract-v1 navigation gate scene
(``s7_pair_with_solo_v7``, r1/r2, no cargo, scene profile v6 light_scale 0.30).
No controller, no LLM, no evaluator/GT input is built or called: only
setup-only qpos poses, the camera capture, and eval-only geometry/measurement.

Two frozen checks:

1. **Zone-free frames (②).** Five r1 poses whose camera does not face zone B:
   south wall, north wall, pickup west, pickup rear, and the west (empty) lane.
   PASS iff the approved detector (`gpu_calib_v230`) returns no detection and
   the largest 4-connected component is < 600 px in every frame.
2. **Forward-path clearance (③).** Five poses along the approved 2.4 m leg
   (x -0.898 .. 1.502 on the gate lane) with r2 driving the parallel lane at the
   same x. PASS iff the 2D corridor does not intersect any wall/divider/jamb
   rectangle for the robot envelope, the two lanes keep a positive gap, the
   scene XML spawns no cargo body, and both lanes fit inside the wide door.

The script only records numbers and a verdict; it never claims gate success.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SEED = 601
TICKS = (0, 5)
# Approved forward acquisition cap (m) and the gate lane y from the contract.
FORWARD_CAP_M = 2.4
SPAWN_X = -0.8982
PATH_X = (SPAWN_X, -0.3, 0.3, 0.9, 1.5)
ZONE_FREE_POSES = (
    ('wall_south', 1.8, -90.0),
    ('wall_north', 1.8, 90.0),
    ('pickup_west', -1.4, 180.0),
    ('pickup_rear', SPAWN_X, 180.0),
    ('lane_west', 1.5, 180.0),
)
# Manufacturer envelope of the masterpi v3 chassis (sim/masterpi_geometry.py):
# OFFICIAL_TOTAL_LENGTH_M 0.185, OFFICIAL_TOTAL_WIDTH_M 0.162.  The conservative
# bounding radius is the half diagonal; no controller reads these values.
ROBOT_HALF_LENGTH_M = 0.185 / 2.0
ROBOT_HALF_WIDTH_M = 0.162 / 2.0
ROBOT_BOUNDING_RADIUS_M = math.hypot(ROBOT_HALF_LENGTH_M, ROBOT_HALF_WIDTH_M)
MIN_COMPONENT_PX = 600
ZONE_B_CENTER = (4.6, -2.1)
ZONE_B_HALF = (0.3, 0.7)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(clone, *args):
    return subprocess.check_output(['git', '-C', str(clone), *args], text=True).strip()


def poses_zone_free(lane):
    r1, r2 = lane['r1'], lane['r2']
    out = {}
    for name, x, yaw_deg in ZONE_FREE_POSES:
        out[name] = {'r1': [x, r1[1], r1[2], r1[3] + math.radians(yaw_deg)],
                     'r2': list(r2)}
    return out


def poses_record(poses):
    """JSON-safe {pose: {robot: [x, y, z, yaw]}} copy of the setup-only spawns."""
    return {name: {rid: [round(float(v), 6) for v in pose[rid]]
                   for rid in ('r1', 'r2')}
            for name, pose in poses.items()}


def poses_path(lane):
    r1, r2 = lane['r1'], lane['r2']
    out = {}
    for x in PATH_X:
        # Both robots advance the same own-command distance (the approved leg is
        # symmetric), so the tightest lateral case is the same x on both lanes.
        out[f'x{x:.3f}'] = {'r1': [x, r1[1], r1[2], r1[3]],
                            'r2': [x, r2[1], r2[2], r2[3]]}
    return out


def measure_frame(rgb):
    """Measure one RGB frame with the exact detector path (no acceptance claim)."""
    import numpy as np
    from harness.e2ewarp_selfnav import (BEARING_POSITIVE_LEFT, GPU_CALIB_V1,
                                         GPU_CALIB_V230, GpuCalibZoneDetector,
                                         hue_degrees_to_opencv, largest_component,
                                         rgb_to_hsv)
    arr = np.asarray(rgb, dtype=np.uint8)
    h_deg, s, v = rgb_to_hsv(arr)
    h = hue_degrees_to_opencv(h_deg)

    def band_measure(band):
        lo, hi = band['hue_cv']
        vlo, vhi = band['val']
        mask = (h >= lo) & (h <= hi) & (s >= band['sat_min']) & (v >= vlo) & (v <= vhi)
        comp = largest_component(mask)
        return dict(total_pixels=int(mask.sum()),
                    largest_component_px=0 if comp is None else int(comp['area']),
                    largest_component_bbox=None if comp is None else
                    [int(comp[k]) for k in ('left', 'top', 'right', 'bottom')],
                    band=dict(hue_cv=list(band['hue_cv']), sat_min=band['sat_min'],
                              val=list(band['val']), min_pixels=band['min_pixels'],
                              units=band['units']))

    upper = largest_component((h >= GPU_CALIB_V230['hue_cv'][0])
                              & (h <= GPU_CALIB_V230['hue_cv'][1])
                              & (s >= GPU_CALIB_V230['sat_min'])
                              & (v >= GPU_CALIB_V230['val'][0])
                              & (v <= GPU_CALIB_V230['val'][1])
                              & (np.arange(arr.shape[0])[:, None] < arr.shape[0] // 2))
    lower = largest_component((h >= GPU_CALIB_V230['hue_cv'][0])
                              & (h <= GPU_CALIB_V230['hue_cv'][1])
                              & (s >= GPU_CALIB_V230['sat_min'])
                              & (v >= GPU_CALIB_V230['val'][0])
                              & (v <= GPU_CALIB_V230['val'][1])
                              & (np.arange(arr.shape[0])[:, None] >= arr.shape[0] // 2))
    wall = (h >= 120) & (h <= 160) & (s >= 40) & (v >= 10)
    neutral = (s < 25) & (v >= 20)
    return dict(
        v230=band_measure(GPU_CALIB_V230),
        v1=band_measure(GPU_CALIB_V1),
        v230_upper_largest_component_px=0 if upper is None else int(upper['area']),
        v230_lower_largest_component_px=0 if lower is None else int(lower['area']),
        detections_v230=GpuCalibZoneDetector(
            profile='gpu_calib_v230', bearing_convention=BEARING_POSITIVE_LEFT)(arr),
        detections_v1=GpuCalibZoneDetector()(arr),
        wall_pixels=int(wall.sum()), wall_fraction=round(float(wall.mean()), 6),
        neutral_pixels=int(neutral.sum()), neutral_fraction=round(float(neutral.mean()), 6),
        v_median=int(np.median(v)), s_median=int(np.median(s)),
    )


def _aabb_distance(rect, center, half):
    """Axis-aligned rectangle distance: 0 when the rectangles touch/overlap."""
    (x0, x1, y0, y1) = rect
    dx = max(center[0] - half[0] - x1, x0 - (center[0] + half[0]), 0.0)
    dy = max(center[1] - half[1] - y1, y0 - (center[1] + half[1]), 0.0)
    return math.hypot(dx, dy)


def _rect_intersects(rect, center, half):
    (x0, x1, y0, y1) = rect
    return not (center[0] + half[0] <= x0 or center[0] - half[0] >= x1
                or center[1] + half[1] <= y0 or center[1] - half[1] >= y1)


def swept_rect(lane_y, x0=SPAWN_X, x1=SPAWN_X + FORWARD_CAP_M):
    """Exact axis-aligned footprint swept by a yaw-0 robot over the leg.

    The robot keeps yaw 0 for the whole approved leg, so the union of its
    axis-aligned body rectangle (0.185 x 0.162 m) over base x in [x0, x1] is one
    rectangle: [x0-half_length, x1+half_length] x [y-half_width, y+half_width].
    No bounding-circle approximation is needed.
    """
    return [x0 - ROBOT_HALF_LENGTH_M, x1 + ROBOT_HALF_LENGTH_M,
            lane_y - ROBOT_HALF_WIDTH_M, lane_y + ROBOT_HALF_WIDTH_M]


def geometry_audit(clone, lane):
    """Eval/setup-only 2D clearance audit of the approved forward corridor."""
    map_path = clone / 'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'
    static = json.loads(map_path.read_text())
    lanes = {}
    for rid in ('r1', 'r2'):
        y = float(lane[rid][1])
        rect = swept_rect(y)
        per_obstacle = {}
        min_clearance = float('inf')
        intersections = []
        for obs in static['obstacles']:
            center = obs['center_m']
            half = obs['half_extents_m']
            if _rect_intersects(rect, center, half):
                intersections.append(obs['id'])
            clearance = _aabb_distance(rect, center, half)
            per_obstacle[obs['id']] = round(clearance, 4)
            min_clearance = min(min_clearance, clearance)
        lanes[rid] = dict(y=y, swept_body_rect_m=[round(v, 4) for v in rect],
                          obstacle_clearance_m=per_obstacle,
                          min_obstacle_clearance_m=round(min_clearance, 4),
                          intersecting_obstacles=intersections)
    door = next(p for p in static['passages'] if p['id'] == 'door_wide')
    door_x = float(door['center_m'][0])
    door_ylo = float(door['center_m'][1] - door['half_extents_m'][1])
    door_yhi = float(door['center_m'][1] + door['half_extents_m'][1])
    door_rows = {}
    for rid in ('r1', 'r2'):
        y = float(lane[rid][1])
        door_rows[rid] = dict(lane_y=y, lane_inside_door=bool(door_ylo <= y <= door_yhi),
                              margin_to_door_edge_m=round(
                                  min(abs(y - door_ylo), abs(y - door_yhi)), 4),
                              margin_after_half_width_m=round(
                                  min(abs(y - door_ylo), abs(y - door_yhi))
                                  - ROBOT_HALF_WIDTH_M, 4))
    lane_gap = abs(float(lane['r1'][1]) - float(lane['r2'][1]))
    garage = dict(
        schema='ugrp.e2ewarp.nav_fwd24_geometry_audit.v1',
        scope='eval/setup-only 2D clearance audit; never a controller input',
        map_id=static['map_id'], map_sha256=sha(map_path),
        robot_envelope_m=dict(half_length=ROBOT_HALF_LENGTH_M,
                              half_width=ROBOT_HALF_WIDTH_M,
                              bounding_radius=ROBOT_BOUNDING_RADIUS_M,
                              method='exact axis-aligned body rectangle swept at yaw 0'),
        forward_cap_m=FORWARD_CAP_M, corridor_x=[round(SPAWN_X, 4),
                                                 round(SPAWN_X + FORWARD_CAP_M, 4)],
        lanes=lanes,
        lane_center_gap_m=round(lane_gap, 4),
        lane_body_gap_m=round(lane_gap - 2.0 * ROBOT_HALF_WIDTH_M, 4),
        wide_door=dict(id=door['id'], center_x=door_x, opening_y=[door_ylo, door_yhi],
                       corridor_end_to_door_m=round(door_x - (SPAWN_X + FORWARD_CAP_M), 4),
                       corridor_front_to_door_m=round(
                           door_x - (SPAWN_X + FORWARD_CAP_M + ROBOT_HALF_LENGTH_M), 4),
                       lanes=door_rows),
        pass_criteria=dict(intersections_0=all(not v['intersecting_obstacles']
                                               for v in lanes.values()),
                           lane_gap_positive=bool(lane_gap - 2.0 * ROBOT_HALF_WIDTH_M > 0.0),
                           door_clear=all(v['lane_inside_door'] and
                                          v['margin_after_half_width_m'] > 0.0
                                          for v in door_rows.values())),
    )
    return garage


def cargo_count(scene_xml):
    tree = ET.fromstring(scene_xml)
    names = [str(node.get('name') or '') for node in tree.iter()]
    bodies = [name for name in names if name.startswith('cargo_')]
    return dict(cargo_body_names=bodies, cargo_body_n=len(bodies),
                r3_body_n=sum(1 for name in names if name.startswith('r3__')))


def render_batch(clone, out, values, head, poses, prefix, measure_fn, extra):
    from scripts.e2e_warp_physics import build_context, transport
    import numpy as np
    from PIL import Image
    import hashlib as _hash

    contexts, xml_hashes = [], set()
    for i, (name, spawn) in enumerate(poses.items()):
        ctx = build_context(SEED, out / f'{prefix}-{i:02d}', values, nav_scene=True,
                            nav_spawns=spawn)
        xml_hashes.add(_hash.sha256(ctx['world'].scene_xml.encode()).hexdigest())
        contexts.append(ctx)
    if len(xml_hashes) != 1:
        raise SystemExit('POSE_SCENE_XML_NOT_IDENTICAL:' + str(sorted(xml_hashes)))
    hooks = transport(contexts, out / f'transport-{prefix}', head, values)
    hooks.initialize(contexts)
    frames = {}
    for tick in TICKS:
        if tick:
            # transport() shares one batched state; step all worlds together.
            for _ in range(tick):
                hooks.step(contexts, np.ones(len(contexts), dtype=bool))
        for i, (name, spawn) in enumerate(poses.items()):
            for rid in ('r1', 'r2'):
                jpeg = hooks.capture(i, contexts[i]['world'], rid)
                path = out / 'frames' / f'{prefix}-{name}-{rid}-t{tick:03d}.jpg'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(jpeg)
                rgb = np.asarray(Image.open(path).convert('RGB'))
                row = dict(pose=name, robot=rid, tick=int(tick), spawn=list(spawn[rid]),
                           path=str(path.relative_to(out)),
                           sha256=_hash.sha256(jpeg).hexdigest(), jpeg_bytes=len(jpeg))
                row.update(measure_fn(rgb))
                row.update(extra)
                frames[f'{name}-{rid}-t{tick:03d}'] = row
    return frames, sorted(xml_hashes)[0], contexts, hooks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, help='new run directory (must not exist)')
    ap.add_argument('--expected-source-sha', required=True)
    a = ap.parse_args(argv)
    clone = Path(__file__).resolve().parents[2]
    if Path.cwd().resolve() != clone:
        raise SystemExit('CWD_MUST_BE_CLONE_ROOT:' + str(Path.cwd()))
    out = Path(a.out).resolve()
    if out.exists():
        raise SystemExit('OUTPUT_EXISTS:' + str(out))
    head = git(clone, 'rev-parse', 'HEAD')
    if head != a.expected_source_sha:
        raise SystemExit('SOURCE_SHA_MISMATCH:' + head)
    if git(clone, 'status', '--porcelain', '--untracked-files=normal'):
        raise SystemExit('SOURCE_DIRTY')
    out.mkdir(parents=True)
    (out / 'render_check.py').write_text(Path(__file__).read_text())
    sys.path.insert(0, str(clone))

    from harness.e2ewarp_nav_gate import (FORWARD_ACQUISITION_CAP_M, NAV_SCENARIO,
                                          pair_lane_spawns)
    if FORWARD_CAP_M != FORWARD_ACQUISITION_CAP_M:
        raise SystemExit('FORWARD_CAP_MISMATCH_WITH_GATE_MODE')
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim import scene_contrast_v5 as contrast

    stack = json.loads((clone / 'configs/current_stack.json').read_text())
    values = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
    scene_profile = values['scene_profile']
    profile = contrast.profile_record(scene_profile)
    if profile['light_scale'] != .30 or profile['light_scale_factor_vs_base'] != 1.0:
        raise SystemExit('SCENE_PROFILE_LIGHT_SCALE_NOT_0.30')
    lane_scene = ScenarioFinalV3Scene.from_scenario(NAV_SCENARIO, SEED)
    lane = pair_lane_spawns(lane_scene.config['setup_only']['spawns'])
    if abs(float(lane['r1'][0]) - SPAWN_X) > 5e-4:
        raise SystemExit('SPAWN_MISMATCH:' + str(lane['r1'][0]))
    if abs(float(lane['r1'][1]) - (-2.375)) > 1e-9 or abs(float(lane['r2'][1]) - (-2.875)) > 1e-9:
        raise SystemExit('SPAWN_LANE_MISMATCH')

    zone_free = poses_zone_free(lane)
    path = poses_path(lane)
    frames_free, xml_free, ctx_free, hooks_free = render_batch(
        clone, out, values, head, zone_free, 'zonefree', measure_frame,
        dict(group='zone_free'))
    cargo = cargo_count(ctx_free[0]['world'].scene_xml)
    frames_path, xml_path, ctx_path, hooks_path = render_batch(
        clone, out, values, head, path, 'path', measure_frame, dict(group='forward_path'))
    cargo_path = cargo_count(ctx_path[0]['world'].scene_xml)

    free_rows = [f for f in frames_free.values() if f['robot'] == 'r1']
    path_rows = [f for f in frames_path.values() if f['robot'] == 'r1']
    free_max = max((f['v230']['largest_component_px'] for f in free_rows), default=0)
    free_det = sum(len(f['detections_v230']) for f in free_rows)
    zone_free_pass = bool(free_rows and free_det == 0 and free_max < MIN_COMPONENT_PX)

    geometry = geometry_audit(clone, lane)
    geometry['cargo'] = dict(zone_free_batch=cargo, path_batch=cargo_path,
                             cargo_spawned=bool(cargo['cargo_body_n'] or cargo_path['cargo_body_n']))
    geometry['input_boundary'] = dict(
        render_only=True, controller_n=0, llm_calls=0, ground_truth_inputs=0,
        top_camera_inputs=0, held_world_reads=0,
        static_map_input_to_controller=False,
        static_map_used_for='scene construction + eval/setup-only clearance audit',
        spawn_mutation='setup-only qpos; never a controller input')
    path_pass = bool(path_rows and all(geometry['pass_criteria'].values())
                     and not geometry['cargo']['cargo_spawned'])

    measure = dict(
        schema='ugrp.e2ewarp.nav_v230_fwd24_render_check.v1',
        purpose='render-only ②③ preflight for the approved v230_fwd24 gate mode; '
                'no controller, LLM, GT, evaluator or top-camera input',
        domain='sim',
        seed=SEED, scenario_id=NAV_SCENARIO,
        source_sha=head, clone=str(clone), repo_clean=True,
        gate_mode=dict(name='v230_fwd24', env_selected=False,
                       note='render-only; env not used in this script'),
        band=dict(hue_cv=[110.0, 114.0], sat_min=100.0, val=[30.0, 230.0],
                  min_pixels=MIN_COMPONENT_PX,
                  units='opencv_h_0_180_sv_0_255'),
        forward=dict(cap_m=FORWARD_CAP_M, spawn_x=SPAWN_X,
                     corridor_end_x=SPAWN_X + FORWARD_CAP_M, path_x=list(PATH_X)),
        scene_profile=dict(name=scene_profile, sha256=profile['sha256'],
                           light_scale=profile['light_scale'],
                           light_scale_factor_vs_base=profile['light_scale_factor_vs_base']),
        scene_xml_sha256=dict(zone_free=xml_free, forward_path=xml_path),
        map=dict(map_id='zone_wide_two_doors_final_v3',
                 sha256=sha(clone / 'maps/zones_final_v3/zone_wide_two_doors_final_v3.json')),
        calibration_note='this preflight uses no odometry and no calibration artifact',
        camera=dict(width=640, height=480, hz=10, gamma=1.0, jpeg_quality=82,
                    remap_sha256=hashlib.sha256(
                        hooks_free.mx.tobytes() + hooks_free.my.tobytes()).hexdigest()),
        poses=dict(zone_free=poses_record(zone_free),
                   forward_path=poses_record(path)),
        ticks=list(TICKS),
        frames=dict(zone_free=frames_free, forward_path=frames_path),
        checks=dict(
            zone_free=dict(frame_n=len(free_rows), detections_total=free_det,
                           max_largest_component_px=free_max,
                           hard_rule='detections==0 and max<600',
                           passed=zone_free_pass),
            forward_path=dict(frame_n=len(path_rows),
                              pose_n=len(path),
                              passed=path_pass),
        ),
        geometry=geometry,
        verdict=dict(zone_free_pass=zone_free_pass, forward_path_pass=path_pass,
                     step_b_allowed=bool(zone_free_pass and path_pass)),
    )
    (out / 'measure.json').write_text(json.dumps(measure, ensure_ascii=False, indent=1) + '\n')
    sums = [f'{v["sha256"]}  {v["path"]}' for v in frames_free.values()] + \
           [f'{v["sha256"]}  {v["path"]}' for v in frames_path.values()] + \
           [f'{sha(out / "measure.json")}  measure.json']
    (out / 'SHA256SUMS').write_text('\n'.join(sorted(sums)) + '\n')
    print(json.dumps(dict(out=str(out), source_sha=head,
                          zone_free=dict(frame_n=len(free_rows), detections=free_det,
                                         max_px=free_max, passed=zone_free_pass,
                                         per_pose={f['pose']: f['v230']['largest_component_px']
                                                   for f in free_rows}),
                          forward_path=dict(frame_n=len(path_rows), passed=path_pass,
                                            geometry=geometry['pass_criteria'],
                                            lane_gap_m=geometry['lane_body_gap_m'],
                                            min_obstacle_clearance_m={
                                                rid: geometry['lanes'][rid]['min_obstacle_clearance_m']
                                                for rid in ('r1', 'r2')}),
                          step_b_allowed=measure['verdict']['step_b_allowed']),
                     ensure_ascii=False, indent=1))
    return 0 if measure['verdict']['step_b_allowed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
