"""S3 v7 physical owner; evaluation data never return to the runtime."""
import copy
import math
from pathlib import Path

from sim.zone_s3_host import PhysicsBackend as OldBackend, ROBOTS
from sim.final_environment_checks import PhysicsBackend as BaseBackend
from scripts.run_final_environment_checks import write


class PhysicalStop(RuntimeError):
    pass


HEIGHT_REFERENCE = 'world_body_center_of_mass_v1'


def referee_truth(host):
    """Evaluation only: body origins need not be inside cargo (beam origin is at floor).

    Use MuJoCo's world inertial-frame position for height, including body rotation.
    Do not clamp penetration, change referee thresholds, or feed truth to control.
    Footprint x/y/yaw retain their original geometric reference.
    """
    from scripts.run_zone_study_integration import StudyTeamHost
    rows = StudyTeamHost.referee_truth(host)
    for item, row in rows.items():
        row['z'] = float(host.world.data.body(host.objects[item]['body_name']).xipos[2])
    return rows


def make_scene(bundle, seed):
    from harness import zone_s3_no_prior_contract as contract
    from sim.zone_environment_scene_provider import scenario_scene
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml
    scene = wrap(install(scenario_scene(contract.inputs()[0], seed), 'floor_light_v1'))
    original = scene.robot_transform
    def transform(xml, **kwargs):
        xml = camera.transform_xml(original(xml, **kwargs), profile_id=camera.PROFILE_ID)
        for rid in ROBOTS:
            xml = transform_xml(xml, servo_stiffness='real_v1', robot_id=rid)
        return xml
    scene.robot_transform = transform
    return scene


class PhysicsBackend(OldBackend):
    def __init__(self, bundle, out, *, seed):
        import mujoco
        from sim.masterpi_drive_friction_v7 import build_world, PROFILE
        from sim.camera_robot_port import CameraRobotPort
        from sim.s2_align_pulse import FinePulsePort
        from sim.final_pair_highpose_nearclip import audit
        self.out, self.bundle = Path(out), bundle
        self.world, self.ports, self.streams = None, {}, {}
        self.frame, self.deadline, self.commands = 0, None, {}
        self.scene, self.eval_rows = make_scene(bundle, seed), []
        self.lifted = set()
        try:
            self.world = build_world(self.scene, drive_profile=PROFILE, idle_robot_contacts='off',
                roller_collision='mesh', seed=seed, width=640, height=480, render=True,
                warehouse_layout=self.scene.engine_layout, warehouse_cargo_ids=None)
            self.dt = float(self.world.model.opt.timestep)
            if not math.isfinite(self.dt) or self.dt <= 0 or abs(.05/self.dt-round(.05/self.dt)) > 1e-7:
                raise ValueError('SIM timestep must divide .05 seconds')
            self.nearclip_audit = audit(self.world.model)
            self.ports = {r: CameraRobotPort(self.world, r, allow_reverse=True, allow_mecanum=True) for r in ROBOTS}
            self.ports['r3'] = FinePulsePort(self.world, 'r3', allow_reverse=True, allow_mecanum=True,
                min_wheel_cmd='real_v1', alignment_pulse='real_fine_v1')
            self.objects = copy.deepcopy(self.scene.config['setup_only']['objects'])
            for cargo in self.scene.cargo:
                self.objects[cargo.item_id] = dict(kind=cargo.kind, body_name='cargo_'+cargo.item_id)
            m = self.world.model
            names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or '' for i in range(m.ngeom)]
            self._fingers = {r: ({i for i, n in enumerate(names) if n == r+'__left_finger'},
                {i for i, n in enumerate(names) if n == r+'__right_finger'}) for r in ROBOTS}
            self._box_geom = {item: {i for i in range(m.ngeom) if int(m.geom_bodyid[i]) == int(m.body(o['body_name']).id)}
                              for item, o in self.objects.items()}
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        # Standard Scene reset. No special loader recognizes this new ID.
        from sim.solo_cyan_v106 import PhysicsBackend as SoloBackend
        from scripts.run_zone_study_integration import placements_match
        from harness.zone_s3_no_prior_contract import inputs
        elapsed = SoloBackend.reset(self, cap)
        self.spec = self.scene.spec
        placements_match(inputs()[0], self)
        write(self.out/'eval_only/drive-v7.json', self.world.drive_profile_record)
        return elapsed

    def eval_sample(self):
        BaseBackend.eval_sample(self)
        self._append('eval_only/referee_truth.jsonl', dict(t=self.now,
            items=referee_truth(self), height_reference=HEIGHT_REFERENCE))
        from harness.zone_s2_realism_contract import SAFETY
        import numpy as np
        if not np.isfinite(self.world.data.qpos).all() or not np.isfinite(self.world.data.qvel).all():
            raise PhysicalStop('NONFINITE_STATE')
        for rid in ROBOTS:
            b = self.world.data.body(rid+'__robot')
            tilt = math.degrees(math.acos(float(np.clip(b.xmat[8], -1, 1))))
            self._append(f'eval_only/{rid}/trajectory.jsonl', dict(t=self.now,
                robot_xyz_m=b.xpos.tolist(), robot_yaw_rad=math.atan2(float(b.xmat[3]), float(b.xmat[0])),
                tilt_deg=tilt))
            if tilt >= SAFETY['robot_tilt_limit_deg']:
                raise PhysicalStop('ROBOT_TILT_LIMIT:'+rid)
        for item, config in self.objects.items():
            body = self.world.data.body(config['body_name'])
            if float(body.xpos[2]) > .08:
                self.lifted.add(item)
            owners = ('r3',) if config['kind'] == 'cyan' else ('r1', 'r2')
            releasing = all(self.commands[r].get(1, 2000) >= 2000 for r in owners)
            if item in self.lifted and float(body.xpos[2]) <= .035 and not releasing:
                raise PhysicalStop('LOAD_DROP:'+item)
