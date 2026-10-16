"""S3-only missing-pose wait; sealed final-pair/highpose guards stay unchanged."""
import math

from harness.zone_final_pair_guards import PairRecheck as Previous
from harness.zone_own_sweep import SweepRecheck as PreviousSweep


class _MissingPoseWait:
    def __init__(self, *, loaded_profile=None, fail_closed_without_pose=False):
        super().__init__(loaded_profile=loaded_profile)
        self.fail_closed_without_pose = fail_closed_without_pose

    def check(self, now, guard, current, target, pose, *, loaded):
        if self.fail_closed_without_pose and (pose is None or not all(
                math.isfinite(float(v)) for v in
                (pose.x, pose.y, pose.yaw, pose.std_xy, pose.std_yaw))):
            self._account_wait(now)
            result = self._wait(now)
            self.sweep_waiting = result == 'wait'
            return result
        return super().check(now, guard, current, target, pose, loaded=loaded)


class PairRecheck(_MissingPoseWait, Previous):
    pass


class SweepRecheck(_MissingPoseWait, PreviousSweep):
    """Explicit S3 probe adapter; the solo runtime keeps its frozen default."""


def attach(execution, *, fail_closed_without_pose=False):
    guard = execution.command_guard
    if isinstance(guard.recheck, PairRecheck):
        return
    recheck = PairRecheck(loaded_profile=guard.recheck.loaded_profile,
                          fail_closed_without_pose=fail_closed_without_pose)
    recheck.__dict__.update(vars(guard.recheck))
    guard.recheck = recheck
    execution.controller.driver.sweep_recheck = recheck
