"""V3 teacher station geometry. No modification of the frozen v2 teacher.

This adapter is for demonstration/setup consumers only; its item pose argument
must never be supplied to a student's control or success-notification path.
"""
import math

from sim.zone_model_conventions import convention, station_offset


class TeacherStationsV3:
    def __init__(self, scene):
        self.scene = scene
        self.profile = convention(scene)
        if self.profile['robot_model'] != 'masterpi_v3':
            raise ValueError('v3 teacher stations require a v3 scene')

    def station(self, kind, role, item_pose):
        from harness.zone_team_footprint import transform
        x, y, yaw = station_offset(self.scene, kind, role)
        xy = transform([(x, y)], item_pose)[0]
        return (*xy, item_pose[2] + yaw)

    def approach(self, kind, role, item_pose, *, backoff_m=.10):
        x, y, yaw = self.station(kind, role, item_pose)
        return x - backoff_m * math.cos(yaw), y - backoff_m * math.sin(yaw), yaw
