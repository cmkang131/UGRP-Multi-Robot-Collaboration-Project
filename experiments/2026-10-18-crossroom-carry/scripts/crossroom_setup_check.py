#!/usr/bin/env python3
"""Setup-only validation for cross-room carry Stage A, run on gcp3.

Builds the MJWarp scene once (no rollout), resets every authored start, and
reports:
  * the simulator spawn-overlap admission (floor/cargo/wall checks),
  * the base pose (setup/eval only),
  * the clearance from the start to every cargo body (the long_beam is at
    [1.275, 0.45]; the pickup room has six boxes + one beam),
  * whether the straight start->door approach segment is blocked by the beam,
  * peer park clearance to zones and walls.

No controller is run and no physics step is executed, so this is a setup-only
check.  It writes ``setup-validation.json`` used to freeze the gate.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def aabb_distance(x, y, cx, cy, hx, hy):
    dx = max(cx - hx - x, 0.0, x - (cx + hx))
    dy = max(cy - hy - y, 0.0, y - (cy + hy))
    return math.hypot(dx, dy)


def point_obb_distance(x, y, cx, cy, yaw, hx, hy, samples=800):
    """Sample segment->OBB distance by dense sampling (setup check only)."""
    c, s = math.cos(-yaw), math.sin(-yaw)
    dx, dy = x - cx, y - cy
    lx, ly = c * dx - s * dy, s * dx + c * dy
    return aabb_distance(lx, ly, 0.0, 0.0, hx, hy)


def segment_min_obb_distance(p0, p1, cx, cy, yaw, hx, hy, samples=800):
    best = float('inf')
    for i in range(samples + 1):
        u = i / samples
        x = p0[0] + (p1[0] - p0[0]) * u
        y = p0[1] + (p1[1] - p0[1]) * u
        best = min(best, point_obb_distance(x, y, cx, cy, yaw, hx, hy, samples=1))
    return round(best, 4)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--renderer', type=Path, required=True)
    ap.add_argument('--legacy', type=Path, required=True)
    ap.add_argument('--setups', type=Path, required=True)
    ap.add_argument('--map', type=Path,
                    default=ROOT / 'maps/zones/zone_wide_door_geometry_v3.json')
    ap.add_argument('--scenario', type=Path,
                    default=ROOT / 'configs/zone_study_scenarios_v7/s1_normal_mixed_v7.json')
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    cp = load_module('crossroom_probe_mod',
                     ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py')
    cp.register_vendor()
    setups = json.loads(a.setups.read_text())
    episodes = setups['episodes']
    zones_map = json.loads(a.map.read_text())
    scenario = json.loads(a.scenario.read_text())
    placements = scenario['eval']['setup']['placements']
    regions = zones_map['regions']
    passages = zones_map['passages']
    door = next(p for p in passages if p['kind'] == 'door')
    door_xy = door['center_m'][:2]
    obstacles = zones_map['obstacles']
    parks = setups.get('park_eval_only', {})

    beam = next((p for p in placements if p['kind'] == 'long_beam'), None)
    BEAM_HALF = (0.30, 0.020)  # 600x40 mm bar, sim/zone_cargo.py long_beam

    with cp.prefixed_paths(a.renderer, a.legacy):
        import mujoco
        import numpy as np
        from harness.active_camera import SEARCH
        from sim.spawn_overlap_check import check, OPTION as OVERLAP
        plan0 = {**episodes[0], 'scenario_id': 's1_normal_mixed_v7',
                 'end_color_scene': 'grasp_act_teal_blue_v1'}
        m, hardware, xml, scene = cp.make_model(a.renderer, a.legacy, plan0)
        body = m.body('r1__robot').id
        adr = int(m.jnt_qposadr[int(m.body_jntadr[body])])
        free_bodies = []
        for i in range(1, m.nbody):
            if not int(m.body_jntnum[i]):
                continue
            jid = int(m.body_jntadr[i])
            if int(m.jnt_type[jid]) != int(mujoco.mjtJoint.mjJNT_FREE):
                continue
            name = m.body(i).name
            if name.startswith(('r1__', 'r2__', 'r3__')):
                continue
            free_bodies.append((i, name))
        rows = []
        for idx, plan in enumerate(episodes):
            plan = {**plan, 'scenario_id': 's1_normal_mixed_v7',
                    'end_color_scene': 'grasp_act_teal_blue_v1'}
            d = cp.reset_episode(m, hardware, plan, __import__(
                'scripts.probe_scene_tex2', fromlist=['_free_pose']), SEARCH, mujoco)
            admission = cp.overlap_check(m, d, mujoco, check, OVERLAP)
            qp = d.qpos
            w, x, y, z = qp[adr + 3:adr + 7]
            yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            bx, by = float(qp[adr]), float(qp[adr + 1])
            cargos = []
            for bi, bname in free_bodies:
                bj = int(m.body_jntadr[bi])
                ba = int(m.jnt_qposadr[bj])
                cx, cy = float(qp[ba]), float(qp[ba + 1])
                item = None
                best = 1e9
                for p in placements:
                    px, py = p['pose_m'][0], p['pose_m'][1]
                    dd = math.hypot(px - cx, py - cy)
                    if dd < best:
                        best, item = dd, p
                cargos.append(dict(body=bname, item_id=item['item_id'],
                                   kind=item['kind'], xy=[round(cx, 3), round(cy, 3)],
                                   match_dist_m=round(best, 4),
                                   base_dist_m=round(math.hypot(cx - bx, cy - by), 4)))
            cargos = [c for c in cargos if c['match_dist_m'] < 0.25]
            min_cargo = min(cargos, key=lambda c: c['base_dist_m']) if cargos else None
            beam_clear = None
            beam_blocked = None
            if beam is not None:
                bx0, by0 = beam['pose_m'][0], beam['pose_m'][1]
                beam_yaw = beam['pose_m'][2]
                beam_clear = segment_min_obb_distance(
                    (bx, by), (door_xy[0] - 0.15, door_xy[1]),
                    bx0, by0, beam_yaw, *BEAM_HALF)
                beam_blocked = bool(beam_clear < cp_robot_radius() + 0.01)
            divider_clear = min(aabb_distance(bx, by, o['center_m'][0], o['center_m'][1],
                                              o['half_extents_m'][0], o['half_extents_m'][1])
                                for o in obstacles if o.get('kind') == 'wall')
            in_zone = [name for name, r in regions.items()
                       if abs(bx - r['center_m'][0]) <= r['half_extents_m'][0]
                       and abs(by - r['center_m'][1]) <= r['half_extents_m'][1]]
            rows.append(dict(
                episode=idx, group='N' if idx < 8 else 'F',
                spawn_eval_only=plan['spawns']['r1'],
                base_xyyaw_eval_only=[round(bx, 4), round(by, 4), round(yaw, 4)],
                admission=admission,
                in_region=in_zone,
                min_cargo=min_cargo,
                beam_door_path_min_clearance_m=beam_clear,
                beam_blocks_straight_door_path=beam_blocked,
                wall_min_clearance_m=round(divider_clear - cp_robot_radius(), 4),
                pass_=bool(admission.get('accepted')) and not in_zone,
            ))
        park_rows = []
        for rid, pose in parks.items():
            x0, y0 = pose[0], pose[1]
            zone_clear = min(aabb_distance(x0, y0, r['center_m'][0], r['center_m'][1],
                                           r['half_extents_m'][0], r['half_extents_m'][1])
                             for r in regions.values())
            wall_clear = min(aabb_distance(x0, y0, o['center_m'][0], o['center_m'][1],
                                           o['half_extents_m'][0], o['half_extents_m'][1])
                             for o in obstacles if o.get('kind') == 'wall')
            in_zone = [name for name, r in regions.items()
                       if abs(x0 - r['center_m'][0]) <= r['half_extents_m'][0]
                       and abs(y0 - r['center_m'][1]) <= r['half_extents_m'][1]]
            park_rows.append(dict(robot=rid, pose=pose[:2],
                                  zone_min_clearance_m=round(zone_clear, 4),
                                  wall_min_clearance_m=round(wall_clear, 4),
                                  in_region=in_zone,
                                  pass_=not in_zone and zone_clear > cp_robot_radius()
                                  and wall_clear > cp_robot_radius()))
    out = dict(
        schema='ugrp.crossroom_carry.setup_validation.v1',
        stage='A_unloaded',
        renderer=str(a.renderer), legacy=str(a.legacy),
        setups=str(a.setups), map_id=zones_map.get('map_id'),
        scenario=scenario.get('scenario_id'),
        door_center_m_eval_only=door_xy,
        long_beam_placement_eval_only=(beam and dict(
            item_id=beam['item_id'], pose_m=beam['pose_m'])),
        n=len(rows),
        pass_n=sum(1 for r in rows if r['pass_']),
        episodes=rows,
        peer_parks=park_rows,
        scope=('setup-only: scene built once, every start reset, no physics '
               'rollout and no controller run. Truth/setup coordinates appear '
               'only in this validator and in eval-only cells.'),
    )
    a.output.write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps(dict(n=out['n'], pass_n=out['pass_n'],
                          failed=[r['episode'] for r in rows if not r['pass_']],
                          beam_path=[(r['episode'], r['beam_door_path_min_clearance_m'],
                                      r['beam_blocks_straight_door_path'])
                                     for r in rows],
                          parks=park_rows), indent=1))
    return 0


def cp_robot_radius():
    return 0.195


if __name__ == '__main__':
    raise SystemExit(main())
