"""Isolated egomap22 physical owner. Only own RGB leaves capture; GT write-only."""
import copy
from pathlib import Path
from sim import wall_servo_stiffness as old
from sim.active_wall_texture import transform_xml


def make_scene(bundle,seed):
    base=copy.deepcopy(bundle)
    base['options']['wall_texture']='off'
    scene=old.make_scene(base,seed)
    original=scene.transform
    scene.transform=lambda xml:transform_xml(original(xml),wall_texture=bundle['options'].get('wall_texture','off'))
    return scene


class PhysicsBackend(old.PhysicsBackend):
    def __init__(self,bundle,out,*,seed):
        self.out,self.bundle=Path(out),bundle
        self.world,self.ports,self.streams=None,{},{}
        self.frame,self.deadline,self.commands=0,None,{}
        self.eval_rows=[]
        self.scene=make_scene(bundle,seed)
        try:
            self.world=old.old.build_world(self.scene,drive_profile='masterpi_drive_friction_v7',
                roller_collision='mesh',idle_robot_contacts='off',seed=seed,width=640,height=480,
                render=True,warehouse_layout=self.scene.engine_layout,warehouse_cargo_ids=None)
            with self.world.physics_lock:
                for controller in self.world.controllers.values():old.old.bind_camera(controller)
            self.dt=float(self.world.model.opt.timestep)
            assert abs(.05/self.dt-round(.05/self.dt))<1e-7
            self.nearclip_audit=old.old.audit(self.world.model)
            self._ports()
        except Exception:
            self.close()
            raise
