"""Physics owner only. Authored spawn and commands; truth has no feedback path."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import mujoco
import numpy as np
from sim.solo_cyan_v106 import PhysicsBackend as Base
from sim.zone_final_v3_scene import FinalV3Scene
from sim.zone_cargo_contact import base_profile
from sim import masterpi_camera_review_v3 as camera
from sim.masterpi_drive_friction_v7 import build_world
from sim.s2_real_output import RealPrimitivePort
from sim.final_pair_highpose_nearclip import audit,wrap
from sim.render_profile import install
from scripts.run_wall_parallax_strafe import write

class PhysicalStop(RuntimeError):pass

# Byte-identical function from PR406 6bd861fb:sim/s2_realism_camera_binding.py.
def bind_camera(controller):
    def apply():
        controller.model.cam_pos[controller.robot_cam_cid] = np.asarray(camera.POSITION_M)
        controller.model.cam_quat[controller.robot_cam_cid] = np.asarray(camera.QUAT_WXYZ)
        mujoco.mj_forward(controller.model, controller.data)
    original = controller._configure_measured_robot_camera

    def configure():
        original()  # preserve the inherited measured K/D and resolution
        apply()

    controller._configure_measured_robot_camera = configure
    controller._sync_real_camera_mount = apply
    apply()

def make_scene(bundle,seed):
    spawn=bundle['spawn']
    class StrafeScene(FinalV3Scene):
        def _resolve(self):
            super()._resolve()
            pose=self.config['setup_only']['spawns']['r3']
            pose[0],pose[1],pose[3]=spawn
            self.config['setup_only']['parallax_authored_spawn']=spawn
        def transform(self,xml):
            root=ET.fromstring(super().transform(xml))
            body=root.find("worldbody/body[@name='r3__robot']")
            assert body is not None
            pose=self.config['setup_only']['spawns']['r3']
            body.set('pos',' '.join(map(str,pose[:3])))
            body.set('quat',f'{math.cos(spawn[2]/2)} 0 0 {math.sin(spawn[2]/2)}')
            return ET.tostring(root,encoding='unicode')
    scene=StrafeScene.from_spec(dict(map=bundle['map_id'],seed=seed,goal={'B':{'cyan':1}},
        extra_boxes={},team_cargo=[]),base_profile(bundle['contact_profile']))
    scene=wrap(install(scene,'floor_light_v1'))
    transform=scene.robot_transform
    scene.robot_transform=lambda xml,**kw:camera.transform_xml(transform(xml,**kw),profile_id=camera.PROFILE_ID)
    return scene

class PhysicsBackend(Base):
    def __init__(self,bundle,out,*,seed):
        self.out,self.bundle=Path(out),bundle
        self.world,self.ports,self.streams=None,{},{}
        self.frame,self.deadline,self.commands=0,None,{}
        self.eval_rows=[]
        self.scene=make_scene(bundle,seed)
        try:
            self.world=build_world(self.scene,roller_collision='mesh',idle_robot_contacts='off',
                seed=seed,width=640,height=480,render=True,
                warehouse_layout=self.scene.engine_layout,warehouse_cargo_ids=None)
            with self.world.physics_lock:
                for controller in self.world.controllers.values():bind_camera(controller)
            self.dt=float(self.world.model.opt.timestep)
            assert abs(.05/self.dt-round(.05/self.dt))<1e-7
            self.nearclip_audit=audit(self.world.model)
            self._ports()
        except Exception:
            self.close()
            raise
    def _ports(self):
        self.ports={rid:RealPrimitivePort(self.world,rid,allow_reverse=True,
            allow_mecanum=True,min_wheel_cmd='real_v1') for rid in ('r1','r2','r3')}
    def reset(self,cap):
        elapsed=super().reset(cap)
        self._ports()  # IntegerClock reset creates legacy ports; install explicit S2 capability AFTER reset.
        write(self.out/'eval_only/drive-v7.json',self.world.drive_profile_record)
        write(self.out/'eval_only/camera-v3.json',camera.record())
        return elapsed
    def eval_sample(self):
        super().eval_sample()
        m,d=self.world.model,self.world.data
        b=d.body('r3__robot')
        cam=d.camera('r3__robot_cam')
        self._append('eval_only/camera.jsonl',dict(t=self.now,body_xyz=b.xpos.tolist(),
            body_rotation=b.xmat.tolist(),camera_xyz=cam.xpos.tolist(),camera_rotation=cam.xmat.tolist()))
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all():raise PhysicalStop('NONFINITE')
        if math.degrees(math.acos(float(np.clip(b.xmat[8],-1,1))))>10:raise PhysicalStop('TILT_GT10')
        for c in d.contact[:d.ncon]:
            names=[mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,int(i)) or '' for i in (c.geom1,c.geom2)]
            if any(n.startswith('r3__') for n in names) and any('wall' in n for n in names):
                raise PhysicalStop('WALL_CONTACT')
        actual=m.camera('r3__robot_cam')
        assert np.allclose(actual.pos,camera.POSITION_M,atol=1e-12)
        assert np.allclose(actual.quat,camera.QUAT_WXYZ,atol=1e-12)
