"""Static projection of physical texels through the unchanged camera (gcp2)."""
import json
import math
from pathlib import Path
import platform
import cv2
import numpy as np
from scripts import probe_scene_tex2 as p
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D


def measure():
    import mujoco
    from scripts.generate_scene_textures import MAPS
    model, scene, hw, _, _ = p.build_model(MAPS[0], 'floor_light_textured_v1')
    data = mujoco.MjData(model)
    view = p.wall_views(json.loads(MAPS[0].read_text()))[0]
    p.fixture(model, data, scene, view, 'drive', hw)
    camera = model.camera('r1__robot_cam').id
    origin = data.cam_xpos[camera].copy()
    rotation = data.cam_xmat[camera].reshape(3, 3)
    forward = -rotation[:, 2]; forward[2] = 0; forward /= np.linalg.norm(forward)
    left = np.array([-forward[1], forward[0], 0])

    def project(world):
        local = (world-origin)@rotation
        local[:, 1:] *= -1
        uv, _ = cv2.fisheye.projectPoints(local.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                         scaled_camera_matrix(640, 480), np.array(CAMERA_FISHEYE_D))
        return uv.reshape(-1, 2)

    rows = []
    texel = 16/3072  # exact floor asset span/dimension, texuniform=false/repeat1
    for distance in (.5, 1., 2., 3.):
        center = origin+distance*forward; center[2] = 0
        points = np.array([center, center+texel*left, center+texel*forward])
        uv = project(points)
        jac = np.column_stack((uv[1]-uv[0], uv[2]-uv[0]))
        singular = np.linalg.svd(jac, compute_uv=False)
        rows.append({'ground_forward_distance_m': distance, 'center_uv': uv[0].tolist(),
            'native_frame_visible': bool(0 <= uv[0, 0] < 640 and 0 <= uv[0, 1] < 480),
            'one_floor_texel_m': texel, 'texel_px_transverse_longitudinal': np.linalg.norm(jac, axis=0).tolist(),
            'singular_values_px': singular.tolist(),
            'physical_structure_for_5_to_20px_m_each_axis': [(np.array([5, 20])*texel/x).tolist() for x in singular]})
    return {'camera_origin_world': origin.tolist(), 'camera_height_m': float(origin[2]),
            'floor': rows, 'wall_frontal_pinhole': [dict(distance_m=d,
                texel_m=6.5/1024, nominal_texel_px=619.5194540517232*(6.5/1024)/d) for d in (.5, 1., 2., 3.)],
            'note': 'local projection, no floor-metric calibration admission; wall example 6.5m face. Actual lens/poses remain fixed.'}


if __name__ == '__main__':
    if not platform.node().startswith('ugrp-sim-gcp2'):
        raise SystemExit('gcp2 only')
    print(json.dumps(measure(), indent=2))
