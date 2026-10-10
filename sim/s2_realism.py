"""Native v7 wheel physics with v3 own camera; separate abort-only supervisor."""
import math
from pathlib import Path
import numpy as np

from sim import solo_cyan_v106 as old
from sim import masterpi_camera_review_v3 as camera
from sim.masterpi_drive_friction_v7 import build_world, PROFILE
from sim.camera_robot_port import CameraRobotPort
from sim.final_pair_highpose_nearclip import audit
from scripts.run_final_environment_checks import write
from harness.zone_s2_realism_contract import SAFETY


class PhysicalStop(RuntimeError):
    pass


class StopGuard:
    """20 Hz physical supervisor. Stops the experiment, never supplies a pose/action."""
    def __init__(self):
        self.lifted = False
        self.lost_since = None

    def check(self, row, *, release_allowed):
        if row['robot_tilt_deg'] >= SAFETY['robot_tilt_limit_deg']:
            raise PhysicalStop('ROBOT_TILT_LIMIT')
        self.lifted |= row['cyan_z_m'] > SAFETY['lift_z_m']
        if not self.lifted or release_allowed:
            self.lost_since = None
            return
        # Both finger contacts absent/present are physical topology, not an inferred grasp receipt.
        if not all(row['finger_contacts']):
            if self.lost_since is None:
                self.lost_since = row['t']
            if row['t']-self.lost_since >= SAFETY['grip_lost_s']-1e-8:
                raise PhysicalStop('GRIP_LOSS')
            if row['cyan_min_z_m'] <= SAFETY['drop_floor_m']:
                raise PhysicalStop('LOAD_DROP')
        else:
            self.lost_since = None


def make_scene(bundle, seed):
    scene = old.make_scene(bundle, seed)
    transform = scene.robot_transform

    def robot_transform(xml, **kwargs):
        return camera.transform_xml(transform(xml, **kwargs), profile_id=camera.PROFILE_ID)

    scene.robot_transform = robot_transform
    scene.manifest['s2_realism_options'] = dict(bundle['options'])
    return scene


class PhysicsBackend(old.PhysicsBackend):
    def __init__(self, bundle, out, *, seed):
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.scene, self.eval_rows, self.guard = make_scene(bundle, seed), [], StopGuard()
        self.release_allowed = False
        try:
            self.world = build_world(self.scene, drive_profile=PROFILE, seed=seed, width=640,
                                     height=480, render=True, warehouse_layout=self.scene.engine_layout,
                                     warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide 0.05 s')
            self.nearclip_audit = audit(self.world.model)
            self.ports = {r: CameraRobotPort(self.world, r, allow_reverse=True, allow_mecanum=True)
                          for r in ('r1', 'r2', 'r3')}
            m = self.world.model
            for rid in self.ports:
                cam = m.camera(rid+'__robot_cam')
                if not (np.allclose(cam.pos, camera.POSITION_M, atol=1e-12) and
                        np.allclose(cam.quat, camera.QUAT_WXYZ, atol=1e-12)):
                    raise ValueError('v3 camera not applied')
            self.rid = bundle['task']['robot_id']
            item = next(iter(self.scene.config['setup_only']['objects'].values()))
            self.cargo_bid = m.body(item['body_name']).id
            self.cargo_geoms = {i for i in range(m.ngeom) if m.geom_bodyid[i] == self.cargo_bid}
            self.fingers = [m.geom(self.rid+'__'+side+'_finger').id for side in ('left','right')]
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        elapsed = super().reset(cap)
        write(self.out/'eval_only/drive-v7.json', self.world.drive_profile_record)
        write(self.out/'eval_only/camera-v3.json', camera.record())
        return elapsed

    def eval_sample(self):
        super().eval_sample()
        m, d = self.world.model, self.world.data
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all():
            raise PhysicalStop('NONFINITE_STATE')
        row = self.eval_rows[-1]
        robot = d.body(self.rid+'__robot')
        contact = [False, False]
        for c in d.contact[:d.ncon]:
            for a, b in ((c.geom1,c.geom2), (c.geom2,c.geom1)):
                if b in self.cargo_geoms and a in self.fingers:
                    contact[self.fingers.index(a)] = True
        extent = abs(np.asarray(row['cyan_rotation']).reshape(3,3)[2]) @ np.asarray(row['box_half_m'])
        record = dict(t=self.now, cyan_z_m=row['cyan_xyz_m'][2],
                      cyan_min_z_m=float(row['cyan_xyz_m'][2]-extent), finger_contacts=contact,
                      robot_tilt_deg=math.degrees(math.acos(float(np.clip(robot.xmat[8],-1,1)))),
                      release_allowed=self.release_allowed,
                      wheel_command=self.world.robot(self.rid).motor_command.tolist(),
                      drive_input_state=self.world.drive_input_state.get(self.rid,np.zeros(4,dtype=int)).tolist(),
                      base_external_force=d.xfrc_applied[robot.id].tolist())
        self._append('eval_only/supervisor.jsonl', record)
        self.guard.check(record, release_allowed=self.release_allowed)
