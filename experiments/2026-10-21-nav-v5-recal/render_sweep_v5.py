#!/usr/bin/env python3
"""Render-only nav re-calibration sweep on the ACT v5 scene (BRANCH_NAV_V5, 2026-10-21).

Same method as the 2026-10-19 Step A sweep (r1 gate lane, x = 1.5/2.0/2.5/2.8/3.0/3.5,
ticks 0/5, zone component size, non-zone false detections, bbox bottom row), on
``walls_floor_contrast_v5_indigo110_s80`` with a same-session v6 control
(``walls_floor_contrast_v6_indigo110_s80_neutral_start``).

Why v5 needs its own check: v5 keeps the authored pickup floor overlay
(``rgba .12 .36 .70``), which the MJWarp native renderer draws opaque at OpenCV
H 107-108 / S~212 / V~90 (``experiments/2026-10-18-nav-gate-1``), two to three
hue units under zone B.  v6 replaced it with neutral tiles; lighting is the same
(v6 light_scale 0.30 = factor 1.0 on the noshadow_bright_v1 base).

Zone attribution (eval-only, setup-only): every lane pose is rendered twice in
the same scene, once normal and once with the zone B paint geom ``zone_zone_B``
repainted neutral grey.  Band pixels that survive the repaint are *non-zone*;
band pixels that vanish are *zone*.  The repainted frame is a reference image
for measurement only and never reaches a controller.

No controller, no LLM, no evaluator/GT input; only setup-only qpos poses, the
camera capture and eval-only measurement.  The script records numbers and a
per-band verdict computed with the frozen rules of
``NAV_V5_RECAL_PREREG(.json|_DRAFT.json)``; it never claims gate success.
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
SPAWN_X = -0.8982
#: Step A lane x (r1 base origin, yaw 0) - the 2026-10-19 sweep list plus 2.8/3.5.
STEP_A_X = (1.5, 2.0, 2.5, 2.8, 3.0, 3.5)
#: The approved 2.4 m forward leg (pickup room, the v5 blue floor is in view).
PATH_X = (SPAWN_X, -0.3, 0.3, 0.9)
ZONE_FREE_POSES = (
    ('wall_south', 1.8, -90.0),
    ('wall_north', 1.8, 90.0),
    ('pickup_west', -1.4, 180.0),
    ('pickup_rear', SPAWN_X, 180.0),
    ('lane_west', 1.5, 180.0),
)
MIN_COMPONENT_PX = 600
ZONE_GEOM = 'zone_zone_B'
ABLATE_RGBA = '0.5 0.5 0.5 1'
V5_PROFILE = 'walls_floor_contrast_v5_indigo110_s80'
V6_PROFILE = 'walls_floor_contrast_v6_indigo110_s80_neutral_start'
#: Pre-registered band candidates, in selection order (only the hue floor moves).
BANDS = (
    ('B0', 'gpu_calib_v230', 'v230_r5'),
    ('B1', 'gpu_calib_v5_h111', 'v230_r5_v5h111'),
    ('B2', 'gpu_calib_v5_h112', 'v230_r5_v5h112'),
)
#: bbox edge tolerance between the detected component and the zone-only component.
EDGE_TOL_PX = 3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(clone, *args):
    return subprocess.check_output(['git', '-C', str(clone), *args], text=True).strip()


# ---- pure helpers (unit-tested without a simulator) -------------------------
def ablate_zone_xml(xml, geom_name=ZONE_GEOM, rgba=ABLATE_RGBA):
    """Repaint the zone B floor geom neutral grey (S == 0). Eval-only reference."""
    root = ET.fromstring(xml)
    hits = [g for g in root.iter('geom') if g.get('name') == geom_name]
    if len(hits) != 1:
        raise ValueError(f'ZONE_GEOM_NOT_UNIQUE:{geom_name}:{len(hits)}')
    for g in hits:
        g.attrib.pop('material', None)
        g.set('rgba', rgba)
    return ET.tostring(root, encoding='unicode')


def lane_poses(lane, xs):
    """r1 on its lane at x; r2 at the same x on the parallel lane (both yaw 0)."""
    r1, r2 = lane['r1'], lane['r2']
    return {f'x{x:+.3f}': {'r1': [x, r1[1], r1[2], r1[3]], 'r2': [x, r2[1], r2[2], r2[3]]}
            for x in xs}


def zone_free_poses(lane):
    r1, r2 = lane['r1'], lane['r2']
    return {name: {'r1': [x, r1[1], r1[2], r1[3] + math.radians(yaw)], 'r2': list(r2)}
            for name, x, yaw in ZONE_FREE_POSES}


def band_mask(rgb, band):
    import numpy as np
    from harness.e2ewarp_selfnav import hue_degrees_to_opencv, rgb_to_hsv
    h_deg, s, v = rgb_to_hsv(np.asarray(rgb, dtype=np.uint8))
    h = hue_degrees_to_opencv(h_deg)
    lo, hi = band['hue_cv']
    vlo, vhi = band['val']
    return (h >= lo) & (h <= hi) & (s >= band['sat_min']) & (v >= vlo) & (v <= vhi)


def _component(mask):
    from harness.e2ewarp_selfnav import largest_component
    comp = largest_component(mask)
    return None if comp is None else dict(px=int(comp['area']),
                                          bbox=[int(comp[k]) for k in
                                                ('left', 'top', 'right', 'bottom')])


def measure_pair(rgb, rgb_ablated, profile):
    """One frame, one band: detection, zone-only component, non-zone component."""
    import numpy as np
    from harness.e2ewarp_selfnav import (BEARING_POSITIVE_LEFT, GPU_CALIB_PROFILES,
                                         GpuCalibZoneDetector, ground_distance_m)
    band = GPU_CALIB_PROFILES[profile]
    det = GpuCalibZoneDetector(profile=profile, bearing_convention=BEARING_POSITIVE_LEFT)
    m = band_mask(rgb, band)
    row = dict(total_px=int(m.sum()), largest=_component(m))
    hits = det(np.asarray(rgb, dtype=np.uint8))
    row['detected'] = bool(hits)
    if hits:
        left, top, right, bottom = (int(v) for v in hits[0]['bbox'])
        row['detection'] = dict(bbox=[left, top, right, bottom], px=int(hits[0]['pixels']),
                                bottom_row=bottom - 1, bottom_norm=round(bottom / m.shape[0], 6),
                                height_norm=round(float(hits[0]['height_norm']), 6),
                                bearing_deg=round(float(hits[0]['bearing_deg']), 4),
                                bottom_ground_m=ground_distance_m((left + right - 1) / 2.0,
                                                                  bottom - 1))
    if rgb_ablated is not None:
        ma = band_mask(rgb_ablated, band)
        zone = m & ~ma
        row['zone_only'] = _component(zone)
        row['nonzone'] = dict(total_px=int(ma.sum()), largest=_component(ma),
                              detected=bool(det(np.asarray(rgb_ablated, dtype=np.uint8))))
        if hits:
            l, t, r, b = row['detection']['bbox']
            inside = np.zeros_like(m)
            inside[t:b, l:r] = True
            row['detection']['nonzone_px_in_bbox'] = int((m & ma & inside).sum())
    return row


def edges_match(det_bbox, zone_bbox, tol=EDGE_TOL_PX):
    """Left/right/bottom edges of the detection agree with the zone-only component."""
    if det_bbox is None or zone_bbox is None:
        return False
    return all(abs(int(det_bbox[i]) - int(zone_bbox[i])) <= tol for i in (0, 2, 3))


def evaluate_band(rows):
    """Frozen per-band criteria C1-C4 over measured rows (see the prereg)."""
    free = [r for r in rows if r['group'] == 'zone_free' and r['robot'] == 'r1']
    lane = [r for r in rows if r['group'] in ('step_a', 'path')]
    step_a_r1 = [r for r in rows if r['group'] == 'step_a' and r['robot'] == 'r1']
    c1 = bool(free) and all(not r['m']['detected'] and
                            (r['m']['largest'] or {}).get('px', 0) < MIN_COMPONENT_PX
                            for r in free)
    c2 = bool(lane) and all(not r['m']['nonzone']['detected'] and
                            (r['m']['nonzone']['largest'] or {}).get('px', 0) < MIN_COMPONENT_PX
                            for r in lane)
    c3 = bool(step_a_r1) and all(r['m']['detected'] for r in step_a_r1)
    detected = [r for r in lane if r['m']['detected']]
    c4 = all(edges_match(r['m']['detection']['bbox'], (r['m']['zone_only'] or {}).get('bbox'))
             for r in detected)
    fail = dict(
        c1=[r['key'] for r in free if r['m']['detected'] or
            (r['m']['largest'] or {}).get('px', 0) >= MIN_COMPONENT_PX],
        c2=[r['key'] for r in lane if r['m']['nonzone']['detected'] or
            (r['m']['nonzone']['largest'] or {}).get('px', 0) >= MIN_COMPONENT_PX],
        c3=[r['key'] for r in step_a_r1 if not r['m']['detected']],
        c4=[r['key'] for r in detected if not edges_match(
            r['m']['detection']['bbox'], (r['m']['zone_only'] or {}).get('bbox'))])
    return dict(C1_zone_free=c1, C2_nonzone_fp0=c2, C3_step_a_r1_detect=c3,
                C4_no_floor_merge=c4, passed=bool(c1 and c2 and c3 and c4),
                frame_n=dict(zone_free_r1=len(free), lane=len(lane), step_a_r1=len(step_a_r1),
                             lane_detected=len(detected)),
                failing_frames=fail)


def select_band(verdicts):
    """Frozen rule: B0 if it passes; else the first passing of B1, B2; else stop."""
    for name, _profile, _mode in BANDS:
        if verdicts.get(name, {}).get('passed'):
            return dict(selected=name, profile=dict((b[0], b[1]) for b in BANDS)[name],
                        gate_mode=dict((b[0], b[2]) for b in BANDS)[name],
                        step_b_allowed=True)
    return dict(selected=None, profile=None, gate_mode=None, step_b_allowed=False,
                stop='NO_BAND_PASSED: report, do not run Step B, no new band after results')


# ---- render (VM only) ------------------------------------------------------
def render_batch(out, values, head, poses, prefix, xml_transform=None):
    from scripts.e2e_warp_physics import build_context, transport
    import numpy as np
    from PIL import Image

    contexts, xml_hashes = [], set()
    for i, (name, spawn) in enumerate(poses.items()):
        ctx = build_context(SEED, out / f'{prefix}-{i:02d}', values, nav_scene=True,
                            nav_spawns=spawn, eval_xml_transform=xml_transform)
        xml_hashes.add(hashlib.sha256(ctx['world'].scene_xml.encode()).hexdigest())
        contexts.append(ctx)
    if len(xml_hashes) != 1:
        raise SystemExit('POSE_SCENE_XML_NOT_IDENTICAL:' + str(sorted(xml_hashes)))
    hooks = transport(contexts, out / f'transport-{prefix}', head, values)
    hooks.initialize(contexts)
    frames = {}
    for tick in TICKS:
        if tick:
            for _ in range(tick):
                hooks.step(contexts, np.ones(len(contexts), dtype=bool))
        for i, (name, spawn) in enumerate(poses.items()):
            for rid in ('r1', 'r2'):
                jpeg = hooks.capture(i, contexts[i]['world'], rid)
                path = out / 'frames' / f'{prefix}-{name}-{rid}-t{tick:03d}.jpg'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(jpeg)
                frames[(name, rid, tick)] = dict(
                    path=str(path.relative_to(out)), sha256=hashlib.sha256(jpeg).hexdigest(),
                    rgb=np.asarray(Image.open(path).convert('RGB')), spawn=list(spawn[rid]))
    remap = hashlib.sha256(hooks.mx.tobytes() + hooks.my.tobytes()).hexdigest()
    return frames, sorted(xml_hashes)[0], remap, contexts


def scene_rows(out, values, head, lane, label):
    groups = dict(step_a=lane_poses(lane, STEP_A_X), path=lane_poses(lane, PATH_X),
                  zone_free=zone_free_poses(lane))
    normal_poses = {f'{g}:{k}': v for g, poses in groups.items() for k, v in poses.items()}
    lane_only = {k: v for k, v in normal_poses.items() if not k.startswith('zone_free:')}
    normal, xml_n, remap, ctx = render_batch(out, values, head, normal_poses, f'{label}-normal')
    ablated, xml_a, _, _ = render_batch(out, values, head, lane_only, f'{label}-ablated',
                                        xml_transform=ablate_zone_xml)
    rows = {b[0]: [] for b in BANDS}
    meta = {}
    for (name, rid, tick), f in normal.items():
        group, pose = name.split(':', 1)
        a = ablated.get((name, rid, tick))
        key = f'{label}:{name}-{rid}-t{tick:03d}'
        meta[key] = dict(group=group, pose=pose, robot=rid, tick=tick, spawn=f['spawn'],
                         frame=f['path'], sha256=f['sha256'],
                         ablated_frame=None if a is None else a['path'],
                         ablated_sha256=None if a is None else a['sha256'])
        for bname, profile, _ in BANDS:
            rows[bname].append(dict(key=key, group=group, pose=pose, robot=rid, tick=tick,
                                    m=measure_pair(f['rgb'], None if a is None else a['rgb'],
                                                   profile)))
    render = ctx[0]['scene'].manifest.get('render_profile', {}) if hasattr(
        ctx[0].get('scene'), 'manifest') else {}
    return rows, meta, dict(scene_xml_sha256_normal=xml_n, scene_xml_sha256_ablated=xml_a,
                            remap_sha256=remap,
                            render_profile_sha256=render.get('sha256'),
                            render_profile_name=render.get('name'),
                            poses={g: {k: [round(float(x), 6) for x in v['r1']]
                                       for k, v in p.items()} for g, p in groups.items()})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True, help='new run directory (must not exist)')
    ap.add_argument('--expected-source-sha', required=True)
    ap.add_argument('--prereg', required=True, help='frozen NAV_V5_RECAL_PREREG.json')
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
    prereg_path = Path(a.prereg).resolve()
    prereg = json.loads(prereg_path.read_text())
    if prereg.get('status') != 'FROZEN':
        raise SystemExit('PREREG_NOT_FROZEN:' + str(prereg.get('status')))
    out.mkdir(parents=True)
    (out / 'render_sweep_v5.py').write_text(Path(__file__).read_text())
    sys.path.insert(0, str(clone))

    from harness.e2ewarp_nav_gate import NAV_SCENARIO, pair_lane_spawns
    from harness.e2ewarp_nav_scene import apply_scene_profile, scene_selection
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim import scene_contrast_v5 as contrast

    stack = json.loads((clone / 'configs/current_stack.json').read_text())
    values_v6 = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
    if values_v6['scene_profile'] != V6_PROFILE:
        raise SystemExit('STACK_SCENE_PROFILE_NOT_V6:' + values_v6['scene_profile'])
    values_v5, _ = apply_scene_profile(values_v6, scene_selection('v5'))
    lane_scene = ScenarioFinalV3Scene.from_scenario(NAV_SCENARIO, SEED)
    lane = pair_lane_spawns(lane_scene.config['setup_only']['spawns'])
    if abs(float(lane['r1'][0]) - SPAWN_X) > 5e-4:
        raise SystemExit('SPAWN_MISMATCH:' + str(lane['r1'][0]))
    if abs(float(lane['r1'][1]) + 2.375) > 1e-9 or abs(float(lane['r2'][1]) + 2.875) > 1e-9:
        raise SystemExit('SPAWN_LANE_MISMATCH')

    scenes = {}
    for label, values in (('v5', values_v5), ('v6', values_v6)):
        rows, meta, info = scene_rows(out, values, head, lane, label)
        profile = contrast.profile_record(values['scene_profile'])
        info.update(scene_profile=values['scene_profile'], profile_sha256=profile['sha256'])
        verdicts = {b: evaluate_band(r) for b, r in rows.items()}
        scenes[label] = dict(info=info, frames=meta, rows=rows, verdicts=verdicts)
    selection = select_band(scenes['v5']['verdicts'])
    measure = dict(
        schema='ugrp.e2ewarp.nav_v5_recal_render_sweep.v1',
        purpose='render-only BRANCH_NAV_V5 band check on the ACT v5 scene; v6 same-session '
                'control; no controller, LLM, GT, evaluator or top-camera input',
        domain='sim', seed=SEED, scenario_id=NAV_SCENARIO, source_sha=head, repo_clean=True,
        prereg=dict(path=str(prereg_path), sha256=sha(prereg_path), status=prereg['status']),
        ticks=list(TICKS), step_a_x=list(STEP_A_X), path_x=list(PATH_X),
        min_component_px=MIN_COMPONENT_PX, edge_tol_px=EDGE_TOL_PX,
        zone_attribution=dict(method='normal minus zone-B-repainted render (same scene, '
                                     'same pose, same tick)', geom=ZONE_GEOM,
                              rgba=ABLATE_RGBA, eval_only=True),
        bands={b: dict(profile=p, gate_mode=m) for b, p, m in BANDS},
        scenes=scenes,
        selection=dict(scene='v5', rule='B0 if pass; else first passing of B1, B2; else stop',
                       **selection),
        v6_control_note='v6 verdicts are a same-session control of the method; they do not '
                        'select the band and are never pooled with v5',
        input_boundary=dict(render_only=True, controller_n=0, llm_calls=0,
                            ground_truth_inputs=0, top_camera_inputs=0,
                            spawn_mutation='setup-only qpos; never a controller input'),
    )
    (out / 'measure.json').write_text(json.dumps(measure, ensure_ascii=False, indent=1) + '\n')
    sums = []
    for label in scenes:
        for v in scenes[label]['frames'].values():
            sums.append(f'{v["sha256"]}  {v["frame"]}')
            if v['ablated_frame']:
                sums.append(f'{v["ablated_sha256"]}  {v["ablated_frame"]}')
    sums.append(f'{sha(out / "measure.json")}  measure.json')
    (out / 'SHA256SUMS').write_text('\n'.join(sorted(set(sums))) + '\n')
    print(json.dumps(dict(out=str(out), source_sha=head,
                          v5={b: v['passed'] for b, v in scenes['v5']['verdicts'].items()},
                          v6_control={b: v['passed'] for b, v in scenes['v6']['verdicts'].items()},
                          v5_failing=scenes['v5']['verdicts']['B0']['failing_frames'],
                          selection=selection), ensure_ascii=False, indent=1))
    return 0 if selection['step_b_allowed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
