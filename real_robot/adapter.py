"""Unified per-robot Sim2Real adaptation layer (perception + vision + calibration metadata).

Every robot has one profile JSON under `configs/real_robot/<robot_id>.json`:
- Pi side (`real_robot/executor.py`): reads `wheels`, `pulse_scale`, `servos` so every sim
  14-value command produces sim-equivalent physical motion on that robot.
- Laptop side (`Sim2RealAdapter`): reads `camera` and `vision` from the exact same JSON so
  every real camera frame is warped into the simulator's camera model `(K_SIM, D_SIM, -18 deg)`
  and colour/vision filters match the robot's physical environment before reaching `PickBrain`,
  `SignBrain`, `ACT`, or any future multi-robot planner.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from .calibration import (
    RED_HUE_MAX_DEFAULT,
    RED_SAT_MIN_DEFAULT,
    Calibration,
    CameraConfig,
    VisionConfig,
    load as load_calibration,
)


class Sim2RealAdapter:
    """Applies one robot's perception-side calibration (SimCameraWarp + vision env) transparently."""

    def __init__(
        self,
        calibration: Calibration | None = None,
        *,
        camera: CameraConfig | None = None,
        vision: VisionConfig | None = None,
        calibration_path: str | Path | None = None,
    ):
        self.calibration = calibration
        self.calibration_path = str(calibration_path) if calibration_path is not None else None
        self.camera: CameraConfig = camera if camera is not None else (
            calibration.camera if calibration is not None else CameraConfig()
        )
        self.vision: VisionConfig = vision if vision is not None else (
            calibration.vision if calibration is not None else VisionConfig()
        )
        self._warper = None
        if self.camera.enabled:
            from .camera_warp import SimCameraWarp
            self._warper = SimCameraWarp(
                f_real=self.camera.f_real,
                pitch_offset_deg=self.camera.pitch_offset_deg,
                yaw_offset_deg=self.camera.yaw_offset_deg,
                roll_offset_deg=self.camera.roll_offset_deg,
                cx_real=self.camera.cx_real,
                cy_real=self.camera.cy_real,
                d_real=self.camera.d_real,
                jpeg_quality=self.camera.jpeg_quality,
            )

    @classmethod
    def from_file(cls, path: str | Path, *, camera_overrides: dict | None = None,
                  vision_overrides: dict | None = None) -> 'Sim2RealAdapter':
        cal = load_calibration(path)
        cam = replace(cal.camera, **(camera_overrides or {}))
        vis = replace(cal.vision, **(vision_overrides or {}))
        return cls(cal, camera=cam, vision=vis, calibration_path=path)

    @property
    def frame_transform(self):
        return self._warper

    def transform_frame(self, jpeg: bytes) -> bytes:
        return self._warper(jpeg) if self._warper is not None else jpeg

    def vision_env(self) -> dict[str, str]:
        """Return only non-default UGRP_* environment overrides so sim defaults stay untouched."""
        env: dict[str, str] = {}
        if self.vision.camera_pitch_offset_deg != 0.0:
            env['UGRP_CAMERA_PITCH_OFFSET_DEG'] = str(self.vision.camera_pitch_offset_deg)
        if self.vision.area_scale != 1.0:
            env['UGRP_APPROACH_AREA_SCALE'] = str(self.vision.area_scale)
        if self.vision.red_hue_max != RED_HUE_MAX_DEFAULT:
            env['UGRP_RED_HUE_MAX'] = str(self.vision.red_hue_max)
        if self.vision.red_sat_min != RED_SAT_MIN_DEFAULT:
            env['UGRP_RED_SAT_MIN'] = str(self.vision.red_sat_min)
        return env

    @contextmanager
    def vision_context(self):
        """Temporarily apply this robot's vision thresholds to process env (inherited by ACT worker)."""
        keys = (
            'UGRP_CAMERA_PITCH_OFFSET_DEG',
            'UGRP_APPROACH_AREA_SCALE',
            'UGRP_RED_HUE_MAX',
            'UGRP_RED_SAT_MIN',
        )
        prev = {k: os.environ.get(k) for k in keys}
        overrides = self.vision_env()
        try:
            for k in keys:
                if k in overrides:
                    os.environ[k] = overrides[k]
                else:
                    os.environ.pop(k, None)
            yield self
        finally:
            for k, old in prev.items():
                if old is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = old

    def summary(self) -> dict:
        out = {
            'calibration_path': self.calibration_path,
            'robot_id': self.calibration.robot_id if self.calibration is not None else None,
            'measured': self.calibration.measured if self.calibration is not None else None,
            'camera': self._warper.config() if self._warper is not None else None,
            'vision': asdict(self.vision),
        }
        if self.calibration is not None:
            out['pulse_scale'] = dict(self.calibration.pulse_scale)
            non_default_servos = {
                str(sid): asdict(cfg)
                for sid, cfg in self.calibration.servos.items()
                if cfg.offset_pwm != 0 or cfg.min_pwm != 500 or cfg.max_pwm != 2500
            }
            if non_default_servos:
                out['servos'] = non_default_servos
        return out
