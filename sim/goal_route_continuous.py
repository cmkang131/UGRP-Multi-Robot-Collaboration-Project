"""P1 standard single-door Scene adapter; scene state never enters policy.

The legacy egomap plant selects FinalV3Scene (two-door registry). P1 explicitly
selects the already registered MasterPiV3ZoneScene, same physical v7/v3 hooks.
"""
import copy
import math
from harness.active_camera import bind
from sim import wall_parallax_strafe as legacy
from sim.zone_masterpi_v3_scene import MasterPiV3ZoneScene
from sim.own_map_closed_loop import PhysicsBackend as Base
from sim.wall_texture import transform_xml as texture
from sim.servo_stiffness import transform_xml as stiffness


def make_scene(bundle,seed):
    # Reuse authored spawn / camera / render / nearclip setup byte-for-byte;
    # change only the correct existing registry class, not scene geometry.
    class AssignedP1Scene(MasterPiV3ZoneScene):
        def _resolve(self):
            super()._resolve()
            spawns=self.config['setup_only']['spawns']
            original=copy.deepcopy(spawns)
            # S2 permutes robot IDs over three authored rows. Assign r3 to the
            # preregistered row by permutation, never overlay two bodies.
            owner=next((rid for rid,p in spawns.items() if math.dist(p[:2],bundle['spawn'][:2])<.001),None)
            if owner is not None and owner!='r3':spawns['r3'],spawns[owner]=spawns[owner],spawns['r3']
            self.config['setup_only']['goal_route_spawn_assignment']=dict(original=original,swapped_with=owner,
                rule='assign active robot to preregistered standard row by swapping robot IDs; no deletion')
    factory=bind(legacy.make_scene,FinalV3Scene=AssignedP1Scene)
    scene=factory(bundle,seed)
    original=scene.transform
    scene.transform=lambda xml:stiffness(texture(original(xml),wall_texture=bundle['options']['wall_texture']),
        servo_stiffness=bundle['options']['servo_stiffness'])
    return scene


class PhysicsBackend(Base):
    __init__=bind(Base.__init__,make_scene=make_scene)
