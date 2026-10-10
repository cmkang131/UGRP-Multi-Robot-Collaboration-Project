"""Evaluation-only COM/contact drop guard. Never returned to a controller."""
import math

MODE = 'contact_com_v1'


class DropGuard:
    def __init__(self):
        self.lifted = False
        self.previous = None
        self.free_z = None

    def observe(self, *, t, com_z, origin_z, finger_contact, floor_contact):
        if not all(math.isfinite(v) for v in (t, com_z, origin_z)):
            raise ValueError('nonfinite drop evaluation')
        self.lifted |= com_z > .08
        vz = ((com_z-self.previous[1])/(t-self.previous[0])
              if self.previous and t > self.previous[0] else 0.)
        unsupported = not finger_contact and not floor_contact
        if unsupported and self.lifted:
            if self.free_z is None:
                self.free_z = self.previous[1] if self.previous else com_z
        else:
            self.free_z = None
        descent = max(0., self.free_z-com_z) if self.free_z is not None else 0.
        # Supported lowering and floor placement are not drops. Actual
        # unsupported fall stays a stop, including an intentional early open.
        drop = self.lifted and unsupported and (com_z <= .035 or descent >= .020 and vz < -.10)
        self.previous = (t, com_z)
        return dict(t=t, mode=MODE, com_z_m=com_z, origin_z_m=origin_z,
                    finger_contact=bool(finger_contact), floor_contact=bool(floor_contact),
                    vertical_speed_m_s=vz, unsupported_descent_m=descent, drop=bool(drop))
