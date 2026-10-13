"""Evaluation-only COM/contact drop guard. Never returned to a controller."""
import math

MODE = 'contact_com_v1'
MODE_REST = 'contact_com_rest_v1'   # default-off: a beam resting on the floor ends the lifted state
REST_S = 1.0
REST_CLEAR_DEFAULT = False   # set by e2e_relook_giveup.install for dev_light_rest_v1 runs


class DropGuard:
    def __init__(self, rest_clear=False):
        self.rest_clear = rest_clear
        self.rest_since = None
        self.lifted = False
        self.previous = None
        self.free_z = None

    def observe(self, *, t, com_z, origin_z, finger_contact, floor_contact):
        if not all(math.isfinite(v) for v in (t, com_z, origin_z)):
            raise ValueError('nonfinite drop evaluation')
        self.lifted |= com_z > .08
        vz = ((com_z-self.previous[1])/(t-self.previous[0])
              if self.previous and t > self.previous[0] else 0.)
        rest = self.rest_clear or REST_CLEAR_DEFAULT
        if rest:
            # Set down and settled on the floor (supported, slow, low): no longer "lifted",
            # so a one-sample contact flicker of a resting beam is not a drop. A real
            # unsupported fall is still flagged while it happens (before it can rest).
            if floor_contact and not finger_contact and com_z <= .03 and abs(vz) <= .02:
                self.rest_since = t if self.rest_since is None else self.rest_since
                if t-self.rest_since >= REST_S:
                    self.lifted = False
            else:
                self.rest_since = None
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
        return dict(t=t, mode=MODE_REST if (self.rest_clear or REST_CLEAR_DEFAULT) else MODE, com_z_m=com_z, origin_z_m=origin_z,
                    finger_contact=bool(finger_contact), floor_contact=bool(floor_contact),
                    vertical_speed_m_s=vz, unsupported_descent_m=descent, drop=bool(drop))
