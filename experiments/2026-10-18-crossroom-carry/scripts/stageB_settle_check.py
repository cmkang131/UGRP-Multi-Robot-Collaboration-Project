#!/usr/bin/env python3
"""Setup-only Stage B loaded-start validator (no rollout, run on gcp3).

Builds the reduced single-red-box scene, places the box in the closed gripper
for every authored start, settles 1 Sim s on the CPU solver, and reports the
box displacement, the box->gripper-site distance and clearances.  No
controller runs and no warp rollout happens.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--renderer', type=Path, required=True)
    ap.add_argument('--legacy', type=Path, required=True)
    ap.add_argument('--setups', type=Path, required=True)
    ap.add_argument('--scene', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--gripper-pwm', type=int, default=1500)
    a = ap.parse_args()
    cp = load_module('crossroom_probe_mod',
                     ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/crossroom_probe.py')
    carry_mod = load_module('crossroom_carry_state',
                            ROOT / 'experiments/2026-10-18-crossroom-carry/scripts/carry_state_own.py')
    cp.register_vendor()
    setups = json.loads(a.setups.read_text())
    scenario = json.loads(a.scene.read_text())
    plan0 = {**setups['episodes'][0], 'scenario_id': scenario,
             'end_color_scene': 'off'}
    with cp.prefixed_paths(a.renderer, a.legacy):
        import mujoco
        import numpy as np
        from types import SimpleNamespace
        from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
        from harness.active_camera import SEARCH
        from scripts import probe_scene_tex2 as st
        m, hardware, xml, scene = cp.make_model(a.renderer, a.legacy, plan0)
        placements = scenario['eval']['setup']['placements']
        box_body = 'cargo_' + placements[0]['item_id']
        box_qadr = int(m.jnt_qposadr[m.joint(box_body + '_free').id])
        gs_id = m.site('r1__grip_site').id
        rows = []
        for idx, plan in enumerate(setups['episodes']):
            plan = {**plan, 'scenario_id': scenario,
                    'end_color_scene': 'off'}
            d = cp.reset_episode(m, hardware, plan, st, SEARCH, mujoco)
            st.set_arm(m, d, 'r1', {**SEARCH, 1: a.gripper_pwm}, hardware)
            mujoco.mj_forward(m, d)
            gs = d.site_xpos[gs_id].copy()
            adr = int(m.jnt_qposadr[int(m.body_jntadr[m.body('r1__robot').id])])
            w, x, y, z = d.qpos[adr + 3:adr + 7]
            yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
            st._free_pose(m, d, box_body,
                          (float(gs[0]), float(gs[1]), float(gs[2])), yaw)
            mujoco.mj_forward(m, d)
            ctrl = np.zeros(m.nu)
            for i in range(m.nu):
                if '__servo_' in m.actuator(i).name:
                    ctrl[i] = d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i, 0])])]
            closed = MasterPiDynamicsV2.pulse_to_joint_targets(
                SimpleNamespace(physical_params=hardware), {1: a.gripper_pwm})['gripper']
            for i in range(m.nu):
                if m.actuator(i).name in ('r1__servo_gripper_left',
                                          'r1__servo_gripper_right'):
                    ctrl[i] = closed
            d.ctrl[:] = ctrl
            start = d.qpos[box_qadr:box_qadr + 3].copy()
            settle_steps = int(round(1.0 / float(m.opt.timestep)))
            for _ in range(settle_steps):
                mujoco.mj_step(m, d)
            after = d.qpos[box_qadr:box_qadr + 3].copy()
            gs_after = d.site_xpos[gs_id].copy()
            box_to_site = float(np.linalg.norm(after - gs_after))
            rows.append(dict(
                episode=idx, group='N' if idx < 8 else 'F',
                spawn_eval_only=plan['spawns']['r1'],
                box_start_eval_only=[round(float(v), 4) for v in start],
                box_after_eval_only=[round(float(v), 4) for v in after],
                box_displacement_1s_m=round(float(np.linalg.norm(after - start)), 5),
                box_to_grip_site_m=round(box_to_site, 5),
                box_z_after_m=round(float(after[2]), 4),
                gripper_closed_joint_target=float(closed),
                settle_steps=settle_steps,
                settle_ok=bool(box_to_site < 0.01 and float(after[2]) > 0.03),
            ))
    out = dict(schema='ugrp.crossroom_carry.stageB_settle_check.v1',
               scene=scenario['scenario_id'], n=len(rows),
               pass_n=sum(1 for r in rows if r['settle_ok']),
               gripper_pwm_closed=a.gripper_pwm,
               cargo_own_thresholds=carry_mod.thresholds(),
               episodes=rows,
               scope=('setup-only settle check: single red box placed in the closed gripper, '
                      '1 Sim s CPU settle per start, no controller and no rollout. '
                      'Weld is not used.'))
    a.output.write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(dict(n=out['n'], pass_n=out['pass_n'],
                          failed=[r['episode'] for r in rows if not r['settle_ok']],
                          disp=[(r['episode'], r['box_displacement_1s_m'],
                                 r['box_to_grip_site_m'], r['box_z_after_m']) for r in rows]),
                     indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
