"""Static-frame renders (RGB + teacher segmentation label) of random robot poses under chosen floor/light/wall looks.

NO physics step: the scene builder settles ~1.3 SIM s once, afterwards only ``mj_forward`` runs (world time asserted
unchanged).  Re-uses the B1 static renderer (`experiments/2026-09-29-carry-relocalization-b1/render_checkpoints.py`):
same scene (final tag-free map ``zone_wide_door_geometry_v2``, robot model v2), same arm static-gravity-equilibrium, same
``world.render_jpeg`` fisheye JPEG, same class-table label render.  What is new: random robot poses / looks / partner
poses / beam poses, and a per-look XML edit (ground colours, light gain, wall colour gain).

Labels are TEACHER labels: training targets / dev scoring only.  The trained network's run-time input is the own RGB frame.

usage (sim env): python render_static_set.py <out_dir> --split train|dev --looks tr00 tr01 ... default floor_light_v1 ho_plain_grey ...
                                              --n-per-look 60 --seed 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
B1 = ROOT / 'experiments' / '2026-09-29-carry-relocalization-b1'
sys.path[:0] = [str(ROOT), str(B1), str(ROOT / 'experiments' / '2026-09-26-vision-loc'), str(HERE)]

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import render_checkpoints as rc  # noqa: E402  (B1 static renderer; import only: its main() is not run)
import floors  # noqa: E402

MAP_FILE = ROOT / 'maps' / 'zones' / 'zone_wide_door_geometry_v2.json'
VL_TRAIN_EPISODES = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926/render')
CLEAR_M = 0.24                       # robot centre clearance to any wall rectangle
EXCL_POS_M, EXCL_YAW = 0.30, math.radians(30.)   # keep training poses away from the B1 evaluation stations
N_TRAIN_LOOKS = 24


def all_looks():
    lk = {l['name']: l for l in [floors.DEFAULT_LOOK, floors.FLOOR_LIGHT_LOOK, *floors.HELD_OUT, floors.HELD_OUT_WALL, *floors.train_looks(N_TRAIN_LOOKS)]}
    return lk


def eval_stations():
    st = []
    for bx, by in rc.ROUTE:
        st.append((bx - rc.STATION_M, by, 0.0))
        st.append((bx + rc.STATION_M, by, math.pi))
    return st


def wall_rects():
    m = json.loads(MAP_FILE.read_text())
    return [(o['center_m'], o['half_extents_m']) for o in m['obstacles']], m['bounds_m']


def free(x, y, rects, bounds, clear=CLEAR_M):
    x0, x1, y0, y1 = bounds
    if not (x0 + clear < x < x1 - clear and y0 + clear < y < y1 - clear):
        return False
    for (cx, cy), (hx, hy) in rects:
        if abs(x - cx) < hx + clear and abs(y - cy) < hy + clear:
            return False
    return True


def recorded_servos():
    """Commanded servo states seen in the VIS3 TRAIN teacher episodes (the deployment distribution of arm looks)."""
    out = []
    for ep in sorted(VL_TRAIN_EPISODES.glob('vl-train-s90*')):
        seen = set()
        for line in (ep / 'inputs' / 'frames.jsonl').read_text().splitlines():
            s = json.loads(line).get('commanded_servo')
            if s:
                key = tuple(sorted(s.items()))
                if key not in seen:
                    seen.add(key)
                    out.append({int(k): int(v) for k, v in s.items()})
    return out


def look_xml_transform(look):
    """Extra XML edit on top of the repository profile: ground colours, extra light gain, wall rgba gain."""
    import xml.etree.ElementTree as ET

    def edit(xml):
        root = ET.fromstring(xml)
        if 'rgb1' in look:
            for t in root.iter('texture'):
                if t.get('name') == 'ground':
                    t.set('rgb1', ' '.join(f'{v:.4g}' for v in look['rgb1']))
                    t.set('rgb2', ' '.join(f'{v:.4g}' for v in look['rgb2']))
        f = float(look.get('light_scale', .3)) / .3
        if abs(f - 1.) > 1e-9:
            for light in root.iter('light'):
                for key, dflt in (('ambient', (0., 0., 0.)), ('diffuse', (.7, .7, .7)), ('specular', (.3, .3, .3))):
                    v = [float(a) for a in light.get(key).split()] if light.get(key) is not None else list(dflt)
                    light.set(key, ' '.join(f'{a * f:.6g}' for a in v))
        w = float(look.get('wall_scale', 1.))
        if abs(w - 1.) > 1e-9:
            for g in root.iter('geom'):
                if (g.get('name') or '').startswith('zone_wall_'):
                    rgba = [float(a) for a in g.get('rgba').split()]
                    g.set('rgba', ' '.join(f'{min(a * w, 1.):.4g}' for a in rgba[:3]) + f' {rgba[3]:.4g}')
        return ET.tostring(root, encoding='unicode')
    return edit


def build_world_look(look):
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_cargo_contact import CARGO_PROFILES, apply as apply_cargo_profile
    from sim.zone_geometry_scene import GeometryCargoZoneScene
    from sim.zone_own_scene_provider import own_scene
    spec = {'map': rc.MAP_ID, 'seed': 911, 'goal': {'B': {'cyan': 1}}, 'contact_profile': 'cargo_noslip_v1',
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': [rc.ROUTE[0][0], rc.ROUTE[0][1], 0.0]}]}
    scene0 = GeometryCargoZoneScene.from_spec(spec, 'local_contact_fine')
    scene0.config['setup_only']['objects'] = {}
    scene = own_scene(spec, spec['contact_profile'], scene0)
    if look['profile'] != 'default':
        from sim import render_profile as rp
        rp.install(scene, look['profile'])
        inner = scene.transform
        extra = look_xml_transform(look)
        scene.transform = lambda xml: extra(inner(xml))
    xf = ((lambda xml: apply_cargo_profile(scene.transform(xml), spec['contact_profile']))
          if spec['contact_profile'] in CARGO_PROFILES else scene.transform)
    world = MultiMasterPiProductionV2(seed=911, width=640, height=480, render=True, warehouse_layout=scene.engine_layout,
                                      warehouse_cargo_ids=None, xml_transform=xf)
    scene.setup(world)
    return world, scene


def sample_state(rng, rects, bounds, stations, servos, split, mode='uniform'):
    def pose():
        while True:
            x = rng.uniform(bounds[0], bounds[1]); y = rng.uniform(bounds[2], bounds[3])
            if free(x, y, rects, bounds):
                return float(x), float(y), float(rng.uniform(-math.pi, math.pi))

    def pose_far():
        # 'farwall' mode: like the carry corridor - heading within 20 deg of +x or -x (looking down the corridor / at the far wall)
        while True:
            x = rng.uniform(bounds[0], bounds[1]); y = rng.uniform(bounds[2], bounds[3])
            if free(x, y, rects, bounds):
                base = 0.0 if rng.random() < .5 else math.pi
                return float(x), float(y), float(base + rng.uniform(-math.radians(20), math.radians(20)))

    def near_station(p):
        return any(math.hypot(p[0] - s[0], p[1] - s[1]) < EXCL_POS_M and abs((p[2] - s[2] + math.pi) % (2 * math.pi) - math.pi) < EXCL_YAW for s in stations)
    while True:
        rid = 'r1' if rng.random() < .5 else 'r2'
        p_self, p_partner = (pose_far() if mode == 'farwall' else pose()), pose()
        if near_station(p_self) or math.hypot(p_self[0] - p_partner[0], p_self[1] - p_partner[1]) < .40:
            continue
        break
    u = rng.random() if mode != 'farwall' else 0.5      # farwall: search-pose family only
    if u < .35:
        arm = {3: 1072, 4: 2400, 5: 1482}
        arm = {k: int(v + rng.integers(-45, 46)) for k, v in arm.items()}
        servo = {**arm, 1: 2000, 6: int(rng.integers(700, 2301))}
    elif u < .60:
        arm = {3: 740, 4: 2320, 5: 1320}
        arm = {k: int(v + rng.integers(-45, 46)) for k, v in arm.items()}
        servo = {**arm, 1: 2000, 6: int(rng.integers(700, 2301))}
    else:
        servo = dict(servos[int(rng.integers(len(servos)))])
        servo[6] = int(np.clip(servo.get(6, 1500) + rng.integers(-60, 61), 500, 2500))
    beam = None
    if rng.random() < .5:
        for _ in range(50):
            x = rng.uniform(bounds[0], bounds[1]); y = rng.uniform(bounds[2], bounds[3])
            if free(x, y, rects, bounds, .30):
                beam = (float(x), float(y), float(rng.uniform(-math.pi, math.pi)))
                break
    return {'robot': rid, 'pose': p_self, 'partner_pose': p_partner, 'servo': servo, 'beam': beam, 'partner_pan': int(rng.integers(900, 2100))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out_dir')
    ap.add_argument('--split', choices=('train', 'dev'), required=True)
    ap.add_argument('--looks', nargs='+', required=True)
    ap.add_argument('--n-per-look', type=int, default=60)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--mode', choices=('uniform', 'farwall'), default='uniform')
    a = ap.parse_args(argv)
    looks = all_looks()
    rects, bounds = wall_rects()
    stations = eval_stations()
    servos = recorded_servos()
    out = Path(a.out_dir)
    for name in a.looks:
        look = looks[name]
        d = out / name
        if (d / 'manifest.json').exists():
            print('skip', name)
            continue
        (d / 'frames').mkdir(parents=True, exist_ok=True)
        (d / 'labels').mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        world, scene = build_world_look(look)
        t_build = float(world.data.time)
        label_render = rc.make_label_renderer(world)
        seed = int(hashlib.sha256((f'{a.seed}|{a.split}|{name}' + ('' if a.mode == 'uniform' else '|' + a.mode)).encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        rows = []
        for i in range(a.n_per_look):
            st = sample_state(rng, rects, bounds, stations, servos, a.split, a.mode)
            rid = st['robot']
            partner = 'r2' if rid == 'r1' else 'r1'
            b = st['beam'] or (rc.ROUTE[0][0], rc.ROUTE[0][1], 0.0)
            rc.place_beam(world, scene, b[0], b[1], b[2])
            rc.place_robot(world, rid, *st['pose'])
            rc.place_robot(world, partner, *st['partner_pose'])
            rc.set_look(world, partner, {1: 2000, 3: 1072, 4: 2400, 5: 1482, 6: st['partner_pan']})
            resid = rc.set_look(world, rid, st['servo'])
            jpeg = bytes(world.render_jpeg(robot_id=rid, camera='robot_cam'))
            lab = label_render(rid)
            fn = f'{i:04d}'
            (d / 'frames' / f'{fn}.jpg').write_bytes(jpeg)
            ok, png = cv2.imencode('.png', lab)
            (d / 'labels' / f'{fn}.png').write_bytes(png.tobytes())
            truth = rc.camera_truth(world, rid)
            rows.append({'name': fn, 'file': f'frames/{fn}.jpg', 'label': f'labels/{fn}.png', 'look': name, 'robot': rid,
                         'servo': {str(k): int(v) for k, v in st['servo'].items()}, 'eval_only': {**truth, 'beam': st['beam'], 'partner_pose': st['partner_pose'], 'resid_nm': resid},
                         'sha256': hashlib.sha256(jpeg).hexdigest()})
        assert float(world.data.time) == t_build, 'physics advanced while rendering'
        (d / 'manifest.json').write_text(json.dumps({'schema': 'ugrp.seg_lightfloor.static_set.v1', 'split': a.split, 'look': look,
                                                     'look_sha256': floors.look_sha(look), 'seed': seed, 'n': len(rows), 'map_id': rc.MAP_ID,
                                                     'world_time_s': t_build, 'wall_s': round(time.time() - t0, 1), 'rows': rows}))
        print(name, len(rows), 'frames', round(time.time() - t0, 1), 's', flush=True)
        world.close()


if __name__ == '__main__':
    main()
