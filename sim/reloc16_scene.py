"""Explicit fixed-scene quality adapter on the existing GL owner thread."""
PROFILE='walls_floor_contrast_v5_indigo110_s80'
QUALITY='no_mip_v1'


def configure_world(world,profile):
    if profile!=PROFILE:return None
    from sim.camera_render_quality import configure_context
    from sim.scene_contrast_v5 import verify_model
    # Native dimensions/MSAA remain unchanged. no_mip is GL texture state only.
    result=world._render_executor.submit(configure_context,world.renderer,world.model,QUALITY).result(timeout=30)
    import os
    return dict(scene=verify_model(world.model,profile),camera_quality=result,
                sensor_options={k:os.environ[k] for k in ('UGRP_SCENE_COLOUR_BOUNDARY','UGRP_SCENE_RENDER_PROFILE','UGRP_SCENE_COLOUR_CALIBRATION','UGRP_SCENE_COLOUR_CALIBRATION_SHA256','UGRP_RELOC16_FLOOR_LANDMARK_MASK','UGRP_RELOC16_BOUNDARY_PROPOSALS','UGRP_RELOC16_CARRY_WALL_FIELD') if k in os.environ},
                input_modalities_changed=False)
