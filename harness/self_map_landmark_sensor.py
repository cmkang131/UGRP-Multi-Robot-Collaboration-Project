"""Offline RGB adapter to the pinned, unchanged S2 landmark measurements.

Only own RGB, commanded servo and frozen observed wall-column rows enter.
Camera geometry is egomap34 SEARCH command FK; no live joints or truth pose.
"""
from types import SimpleNamespace
import cv2
import numpy as np
from harness.own_map_amcl_vendor import landmarks as lm, visibility as vis
from harness.own_map_amcl_vendor.landmark_color import cyan
from harness.active_wall_vision import modules
from harness.active_camera import transform


class Sensor:
    def __init__(self, hues):
        self.palette = SimpleNamespace(hues=list(hues))
        self.cache = {}
        self.visibility = SimpleNamespace(cache={})

    def measure(self, bgr, servo, wall_columns):
        mp = modules()[0]
        assert np.allclose(mp.K_INV, vis.K_INV)
        key = tuple(sorted(servo.items()))
        if key not in self.cache:
            origin, rotation = transform(servo)
            cm = mp.ColumnModel(key, 0., mp.column_positions(96, 2), camera_transform=(origin, rotation))
            height, width = bgr.shape[:2]
            yy, xx = np.indices((height, width))
            _, valid, depth = lm.ground(cm, np.c_[xx.ravel(), yy.ravel()], mp.K_INV)
            shadow = vis.depth_image(self.visibility, cm, servo)
            idx = np.argmin(abs(np.arange(width)[:, None]-cm.columns[None, :]), axis=1)
            clear = valid.reshape(height, width) & (depth.reshape(height, width) < shadow[:, idx])
            self.cache[key] = cm, clear
        cm, visible = self.cache[key]
        image = mp.undistort(bgr)
        radius = vis.PARAMS['cargo_padding_px']
        cargo = cv2.dilate(cyan(image).astype(np.uint8),
            np.ones((2*radius+1, 2*radius+1), np.uint8)).astype(bool)
        clear = visible & ~cargo
        # Missing columns stay missing; never infer a door from no return.
        obs = SimpleNamespace(columns=cm.columns, b_kind=np.zeros(len(cm.columns), int),
                              b_lo=np.full(len(cm.columns), np.nan))
        for j, uv in zip(wall_columns['columns'], wall_columns['uv']):
            if abs(float(cm.columns[j])-uv[0]) > 1e-6:
                raise ValueError('FROZEN_COLUMN_ABI_MISMATCH')
            obs.b_kind[j], obs.b_lo[j] = 1, uv[1]
        features = (lm.floor_features(image, cm, mp.K_INV, self.palette, clear) +
                    lm.door_features(image, cm, obs, mp.K, clear))
        return features
