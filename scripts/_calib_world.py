"""World builder shared by the camera-calibration/cone probes: the E2E physics build (v3 camera profile, real_v1 servo
stiffness = arm sag, v3 camera binding) so extrinsics are measured under the same arm sag the runs have. Render only."""
import sys
sys.path.insert(0, '.')


def build_world(xml_extra=None, static_map=None):
    from sim.multi_masterpi_production import MultiMasterPiProductionV2
    from sim.zone_arena import episode
    from sim.zone_scene import ZoneScene
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.s2_realism_camera_binding import bind_camera
    config = episode('zone_wide_door', 11, goal={'B': {'cyan': 1}})
    config['contact_solver_profile'] = 'local_contact_fine'; config['extra_boxes'] = {}
    definition = ZoneScene.from_zone_config(config)
    if static_map is not None:
        definition.config['static_map'] = static_map

    def transform(xml):
        xml = camera.transform_xml(definition.transform(xml), profile_id=camera.PROFILE_ID)
        for rid in ('r1', 'r2', 'r3'):
            xml = stiffness(xml, servo_stiffness='real_v1', robot_id=rid)
        return xml_extra(xml) if xml_extra else xml
    world = MultiMasterPiProductionV2(seed=11, width=640, height=480, render=True, warehouse_layout=definition.engine_layout,
                                      warehouse_cargo_ids=None, xml_transform=transform)
    definition.setup(world)
    bind_camera(world.robot('r1'))
    return world, definition
