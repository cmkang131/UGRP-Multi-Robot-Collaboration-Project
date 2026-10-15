"""Finite, gcp2-only static camera sampling/texture investigation.

All truth masks and synthetic pose increments are evaluation fixtures only.
No mj_step, navigation, learner, model endpoint or GUI is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import sys
import time

import cv2
import numpy as np
from PIL import Image

from scripts import probe_scene_tex2 as old
from scripts.summarize_scene_tex2_probe import distribution
from sim import camera_render_quality as quality

MATERIALS = (*old.PROFILES, 'walls_floor_textured_v3')
ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    return old.write(path, value)


def features(bgr, mask, fast=20):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    kp, desc = cv2.ORB_create(nfeatures=800, fastThreshold=fast).detectAndCompute(
        gray, mask.astype(np.uint8)*255)
    return kp, desc


def measure(bgr, masks):
    """ORB defaults match v2; FAST7 additionally matches reloc11_features.

    Laplacian is calculated BEFORE masking. Erode its 3x3 support, so object
    boundaries cannot inflate the floor sharpness score.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F, ksize=1)
    out = {}
    for label in ('wall', 'floor'):
        mask = masks[label]
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        interior = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        row = {'pixels': int(mask.sum()), 'laplacian_variance': float(lap[interior].var()) if interior.any() else None}
        for fast in (20, 7):
            kp, _ = features(bgr, mask, fast)
            row['orb'+str(fast)] = len(kp)
            row['interior'+str(fast)] = int(sum(dist[min(mask.shape[0]-1, round(k.pt[1])),
                min(mask.shape[1]-1, round(k.pt[0]))] >= k.size*math.sqrt(2)/2 for k in kp))
        out[label] = row
    return out


def jpeg(bgr, q, *, pil=False):
    if pil:
        buf = io.BytesIO()
        Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).save(buf, format='JPEG', quality=q)
        raw = buf.getvalue()
    else:
        ok, raw = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, q])
        if not ok:
            raise OSError('JPEG encode failed')
        raw = raw.tobytes()
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR), raw


def semantic(bgr, pwm):
    result = old.detector_results(bgr, pwm)
    boxes = result['boxes_own_zone_v2']
    # Exact existing detector kind multiset (same semantic comparison as v2).
    counts = Counter(x['kind'] for x in boxes.get('detections', [])) if isinstance(boxes, dict) else Counter(x['kind'] for x in boxes)
    return {'box_counts': dict(counts), 'detectors': result}


def classify(bgr, palettes):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # Authored bounds and the existing all-hue paint S20 lower limit.
    masks = {('wall' if k == 'walls' else k): (hsv[..., 1] < 20) &
            (hsv[..., 2] >= p['v'][0]) & (hsv[..., 2] <= p['v'][1]) for k, p in palettes.items()}
    if palettes['floor'].get('neutral_v1_floor'):
        # Authored neutral RGB floor has B-R=0; cool wall has B-R>0.
        # Channel ordering is a material colour classifier, not a new
        # acceptance/error threshold or a change to cargo/zone detectors.
        cool = bgr[..., 0].astype(int) > bgr[..., 2].astype(int)
        masks['wall'] &= cool
        masks['floor'] &= ~cool
    return masks


def matching(a, b, ma, mb):
    from harness.natural_floor_slam import _matches, Options
    out = {}
    for surface in ('floor', 'wall'):
        for fast in (20, 7):
            ka, da = features(a, ma[surface], fast)
            kb, db = features(b, mb[surface], fast)
            pairs = _matches(da, db, Options().ratio) if da is not None and db is not None else []
            out[surface+str(fast)] = {'before': len(ka), 'after': len(kb), 'mutual_ratio_matches': len(pairs)}
    return out


def capture(renderer, model, data, rid, groups, name):
    import mujoco
    option = mujoco.MjvOption()
    option.geomgroup[:] = 1
    option.geomgroup[4:6] = 0
    start = time.perf_counter()
    renderer.update_scene(data, camera=rid+'__robot_cam', scene_option=option)
    ideal = renderer.render().copy()
    rendered = time.perf_counter()
    stages = quality.sampling_stages(ideal, name)
    sampled = time.perf_counter()
    renderer.enable_segmentation_rendering()
    try:
        renderer.update_scene(data, camera=rid+'__robot_cam', scene_option=option)
        seg = renderer.render().copy()
    finally:
        renderer.disable_segmentation_rendering()
    ids = np.where(seg[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM), seg[..., 0], -1)
    final_ids = quality.remap_ids(ids, name)
    native_masks = {k: np.isin(final_ids, list(v)) for k, v in groups.items()}
    # For intermediate fisheye metrics, retain high-resolution labels.
    q = quality.resolve(name)
    high_ids = quality.remap_ids(ids, name, old.WIDTH, old.HEIGHT) if q.scale == 1 else None
    if q.scale != 1:
        from sim.masterpi_camera_profile import raw_fisheye_remap
        mx, my = raw_fisheye_remap(old.WIDTH*q.scale, old.HEIGHT*q.scale)
        high_ids = cv2.remap(ids.astype(np.float32), mx, my, cv2.INTER_NEAREST,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=-1).astype(np.int32)
    stage_masks = {'pinhole': {k: np.isin(ids, list(v)) for k, v in groups.items()},
                   'fisheye': {k: np.isin(high_ids, list(v)) for k, v in groups.items()}, 'final': native_masks}
    return {k: cv2.cvtColor(v, cv2.COLOR_RGB2BGR) for k, v in stages.items()}, stage_masks, {
        'render_s': rendered-start, 'remap_reduce_s': sampled-rendered, 'rgb_s': sampled-start,
        'excludes_segmentation_and_analysis': True}


def run(args):
    import mujoco
    from scripts.generate_scene_textures import MAPS
    from scripts.audit_scene_textures import color_ranges
    from sim.natural_scene_texture_v2 import manifest
    palettes = manifest()['palettes_hsv']
    if 'walls_floor_textured_v3' in args.materials:
        from sim.natural_scene_texture_v3 import manifest as v3_manifest
        palettes = v3_manifest()['palettes_hsv']
    ranges, _, _ = color_ranges()
    external = json.loads((ROOT/'experiments/2026-10-15-scene-tex2/color_external_sources.json').read_text())
    for path, sha in external['source_sha256'].items():
        if old.sha256((ROOT/path).read_bytes()) != sha:
            raise ValueError('COLOUR_SOURCE_CHANGED:'+path)
    ranges += external['additional_hsv_ranges']
    args.output.mkdir(parents=True, exist_ok=False)
    rows, models, errors = [], [], []
    meta = {'source_sha': args.source_sha, 'host': platform.node(), 'mujoco': mujoco.__version__,
            'opencv': cv2.__version__, 'materials': args.materials, 'qualities': args.qualities,
            'physics_steps': 0, 'model_calls': 0, 'sim_s': 0, 'cap_end': False,
            'reproduction_command': [sys.executable, '-m', 'scripts.probe_scene_tex3', *sys.argv[1:]],
            'scope': 'static fixture sequence, NOT motion/VO/localization success',
            'matching_increment': 'one raw fisheye center pixel horizontal angle atan(1/fx), evaluation-only base yaw',
            'segmentation_palette_source': 'v3' if 'walls_floor_textured_v3' in args.materials else 'v2',
            'rejection_table': str(args.output/'rejection-table.json')}
    meta['planned_frames'] = sum(old.planned_case_count(len(old.wall_views(json.loads(p.read_text()))), args.poses)
        for p in MAPS) * len(old.ROBOTS) * len(args.materials) * len(args.qualities)
    write(args.output/'meta.json', meta)
    try:
        for map_path in MAPS:
            views = old.wall_views(json.loads(map_path.read_text()))
            reference = None
            for material in args.materials:
                for quality_name in args.qualities:
                    model, scene, hardware, xml, audit = old.build_model(map_path, material)
                    fp = (old.physics_fingerprint(model)['sha256'], old.camera_fingerprint(model)['sha256'])
                    if reference is None:
                        reference = fp
                    if fp != reference:
                        raise ValueError('PHYSICS_OR_CAMERA_PARITY_FAIL')
                    width, height = quality.configure_model(model, quality_name)
                    renderer = mujoco.Renderer(model, height, width)
                    try:
                        context = quality.configure_context(renderer, model, quality_name)
                        models.append({'map': map_path.stem, 'material': material, 'quality': quality_name,
                            'physics_sha256': fp[0], 'camera_sha256': fp[1], 'identical': fp == reference,
                            'render': context, 'light_castshadow': model.light_castshadow.tolist()})
                        data = mujoco.MjData(model)
                        groups = old.geometry_groups(model, scene)
                        for vi, view in enumerate(views):
                            for pose in old.poses_for_view(vi, args.poses):
                                pwm, setup = old.fixture(model, data, scene, view, pose, hardware)
                                base_qpos = data.qpos.copy()
                                for rid in old.ROBOTS:
                                    case = f'{map_path.stem}--view{vi}--{pose}--{rid}'
                                    stem = case+'--'+material+'--'+quality_name
                                    # Resume only complete same-fixture records after external VM STOP.
                                    # This does not alter sampling, fixture positions or measurements.
                                    # Keep originals immutable; link their media and preserve provenance.
                                    if args.resume_from is not None and (args.resume_materials is None or material in args.resume_materials):
                                        from scripts.summarize_scene_tex3 import read
                                        saved_path = args.resume_from/(stem+'.json')
                                        if saved_path.is_file() or saved_path.with_name(saved_path.name+'.zst').is_file():
                                            saved = read(saved_path)
                                            if (saved['case'], saved['material'], saved['quality'], saved['qpos_sha256']) != (
                                                    case, material, quality_name, old._array_digest(base_qpos)):
                                                raise ValueError('RESUME_FIXTURE_MISMATCH')
                                            for enc in saved['encodings'].values():
                                                if old.sha256((args.resume_from/enc['file']).read_bytes()) != enc['sha256']:
                                                    raise ValueError('RESUME_FRAME_HASH_MISMATCH')
                                            required = [stem+'--next.png', stem+'--mask-floor.png', stem+'--mask-wall.png']
                                            if any(cv2.imread(str(args.resume_from/f)) is None for f in required):
                                                raise ValueError('RESUME_AUXILIARY_IMAGE_MISSING')
                                            for source in args.resume_from.glob(stem+'*'):
                                                if source.suffix in ('.png', '.jpg'):
                                                    (args.output/source.name).symlink_to(source.resolve())
                                            original = saved_path if saved_path.is_file() else saved_path.with_name(saved_path.name+'.zst')
                                            saved['resume_provenance'] = {'original': str(original), 'sha256': old.sha256(original.read_bytes()),
                                                'source_sha': json.loads((args.resume_from/'meta.json').read_text())['source_sha'],
                                                'excluded_from_rerender_cost': True}
                                            path = write(args.output/(stem+'.json'), saved)
                                            rows.append({'case': case, 'material': material, 'quality': quality_name, 'record': path.name})
                                            continue
                                    stages, masks, timing = capture(renderer, model, data, rid, groups, quality_name)
                                    # Warm timing after shaders/textures are resident. Fixed three repetitions
                                    # are measurements, never a timer-based search budget.
                                    samples = []
                                    for _ in range(3):
                                        t = time.perf_counter()
                                        renderer.render()
                                        r = time.perf_counter()
                                        quality.sampling_stages(cv2.cvtColor(stages['pinhole'], cv2.COLOR_BGR2RGB), quality_name)
                                        samples.append({'render_s': r-t, 'rgb_s': time.perf_counter()-t})
                                    row = {'case': case, 'material': material, 'quality': quality_name, 'pose': pose,
                                        'map': map_path.stem, 'view': vi, 'robot': rid, 'timing': timing,
                                        'warm_timing': samples, 'qpos_sha256': old._array_digest(base_qpos),
                                        'stages': {k: measure(v, masks[k]) for k, v in stages.items()}, 'encodings': {}}
                                    encodings = {'png': (stages['final'], None),
                                                 'jpeg90': jpeg(stages['final'], 90),
                                                 'pil82': jpeg(stages['final'], 82, pil=True)}
                                    for enc, (image, raw) in encodings.items():
                                        path = args.output/(stem+('--'+enc+'.jpg' if raw else '.png'))
                                        if raw:
                                            path.write_bytes(raw)
                                        else:
                                            cv2.imwrite(str(path), image)
                                        predicted = classify(image, palettes)
                                        colours = old.colour_metrics(image, masks['final'], ranges)
                                        row['encodings'][enc] = {'surfaces': measure(image, masks['final']),
                                            'iou': {k: old.mask_score(predicted[k], masks['final'][k]) for k in ('floor', 'wall')},
                                            'semantic': semantic(image, pwm),
                                            'intrusions': {label: c['surface_false_pixels'] for label, c in colours.items()
                                                           if any(c['surface_false_pixels'].values())},
                                            'target_support': {label: c['target_support_pixels'] for label, c in colours.items()
                                                               if any(c['target_support_pixels'].values())},
                                            'file': path.name, 'sha256': old.sha256(path.read_bytes())}
                                    for k in ('floor', 'wall'):
                                        cv2.imwrite(str(args.output/(stem+'--mask-'+k+'.png')), masks['final'][k].astype(np.uint8)*255)
                                    # Two consecutive STATIC poses, independent of commands/physics. Increment
                                    # is derived from native center angular pixel scale, not a fitted gate.
                                    bid = model.body(rid+'__robot').id
                                    adr = int(model.jnt_qposadr[int(model.body_jntadr[bid])])
                                    from sim.masterpi_camera_profile import CAMERA_FX_PX
                                    dtheta = math.atan(1/CAMERA_FX_PX)
                                    w, x, y, z = base_qpos[adr+3:adr+7]
                                    c, s = math.cos(dtheta/2), math.sin(dtheta/2)
                                    data.qpos[adr+3:adr+7] = [c*w-s*z, c*x-s*y, c*y+s*x, c*z+s*w]
                                    mujoco.mj_forward(model, data)
                                    after, after_masks, _ = capture(renderer, model, data, rid, groups, quality_name)
                                    row['matches'] = {}
                                    for enc, (before, _) in encodings.items():
                                        b = after['final'] if enc == 'png' else jpeg(after['final'], 90 if enc == 'jpeg90' else 82, pil=enc == 'pil82')[0]
                                        row['matches'][enc] = matching(before, b, masks['final'], after_masks['final'])
                                    cv2.imwrite(str(args.output/(stem+'--next.png')), after['final'])
                                    data.qpos[:] = base_qpos
                                    mujoco.mj_forward(model, data)
                                    path = write(args.output/(stem+'.json'), row)
                                    rows.append({'case': case, 'material': material, 'quality': quality_name, 'record': path.name})
                        print(json.dumps({'finished': [map_path.stem, material, quality_name], 'frames': len(rows)}), flush=True)
                    finally:
                        renderer.close()
    except BaseException as exc:
        import traceback
        errors.append({'category': 'SUPERVISOR_STOP' if isinstance(exc, KeyboardInterrupt) else 'HOST_ERROR', 'blocking_object': 'camera_probe', 'minimum_gap_m': None,
                       'minimum_gap_reason': 'static image diagnosis, no clearance gate', 'reason': repr(exc),
                       'traceback': traceback.format_exc()})
        raise
    finally:
        write(args.output/'models.json', models)
        write(args.output/'index.json', rows)
        write(args.output/'rejection-table.json', {'stages': [
            {'stage': 'render_and_analyse', 'cumulative_pass_n': len(rows), 'rejected_n': len(errors)}],
            'errors': errors, 'raw_path': str(args.output), 'reproduction_command': meta['reproduction_command']})
        write(args.output/'summary.json', {**meta, 'frames': len(rows), 'status': 'INCOMPLETE_OR_HOST_ERROR'
              if errors or len(rows) != meta['planned_frames'] else 'MEASURED', 'errors': errors})
        write(args.output/'SHA256SUMS.json', {p.name: old.sha256(p.read_bytes()) for p in args.output.iterdir()
                                            if p.is_file() and not p.name.startswith('SHA256SUMS')})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--materials', nargs='+', choices=MATERIALS, default=list(old.PROFILES))
    p.add_argument('--qualities', nargs='+', choices=quality.PROFILES, default=list(quality.PROFILES))
    p.add_argument('--poses', nargs='+', choices=old.POSES+old.POSITIVE_POSES)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--resume-from', type=Path)
    p.add_argument('--resume-materials', nargs='+', choices=MATERIALS)
    a = p.parse_args()
    if platform.system() != 'Linux' or not a.execute or not platform.node().startswith('ugrp-sim-gcp2'):
        p.error('explicit execution on gcp2 required; Mac rendering forbidden')
    old.validate_source(a.source_sha)
    old.setup_proof(Path('/home/ugrp/ugrp-sim/scenetex2-setup-proof.md'))
    os.chdir(ROOT)
    run(a)


if __name__ == '__main__':
    main()
