#!/usr/bin/env python3
"""Render-only carry-pose camera test (E2E-min, GPU render, no physics judgement).

For each pose in carry_pose_candidates.json (3 candidates + the
gripper_hold_arm_search_v1 reference), both robots sit on their nav lanes
(r1 y=-2.375, r2 y=-2.875, yaw 0) at x in RENDER_X with the arm set to that
PWM (setup-only qpos via build_context(nav_arm_pwm=...)).  Each robot's own
cube is placed at its finger-pad midpoint ("on") or hidden 0.5 m under the
floor at (x+0.2, lane y) ("off").

Scene identity: every world of one pose batch is built with the SAME setup cube
xy (SETUP_CUBE_X, lane y), so the scene XML is byte-identical across x and
on/off (transport() batches one exact model).  The per-x robot spawn, arm pose
and cube placement are applied only after compile, as qpos/ctrl.  (Before this,
nav_cubes xy = x+0.2 was written into the cargo body ``pos`` by
sim/zone_arena.py and the XML differed per x -> POSE_SCENE_XML_NOT_IDENTICAL.)
The check itself stays: harness.e2e_min_carry_pose.scene_identity is recorded
per pose (raw/normalised sha256, normalised fields) in measure.json.  Only tick 0 is rendered:
no hooks.step, no controller, no LLM, no GT input to anything.

Per frame: v230 band largest 4-connected component (px), its bbox bottom row,
v230 detector output, and (on vs off) the cube occlusion fraction of the frame
and the zone-band mask loss.  Verdict = harness.e2e_min_carry_pose.verdict
(prereg draft CARRY_POSE_RENDER_DRAFT.md).

Runs in a clean clone root on the L4 VM:
  python experiments/2026-10-21-e2e-min/carry_pose_render.py \
     --out <new dir> --expected-source-sha <HEAD>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SEED = 601
HIDE_Z = -0.5
CUBES = {'r1': 'cyan_1', 'r2': 'red_1'}
#: Setup-only cube x written into the scene XML (free-joint body pos = qpos0).
#: Identical for every world; the rendered cube pose is set by place_cubes().
SETUP_CUBE_X = 1.7


def git(clone, *args):
    return subprocess.check_output(['git', '-C', str(clone), *args], text=True).strip()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def grip_center(model, data, robot):
    """Midpoint of the two finger geoms (setup-only, render placement)."""
    import numpy as np
    left = data.geom_xpos[model.geom(robot + '__left_finger').id]
    right = data.geom_xpos[model.geom(robot + '__right_finger').id]
    return (np.asarray(left) + np.asarray(right)) / 2.0


def place_cubes(ctx, geometry, held, off_xy):
    """Set each cube's free-joint qpos: finger-pad midpoint (held) or off_xy at HIDE_Z."""
    import mujoco
    model, data = ctx['world'].model, ctx['world'].data
    placed = {}
    for robot, adr in geometry['cube_qpos_adr'].items():
        if held:
            center = grip_center(model, data, robot)
            pos = [float(center[0]), float(center[1]), float(center[2])]
        else:
            pos = [float(off_xy[robot][0]), float(off_xy[robot][1]), HIDE_Z]
        data.qpos[adr:adr + 7] = [*pos, 1, 0, 0, 0]
        data.qvel[:] = 0
        placed[robot] = [round(v, 4) for v in pos]
    mujoco.mj_forward(model, data)
    return placed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    ap.add_argument('--expected-source-sha', required=True)
    a = ap.parse_args(argv)
    clone = Path(__file__).resolve().parents[2]
    if Path.cwd().resolve() != clone:
        raise SystemExit('CWD_MUST_BE_CLONE_ROOT')
    out = Path(a.out).resolve()
    if out.exists():
        raise SystemExit('OUTPUT_EXISTS:' + str(out))
    head = git(clone, 'rev-parse', 'HEAD')
    if head != a.expected_source_sha:
        raise SystemExit('SOURCE_SHA_MISMATCH:' + head)
    if git(clone, 'status', '--porcelain', '--untracked-files=normal'):
        raise SystemExit('SOURCE_DIRTY')
    sys.path.insert(0, str(clone))
    out.mkdir(parents=True)

    import numpy as np
    from PIL import Image
    from harness import e2e_min_carry_pose as C
    from harness.e2ewarp_nav_gate import LANE_Y, NAV_SCENARIO
    from scripts.e2e_warp_physics import build_context, transport

    cand_path = clone / 'experiments/2026-10-21-e2e-min/carry_pose_candidates.json'
    candidates = json.loads(cand_path.read_text())
    stack = json.loads((clone / 'configs/current_stack.json').read_text())
    values = {r['id']: r['current'] for r in stack['rules'] if 'e2e_llm' in r['flows']}
    poses = {name: candidates['poses'][name] for name in (*C.CANDIDATES, C.REFERENCE)}

    rows, geometry_rows, identity, placements = [], {}, {}, {}
    setup_cubes = {r: dict(item_id=CUBES[r], xy=[SETUP_CUBE_X, float(LANE_Y[r])]) for r in ('r1', 'r2')}
    for pose_name, pwm in poses.items():
        contexts, cells = [], []
        for x in C.RENDER_X:
            spawns = {r: [float(x), float(LANE_Y[r]), 0.032355118817659255, 0.0] for r in ('r1', 'r2')}
            off_xy = {r: [float(x) + 0.2, float(LANE_Y[r])] for r in ('r1', 'r2')}
            for held in (True, False):
                folder = out / 'worlds' / f'{pose_name}-x{x:.1f}-{"on" if held else "off"}'
                ctx = build_context(SEED, folder, values, nav_scene=True, nav_spawns=spawns,
                                    nav_cubes=setup_cubes, nav_arm_pwm={r: pwm for r in ('r1', 'r2')})
                geometry = json.loads((folder / 'eval-geometry.json').read_text())
                placed = place_cubes(ctx, geometry, held, off_xy)
                contexts.append(ctx)
                cells.append(dict(x=float(x), held=held, placed=placed))
                placements[folder.name] = placed
                geometry_rows[folder.name] = dict(cargo_contact_pairs=geometry.get('cargo_contact_pairs'),
                                                  cube_items=geometry.get('cube_items'))
        record = C.scene_identity(c['world'].scene_xml for c in contexts)
        identity[pose_name] = record
        if not (record['identical'] and record['raw_identical']):
            # Written before failing so the VM report carries the evidence.
            (out / f'scene-identity-{pose_name}.json').write_text(json.dumps(record, indent=1) + '\n')
            if not record['identical']:
                raise SystemExit(C.SCENE_XML_NOT_IDENTICAL + ':' + pose_name)
            # Pose-only difference, but transport() needs one exact model per batch.
            raise SystemExit('POSE_SCENE_XML_RAW_DIFFERS_POSE_ONLY:' + pose_name + ':'
                             + ','.join(record['differing_fields']))
        hooks = transport(contexts, out / f'transport-{pose_name}', head, values)
        hooks.initialize(contexts)
        frames = {}
        for i, cell in enumerate(cells):
            for robot in ('r1', 'r2'):
                jpeg = hooks.capture(i, contexts[i]['world'], robot)
                path = out / 'frames' / f'{pose_name}-x{cell["x"]:.1f}-{robot}-{"on" if cell["held"] else "off"}.jpg'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(jpeg)
                frames[(cell['x'], robot, cell['held'])] = (path, np.asarray(Image.open(path).convert('RGB')))
        for x in C.RENDER_X:
            for robot in ('r1', 'r2'):
                (p_on, on), (p_off, off) = frames[(x, robot, True)], frames[(x, robot, False)]
                m_on, m_off = C.measure_frame(on), C.measure_frame(off)
                rows.append(dict(pose=pose_name, robot=robot, x=x,
                                 largest_component_px=m_on['largest_component_px'],
                                 bbox_bottom_row=m_on['bbox_bottom_row'],
                                 detections_v230=m_on['detections_v230'],
                                 largest_component_px_cube_off=m_off['largest_component_px'],
                                 bbox_bottom_row_cube_off=m_off['bbox_bottom_row'],
                                 occlusion_fraction=round(C.occlusion_fraction(on, off), 6),
                                 zone_mask_loss=C.mask_loss(m_off['mask'], m_on['mask']),
                                 frame_on=str(p_on.relative_to(out)), frame_off=str(p_off.relative_to(out)),
                                 sha256_on=sha(p_on), sha256_off=sha(p_off)))
        hooks.close() if hasattr(hooks, 'close') else None

    verdict = C.verdict([r for r in rows if r['pose'] in C.CANDIDATES])
    measure = dict(schema='ugrp.e2e_min.carry_pose_render.v1', source_sha=head, seed=SEED,
                   scenario_id=NAV_SCENARIO, scene_profile=values['scene_profile'],
                   candidates_sha256=sha(cand_path), poses=poses, render_x=list(C.RENDER_X),
                   ticks=[0], physics_steps=0, controller_n=0, llm_calls=0,
                   cube_placement='finger-pad midpoint (render only; fingers may interpenetrate)',
                   cube_setup_xml_xy={r: c['xy'] for r, c in setup_cubes.items()},
                   cube_off_rule='qpos (x+0.2, lane y, HIDE_Z) set after compile',
                   placements=placements, scene_identity=identity,
                   rows=rows, geometry=geometry_rows, verdict=verdict,
                   scope='render-only camera test; not a physics or grasp-retention judgement')
    (out / 'measure.json').write_text(json.dumps(measure, ensure_ascii=False, indent=1) + '\n')
    print(json.dumps(dict(out=str(out), verdict=verdict), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
