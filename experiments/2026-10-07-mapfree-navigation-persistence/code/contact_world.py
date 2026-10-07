"""Pure-2D contact/stop sensor adapter, evaluation boundary only.

No geometric collision labels or truth poses leave this module via contact_sample.
Existing camera/FOV/error draws remain unchanged. First contact is still a collision.
"""
import numpy as np
from grid_world_v2 import RectangleWorld
from diagnose_environment import OracleWorld, rectangle_contacts
from harness.self_odom_grid import transform


class ContactWorld(RectangleWorld):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bumper_pressed = False
        self.contact_events = []

    def _motion_step(self, body_delta, variance):
        delta = body_delta+self.motion_rng.normal(size=3)*np.sqrt(variance)
        before = self.pose.copy()
        proposed = np.r_[transform([delta[:2]], before)[0], before[2]+delta[2]]
        contacts = rectangle_contacts(proposed, self.rects, self.static['bounds_m'])
        if contacts:
            if not self.bumper_pressed:
                self.collisions += 1
                self.contact_events.append(dict(t=self.motion.t, pose_world=before.tolist(),
                                                proposed_pose_world=proposed.tolist(), contacts=contacts))
            self.bumper_pressed = True
            # Reject penetrating substep. Odometry still integrates its own command.
            return
        if np.linalg.norm(delta) > 1e-12:
            self.bumper_pressed = False
        self.pose = proposed
        self.distance += float(np.linalg.norm(proposed[:2]-before[:2]))
        self.path.append(self.pose.tolist())

    def contact_sample(self, t):
        return dict(t=float(t), pressed=bool(self.bumper_pressed))


class ContactOracleWorld(OracleWorld, ContactWorld):
    pass
