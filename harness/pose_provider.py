"""Controller-facing pose contract; only own observations/commands and static geometry.

``last_fix_t`` is the raw capture SIM time of an accepted observation update,
never prediction time, delivery time, a rounded subtraction or a setup prior.
``fix_age_s`` may retain a provider's historical rounding. Controllers use the
raw time for sweep boundaries. A fix is not proof of accuracy: covariance and
the existing uncertainty gates remain mandatory. Observation quality is
provider diagnostic evidence, not a second confidence threshold.
"""
from __future__ import annotations

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from harness.owncam_pose_source import PoseReport


class PoseProvider(Protocol):
    source: str

    def report(self, now: float) -> PoseReport: ...
    def on_frame(self, now: float, rgb) -> PoseReport: ...
    def on_command(self, row) -> None: ...
    def set_motion_profile(self, now: float, name: str | None) -> None: ...
    def get_motion_params(self) -> dict:
        """Detached calibrated motion parameters for the published provider state.

        Uses static calibration and own issued-command load/profile bookkeeping.
        This read cannot advance time, release delayed inputs or renew a fix.
        Delayed providers expose the already released profile only.
        """
        ...
    def begin_relocalization(self, now: float, servo) -> None: ...
    def expected_observability(self, pose, pan: int, static_map) -> float:
        """Nonnegative proposal score at LOOK_P20, never an observed fix.

        Inputs are the own estimated base pose, proposed issued pan and static
        map. No live objects, peer state or evaluation measurements are allowed.
        Zero means no supported prediction; score units are provider-specific.
        """
        ...


def is_own_pose_provider(value):
    """Registered implementations; a matching source label alone is insufficient."""
    from harness.owncam_pose_source import OwnCamPoseSource
    from harness.vision_pose_source import VisionPoseSource
    from harness.zone_study_pose_delay import DelayedPoseSource
    from harness.owncam_pose_guard_provider import GuardedPoseProviderV3

    if isinstance(value, (DelayedPoseSource, GuardedPoseProviderV3)):
        return is_own_pose_provider(value.provider)
    return isinstance(value, (OwnCamPoseSource, VisionPoseSource))
