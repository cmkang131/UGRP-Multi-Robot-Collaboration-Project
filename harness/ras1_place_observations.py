"""Feed ras1 fixed-camera wall observations to the current carry place memory."""
import math

import numpy as np

from harness.place_memory_v1 import PlaceMemory


class Ras1PlaceObservations:
    """Local, design-scale observations in the body frame at the first view.

    The source is the unloaded ras1 recorder and its fixed floor profile. The
    initial camera offset is nominal kinematics. Archival contacts use the
    initial camera axes with their origin shifted to each camera position.
    This interface supplies no arena-frame pose or door measurement.
    """

    def __init__(self, *, scale, floor_profile, source='ras1_fixed_camera'):
        self.source = source
        self._posture = {int(key): value for key, value in floor_profile['pose'].items()}
        self._height = float(scale['camera_height_cm']) / 100
        origin = np.asarray(scale['camera_origin_design_m'], dtype=float)
        if (origin.shape != (3,) or not np.isfinite(origin).all()
                or self._height <= 0 or not math.isclose(self._height, origin[2], rel_tol=1e-6)):
            raise ValueError('INVALID_RAS1_DESIGN_SCALE')
        self._camera_offset = origin[:2]
        self.places = PlaceMemory(projection=None)
        self.pose = None
        self._last_time = -math.inf
        self._anchored = False
        self.updates = 0

    def observe(self, checkpoint):
        """Consume one settled own-camera result. Unavailable poses stay absent."""
        t = float(checkpoint['t'])
        if not math.isfinite(t) or t <= self._last_time:
            raise ValueError('RAS1_PLACE_FRAME_ORDER')
        posture = {int(key): value for key, value in checkpoint['commanded_arm_pose'].items()}
        tracking = checkpoint['tracking']
        points = np.asarray(checkpoint['contact_points_cm'], dtype=float).reshape(-1, 2)
        camera = np.asarray(checkpoint['camera_xy_cm'], dtype=float) / 100
        self.pose = None
        self._last_time = t
        if posture != self._posture:
            self._anchored = False
            return False
        if (camera.shape != (2,) or not np.isfinite(camera).all()
                or not len(points) or not np.isfinite(points).all()):
            return False

        if tracking.get('reason') == 'anchor' and self.updates == 0 and np.all(camera == 0):
            pose = (0., 0., 0.)
        elif (self._anchored and tracking.get('reason') == 'ok'
              and tracking.get('pose_status') == 'nominal_floor_pose' and tracking.get('pose') is not None):
            visual = tracking['pose']
            pose = (visual['x'] * self._height, visual['y'] * self._height,
                    math.radians(visual['yaw_deg']))
        else:
            return False
        if not np.isfinite(pose).all():
            return False

        # Shift contacts to the initial body origin, then rotate them into
        # the current body axes. PlaceMemory applies the same pose it uses
        # for the rest of the carry observations.
        initial_body_points = points / 100 + camera + self._camera_offset
        c, s = math.cos(pose[2]), math.sin(pose[2])
        local = (initial_body_points - pose[:2]) @ np.array([[c, -s], [s, c]])
        self.places.observe_wall_contacts(local, pose=pose, phase=self.source)
        self.pose = dict(zip(('x', 'y', 'yaw'), pose))
        self._anchored = True
        self.updates += 1
        return True

    def record(self):
        return dict(source=self.source, frame='initial_body',
                    metric_accuracy_verified=False, visual_pose=self.pose,
                    updates=self.updates, wall_points_m=list(self.places.walls.values()))
