"""Pixel budget only. MuJoCo camera mount/FOV and physics are unchanged."""


def dimensions(bundle):
    from harness.e2e_speed4 import Options
    return (320, 240) if Options(**bundle.get('speed4', {})).render_half else (640, 480)


def install(world, bundle):
    from harness.e2e_speed4 import Options
    if not Options(**bundle.get('speed4', {})).render_half:
        return
    import cv2
    original = world._render_rgb_direct

    def render(robot, camera):
        rgb = original(robot, camera)
        # Frozen wall/beam/VO frontends use 640x480 calibration. Upsampling does
        # not restore lost detail; the saved JPEG is the exact degraded input.
        return cv2.resize(rgb, (640, 480), interpolation=cv2.INTER_LINEAR) if camera == 'robot_cam' else rgb

    world._render_rgb_direct = render
