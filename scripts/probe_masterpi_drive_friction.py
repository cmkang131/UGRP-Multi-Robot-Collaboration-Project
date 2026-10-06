"""Finite drive diagnostic, fixed commands; no robot policy or model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = Path('/Users/changmin/projects/ugrp/outputs')
PROFILE = 'masterpi_drive_friction_v1'
PUBLIC_PROFILE = 'masterpi_drive_friction_v2'
THRESHOLD_PROFILE = 'masterpi_drive_friction_v3'
STRIBECK_PROFILE = 'masterpi_drive_friction_v4'
KARNOPP_PROFILE = 'masterpi_drive_friction_v5'
HARD_PROFILE = 'masterpi_drive_friction_v5_hard_v1'
DEADZONE_PROFILE = 'masterpi_drive_friction_v6'
CONTACT_PROFILES = (PROFILE, PUBLIC_PROFILE, THRESHOLD_PROFILE, STRIBECK_PROFILE, KARNOPP_PROFILE, HARD_PROFILE, DEADZONE_PROFILE)
CASES = ('rest', 'forward', 'left', 'turn', 'push', 'no_contact', 'rated_speed')


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def run_case(profile, case, loaded, output, wheel_input=None, drive_s=1.5, torque_audit=False, long_lane=False, stall_audit=False):
    import mujoco
    import numpy as np
    from sim.masterpi_drive_friction import build_world
    if profile == PUBLIC_PROFILE:
        from sim.masterpi_drive_friction_v2 import build_world
    elif profile == THRESHOLD_PROFILE:
        from sim.masterpi_drive_friction_v3 import build_world
    elif profile == STRIBECK_PROFILE:
        from sim.masterpi_drive_friction_v4 import build_world
    elif profile == KARNOPP_PROFILE:
        from sim.masterpi_drive_friction_v5 import build_world
    elif profile == HARD_PROFILE:
        from sim.masterpi_drive_friction_v5_hard import build_world
    elif profile == DEADZONE_PROFILE:
        from sim.masterpi_drive_friction_v6 import build_world
    from sim.zone_final_v3_scene import FinalV3Scene, build_world as legacy_world
    from harness.zone_pair_highpose import HIGH
    from sim.masterpi_dynamics_v2 import FORWARD_PATTERN, LEFT_PATTERN, YAW_LEFT_PATTERN

    scene = FinalV3Scene.from_spec({'map': 'zone_wide_two_doors_final_v3', 'seed': 1601,
        'goal': {'B': {'cyan': 1}}, 'extra_boxes': {}, 'team_cargo': []}, 'local_contact_fine')
    spawn_x = 2.5 if long_lane else 3.
    # Empty east room. Setup-only poses; diagnostic trajectories are prewritten.
    scene.config['setup_only']['spawns']['r1'] = [spawn_x, -1., .0325, 0.]
    kwargs = dict(seed=1601, render=False, warehouse_layout=scene.engine_layout,
                  use_calibration_manifest=False)
    world = None
    output.mkdir()
    started = time.perf_counter()
    result = {'profile': profile, 'case': case, 'loaded': loaded, 'status': 'HOST_ERROR',
              'qualification': 'staged DEV physics diagnostic, not student/hardware success',
              'model_calls': 0, 'physical_success': None, 'loadavg_start': os.getloadavg()}
    try:
        world = (build_world(scene, drive_profile=profile, **kwargs) if profile in CONTACT_PROFILES else
                 legacy_world(scene, 'cargo_noslip_v1', initial_sim_cap_s=30., **kwargs))
        scene.setup(world)
        c = world.robot('r1'); m, d = world.model, world.data
        c.set_servo_pulses({**HIGH, 1:2000}, forward_only=True)
        c.set_base_pose_for_test((spawn_x, -1., .0325), 0.)
        item = next(iter(scene.config['setup_only']['objects'].values()))
        cargo = m.body(item['body_name']).id
        cargo_j = int(m.body_jntadr[cargo]); cargo_q = int(m.jnt_qposadr[cargo_j])
        if loaded:
            # Initial-state staging only. No weld, no ongoing pose correction.
            d.qpos[cargo_q:cargo_q+3] = c.site_xyz('grip_site')
            d.qpos[cargo_q+3:cargo_q+7] = d.xquat[c.gripper_bid]
            for jid in c.gripper_joint:
                d.qpos[int(m.jnt_qposadr[jid])] = (.0467-.040)/2
            c.set_servo_pulses({1:1500})
        else:
            d.qpos[cargo_q:cargo_q+3] = [.5, -.5, .016]
        mujoco.mj_forward(m, d)
        dt = float(m.opt.timestep)
        for _ in range(round(.8/dt)):
            world._physics_step_for(c, np.zeros(4))
        result['cargo_mass_kg'] = float(m.body_mass[cargo])
        result['robot_mass_kg'] = float(c.robot_mass_kg)
        result['cargo_initial_z_m'] = float(d.xpos[cargo, 2])
        if loaded and d.xpos[cargo, 2] < .08:
            result['status'] = 'STAGING_FAILED'
            return result
        if case == 'no_contact':
            # Collision ablation at the SAME pose, gravity zero: no linear
            # momentum can be supplied by internal wheel torque in free flight.
            m.geom_contype[:] = 0; m.geom_conaffinity[:] = 0
            m.pair_margin[:] = -100
            m.opt.gravity[:] = 0
            d.qvel[:] = 0
            mujoco.mj_forward(m, d)
        start_t = float(d.time); start_xyz = c.base_xyz().copy(); start_yaw = c.base_rpy()[2]
        start_com = d.subtree_com[c.robot_bid].copy()
        patterns = {'forward': FORWARD_PATTERN, 'left': LEFT_PATTERN, 'turn': YAW_LEFT_PATTERN,
                    'no_contact': FORWARD_PATTERN, 'rated_speed': FORWARD_PATTERN}
        cmd = patterns.get(case, np.zeros(4)) * (1. if case == 'rated_speed' else .2)
        if wheel_input is not None:
            from sim.masterpi_drive_friction_v3 import wheel_input_normalized
            cmd = patterns.get(case, np.zeros(4)) * wheel_input_normalized(wheel_input)
        result['wheel_input'] = wheel_input if wheel_input is not None else (100 if case == 'rated_speed' else 20)
        result['normalized_wheel_command'] = cmd.tolist()
        wheel_dofs = [m.jnt_dofadr[m.joint(f'r1__wheel_{w}_joint').id] for w in ('fl','fr','rl','rr')]
        result['drive_command_s'] = drive_s
        result['diagnostic_lane'] = 'east_long_x2.5_v1' if long_lane else 'east_x3_v1'
        rows = []; audit_rows = []; own_contact_pairs = {}; wall0 = time.perf_counter()
        force6 = np.zeros(6)
        jac = np.zeros((3, m.nv)); jacr = np.zeros((3, m.nv))
        for i in range(round((drive_s+1.)/dt)):
            t = i*dt; command = cmd if t < drive_s else np.zeros(4)
            if case == 'push':
                # One-newton lateral force is a declared diagnostic excitation,
                # not an inferred beam force or MasterPi load specification.
                d.xfrc_applied[c.robot_bid, 1] = 1. if t < drive_s else 0.
                if profile not in CONTACT_PROFILES:
                    # Legacy stepping overwrites external xfrc; qfrc provides
                    # the identical declared world-y perturbation in both cases.
                    d.qfrc_applied[c.base_dadr+1] = 1. if t < drive_s else 0.
            audit_now = (torque_audit and t <= .15) or (stall_audit and i % max(1, round(.01/dt)) == 0)
            if audit_now:
                pre_velocity = d.qvel.copy()
            world._physics_step_for(c, command)
            if audit_now:
                from scripts.drive_torque_audit import snapshot, contact_loss_breakdown
                audit = snapshot(m, d, c, pre_velocity, t)
                if stall_audit:
                    audit.update(contact_loss_breakdown(m,d,c,pre_velocity))
                audit_rows.append(audit)
            if i % max(1, round(.02/dt)) == 0:
                tangential = normal = 0.; wheel_contacts = 0; slips = []; own_force = 0.
                for j in range(d.ncon):
                    contact = d.contact[j]
                    names = [m.geom(int(g)).name for g in contact.geom]
                    if any(n.startswith('r1__') and ('_contact' in n and '_roller_' in n or n in
                               [f'r1__wheel_{w}' for w in ('fl','fr','rl','rr')]) for n in names):
                        mujoco.mj_contactForce(m, d, j, force6)
                        if all(n.startswith('r1__') for n in names):
                            own_force += abs(force6[0])
                            key = '|'.join(sorted(names))
                            own_contact_pairs[key] = max(own_contact_pairs.get(key, 0.), abs(float(force6[0])))
                        normal += abs(force6[0]); tangential += np.linalg.norm(force6[1:3]); wheel_contacts += 1
                        velocity = []
                        for geom in contact.geom:
                            mujoco.mj_jac(m, d, jac, jacr, contact.pos, int(m.geom_bodyid[int(geom)]))
                            velocity.append(jac @ d.qvel)
                        relative = velocity[1]-velocity[0]
                        if force6[0] > 1e-6:
                            slips.append(float(np.linalg.norm(relative-(relative@contact.frame[:3])*contact.frame[:3])))
                rows.append({'t': float(d.time-start_t), 'xyz': c.base_xyz().tolist(),
                    'yaw': c.base_rpy()[2], 'velocity': d.qvel[c.base_dadr:c.base_dadr+6].tolist(),
                    'com_xyz': d.subtree_com[c.robot_bid].tolist(),
                    'contact_slip_mps': float(np.mean(slips)) if slips else 0.,
                    'wheel_speed': [float(d.qvel[m.jnt_dofadr[m.joint(f'r1__wheel_{w}_joint').id]])
                                    for w in ('fl','fr','rl','rr')],
                    'wheel_actuator_torque_nm': d.actuator_force[c.wheel_act].tolist(),
                    'wheel_friction_limit_nm': m.dof_frictionloss[wheel_dofs].tolist(),
                    'wheel_normal_n': normal, 'wheel_tangent_n': tangential, 'wheel_contacts': wheel_contacts,
                    'own_wheel_contact_force_n': own_force,
                    'base_external_force': d.xfrc_applied[c.robot_bid].tolist(),
                    'cargo_z': float(d.xpos[cargo, 2])})
            if not np.isfinite(d.qpos).all() or max(abs(c.base_rpy()[0]), abs(c.base_rpy()[1])) > .5:
                result['status'] = 'PHYSICS_FAILURE'; break
            if loaded and d.xpos[cargo, 2] < .08:
                result['status'] = 'LOAD_DROP'; break
        else:
            result['status'] = 'MEASURED_DEV'
        elapsed = time.perf_counter()-wall0
        tail = [r for r in rows if drive_s-.5 <= r['t'] <= drive_s]
        result['tail_forward_min_mps'] = min(r['velocity'][0] for r in tail) if tail else None
        result['tail_forward_progress_m'] = tail[-1]['com_xyz'][0]-tail[0]['com_xyz'][0] if tail else None
        result.update(sim_s=float(d.time-start_t), wall_s=elapsed, wall_per_sim=elapsed/(d.time-start_t),
            commands=2, displacement_m=(c.base_xyz()-start_xyz).tolist(), yaw_change_rad=c.base_rpy()[2]-start_yaw,
            steady_velocity=np.mean([r['velocity'] for r in tail], axis=0).tolist() if tail else None,
            com_displacement_m=(d.subtree_com[c.robot_bid]-start_com).tolist(),
            peak_command_com_xy_m=max(float(np.linalg.norm(np.array(r['com_xyz'])[:2]-start_com[:2]))
                                      for r in rows if r['t'] <= drive_s+.001),
            steady_contact_slip_mps=float(np.mean([r['contact_slip_mps'] for r in tail])) if tail else None,
            steady_wheel_rad_s=np.mean([r['wheel_speed'] for r in tail], axis=0).tolist() if tail else None,
            wheel_contact_samples=sum(r['wheel_contacts'] > 0 for r in rows),
            max_base_external_force=max(np.linalg.norm(r['base_external_force']) for r in rows),
            cargo_min_z_m=min(r['cargo_z'] for r in rows),
            stop_drift_m=float(np.linalg.norm(np.array(rows[-1]['xyz'])[:2]-np.array(next((r for r in rows if r['t']>=drive_s), rows[-1])['xyz'])[:2])),
            warnings={mujoco.mjtWarning(i).name: int(d.warning[i].number) for i in range(len(d.warning)) if d.warning[i].number},
            own_wheel_contact_pairs_max_n=own_contact_pairs,
            drive_parameters=getattr(world, 'drive_profile_record', None),
            scene=scene.record(), xml_sha256=hashlib.sha256(world.scene_xml.encode()).hexdigest())
        if torque_audit or stall_audit:
            write(output/'torque-audit.json', audit_rows)
        write(output/'trace.json', rows)
        (output/'scene.xml').write_text(world.scene_xml)
        return result
    except Exception as exc:
        result['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        result['total_wall_s'] = time.perf_counter()-started
        result['loadavg_end'] = os.getloadavg()
        if world is not None:
            world.close()
        write(output/'result.json', result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--drive-profile', choices=(*CONTACT_PROFILES, 'legacy_wrench'), required=True)
    p.add_argument('--wheel-inputs', nargs='+', type=int, choices=range(0,101),
                   help='legacy signed Board magnitude in 0..100; separate reset for each input')
    p.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    p.add_argument('--loaded', action='store_true')
    p.add_argument('--stall-audit', action='store_true', help='read-only .01 s torque/contact breakdown throughout the command and stop')
    p.add_argument('--long-lane', action='store_true', help='setup x2.5: clearance for 5 s at rated speed')
    p.add_argument('--torque-audit', action='store_true', help='read-only every-step torque breakdown for first .15 s')
    p.add_argument('--drive-seconds', type=float, default=1.5,
                   help='fixed command duration, 1.5 to 5 s; stop duration remains 1 s')
    args = p.parse_args()
    if not 1.5 <= args.drive_seconds <= 5:
        p.error('drive-seconds must be within 1.5..5')
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to(RAW_ROOT):
        p.error('raw output must be absolute below primary outputs/')
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if source != args.expected_source_sha or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        p.error('expected clean committed source required')
    if os.environ.get('UGRP_SIM_MANAGED_CHILD') != '1':
        p.error('use sim_cli workflow run masterpi-drive-friction-probe')
    from scripts import agent_lock
    # Status before atomic acquire. Never reuse someone else's codex lock.
    if agent_lock.status(agent_lock.DEFAULT_ROOT) is not None:
        p.error('physics lock occupied; no simulation started')
    args.output.mkdir(parents=True, exist_ok=False)
    lock = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/drive-friction-model',
        purpose='short drive friction diagnostic', pid=os.getpid(), expected_minutes=3, timing_sensitive=True)
    write(args.output/'manifest.json', {'source_sha': source, 'python': platform.python_version(),
        'command': vars(args) | {'output': str(args.output)}, 'lock': lock, 'model_calls': 0})
    try:
        results = []
        for case in args.cases:
            for level in args.wheel_inputs or [None]:
                name = case if level is None else f'{case}-u{level:03}'
                result = run_case(args.drive_profile, case, args.loaded, args.output/name, level, args.drive_seconds, args.torque_audit, args.long_lane, args.stall_audit)
                results.append(result)
                print(json.dumps({k: result.get(k) for k in ('case','wheel_input','status','steady_velocity','wall_per_sim')}, ensure_ascii=False), flush=True)
                if result['status'] != 'MEASURED_DEV':
                    break
            if results[-1]['status'] != 'MEASURED_DEV':
                break
        write(args.output/'results.json', results)
    finally:
        held = agent_lock.status(agent_lock.DEFAULT_ROOT)
        if held and held['pid'] == os.getpid() and held['branch'] == 'codex/drive-friction-model':
            agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')


if __name__ == '__main__':
    main()
