"""Prepare hardmaps1 only: static planning, diagrams, optional stationary MJCF audit."""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from harness import zone_heldout_maps as hm
from sim import heldout_wall_texture_source as texture

EXP = hm.ROOT/'experiments/2026-10-09-hardmaps1-heldout'
RES = .025
# Unloaded, fixed travel heading. Includes forward arm space, NOT a carry envelope.
BODY = (-.100, .300, -.130, .130)
MARGIN = .025


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def source_sha():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=hm.ROOT, text=True).strip()


def walls(value):
    return [dict(name='zone_'+o['id'], pos=[*o['center_m'], o['height_m']/2],
                 size=[*o['half_extents_m'], o['height_m']/2]) for o in value['obstacles']]


def cues(value):
    layout = texture.layout(sorted(walls(value), key=lambda w: w['name']))
    area = (value['bounds_m'][1]-value['bounds_m'][0])*(value['bounds_m'][3]-value['bounds_m'][2])
    count = sum(len(f['tapes']) for f in layout['faces'])
    return dict(arena_area_m2=area, color_regions=len(value['regions']),
        color_boundary_m=sum(4*sum(r['half_extents_m']) for r in value['regions'].values()),
        wall_height_m=.4, wall_face_area_m2=sum(f['length_m']*f['height_m'] for f in layout['faces']),
        wall_tapes=count, wall_patches=sum(len(f['patches']) for f in layout['faces']),
        tapes_per_arena_m2=count/area, render_profile='floor_light_v1', wall_texture='tape_v1',
        checker_rule='same ground texture, material, texrepeat and arena bounds')


def footprint(yaw):
    x0, x1, y0, y1 = BODY
    if yaw == math.pi:
        x0, x1 = -x1, -x0
    elif yaw != 0:
        raise ValueError('static checker supports authored 0/pi headings only')
    return x0-MARGIN, x1+MARGIN, y0-MARGIN, y1+MARGIN


def forbidden(value, yaw):
    fx0, fx1, fy0, fy1 = footprint(yaw)
    rects = []
    for o in value['obstacles']:
        x, y = o['center_m']; hx, hy = o['half_extents_m']
        rects.append((x-hx-fx1, x+hx-fx0, y-hy-fy1, y+hy-fy0))
    return rects


def segment_clear(a, b, value, yaw):
    # A swept AABB is exact for axis-aligned translation, conservative for connectors.
    x0, x1 = sorted((a[0], b[0])); y0, y1 = sorted((a[1], b[1]))
    bx0, bx1, by0, by1 = value['bounds_m']; fx0, fx1, fy0, fy1 = footprint(yaw)
    if x0+fx0 < bx0 or x1+fx1 > bx1 or y0+fy0 < by0 or y1+fy1 > by1:
        return False
    return all(x1 < ox0 or x0 > ox1 or y1 < oy0 or y0 > oy1
               for ox0, ox1, oy0, oy1 in forbidden(value, yaw))


def plan_all(value, start, targets, yaw):
    xmin, xmax, ymin, ymax = value['bounds_m']
    xs = np.arange(round((xmax-xmin)/RES)+1)*RES+xmin
    ys = np.arange(round((ymax-ymin)/RES)+1)*RES+ymin
    fx0, fx1, fy0, fy1 = footprint(yaw)
    free = np.ones((len(ys), len(xs)), bool)
    free &= (xs[None, :]+fx0 >= xmin) & (xs[None, :]+fx1 <= xmax)
    free &= (ys[:, None]+fy0 >= ymin) & (ys[:, None]+fy1 <= ymax)
    for x0, x1, y0, y1 in forbidden(value, yaw):
        free &= ~((xs[None, :] >= x0-1e-10) & (xs[None, :] <= x1+1e-10) &
                  (ys[:, None] >= y0-1e-10) & (ys[:, None] <= y1+1e-10))

    def point(c):
        return [float(xs[c[0]]), float(ys[c[1]])]

    def connect(p):
        if not segment_clear(p, p, value, yaw):
            raise ValueError(f'blocked authored endpoint {p}')
        ix, iy = round((p[0]-xmin)/RES), round((p[1]-ymin)/RES)
        cells = [(ix+dx, iy+dy) for dx in range(-2, 3) for dy in range(-2, 3)
                 if 0 <= ix+dx < len(xs) and 0 <= iy+dy < len(ys)]
        return [c for c in sorted(cells, key=lambda c: math.dist(p, point(c)))
                if free[c[1], c[0]] and segment_clear(p, point(c), value, yaw)]

    roots = connect(start)
    if not roots:
        raise ValueError('NO_START_CONNECTOR')
    parent = {roots[0]: None}
    queue = deque(parent)
    while queue:
        c = queue.popleft()
        for n in ((c[0]+1,c[1]),(c[0]-1,c[1]),(c[0],c[1]+1),(c[0],c[1]-1)):
            if (0 <= n[0] < len(xs) and 0 <= n[1] < len(ys) and
                    free[n[1], n[0]] and n not in parent):
                parent[n] = c; queue.append(n)
    results = {}
    for name, target in targets.items():
        ends = [c for c in connect(target) if c in parent]
        if not ends:
            raise ValueError(f'NO_STATIC_PATH: {name}')
        cells = []; c = ends[0]
        while c is not None:
            cells.append(point(c)); c = parent[c]
        path = [list(start), *reversed(cells), list(target)]
        if not all(segment_clear(a, b, value, yaw) for a, b in zip(path, path[1:])):
            raise ValueError('SWEPT_PATH_INVALID')
        results[name] = dict(path_xy_m=path, length_m=sum(math.dist(a,b) for a,b in zip(path,path[1:])),
                             continuous_swept_aabb_clear=True)
    return results


def static_check(value):
    from sim.zone_model_conventions import spawn_layout
    spec = spawn_layout(value)
    starts = {f'spawn_row_{i}': ([spec['spawn_x'], y], 0.) for i,y in enumerate(spec['spawn_rows_y'])}
    starts['ego_authored_start'] = ([3.25, .75], math.pi)
    targets = {s['slot_id']: s['center_m'] for row in value['zone_slots'].values() for s in row}
    targets.update({r: value['regions']['zone_'+r]['center_m'] for r in ('A','B','C')})
    result = dict(map_id=value['map_id'], footprint_body_bounds_m=BODY, margin_m=MARGIN,
                  grid_resolution_m=RES, scope='empty static arena, unloaded fixed-heading translation; no policy',
                  starts={k: dict(xy_m=p, yaw_rad=y) for k,(p,y) in starts.items()}, paths={})
    for name,(start,yaw) in starts.items():
        result['paths'][name] = plan_all(value, start, targets, yaw)
    result['reachable_pairs'] = sum(map(len, result['paths'].values()))
    if value['map_id'] == hm.IDS[0]:
        # Demonstrate two distinct west-to-B routes by independently sealing each base door.
        import copy
        result['alternative_routes'] = {}
        for d in value['passages'][:2]:
            sealed = copy.deepcopy(value)
            sealed['obstacles'].append(dict(id='diagnostic_seal', center_m=d['center_m'],
                half_extents_m=d['half_extents_m'], height_m=.4, kind='wall'))
            result['alternative_routes']['sealed_'+d['id']] = plan_all(
                sealed, starts['spawn_row_1'][0], {'B': targets['B']}, 0.)
    return result


def stationary(value, out):
    """Compile/forward/render only. No mj_step, drive commands, controller or model."""
    import mujoco
    from PIL import Image
    from sim.zone_final_v3_scene import FinalV3Scene
    from sim.zone_cargo_contact import base_profile
    from sim.zone_heldout_scene import install
    from sim.render_profile import install as lighting
    from sim.multi_masterpi_production import build_multi_robot_xml
    out.mkdir(parents=True, exist_ok=False)
    scene = FinalV3Scene.from_spec(dict(map=hm.BASE_ID, seed=11, goal={'B': {'cyan': 1}}),
                                   base_profile('cargo_noslip_v1'))
    if value['map_id'] != hm.BASE_ID:
        install(scene, heldout_map=value['map_id'])
    lighting(scene, 'floor_light_v1')
    xml = build_multi_robot_xml(spawns=scene.config['setup_only']['spawns'])
    xml = scene.robot_transform(scene.transform(xml))
    assets = out/'wall-textures'
    record = texture.generate_assets(texture.walls_from_xml(xml), assets)
    xml = texture.transform_xml(xml, wall_texture='tape_v1', assets=assets)
    (out/'scene.xml').write_text(xml)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    checked = []
    for obs in value['obstacles']:
        geom = model.geom('zone_'+obs['id'])
        assert np.allclose(geom.pos, [*obs['center_m'], obs['height_m']/2])
        assert np.allclose(geom.size, [*obs['half_extents_m'], obs['height_m']/2])
        assert geom.contype > 0 and geom.conaffinity > 0
        checked.append(obs['id'])
    cameras = [c['name'] for c in value['top_cameras']] + [f'r{i}__robot_cam' for i in (1,2,3)]
    for c in value['top_cameras']:
        cam = model.camera(c['name'])
        assert np.allclose(cam.pos, c['position_m']) and np.allclose(cam.fovy, c['fov_y_deg'])
    assert all(model.eq_active0[i] == 0 for i in range(model.neq)
               if model.eq_type[i] == mujoco.mjtEq.mjEQ_WELD)
    envelopes = {}
    for rid in ('r1','r2','r3'):
        body = model.body(rid+'__robot').id
        points = []
        for i in range(model.ngeom):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
            if not name.startswith(rid+'__') or not (model.geom_contype[i] or model.geom_conaffinity[i]):
                continue
            centre, half = model.geom_aabb[i,:3], model.geom_aabb[i,3:]
            for sx in (-1,1):
                for sy in (-1,1):
                    for sz in (-1,1):
                        local = centre+half*np.array([sx,sy,sz])
                        world = data.geom_xpos[i]+data.geom_xmat[i].reshape(3,3)@local
                        points.append(data.xmat[body].reshape(3,3).T@(world-data.xpos[body]))
        points = np.array(points)
        envelope = [float(points[:,0].min()),float(points[:,0].max()),
                    float(points[:,1].min()),float(points[:,1].max())]
        assert envelope[0] >= BODY[0] and envelope[1] <= BODY[1], envelope
        assert envelope[2] >= BODY[2] and envelope[3] <= BODY[3], envelope
        envelopes[rid] = envelope
    with mujoco.Renderer(model, height=480, width=640) as renderer:
        for name in cameras:
            renderer.update_scene(data, camera=name)
            rgb = renderer.render().copy()
            assert np.isfinite(rgb).all() and float(rgb.std()) > 1.
            Image.fromarray(rgb).save(out/(name+'.png'))
    contacts = []
    for c in data.contact[:data.ncon]:
        names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, int(i)) or '' for i in (c.geom1,c.geom2)]
        if any(n.startswith('zone_wall_') for n in names) and any(n.startswith(('r1__','r2__','r3__')) for n in names):
            contacts.append(dict(geoms=names, distance_m=float(c.dist)))
    assert not contacts, contacts
    return dict(map_id=value['map_id'], model_ngeom=model.ngeom, checked_walls=checked,
        cameras=cameras, wall_texture_faces=len(record['faces']), robot_wall_contacts=contacts,
        sim_time_s=float(data.time), integration_steps=0, controller_commands=0, model_calls=0,
        scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
        compiled_initial_collision_aabb_body_m=envelopes,
        map_file_sha256=hm.sha(hm.MAP_DIR/(value['map_id']+'.json')),
        mujoco_version=mujoco.__version__, loadavg=list(os.getloadavg()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-maps', action='store_true')
    p.add_argument('--output', type=Path)
    p.add_argument('--stationary', action='store_true', help='explicit stationary compile/forward/render, no stepping')
    p.add_argument('--wait-lock-seconds', type=int, default=0, help='finite wait for another task; never steals/releases its lock')
    args = p.parse_args()
    values = hm.authored_maps()
    if args.write_maps:
        for value in values:
            path = hm.MAP_DIR/(value['map_id']+'.json')
            if path.exists():
                raise FileExistsError(path)
            write(path, value)
        write(hm.CATALOG, dict(schema='ugrp.heldout_maps.v1', suite='hardmaps1', status='prepared_only',
            default_enabled=False, maps={v['map_id']: dict(file_sha256=hm.sha(hm.MAP_DIR/(v['map_id']+'.json')),
                split='held_out', development_use=False) for v in values}))
    if args.output is None:
        return
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    from harness.zone_map_schematic import render_schematic
    base = json.loads((hm.MAP_DIR/(hm.BASE_ID+'.json')).read_text())
    reports = []
    for value in (base, *values):
        if value['map_id'] != hm.BASE_ID:
            assert value == hm.load(value['map_id'])
            reports.append(static_check(value))
        png, _ = render_schematic(value, width_px=1000)
        (out/(value['map_id']+'.png')).write_bytes(png)
    report = dict(source_sha=source_sha(), kind='heldout_static_preparation',
        results=reports, cue_comparison={v['map_id']: cues(v) for v in (base,*values)},
        loadavg=list(os.getloadavg()), controller_trials=0, heldout_tuning=False)
    write(out/'static.json', report)
    if args.stationary:
        from scripts.agent_lock import DEFAULT_ROOT, acquire, release
        wait_until = time.monotonic()+max(0, args.wait_lock_seconds)
        while True:
            try:
                lock = acquire(DEFAULT_ROOT, owner='codex', branch='codex/hard-maps',
                               purpose='hardmaps1 stationary compile/forward/render only; no stepping',
                               pid=os.getpid(), expected_minutes=2)
                break
            except RuntimeError as error:
                if not str(error).startswith('lock held:') or time.monotonic() >= wait_until:
                    raise
                time.sleep(1)
        write(out/'lock.json', lock)
        started = time.monotonic()
        receipt = []
        try:
            for value in (base,*values):
                receipt.append(stationary(value, out/value['map_id']))
        except Exception as error:
            write(out/'failure.json', dict(map_id=value['map_id'], type=type(error).__name__, message=str(error)))
            raise
        finally:
            write(out/'stationary.json', dict(source_sha=source_sha(), maps=receipt,
                  check_wall_s=time.monotonic()-started, qualification='stationary loading, not timing benchmark'))
            release(DEFAULT_ROOT, owner='codex')
    write(out/'artifact-hashes.json', {str(f.relative_to(out)): hm.sha(f) for f in sorted(out.rglob('*')) if f.is_file()})
    print(json.dumps(dict(output=str(out), reachable_pairs=[r['reachable_pairs'] for r in reports])))


if __name__ == '__main__':
    main()
