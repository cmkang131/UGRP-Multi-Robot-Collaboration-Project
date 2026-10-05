"""v98-only v102 affine dead zone (``harness/zone_pair_deadband``) without editing shared, hash-pinned sources.

The #378 diff edited ``zone_final_pair_skill.motor_command`` and ``vision_pose_source_pair_v3.pair_motion_module``. Older
bundles (v88/v90 legacy writers, held-out and loaded schedules) pin those files byte for byte, so the same arithmetic
lives here instead: ``motor_command`` = shared inverse + dead zone added back; ``motion_module`` = shared pair PF
subclass whose partner operand and loaded prediction see the affine-effective command. Without ``deadband.u0`` (every
calibration before v102) both are the shared code exactly.
"""
from __future__ import annotations

import contextlib
from types import SimpleNamespace

from harness import zone_pair_deadband as deadband


def motor_command(profile, velocity):
    from harness import zone_final_pair_skill as skill
    return deadband.inverse_affine(skill.motor_command(profile, velocity), profile['deadband'])


@contextlib.contextmanager
def shared_motor_command():
    """``V3Controller.door_schedule`` calls the module-level ``motor_command``; swap it for the call only."""
    from harness import zone_final_pair_skill as skill
    shared = skill.motor_command
    skill.motor_command = lambda profile, velocity: deadband.inverse_affine(shared(profile, velocity), profile['deadband'])
    try:
        yield
    finally:
        skill.motor_command = shared


def motion_module():
    from harness.vision_pose_source_pair_v3 import pair_motion_module
    base = pair_motion_module()
    Pair = base.OwnCamLocalizer

    class HighPoseMotion(Pair):
        def _partner_of(self, t, cmd):
            raw = super(Pair, self)._partner_of(t, cmd)          # skip the shared ramp-only operand
            if raw is None:
                return None
            return deadband.effective(raw, self.params['motion_loaded']['deadband'])

        def predict_to(self, t):
            db = (self.params.get('motion_loaded') or {}).get('deadband') if self.load.loaded else None
            if not deadband.has_affine(db):
                return super().predict_to(t)
            issued = self.cmd
            self.cmd = deadband.affine(issued, db)
            try:
                return super().predict_to(t)
            finally:
                self.cmd = issued

    return SimpleNamespace(**{**vars(base), 'OwnCamLocalizer': HighPoseMotion})
