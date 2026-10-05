"""Finite v93 command-trajectory diagnostic; no rendering or student success.

Headless scene and geometric edge check reused from PR #361 a9481446. The
new ArmSequence raise/lower commands are fixed before physics starts. Measured
state is output-only; no GT action correction, weld or camera changes.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from harness import zone_final_pair_contract as c
from harness import zone_pair_highpose as pose
from scripts.run_final_environment_checks import check_source, write
from scripts.zone_teacher import ArmSequence
from sim.final_pair_v3 import PhysicsBackend as Base, make_scene
from sim.final_pair_fast_guard import FastGuard

class Headless(FastGuard, Base):
    def __init__(self, bundle, out, *, seed):
        from sim.zone_final_v3_scene import build_world
        from sim.camera_robot_port import CameraRobotPort
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.pose_sample_index, self._last_guard_xy = 0, {}
        self.scene = make_scene(bundle, seed)
        try:
            self.world = build_world(self.scene, bundle['contact_profile'], seed=seed,
                width=640, height=480, render=False,
                warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            for rid in ('r1', 'r2', 'r3'):
                self.ports[rid] = CameraRobotPort(self.world, rid, allow_reverse=True, allow_mecanum=True)
        except Exception:
            self.close()
            raise


def geometry(model, data, rid):
    """Necessary visibility of actual lime surface; not rendered RGB detection.

    First beam-box intersections must lie past the unchanged near plane. Check
    actual scene occlusion at each supported column's run midpoint via mj_ray.
    Counts are geometric support only; material, light and JPEG remain untested.
    """
    import mujoco
    from harness.owncam_view import _pixel_rays
    from harness.own_beam_edge import _first_run_end
    xs, ys, normal, valid = _pixel_rays(1)
    roi = valid & (xs >= 140) & (xs < 500) & (xs % 4 == 0) & (ys >= 40) & (ys < 300)
    xs, ys = xs[roi], ys[roi]
    optical = np.column_stack((normal[roi], np.ones(roi.sum())))
    optical /= np.linalg.norm(optical, axis=1)[:, None]
    cam = data.camera(rid+'__robot_cam')
    origin = cam.xpos.copy()
    axes = cam.xmat.reshape(3, 3) @ np.diag([1., -1., -1.])
    rays = optical @ axes.T
    near = float(model.stat.extent * model.vis.map.znear)
    entries = []
    for part in ('bar', 'band_neg', 'band_pos'):
        gid = model.geom('cargo_beam__'+part).id
        rot = data.geom_xmat[gid].reshape(3, 3)
        o, v, half = rot.T @ (origin-data.geom_xpos[gid]), rays @ rot, model.geom_size[gid]
        with np.errstate(divide='ignore'):
            a, b = (-half-o)/v, (half-o)/v
        enter, leave = np.max(np.minimum(a, b), axis=1), np.min(np.maximum(a, b), axis=1)
        entries.append(np.where(leave >= np.maximum(enter, 0.), enter, np.inf))
    entries = np.asarray(entries)
    depths = entries[0] * (rays @ axes[:, 2])
    colour = (entries.argmin(axis=0) == 0) & np.isfinite(entries[0]) & (depths >= near)
    ends, clear = [], []
    for x in range(140, 500, 4):
        col = np.zeros(260, bool)
        hit = (xs == x) & colour
        col[(ys[hit]-40).astype(int)] = True
        end = _first_run_end(col)
        if end is None:
            continue
        ends.append((x, end+40))
        # Midpoint of the final 40 pixels of this candidate beam band.
        index = np.flatnonzero((xs == x) & (ys == end+20))[0]
        gid = np.array([-1], np.int32)
        mujoco.mj_ray(model, data, origin, rays[index], np.array([1, 1, 1, 1, 0, 0], np.uint8), 1, -1, gid)
        clear.append(model.geom(int(gid[0])).name == 'cargo_beam__bar' if gid[0] >= 0 else False)
    residual = None
    if len(ends) >= 2:
        x, y = np.asarray(ends).T
        residual = float(np.sqrt(np.mean((y-np.polyval(np.polyfit(x, y, 1), x))**2)))
    return {'near_m': near, 'geometric_colour_pixels': int(colour.sum()),
            'continuous_40px_columns': len(ends), 'unoccluded_midpoint_columns': sum(clear),
            'edge_rows_min_max': [min(y for _, y in ends), max(y for _, y in ends)] if ends else None,
            'edge_line_rms_px': residual,
            'colour_depth_min_m': float(depths[colour].min()) if colour.any() else None}


def commands():
    hover, descent = pose.grasp_postures()
    arm = ArmSequence(None, {1: 2000, **descent[-1]})
    events = [(0., sid, pulse) for sid, pulse in arm.commanded.items()]
    events.append((2., 1, 1500))
    arm.commanded[1] = 1500
    arm.queue({**hover, 1: 1500}, 4., duration=1.2, settle=.3)
    pose.queue_path(arm, 10., pose.raise_path())
    pose.queue_path(arm, 34., pose.lower_path())
    arm.queue({1: 2000}, 49., duration=.4, settle=.5)
    events.extend(arm.events)
    result = []
    for t, sid, pulse in sorted(events):
        # Same reset-relative 50 ms dispatch grid as the managed student.
        t = round(np.ceil((t-1e-9)/.05)*.05, 8)
        for rid in c.ROBOTS:
            action = ({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                      {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
            result.append({'t': t, 'robot_id': rid, 'action': action})
    return sorted(result, key=lambda e: e['t'])


def command_joint_limits(model, events):
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    result = {'targets_checked': 0, 'violations': [], 'minimum_margin_rad': float('inf'),
              'minimum_gripper_margin_m': float('inf')}
    names = {'yaw': ('arm_yaw',), 'shoulder': ('shoulder',), 'elbow': ('elbow',),
             'wrist': ('wrist_pitch',), 'gripper': ('left_gripper_close', 'right_gripper_close')}
    for event in events:
        action = event['action']
        servo = ({6: action['pan_pulse']} if action['kind'] == 'look' else
                 {action['servo_id']: action['pulse']})
        targets = MasterPiDynamicsV2.pulse_to_joint_targets(
            SimpleNamespace(physical_params={'servo6_center_pwm': 1500.}), servo)
        for key, angle in targets.items():
            if key not in names:
                continue
            for name in names[key]:
                joint = model.joint(event['robot_id']+'__'+name)
                low, high = model.jnt_range[joint.id]
                margin = min(angle-low, high-angle)
                result['targets_checked'] += 1
                metric = 'minimum_gripper_margin_m' if key == 'gripper' else 'minimum_margin_rad'
                result[metric] = min(result[metric], float(margin))
                if margin < -1e-9:
                    result['violations'].append({'event': event, 'joint': name, 'target': angle,
                                                  'range': [float(low), float(high)]})
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    check_source(args.source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        cwd=c.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary/'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(28, 'HOST_ERROR: less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    held = status(DEFAULT_ROOT)
    if (not held or not held['pid_alive'] or held['owner'] != 'codex'
            or held['branch'] != 'codex/pair-carry-highpose'):
        raise ValueError('own live highpose host lock required')
    # A diagnostic starts from teacher stations, never from a student prior.
    # Preserve the same standard scene/contact/interlock as PR #361.
    bundle = c.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
    args.output.mkdir(parents=True, exist_ok=False)
    events = commands()
    write(args.output/'commands.json', events)
    write(args.output/'bundle.json', bundle)
    result = {'source_sha': args.source_sha, 'student_candidate': 'zone-final-pair-highpose-v93',
        'loadavg_start': list(os.getloadavg()), 'sim_s': 52., 'commands': len(events), 'model_calls': 0,
        'method': '52 SIM s staged, headless fixed raise/lower diagnostic; no student/RGB/calibration acceptance',
        'geometry': [], 'status': 'HOST_ERROR', 'physical_success': None}
    b = None
    try:
        b = Headless(bundle, args.output, seed=911)
        b.reset(5.)
        result['command_joint_limits'] = command_joint_limits(b.world.model, events)
        if result['command_joint_limits']['violations']:
            raise ValueError('commanded joint limit violation')
        from harness.visual_arm_v3 import tool_pose
        result['kinematics'] = {name: vars(tool_pose(p)) for name, p in
            [('high', pose.HIGH), ('via_110', pose.VIA_110), ('via_130', pose.VIA_130)]}
        start = b.now
        b.set_deadline(start+52.)
        j = 0
        for i in range(1041):
            t = round(i*.05, 8)
            b.eval_sample()
            if t in (9., 30., 32.):
                result['geometry'].append({'relative_s': t, 'robots': {
                    rid: geometry(b.world.model, b.world.data, rid) for rid in c.ROBOTS}})
            if i == 1040:
                break
            while j < len(events) and events[j]['t'] <= t+1e-8:
                e = events[j]
                b.issue(e['robot_id'], e['action'])
                j += 1
            b.advance_to(start+(i+1)*.05)
        assert j == len(events)
        result['status'] = 'HEADLESS_CHECK_COMPLETE'
    except Exception as exc:
        result['failure'] = repr(exc)
        raise
    finally:
        if b is not None:
            b.close()
        result['loadavg_end'] = list(os.getloadavg())
        write(args.output/'summary.json', result)
        write(args.output/'artifacts.sha256.json', {str(f.relative_to(args.output)): c.base.sha(f)
              for f in sorted(args.output.rglob('*')) if f.is_file()})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
