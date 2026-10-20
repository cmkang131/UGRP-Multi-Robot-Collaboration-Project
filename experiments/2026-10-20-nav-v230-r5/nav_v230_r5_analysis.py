#!/usr/bin/env python3
"""Eval-only recount for the nav v230-r5 runs (no success claim).

r5 keeps the r3/r4 claim and every r3 constant; the only experiment change is the
*two-stage slot aim* (`v230_r5`): through the door the follower aims at the
component centre (offset 0) and the order-sheet slot turns on only when the
visible destination component's bottom row projects onto the floor at <= 1.5 m,
with the applied offset clamped to +-15 deg.

This script reuses the already-validated r4 recount (it reproduced the r3 numbers
GT 1/2, claim 2/2, mismatch 1, min centre 0.1681 m) and adds the r5-only
diagnostics required by the prereg:

- stage-2 slot activation: time, ground distance at activation, raw vs applied
  offset, clamp ticks, and the fact that `u`/the 0.52 m claim never moved;
- **robot vs wall / door-frame contacts** from the r5 contact-ledger channel
  (eval-only MJWarp contacts by geom name) plus an independent authored-map
  base-box separation recount;
- **commanded integration vs GT movement** (ratio; never used for the verdict);
- the acceptance table (VALID, GT 2/2, claim 2/2, mismatch 0, FP 0, boundary 0).

Everything is evaluation-only: the static map, GT and contacts are read here and
never returned to a controller.  The script writes one JSON report and never
writes into the run directory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'ugrp.e2ewarp.nav_v230_r5_analysis.v1'
R4_TOOL = ROOT / 'experiments/2026-10-19-nav-v230-r4/nav_v230_r4_analysis.py'
MAP_PATH = ROOT / 'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'
TICK_HZ = 10.0
#: Wide-door geometry (authored map): door plane x = 2.2, jambs at y = -2.125
#: (divider south end) and y = -3.125 (south wall inner face).
DOOR_X = 2.2
DOOR_JAMB_Y = (-2.125, -3.125)
#: Authored scene geoms are prefixed ``zone_`` (``zone_wall_divider_1`` is the
#: map's ``wall_divider_1``); both spellings are accepted so a renamed scene
#: cannot silently drop the classification.
WALL_PREFIXES = ('zone_wall_', 'wall_')
DOOR_FRAME_GEOMS = ('zone_wall_divider_1', 'zone_wall_south',
                    'wall_divider_1', 'wall_south')


def _load(path):
    spec = importlib.util.spec_from_file_location('nav_v230_r4_analysis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R4 = _load(R4_TOOL)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def _num(value, digits=4):
    return None if value is None else round(float(value), digits)


# --- stage-2 slot diagnostics -----------------------------------------------
def slot_stage2_report(run):
    """Per-robot stage-2 activation and offset record from the own reports."""
    rows_all = load_json(Path(run) / 'localization.json') or []
    robots = sorted({str(r.get('robot')) for r in rows_all if r.get('robot')})
    out = {}
    for robot in robots:
        rows = sorted([r for r in rows_all if str(r.get('robot')) == robot],
                      key=lambda r: float(r['sim_s']))
        own = [r.get('own_navigation') or {} for r in rows]
        sim = [float(r['sim_s']) for r in rows]
        threshold = next((o.get('slot_stage2_ground_m') for o in own
                          if o.get('slot_stage2_ground_m') is not None), None)
        active_i = next((i for i, o in enumerate(own) if o.get('slot_stage2_active') is True),
                        None)
        ground = [(sim[i], float(o['slot_ground_distance_m'])) for i, o in enumerate(own)
                  if o.get('slot_ground_distance_m') is not None]
        raw = [(sim[i], float(o['slot_bearing_offset_raw_deg'])) for i, o in enumerate(own)
               if o.get('slot_bearing_offset_raw_deg') is not None]
        applied = [(sim[i], float(o['slot_bearing_offset_applied_deg'])) for i, o in enumerate(own)
                   if o.get('slot_bearing_offset_applied_deg') is not None]
        limit = next((o.get('slot_offset_limit_deg') for o in own
                      if o.get('slot_offset_limit_deg') is not None), None)
        active_ticks = sum(1 for o in own if o.get('slot_stage2_active') is True)
        clamp_ticks = sum(1 for o in own
                          if o.get('slot_stage2_active') is True
                          and o.get('slot_bearing_offset_raw_deg') is not None
                          and limit is not None
                          and abs(float(o['slot_bearing_offset_raw_deg'])) > float(limit) + 1e-9)
        armed_i = next((i for i, o in enumerate(own) if o.get('arrival_armed')), None)
        arrival_armed_s = None if armed_i is None else sim[armed_i]
        ground_at_arming = (None if armed_i is None
                            else own[armed_i].get('slot_ground_distance_m'))
        claim_i = next((i for i, o in enumerate(own) if o.get('destination_arrived')), None)
        out[robot] = dict(
            slot=next((o.get('slot') for o in own if o.get('slot') is not None), None),
            stage2_threshold_m=threshold, offset_limit_deg=limit,
            active=active_i is not None,
            activation_sim_s=(None if active_i is None else round(sim[active_i], 3)),
            activation_tick=active_i,
            ground_at_activation_m=(None if active_i is None
                                    else _num(own[active_i].get('slot_ground_at_activation_m'))),
            ground_min_m=(_num(min(value for _, value in ground)) if ground else None),
            ground_min_s=(round(min(ground, key=lambda p: p[1])[0], 3) if ground else None),
            ground_last_m=(_num(ground[-1][1]) if ground else None),
            ground_samples=len(ground),
            active_ticks=active_ticks, inactive_ticks=len(own) - active_ticks,
            raw_offset_min_deg=(_num(min(v for _, v in raw), 3) if raw else None),
            raw_offset_max_deg=(_num(max(v for _, v in raw), 3) if raw else None),
            raw_offset_first_deg=(_num(raw[0][1], 3) if raw else None),
            raw_offset_last_deg=(_num(raw[-1][1], 3) if raw else None),
            applied_offset_min_deg=(_num(min(v for _, v in applied), 3) if applied else None),
            applied_offset_max_deg=(_num(max(v for _, v in applied), 3) if applied else None),
            clamp_ticks=clamp_ticks,
            arrival_armed_s=arrival_armed_s,
            ground_at_arming_m=_num(ground_at_arming),
            claim_s=(None if claim_i is None else round(sim[claim_i], 3)),
            activation_to_arming_ticks=(None if active_i is None or arrival_armed_s is None
                                        else int(round((arrival_armed_s - sim[active_i]) * TICK_HZ))),
            activation_to_arming_m=(None if active_i is None or ground_at_arming is None
                                    else _num(float(own[active_i]['slot_ground_at_activation_m'])
                                              - float(ground_at_arming))),
            note='own-camera only: bbox bottom row -> ground plane; never a map/GT input')
    return out


# --- authored-map wall geometry (independent secondary check) ----------------
def _map_walls():
    payload = json.loads(MAP_PATH.read_text())
    walls = []
    for item in payload.get('obstacles') or []:
        walls.append(dict(id=str(item['id']), scene_geom='zone_' + str(item['id']),
                          center=tuple(float(v) for v in item['center_m']),
                          half=tuple(float(v) for v in item['half_extents_m'])))
    return walls


def _footprint_boxes(run, robot):
    """Authored plan-view collision boxes of one robot (direct children of its base body).

    The authored base body carries the physical footprint: base_lower_collision,
    base_top, front_plate, rear_cage_collision, arm_box_collision,
    yaw_servo_collision and ultrasonic_collision.  Only ``type=box`` geoms with a
    non-zero contype are used; capsules/meshes (arm links, finger jaws, roller
    contact meshes) are *not* in this proxy, so its separation is an upper bound
    and can stay positive while the real body touches (that is why the MJWarp
    scene-contact channel above is the primary record).  The pose is the robot
    base pose times the geom's local x/y offset (all these geoms sit in the base
    body frame; z is irrelevant to a plan-view wall check).
    """
    import xml.etree.ElementTree as ET
    path = Path(run) / 'world-00' / 'scene.xml'
    if not path.is_file():
        return []
    root = ET.parse(path).getroot()
    body = root.find(f".//body[@name='{robot}__robot']")
    if body is None:
        return []
    out = []
    for geom in body.findall('geom'):
        if geom.get('type') != 'box':
            continue
        if geom.get('contype') == '0':
            continue
        size = geom.get('size')
        if not size:
            continue
        half = [float(v) for v in size.split()]
        pos = [float(v) for v in (geom.get('pos') or '0 0 0').split()]
        out.append(dict(name=str(geom.get('name')), half=(half[0], half[1]),
                        local=(pos[0], pos[1])))
    return out


def wall_clearance_report(run, base):
    """Authored-wall vs GT footprint-box separation (eval-only secondary check)."""
    ledger = load_json(Path(run) / 'contact-ledger.json') or {}
    walls = _map_walls()
    scene_by_id = {w['id']: w['scene_geom'] for w in walls}
    wall_rects = [dict(id=w['id'], scene_geom=w['scene_geom'],
                       corners=R4._rect_corners(w['center'], 0.0,
                                                w['half'][0], w['half'][1]))
                  for w in walls]
    robots = base.get('robots') or []
    qpos = np.asarray(np.load(Path(run) / 'evaluation-state.npz')['qpos'])
    out = dict(schema='ugrp.e2ewarp.nav_v230_r5_wall_clearance.v1', eval_only=True,
               map_id='zone_wide_two_doors_final_v3',
               method='GT robot footprint boxes (authored direct-child box geoms) vs '
                      'authored obstacle rectangles; plan view',
               caveat='box-only proxy: capsules/meshes excluded, so a positive '
                      'separation does not prove no contact; the MJWarp scene '
                      'channel is the primary contact record',
               walls=[w['id'] for w in walls], robots={})
    for robot in robots:
        boxes = _footprint_boxes(run, robot)
        if not boxes:
            boxes = [dict(name=robot + '__base_lower_collision',
                          half=(0.0905, 0.0435), local=(0.0, 0.0))]
        _geometry, _adr, xy, yaw = R4.track(run, robot, qpos)
        per_wall = {w['id']: dict(min_m=None, min_s=None, contact_ticks=0,
                                  min_robot_geom=None) for w in walls}
        best = dict(separation_m=None, sim_s=None, wall=None, robot_geom=None)
        ticks_contact, ticks_near = 0, 0
        for i in range(len(xy)):
            tick_min = None
            for wall in wall_rects:
                for box in boxes:
                    c, sn = math.cos(math.radians(float(yaw[i]))), math.sin(math.radians(float(yaw[i])))
                    local_x, local_y = box['local']
                    center = (float(xy[i][0]) + local_x * c - local_y * sn,
                              float(xy[i][1]) + local_x * sn + local_y * c)
                    corners = R4._rect_corners(center, float(yaw[i]),
                                               float(box['half'][0]), float(box['half'][1]))
                    separation = R4.polygon_distance(corners, wall['corners'])
                    entry = per_wall[wall['id']]
                    if entry['min_m'] is None or separation < entry['min_m']:
                        entry.update(min_m=separation, min_s=i / TICK_HZ,
                                     min_robot_geom=box['name'])
                    if entry['min_m'] is not None and separation <= 0.0:
                        entry['contact_ticks'] += 1
                    if tick_min is None or separation < tick_min:
                        tick_min = separation
                    if best['separation_m'] is None or separation < best['separation_m']:
                        best = dict(separation_m=separation, sim_s=i / TICK_HZ,
                                    wall=wall['id'], robot_geom=box['name'])
            if tick_min is not None and tick_min <= 0.0:
                ticks_contact += 1
            if tick_min is not None and tick_min <= 0.01:
                ticks_near += 1
        out['robots'][robot] = dict(
            available=True, footprint_geoms=[box['name'] for box in boxes],
            min_separation_m=_num(best['separation_m']),
            min_separation_s=(None if best['sim_s'] is None else round(best['sim_s'], 3)),
            min_separation_wall=best['wall'],
            min_separation_robot_geom=best['robot_geom'],
            contact_ticks=ticks_contact, near_contact_ticks_1cm=ticks_near,
            per_wall={name: dict(scene_geom=scene_by_id[name],
                                 min_m=_num(value['min_m']),
                                 min_s=(None if value['min_s'] is None
                                        else round(value['min_s'], 3)),
                                 contact_ticks=value['contact_ticks'],
                                 min_robot_geom=value['min_robot_geom'])
                      for name, value in per_wall.items()},
            note='authored map rectangles; proxy, not a physics contact')
    return out


# --- MJWarp robot-vs-scene contact channel ----------------------------------
def scene_contact_report(run):
    ledger = load_json(Path(run) / 'contact-ledger.json') or {}
    totals = ledger.get('scene_geom_totals') or {}
    rows = []
    for key, value in sorted(totals.items()):
        geom = str(value.get('scene_geom'))
        rows.append(dict(robot=value.get('robot'), scene_geom=geom,
                         map_id=(geom[len('zone_'):] if geom.startswith('zone_') else geom),
                         kind=('door_frame' if geom in DOOR_FRAME_GEOMS else
                               'wall' if geom.startswith(WALL_PREFIXES) else 'scene_other'),
                         ticks=int(value.get('ticks') or 0),
                         first_s=value.get('first_s'), last_s=value.get('last_s'),
                         min_dist_m=value.get('min_dist_m')))
    ticks = [dict(sim_s=row['sim_s'],
                  contacts=[dict(robot=c['robot'], scene_geom=c['scene_geom'],
                                 robot_geom=c['robot_geom'], dist_m=c['dist_m'])
                            for c in row['contacts']])
             for row in (ledger.get('scene_ticks') or [])]
    return dict(
        schema='ugrp.e2ewarp.nav_v230_r5_scene_contacts.v1', eval_only=True,
        available=ledger.get('scene_contacts_available'),
        unavailable_reason=ledger.get('scene_unavailable_reason'),
        excluded_geoms=ledger.get('scene_excluded_geoms'),
        contact_ticks=ledger.get('scene_contact_ticks'),
        contact_pairs_total=ledger.get('scene_contact_pairs_total'),
        first_contact_s=ledger.get('scene_first_contact_s'),
        last_contact_s=ledger.get('scene_last_contact_s'),
        per_geom=rows, ticks=ticks[:400],
        tick_rows_truncated=len(ticks) > 400,
        note='MJWarp contact buffer, robot geom vs static scene geom (floor excluded)')


# --- commanded integration vs GT -------------------------------------------
def command_vs_gt(run, base, robots):
    commands = load_json(Path(run) / 'commands.json') or []
    constants = base.get('calibration', {}).get('constants') or {}
    out = {}
    for robot in robots:
        own = [r.get('own_navigation') or {} for r in
               sorted([r for r in (load_json(Path(run) / 'localization.json') or [])
                       if str(r.get('robot')) == robot], key=lambda r: float(r['sim_s']))]
        report = (base.get('robots_report') or {}).get(robot) or {}
        gt_path = report.get('gt_path_m')
        cmd = R4.command_kinematics(commands, robot, constants) if constants else []
        cmd_path = sum(abs(row['forward_m']) for row in cmd)
        odom_path = 0.0
        odom_poses = [(o.get('odom_pose') or None) for o in own]
        for i in range(1, len(odom_poses)):
            prev, cur = odom_poses[i - 1], odom_poses[i]
            if prev is None or cur is None:
                continue
            odom_path += math.hypot(float(cur[0]) - float(prev[0]),
                                    float(cur[1]) - float(prev[1]))
        out[robot] = dict(
            gt_path_m=gt_path, command_path_m=_num(cmd_path),
            odom_path_m=_num(odom_path),
            command_over_gt=(_num(cmd_path / gt_path, 3) if gt_path else None),
            odom_over_gt=(_num(odom_path / gt_path, 3) if gt_path else None),
            commanded_yaw_deg=_num(sum(row['yaw_deg'] for row in cmd), 3),
            note='diagnostic only; never used for the acceptance verdict')
    return out


# --- acceptance table -------------------------------------------------------
def acceptance(base, *, n_robots, preflight=None):
    source = base.get('source') or {}
    expected = base.get('expected_source_sha')
    source_ok = bool(expected and source.get('run_queue_source_sha') == expected
                     and source.get('admission_queue_source_sha') == expected
                     and source.get('run_meta_sha') == expected
                     and source.get('result_source_sha') == expected
                     and source.get('admission_equals_run_queue') is True)
    stack = base.get('stack_check') or {}
    stack_ok = bool(stack.get('ok') is True and int(stack.get('blocked') or 0) == 0)
    boundaries_ok = not (base.get('boundary_violations') or [])
    status = str(base.get('status'))
    status_ok = status in ('cap_end', 'NAV_ARRIVAL_UNVERIFIED')
    gt_n = int(base.get('final_gt_arrival_n') or 0)
    claim_n = int(base.get('arrival_claim_n') or 0)
    mismatch = int(base.get('claim_mismatch_n') or 0)
    fp_final = mismatch                      # claim with a final pose outside the zone
    fp_render = None
    fp_render_max_component_px = None
    fp_render_frames = None
    if preflight is not None:
        measure = preflight if isinstance(preflight, dict) else load_json(preflight, {})
        # render_check.py writes checks.zone_free.{detections_total,max_largest_component_px};
        # accept the flat spellings too so an older measure file still parses.
        checks = (measure.get('checks') or {}).get('zone_free') or {}
        value = checks.get('detections_total', measure.get('zone_free_detections'))
        fp_render = None if value is None else int(value)
        max_px = checks.get('max_largest_component_px',
                            measure.get('zone_free_max_component_px'))
        fp_render_max_component_px = None if max_px is None else int(max_px)
        frames = checks.get('frame_n', measure.get('zone_free_frames'))
        fp_render_frames = None if frames is None else int(frames)
    valid = bool(source_ok and stack_ok and boundaries_ok and status_ok)
    fp_ok = bool(fp_final == 0 and (fp_render is None or fp_render == 0))
    passed = bool(valid and gt_n == n_robots and claim_n == n_robots and mismatch == 0
                  and fp_ok and boundaries_ok)
    return dict(
        schema='ugrp.e2ewarp.nav_v230_r5_acceptance.v1', eval_only=True,
        n_robots=n_robots,
        valid=valid,
        valid_detail=dict(source_ok=source_ok, stack_ok=stack_ok,
                          boundaries_ok=boundaries_ok, status=status, status_ok=status_ok),
        gt_arrival_n=gt_n, claim_n=claim_n, claim_mismatch_n=mismatch,
        claims_outside_gt_at_claim_time_n=int(base.get('claims_outside_gt_at_claim_time_n') or 0),
        fp_final_outside_claim_n=fp_final, fp_render_zone_free_detections=fp_render,
        fp_render_max_component_px=fp_render_max_component_px,
        fp_render_zone_free_frames=fp_render_frames,
        no_claim_n=int(base.get('no_claim_n') or 0),
        boundary_violations=base.get('boundary_violations') or [],
        pass_=passed,
        rule='PASS <=> VALID and GT 2/2 and claim 2/2 and mismatch 0 and FP 0 and boundary 0',
        note='cap_end is not success; contact is a failure cause, not INVALID')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--admission', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--out', type=Path)
    p.add_argument('--preflight-render', type=Path,
                   help='optional render_check.py measure.json for the FP 0 row')
    a = p.parse_args(argv)
    run = a.run.resolve()
    base = R4.recount(run, a.admission, a.expected_source_sha)
    robots = tuple(base.get('robots') or ())
    base['schema'] = SCHEMA
    base['r4_tool'] = dict(path=str(R4_TOOL.relative_to(ROOT)), sha256=sha(R4_TOOL))
    base['r5'] = dict(
        mode=base.get('queue_markers', {}).get('nav_gate_mode'),
        slot_stage2=slot_stage2_report(run),
        scene_contacts=scene_contact_report(run),
        wall_clearance=wall_clearance_report(run, base),
        command_vs_gt=command_vs_gt(run, base, robots),
        scope='r5 two-stage slot; eval-only diagnostics; no success claim',
    )
    base['acceptance'] = acceptance(base, n_robots=len(robots),
                                    preflight=a.preflight_render)
    out = a.out or run.parent / (run.name + '-analysis.json')
    out.write_text(json.dumps(base, ensure_ascii=False, indent=1) + '\n')
    summary = dict(out=str(out), schema=SCHEMA, status=base.get('status'),
                   valid=base['acceptance']['valid'], pass_=base['acceptance']['pass_'],
                   gt_arrival_n=base['acceptance']['gt_arrival_n'],
                   claim_n=base['acceptance']['claim_n'],
                   mismatch=base['acceptance']['claim_mismatch_n'],
                   scene_contact_ticks=base['r5']['scene_contacts']['contact_ticks'],
                   slot_stage2={r: dict(active=v['active'],
                                        activation_sim_s=v['activation_sim_s'],
                                        ground_at_activation_m=v['ground_at_activation_m'],
                                        clamp_ticks=v['clamp_ticks'])
                                for r, v in base['r5']['slot_stage2'].items()})
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
