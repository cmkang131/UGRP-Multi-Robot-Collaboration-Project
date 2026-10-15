"""Explicit selected scene for warp3; the historical teacher is left frozen."""
SCENE = 'walls_floor_contrast_v5_indigo110_s80'


def make_scene(plan):
    # Same construction as frozen grasp_act_scene.make_scene, substituting only
    # the appearance installer. Applying a second lighting transform afterward
    # would multiply illumination twice, so assemble once at this boundary.
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml as stiffness
    from sim.grasp_act_scene import colors
    from sim.scene_contrast_v5 import install, profile_record
    import hashlib
    scene = wrap(install(ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']), SCENE))
    scene.config['setup_only']['spawns'] = plan['spawns']
    original = scene.robot_transform
    def transform(xml, **kwargs):
        before = camera.transform_xml(original(xml, **kwargs), profile_id=camera.PROFILE_ID)
        for rid in ('r1', 'r2', 'r3'):
            before = stiffness(before, servo_stiffness='real_v1', robot_id=rid)
        after = colors(before, plan['end_color_scene'])
        scene.manifest['grasp_act_scene'] = dict(version='grasp_act_scene_v1', colors=plan['end_color_scene'],
            parent_xml_sha256=hashlib.sha256(before.encode()).hexdigest(),
            scene_xml_sha256=hashlib.sha256(after.encode()).hexdigest())
        scene.manifest['warp3_scene'] = profile_record(SCENE)
        return after
    scene.robot_transform = transform
    return scene
