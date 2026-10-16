"""Isolated egomap19 plant. Evaluation state never returns to the scheduler."""
from pathlib import Path
import numpy as np
from sim import wall_parallax_strafe as old
from sim.wall_texture import transform_xml as texture
from sim.servo_stiffness import transform_xml, parameters


def make_scene(bundle, seed):
    scene = old.make_scene(bundle, seed)
    if bundle['case'].startswith('static-'):
        # Authored test fixture from fixed CAD, not a runtime target/observation.
        from harness import servo_camera_fk as fk
        from harness.zone_final_pair_vision import grasp_postures
        from sim.masterpi_geometry_v3 import PHYSICAL_V3
        _, q = fk.commanded_joints({1:2000, **grasp_postures()[1][-1]})
        T = np.eye(4)
        T[:3,3] = fk.model()['floor_to_chassis_translation_m']
        for link in fk.model()['chain']:
            T = T@fk.fixed_transform(link)
            if 'servo' in link:
                J = np.eye(4)
                J[:3,:3] = fk.axis_rotation(link['joint_axis'],q[link['servo']])
                T = T@J
        pad = T@np.array([PHYSICAL_V3.pad_center_from_wrist_m,0,0,1.])
        x,y,yaw = bundle['spawn']
        c,s = np.cos(yaw),np.sin(yaw)
        item = next(iter(scene.config['setup_only']['objects'].values()))
        item['position_m'][:2] = [x+c*pad[0]-s*pad[1],y+s*pad[0]+c*pad[1]]
        scene.config['setup_only']['stiffness_fixture'] = dict(
            rule='nominal floor-grasp pad XY; free cube on floor; no restaging after setup',
            nominal_pad_body=pad[:3].tolist())
    original = scene.transform
    options = bundle.get('options',{})
    scene.transform = lambda xml: transform_xml(
        texture(original(xml),wall_texture=options.get('wall_texture','off')),
        servo_stiffness=options.get('servo_stiffness','off'))
    return scene


class PhysicsBackend(old.PhysicsBackend):
    def __init__(self,bundle,out,*,seed):
        self.out,self.bundle = Path(out),bundle
        self.world,self.ports,self.streams = None,{},{}
        self.frame,self.deadline,self.commands = 0,None,{}
        self.eval_rows = []
        self.scene = make_scene(bundle,seed)
        try:
            self.world = old.build_world(self.scene,drive_profile='masterpi_drive_friction_v7',
                roller_collision='mesh',idle_robot_contacts='off',seed=seed,width=640,height=480,
                render=True,warehouse_layout=self.scene.engine_layout,warehouse_cargo_ids=None)
            with self.world.physics_lock:
                for controller in self.world.controllers.values():
                    old.bind_camera(controller)
            self.dt = float(self.world.model.opt.timestep)
            assert abs(.05/self.dt-round(.05/self.dt))<1e-7
            self.nearclip_audit = old.audit(self.world.model)
            self._ports()
            m=self.world.model
            if bundle['options']['servo_stiffness']=='real_v1':
                for name,spec in parameters().items():
                    i=m.actuator('r3__servo_'+name).id
                    assert abs(m.actuator_gainprm[i,0]-spec['kp'])<1e-10
                    assert m.actuator_biasprm[i,2]<0
                    np.testing.assert_allclose(m.actuator_forcerange[i],
                        [-spec['torque_limit_nm'],spec['torque_limit_nm']],atol=1e-12)
        except Exception:
            self.close()
            raise

    def eval_sample(self):
        super().eval_sample()
        m,d=self.world.model,self.world.data
        values={}
        for sid,name,act in [(6,'arm_yaw','arm_yaw'),(5,'shoulder','shoulder'),
                             (4,'elbow','elbow'),(3,'wrist_pitch','wrist')]:
            j=m.joint('r3__'+name).id
            a=m.actuator('r3__servo_'+act).id
            values[str(sid)]=dict(q_rad=float(d.qpos[m.jnt_qposadr[j]]),
                qvel=float(d.qvel[m.jnt_dofadr[j]]),target_rad=float(d.ctrl[a]),
                torque_nm=float(d.actuator_force[a]),kp=float(m.actuator_gainprm[a,0]),
                kv=float(-m.actuator_biasprm[a,2]))
        self._append('eval_only/servo.jsonl',dict(t=self.now,joints=values,
            commands=self.commands['r3'],qualification='evaluation only, no returned state'))
