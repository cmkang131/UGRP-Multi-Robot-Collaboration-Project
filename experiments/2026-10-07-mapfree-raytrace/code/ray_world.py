"""Evaluation sensor metadata adapter; endpoints, draws and visibility unchanged.

Only commanded/calibrated camera origins accompany the existing own observations.
The geometry below is confined to the privileged visibility evaluator, as before.
"""
import numpy as np
from grid_world import SEARCH, boxes_occupied, commanded_camera
from contact_world import ContactOracleWorld, ContactWorld


class CameraOriginMetadata:
    def visibility(self, points, servo):
        result = super().visibility(points, servo)
        if points is self.floor:
            valid = result[2] & ~boxes_occupied(self.floor, self.rects)
            origin, _ = commanded_camera(servo, 'camera_v3')
            self._floor_origins.extend([origin[:2].tolist() for _ in range(int(valid.sum()))])
        return result

    def observe(self, frame_id):
        self._floor_origins = []
        observation, patches, truth = super().observe(frame_id)
        assert len(self._floor_origins) == len(observation['floor_xy'])
        origin, _ = commanded_camera(SEARCH, 'camera_v3')
        return {**observation, 'floor_origins_xy': self._floor_origins,
                'wall_origins_xy': [origin[:2].tolist() for _ in observation['wall_xy']]}, patches, truth


class RayOracleWorld(CameraOriginMetadata, ContactOracleWorld):
    pass


class RayNoisyWorld(CameraOriginMetadata, ContactWorld):
    """Metadata-only support, not authorization to run the unfitted noise model."""
