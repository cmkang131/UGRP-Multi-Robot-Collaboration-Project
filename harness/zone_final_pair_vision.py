"""Frozen beam pixel algorithms with per-robot measured v3 projection."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from harness import owncam_pair_beam as v1
from harness import owncam_pair_beam_v2 as v2
from harness import owncam_pair_beam_v6d as v6d
from harness import zone_pair_grasp_entry_v6c as entry
from harness.owncam_view import _pixel_rays
from harness.zone_pair_beam_track import standoff_estimate
from harness.zone_final_pair_binding import bind
from harness.zone_final_pair_contract import camera_record
from sim.masterpi_robot_models import station_grasp_convention

GRASP_RADIUS_M = station_grasp_convention('masterpi_v3')['station_radius_m']
ALIGN_TOL_X_M = .003  # the old +/-12 mm includes unreachable v3 physical-pad IK
ALIGN_TOL_Y_M = .003


def grasp_postures():
    """Finite commanded poses shared with acquisition (no unmeasured IK keys).

    RGB aligns the object to this fixed reachable station within 3 mm per
    axis. The small remaining error is a physical acceptance question.
    """
    from harness import visual_arm_v3 as arm
    from scripts.study_owncam_pair_beam import GRASP_Z_M, HOVER_Z_M
    grasp = arm.solve_grip_ik(GRASP_RADIUS_M, 0., GRASP_Z_M, -90.)
    pitch = arm.tool_pose(grasp).pitch_deg
    hover = arm.solve_grip_ik(GRASP_RADIUS_M, 0., HOVER_Z_M, pitch)
    path = [arm.solve_grip_ik(GRASP_RADIUS_M, 0., float(z), pitch)
            for z in np.linspace(HOVER_Z_M, GRASP_Z_M, 8)[1:]]
    return hover, path


def required_camera_poses():
    from harness.owncam_drive import LOOK_P20
    from scripts.run_m2_pair import PREGRASP_PANS_V2
    hover, path = grasp_postures()
    views = [v2.pose_of(name) for name in v2.order()]
    return {'unloaded': [*views, *[{**LOOK_P20, 6: pan} for pan in dict.fromkeys(PREGRASP_PANS_V2)],
                         hover, path[-1]], 'loaded': [path[-1], hover]}


class PairVision:
    def __init__(self, calibration):
        self.calibration = calibration
        # These algorithms use floor-supported beam views; loaded hold/lift
        # checks use pixel masks only, without projecting through a v2 camera.
        self.v1_observe = bind(v1.observe_beam, base_rays=self.base_rays)
        own_v1 = SimpleNamespace(**{**vars(v1), 'observe_beam': self.v1_observe})
        self.v2_observe = bind(v2.observe_beam, v1=own_v1, base_rays=self.base_rays)
        self.points = bind(entry.grasp_range_points, base_rays=self.base_rays)
        errors = bind(v1.align_errors, GRASP_RADIUS_M=GRASP_RADIUS_M)
        self.align_errors = errors
        self.align_command = bind(v1.align_command, align_errors=errors,
                                  ALIGN_TOL_X_M=ALIGN_TOL_X_M, ALIGN_TOL_M=ALIGN_TOL_Y_M)

    def base_rays(self, servo, step=8):
        record = camera_record(self.calibration, 'unloaded', servo)
        xs, ys, normal, valid = _pixel_rays(step)
        optical = np.column_stack((normal, np.ones(len(normal))))
        rays = optical @ np.asarray(record['rotation']).T
        rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        return np.asarray(record['origin_m']), rays, xs, ys, valid

    def observe_beam(self, image, servo, hue_lo=None):
        return self.v2_observe(v6d.widen_lime(v1.decode(image), hue_lo), servo)

    def beam_track(self):
        vision = self
        measured_standoff = bind(standoff_estimate, observe_beam=self.v2_observe)

        class Track(entry.GraspRangeBeamTrack):
            def _standoff(self, obs, servo):
                return measured_standoff(obs, servo, points=vision.points,
                                         min_strip_support=entry.MIN_STRIP_SUPPORT)

            def _partial_points(self, obs, servo):
                self._patch = vision.points(obs['image'], servo)
                return self._patch, 'GRASP_RANGE_BEAM_COLOUR_V3_MEASURED'

        return Track()
