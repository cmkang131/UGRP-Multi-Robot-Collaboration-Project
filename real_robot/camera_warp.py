"""Precomputed cv2.remap warp from a real 640x480 camera to the MuJoCo sim camera model.

Transforms a real camera image (focal length `f_real`, principal point `(cx_real, cy_real)`,
optional fisheye distortion `d_real`, and physical mount pitch offset `pitch_offset_deg`)
into the simulator's fisheye camera (`K_sim`, `D_sim` from `ground_projection.py`, nominal
mount pitch) before frames enter `PickBrain`, `approach_survey_v1`, or ACT.

Sign convention (matching `ground_projection.py`):
    `pitch_offset_deg > 0` means the real camera is pitched STEEPER DOWNWARD than the sim model.
    A sim camera ray `(x_s, y_s, z_s)` rotates into the real camera frame by `R_x(+pitch_offset_deg)`:
        x_r = x_s
        y_r = cos(theta) * y_s - sin(theta) * z_s
        z_r = sin(theta) * y_s + cos(theta) * z_s
    so a ray along sim's optical axis `(0, 0, 1)` samples higher up in the steeper-downward real
    image (`y_r < 0`), moving objects downward in the output image to match sim's flatter view.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import cv2
import numpy as np

_GP_PATH = (
    Path(__file__).resolve().parents[1]
    / 'solo_pipeline'
    / 'harness'
    / 'approach_survey_v1_parts'
    / 'ground_projection.py'
)


def _load_sim_intrinsics() -> tuple[np.ndarray, np.ndarray]:
    spec = importlib.util.spec_from_file_location('ugrp_sim_ground_projection', _GP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return np.array(module.K, dtype=np.float64), np.array(module.D, dtype=np.float64)


K_SIM, D_SIM = _load_sim_intrinsics()


def _finite(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number, got {value!r}')
    return float(value)


class SimCameraWarp:
    """Fast precomputed `cv2.remap` rotational homography + intrinsic matcher into `(K_SIM, D_SIM)`."""

    def __init__(
        self,
        *,
        f_real: float,
        pitch_offset_deg: float = 0.0,
        yaw_offset_deg: float = 0.0,
        roll_offset_deg: float = 0.0,
        cx_real: float = 320.0,
        cy_real: float = 240.0,
        d_real: tuple[float, float, float, float] | list[float] | None = None,
        width: int = 640,
        height: int = 480,
        jpeg_quality: int = 90,
    ):
        self.f_real = _finite('f_real', f_real)
        if self.f_real <= 0.0:
            raise ValueError(f'f_real must be > 0, got {self.f_real}')
        self.pitch_offset_deg = _finite('pitch_offset_deg', pitch_offset_deg)
        if not -60.0 <= self.pitch_offset_deg <= 60.0:
            raise ValueError(f'pitch_offset_deg must be in [-60, 60], got {self.pitch_offset_deg}')
        self.yaw_offset_deg = _finite('yaw_offset_deg', yaw_offset_deg)
        if not -60.0 <= self.yaw_offset_deg <= 60.0:
            raise ValueError(f'yaw_offset_deg must be in [-60, 60], got {self.yaw_offset_deg}')
        self.roll_offset_deg = _finite('roll_offset_deg', roll_offset_deg)
        if not -60.0 <= self.roll_offset_deg <= 60.0:
            raise ValueError(f'roll_offset_deg must be in [-60, 60], got {self.roll_offset_deg}')
        self.cx_real = _finite('cx_real', cx_real)
        self.cy_real = _finite('cy_real', cy_real)
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError(f'width and height must be positive ints, got {(width, height)!r}')
        if type(jpeg_quality) is not int or not 1 <= jpeg_quality <= 100:
            raise ValueError(f'jpeg_quality must be int in 1..100, got {jpeg_quality!r}')
        self.width = width
        self.height = height
        self.jpeg_quality = jpeg_quality
        if d_real is not None:
            d_vals = tuple(_finite('d_real', v) for v in d_real)
            if len(d_vals) != 4:
                raise ValueError(f'd_real must have 4 fisheye coefficients, got {len(d_vals)}')
            self.d_real: tuple[float, float, float, float] | None = d_vals
        else:
            self.d_real = None

        self.map_x, self.map_y = self._build_maps()

    def _build_maps(self) -> tuple[np.ndarray, np.ndarray]:
        w, h = self.width, self.height
        us, vs = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
        uv = np.column_stack((us.ravel(), vs.ravel()))
        xy = cv2.fisheye.undistortPoints(uv[:, None, :], K_SIM, D_SIM).reshape(-1, 2)
        back = cv2.fisheye.distortPoints(xy[:, None, :], K_SIM, D_SIM).reshape(-1, 2)
        valid = np.isfinite(xy).all(axis=1) & (np.linalg.norm(back - uv, axis=1) < 1e-5)

        p = math.radians(self.pitch_offset_deg)
        y = math.radians(self.yaw_offset_deg)
        r = math.radians(self.roll_offset_deg)
        cp, sp = math.cos(p), math.sin(p)
        cy, sy = math.cos(y), math.sin(y)
        cr, sr = math.cos(r), math.sin(r)
        rx = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]], dtype=np.float64)
        ry = np.array([[cy, 0.0, -sy], [0.0, 1.0, 0.0], [sy, 0.0, cy]], dtype=np.float64)
        rz = np.array([[cr, sr, 0.0], [-sr, cr, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
        rot = rz @ ry @ rx

        x_s = xy[:, 0]
        y_s = xy[:, 1]
        x_r = rot[0, 0] * x_s + rot[0, 1] * y_s + rot[0, 2]
        y_r = rot[1, 0] * x_s + rot[1, 1] * y_s + rot[1, 2]
        z_r = rot[2, 0] * x_s + rot[2, 1] * y_s + rot[2, 2]

        ok = valid & (z_r > 1e-6)
        mx = np.full(w * h, -1.0, dtype=np.float32)
        my = np.full(w * h, -1.0, dtype=np.float32)
        xn = x_r[ok] / z_r[ok]
        yn = y_r[ok] / z_r[ok]
        if self.d_real is not None:
            k_real = np.array(
                [[self.f_real, 0.0, self.cx_real], [0.0, self.f_real, self.cy_real], [0.0, 0.0, 1.0]],
                dtype=np.float64,
            )
            pts = cv2.fisheye.distortPoints(
                np.column_stack((xn, yn))[:, None, :],
                k_real,
                np.asarray(self.d_real, dtype=np.float64),
            ).reshape(-1, 2)
            mx[ok] = pts[:, 0].astype(np.float32)
            my[ok] = pts[:, 1].astype(np.float32)
        else:
            mx[ok] = (self.f_real * xn + self.cx_real).astype(np.float32)
            my[ok] = (self.f_real * yn + self.cy_real).astype(np.float32)
        return mx.reshape(h, w), my.reshape(h, w)

    def warp_image(self, img: np.ndarray) -> np.ndarray:
        if img is None or img.shape[:2] != (self.height, self.width):
            raise ValueError(f'expected ({self.height}, {self.width}) image, got {None if img is None else img.shape}')
        return cv2.remap(img, self.map_x, self.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def warp_jpeg(self, jpeg: bytes) -> bytes:
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError('failed to decode input JPEG')
        warped = self.warp_image(img)
        ok, enc = cv2.imencode('.jpg', warped, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            raise RuntimeError('failed to encode warped JPEG')
        return enc.tobytes()

    def __call__(self, jpeg: bytes) -> bytes:
        return self.warp_jpeg(jpeg)

    def config(self) -> dict:
        return {
            'f_real': self.f_real,
            'pitch_offset_deg': self.pitch_offset_deg,
            'yaw_offset_deg': self.yaw_offset_deg,
            'roll_offset_deg': self.roll_offset_deg,
            'cx_real': self.cx_real,
            'cy_real': self.cy_real,
            'd_real': list(self.d_real) if self.d_real is not None else None,
            'width': self.width,
            'height': self.height,
            'jpeg_quality': self.jpeg_quality,
        }
