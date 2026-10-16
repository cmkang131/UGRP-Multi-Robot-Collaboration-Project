"""Host-side S2 v3 mount binding and write-only render-pose evidence."""
OPTION = 'v3_persistent_v1'


def camera_pose(world, controller):
    """Evaluation only, sampled in the render thread's coherent physics view."""
    cid = controller.robot_cam_cid
    return dict(t=float(world.data.time), camera_binding=OPTION,
        local_position_m=world.model.cam_pos[cid].tolist(),
        local_quat_wxyz=world.model.cam_quat[cid].tolist(),
        world_position_m=world.data.cam_xpos[cid].tolist(),
        world_rotation=world.data.cam_xmat[cid].tolist(),
        intrinsic=world.model.cam_intrinsic[cid].tolist(),
        resolution=world.model.cam_resolution[cid].tolist(),
        joint_qpos=world.data.qpos.tolist(), gt_use='eval_only; never controller input')


def attach(world, *, camera_binding='off', audit=None):
    if camera_binding == 'off':
        return world
    if camera_binding != OPTION:
        raise ValueError('unknown S3 camera_binding')
    from sim.s2_realism_camera_binding import bind_camera
    with world.physics_lock:
        for controller in world.controllers.values():
            bind_camera(controller)
    if audit is not None:
        original = world._render_rgb_direct
        names = {id(controller): rid for rid, controller in world.controllers.items()}
        sequence = {rid: 0 for rid in names.values()}

        def render(controller, camera):
            # This executes on the renderer's owner thread. The RLock also
            # spans the snapshot, so no physics step can separate it from RGB.
            with world.physics_lock:
                rgb = original(controller, camera)
                if camera == 'robot_cam':
                    rid = names[id(controller)]
                    row = camera_pose(world, controller)
                    row.update(robot_id=rid, render_index=sequence[rid])
                    audit(rid, row)
                    sequence[rid] += 1
                return rgb

        world._render_rgb_direct = render
    return world
