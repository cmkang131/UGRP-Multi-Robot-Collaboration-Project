"""Offline reproduction of the set-down release-retreat blockage at the dev-map destination (no simulator).

The set-down release retreats each end robot backwards along the beam axis (study_owncam_pair_beam._released,
forward -0.04, 0.15 s commands, 6 s) and every command passes ``SweepGuard.motion_clear``. Robot r2 stands at the +x end of the
beam in zone B (yaw ~ pi), so the retreat is toward ``wall_east`` (inner face x = 5.375). This script evaluates the repo's own
``SweepGuard.chassis_clearance`` (the chassis-outline part of ``motion_clear``) along that retreat for several declared sigmas
and prints the retreat distance at which the clearance turns negative. It reads only the static dev map and the repo guard;
it does not use a simulator pose.

Usage: python experiments/2026-09-29-pair-v6c-carry/retreat_clearance.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from harness.zone_own_guards import (BASE_MARGIN_M, BODY_COVERAGE_RESIDUAL_M, CHASSIS_X_M, CHASSIS_Y_M, K_SIGMA,  # noqa: E402
                                     OwnPose, SweepGuard)

MAP = ROOT / 'maps/zones/zone_wide_door_tags_v2_dock_v3.json'
R2_RELEASE_X_M = 5.018         # r2 staged GT pose at set-down entry in the dxImg cases (report only): 4.6 + 0.418
R2_Y_M, R2_YAW = -2.10, math.pi   # yaw ~ pi (facing -x); the retreat moves the rear toward wall_east
SIGMAS = [(0.0, 0.0), (0.012, 0.0096), (0.03, 0.0096), (0.034, 0.0096), (0.05, 0.0096)]   # (std_xy_m, std_yaw_rad) declared
STEP = 0.002


def main() -> None:
    static_map = json.loads(MAP.read_text())
    guard = SweepGuard(static_map)
    wall = next(o for o in static_map['obstacles'] if o['id'] == 'wall_east')
    face = wall['center_m'][0] - wall['half_extents_m'][0]
    print(f"map {static_map['map_id']} v{static_map['version']}; wall_east inner face x = {face:.3f} m")
    print(f"chassis x {CHASSIS_X_M} y +-{CHASSIS_Y_M}; margin = {BASE_MARGIN_M} + {BODY_COVERAGE_RESIDUAL_M} + {K_SIGMA}*std_xy "
          f"+ {K_SIGMA}*std_yaw*lever")
    print(f"r2 release pose (x, y, yaw) = ({R2_RELEASE_X_M}, {R2_Y_M}, {R2_YAW:.4f}); the retreat moves +x (rear first)\n")
    print('std_xy_m  std_yaw_rad  clearance at release [m]  retreat until clearance < 0 [m]  x at that point')
    for sxy, syaw in SIGMAS:
        x, first = R2_RELEASE_X_M, None
        clear0, _ = guard.chassis_clearance(OwnPose(x, R2_Y_M, R2_YAW, sxy, syaw))
        while x < face + 0.2:
            clear, hit = guard.chassis_clearance(OwnPose(x, R2_Y_M, R2_YAW, sxy, syaw))
            if clear < 0.:
                first = (x, hit)
                break
            x += STEP
        moved = None if first is None else first[0] - R2_RELEASE_X_M
        print(f"{sxy:8.3f}  {syaw:11.4f}  {clear0:24.3f}  {'' if moved is None else format(moved, '31.3f')}  "
              f"{'' if first is None else format(first[0], '.3f') + ' (' + str(first[1]) + ')'}")
    print('\nThe full retreat of a passing set-down (the pickup cases, b604499d-sdPickup, GT) is 0.163 m per robot, so the destination '
          'needs 0.163 m + the rows above: any std_xy >= 0.012 leaves less room than the retreat needs.')
    print('The dxImg probe cases stopped after 0.083-0.093 m of GT retreat (r2 x 5.018 -> 5.096..5.111, SIM 12.7-13.0 s), between the rows with std_xy 0.034 and 0.05.')


if __name__ == '__main__':
    main()
