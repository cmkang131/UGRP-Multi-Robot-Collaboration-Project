"""Finite, render-free posture check; never calibration or student evidence.

Run only from a committed worktree with an owned SIM slot. The standard scene,
physical actuators, v91 abort guard and contact geometry are unchanged. Every
command is fixed before starting; measured state only enters the output.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

import numpy as np

from harness import zone_final_pair_contract as c
from harness.zone_final_pair_vision import grasp_postures
from harness.visual_arm_v3 import solve_grip_ik
from scripts.run_final_environment_checks import check_source, write
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
    hover, descent = grasp_postures()
    high = solve_grip_ik(.2032, 0., .15, -40.)
    visits = [(0., 'floor_grasp', {**descent[-1], 1: 2000}),
              (2., 'close', {1: 1500}), (4., 'controller_hover', hover),
              (16., 'transition_110', solve_grip_ik(.2032, 0., .11, -55.)),
              (20., 'transition_130', solve_grip_ik(.2032, 0., .13, -45.)),
              (24., 'high_view', high), (34., 'pan_minus', {6: 1480}),
              (42., 'center', {6: 1500}), (50., 'pan_plus', {6: 1520}),
              (58., 'center_return', {6: 1500})]
    events = []
    for t, phase, pose in visits:
        for rid in c.ROBOTS:
            for sid, pulse in pose.items():
                action = ({'kind': 'look', 'pan_pulse': pulse} if sid == 6 else
                          {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
                events.append({'t': t, 'phase': phase, 'robot_id': rid, 'action': action})
    return events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-sha', required=True)
    p.add_argument('--sim-slot', required=True)
    args = p.parse_args()
    check_source(args.source_sha)
    from scripts.agent_lock import DEFAULT_ROOT
    from scripts.agent_sim_slots import require_sim_slot
    branch = subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()
    require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner='codex', branch=branch)
    args.output.mkdir(parents=True, exist_ok=False)
    events = commands()
    write(args.output/'commands.json', events)
    bundle = c.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
    result = {'source_sha': args.source_sha, 'loadavg_start': list(os.getloadavg()),
              'method': '66 SIM s headless posture check; no RGB/calibration acceptance',
              'geometry': [], 'status': 'HOST_ERROR'}
    b = None
    try:
        b = Headless(bundle, args.output, seed=911)
        b.reset(5.)
        start = b.now
        b.set_deadline(start+66.)
        j = 0
        for i in range(1321):
            t = round(i*.05, 8)
            b.eval_sample()
            if t in (14., 32., 40., 48., 56., 64.):
                result['geometry'].append({'relative_s': t, 'robots': {
                    rid: geometry(b.world.model, b.world.data, rid) for rid in c.ROBOTS}})
            if i == 1320:
                break
            while j < len(events) and events[j]['t'] <= t+1e-8:
                e = events[j]
                b.issue(e['robot_id'], e['action'])
                j += 1
            b.advance_to(start+(i+1)*.05)
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
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
