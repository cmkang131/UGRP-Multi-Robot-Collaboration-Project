"""Opt-in reuse of the existing S2 v3 render/reset binding; default is identity."""
OPTION = 'v3_persistent_v1'


def attach(world, *, camera_binding='off'):
    if camera_binding == 'off':
        return world
    if camera_binding != OPTION:
        raise ValueError('unknown S3 camera_binding')
    from sim.s2_realism_camera_binding import bind_camera
    with world.physics_lock:
        for controller in world.controllers.values():
            bind_camera(controller)
    return world
