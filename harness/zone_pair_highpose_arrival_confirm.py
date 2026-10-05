"""v98 only: an unloaded approach counts as arrived only if the own camera sees the beam where the dock geometry says.

Finding (v98 raise_high probe 1f7fb800, r1): the approach declared arrival at the grasp pre-station (``wait_approach``
at 118.5 SIM s) with its own estimate 0.030 m from the goal while the own PF was 178 mm off (sigma 3.5-8 mm: over-
confident). Arrival relied on the PF estimate/sigma only. The existing beam-consistency check
(``run_m2_pair.CONSIST_X_M/Y_M`` = 0.25 / 0.20 m) runs only after the approach barrier, and at 0.16 m of error it
would still have passed.

Rule (visual servoing / docking practice: the pre-staged pose is only trusted after the sensor sees the target where
the desired image features s* say; error e = s - s*). At the arrival stop the arm is in the drive posture (the last
stop-and-look returns it there), a posture with a measured camera model. The lime beam silhouette of the own frame
must be consistent with the beam seen from some pose inside the stated tolerance:

* tolerance (all existing constants, nothing tuned): own arrival tolerance ``ARRIVE_TOL_M`` / ``ARRIVE_TOL_YAW_RAD``
  of the driver, plus the order-sheet quantisation of the beam pose (half a cell: ``SHEET_XY_M``/2,
  ``SHEET_YAW_RAD``/2; the sheet is the setup pose rounded to that grid, so the true beam differs by at most that);
* the beam box (static task spec: 600 x 40 mm, black grip bands 36 mm wide centred at the grasp x of the plan) is
  projected through the measured camera model of the posture (``floor_camera`` + the fisheye lens) for the
  3**6 = 729 corner/centre poses of that tolerance box; per image edge (top row, bottom row, left column, right
  column of the lime silhouette) the band is [min, max] of the predicted values over these poses, widened by
  ``MARGIN_PX`` (projection residual measured on recorded frames, below);
* the observed silhouette is the bounding box of the lime connected components of at least
  ``owncam_pair_beam.MIN_POINTS`` pixels (same hue mask as every other beam module). Each of the four edges must
  fall inside its band, and a silhouette must exist. Where a feature depends on whether a small lime piece (the 12 mm
  tails beyond the bands, the end faces) reaches the pixel threshold, the band spans both cases.

On a rejection the driver relocalizes and approaches again, at most ``MAX_VIEW_RETRIES`` times. In v98 the
relocalization is ``GuardedPairApproach._relocalize`` -> provider ``begin_relocalization``: it voids only the fix
receipt and keeps the particle belief and its sigma (it is not ``run_m2_pair._start_reapproach``'s fresh localizer),
then runs the look; ``arrival_checked``/``rotated``/``hold_yaw`` are reset. Kept alone, an over-confident wrong belief
is not corrected by the look and the second arrival is rejected on the same view (independent review #363 P1-2). The
rejection path therefore first arms the provider's one-shot belief expansion (``request_belief_expansion``; expansion
resetting, Ueda et al. 2004, radii 0.1 m / 0.1 m / 0.2 rad as in emcl2) so the look starts from a belief wide enough to
reach the view; no other relocalization (DR checkpoint, look-around) expands. The retry
count ``MAX_VIEW_RETRIES`` = ``run_m2_pair.MAX_REAPPROACH``; the next rejection ends the approach with outcome
``arrival_not_confirmed_by_view`` (controller failure ``APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW``).
The decision waits at most ``CONFIRM_WAIT_S`` (= ``blind_close.HOVER_CONFIRM_MAX_S``) for a frame captured after
the arm and base settled; none inside the window counts as a rejection (fail closed). The window restarts at every
own arm/look/drive command (review #363 P1-1: a small correction issued while the estimate sits on the tolerance
edge must not use up the window of the earlier hold). Total SIM time stays under the existing ``APPROACH_LIMIT_S``
of the approach state. The check sits below the communication layer (before the approach barrier, no status or message change), so
all four communication conditions behave identically.

Inputs: own RGB frame, own issued commands (settle timing), the static order sheet / beam spec / driver goal, the
measured camera model of the drive posture in the static calibration. No ground truth, no simulator state, no
partner pose. The module checks necessary conditions per image edge, not a joint pose fit; it cannot see errors
inside the tolerance and does not correct the pose (an image-based correction step is a possible later addition).
Shared and frozen modules are unchanged.
"""
from __future__ import annotations

import itertools
import math

import cv2
import numpy as np

from harness import owncam_pair_beam as v1
from harness.owncam_drive import ARRIVE_TOL_M, SETTLE_S
from harness.pair_owncam_approach import ARRIVE_TOL_YAW_RAD, SHEET_XY_M, SHEET_YAW_RAD
from harness.vision_pose_source_final import camera_key
from harness.zone_final_pair_camera import floor_camera
from harness.zone_final_pair_contract import TICK_S
from harness.zone_pair_highpose_blind_close import HOVER_CONFIRM_MAX_S
from scripts.run_m2_pair import MAX_REAPPROACH
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

ID = 'v98_approach_arrival_view_confirm_v1'
OUTCOME = 'arrival_not_confirmed_by_view'
FAILURE = 'APPROACH_' + OUTCOME.upper()          # M2Student._approach: 'APPROACH_' + driver.outcome.upper()
CAUSE = 'ARRIVAL_VIEW_NOT_CONFIRMED'
MAX_VIEW_RETRIES = MAX_REAPPROACH
CONFIRM_WAIT_S = HOVER_CONFIRM_MAX_S
FRAME_SETTLE_S = SETTLE_S + TICK_S               # own arm/base settle + one capture period of capture lag

# Projection residual of the measured camera model: on 5 recorded truth-labelled standstill views of the 1f7fb800
# probes in the drive posture 740/2320/1320/1500 (spawn view at 2.2 m, a stop at 0.41 m, the false arrival, the
# staged true dock of r1 and of r2; labels used offline only) every observed silhouette edge lies inside its
# predicted interval, or within 0.3 px of it; the only miss is an edge clipped by the image border. + 1 px mask-edge
# quantisation, rounded up. The verdicts of the recorded false/true views do not change for any margin 0..2 px.
MARGIN_PX = 2.
BAND_HALF_LEN_M = .018                           # "black grip bands 36 mm wide at both ends" (sim.zone_cargo task spec)
BEAM_TOP_Z_M = v1.BEAM_TOP_Z_M
EDGE_SAMPLES = 7                                 # points per box edge (the fisheye bends straight edges)
REFERENCES = (
    'Chaumette & Hutchinson, Visual servo control Part I: Basic approaches, IEEE RAM 13(4), 2006 (error e = s - s*)',
    'Nav2 opennav_docking (open-navigation/opennav_docking): staging pose, then detection-refined dock pose, '
    'bounded max_retries (isDocked detail: unverified)',
    'Nav2 SimpleGoalChecker xy/yaw tolerance + SimpleProgressChecker movement radius/time (docs.nav2.org; page fetch '
    'failed, parameter names from search results)',
    'Thrun, Fox, Burgard, Dellaert, Robust Monte Carlo localization (aMCL), AI 128, 2001: a confident filter cannot '
    'recover without independent evidence (sensor-likelihood monitoring/injection)',
)


def tolerance() -> dict:
    """The stated tolerance box: own arrival tolerance + half an order-sheet cell (all existing constants)."""
    return {'robot_xy_m': ARRIVE_TOL_M, 'robot_yaw_rad': ARRIVE_TOL_YAW_RAD,
            'sheet_xy_m': SHEET_XY_M/2, 'sheet_yaw_rad': SHEET_YAW_RAD/2}


def _box_points(half_len, half_w, height, n=EDGE_SAMPLES):
    """Sampled edges of a box with axis-aligned beam-frame extents, rows (s, t, z)."""
    pts = []
    corners = [(sx*half_len, sy*half_w, z) for sx in (-1, 1) for sy in (-1, 1) for z in (0., height)]
    for a, b in itertools.combinations(corners, 2):
        if sum(abs(x-y) > 1e-12 for x, y in zip(a, b)) == 1:           # an edge: corners differ in one coordinate
            pts.extend(tuple(np.add(a, (np.subtract(b, a))*k/(n-1))) for k in range(n))
    return np.array(pts, float)


class Projector:
    """Measured camera model of one posture: floor-heading-frame points -> raw fisheye pixels."""

    def __init__(self, record):
        cam = floor_camera(record)
        self.origin, self.rotation = np.array(cam['origin_m'], float), np.array(cam['rotation'], float)
        self.k = scaled_camera_matrix(640, 480)
        self.d = np.asarray(CAMERA_FISHEYE_D, np.float64).reshape(4, 1)

    def project(self, points):
        rel = (np.asarray(points, float).reshape(-1, 3)-self.origin) @ self.rotation       # R^T (p - o)
        if not (rel[:, 2] > 1e-6).all():
            raise ValueError('beam point behind the camera inside the tolerance envelope')
        norm = (rel[:, :2]/rel[:, 2:3]).reshape(-1, 1, 2)
        return cv2.fisheye.distortPoints(norm, self.k, self.d).reshape(-1, 2)

    def min_range_m(self, points):
        return float(np.linalg.norm(np.asarray(points, float).reshape(-1, 3)-self.origin, axis=1).min())


def _to_floor(points_beam, beam_xyyaw, robot_xyyaw):
    """Beam-frame (s, t, z) points -> robot floor-heading frame for a beam pose and a robot pose (world, floor z=0)."""
    bx, by, byaw = beam_xyyaw
    rx, ry, ryaw = robot_xyyaw
    p = np.asarray(points_beam, float)
    cb, sb, cr, sr = math.cos(byaw), math.sin(byaw), math.cos(ryaw), math.sin(ryaw)
    wx, wy = bx+cb*p[:, 0]-sb*p[:, 1], by+sb*p[:, 0]+cb*p[:, 1]
    dx, dy = wx-rx, wy-ry
    return np.c_[cr*dx+sr*dy, -sr*dx+cr*dy, p[:, 2]]


def envelope_poses(goal_xyyaw, sheet_xyyaw, tol=None):
    """The 3**6 (robot error) x (beam sheet error) corner/centre poses of the tolerance box."""
    tol = tolerance() if tol is None else tol
    steps = np.array([tol['robot_xy_m'], tol['robot_xy_m'], tol['robot_yaw_rad'],
                      tol['sheet_xy_m'], tol['sheet_xy_m'], tol['sheet_yaw_rad']])
    for s in itertools.product((-1, 0, 1), repeat=6):
        d = np.array(s)*steps
        yield (tuple(np.add(goal_xyyaw, d[:3])), tuple(np.add(sheet_xyyaw, d[3:])))


def predicted_bands(projector, goal_xyyaw, sheet_xyyaw, *, half_len_m, half_w_m, height_m, main_half_len_m,
                    margin_px=MARGIN_PX, tol=None):
    """Per-edge image bands of the lime silhouette over the tolerance box (derivation in the module docstring).

    ``ALL`` = the whole beam box, ``MAIN`` = the lime top section between the bands (|s| <= main_half_len_m). A
    small lime piece beyond the bands may or may not reach the component threshold, so every edge value lies
    between its ALL-based and MAIN-based prediction; the band is the union of that interval over the poses.
    """
    all_pts = _box_points(half_len_m, half_w_m, height_m)
    main_pts = _box_points(main_half_len_m, half_w_m, height_m)
    lo = {k: [] for k in ('top', 'bottom', 'left', 'right')}
    hi = {k: [] for k in lo}
    rng = []
    for robot, beam in envelope_poses(goal_xyyaw, sheet_xyyaw, tol):
        fa, fm = _to_floor(all_pts, beam, robot), _to_floor(main_pts, beam, robot)
        pa, pm = projector.project(fa), projector.project(fm)
        rng.append(projector.min_range_m(fa))
        lo['top'].append(pa[:, 1].min()); hi['top'].append(pm[:, 1].min())
        lo['bottom'].append(pm[:, 1].max()); hi['bottom'].append(pa[:, 1].max())
        lo['left'].append(pa[:, 0].min()); hi['left'].append(pm[:, 0].min())
        lo['right'].append(pm[:, 0].max()); hi['right'].append(pa[:, 0].max())
    bands = {k: (float(min(lo[k]))-margin_px, float(max(hi[k]))+margin_px) for k in lo}
    return {'bands_px': bands, 'margin_px': margin_px, 'poses': len(rng), 'min_range_m': float(min(rng))}


def observe_silhouette(frame_bgr):
    """Bounding box (top, bottom, left, right) of lime components of >= MIN_POINTS px, or None."""
    mask = v1.lime_mask(frame_bgr).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_AREA] >= v1.MIN_POINTS]
    if not keep:
        return None
    s = stats[keep]
    return {'top': int(s[:, cv2.CC_STAT_TOP].min()),
            'bottom': int((s[:, cv2.CC_STAT_TOP]+s[:, cv2.CC_STAT_HEIGHT]-1).max()),
            'left': int(s[:, cv2.CC_STAT_LEFT].min()),
            'right': int((s[:, cv2.CC_STAT_LEFT]+s[:, cv2.CC_STAT_WIDTH]-1).max()),
            'components': len(keep), 'area_px': int(s[:, cv2.CC_STAT_AREA].sum())}


def decide(observed, bands_px):
    """``{'ok', 'reasons', 'observed', 'bands_px'}``; every edge must be inside its band."""
    if observed is None:
        return {'ok': False, 'reasons': ['BEAM_NOT_VISIBLE'], 'observed': None, 'bands_px': bands_px}
    reasons = [k.upper()+'_OUT_OF_BAND' for k, (lo, hi) in bands_px.items() if not lo <= observed[k] <= hi]
    return {'ok': not reasons, 'reasons': reasons, 'observed': observed, 'bands_px': bands_px}


class ArrivalView:
    """Bands for one robot, fixed at construction from static facts."""

    def __init__(self, calibration, posture_key, goal_xyyaw, plan, *, margin_px=MARGIN_PX):
        record = calibration['camera_models']['unloaded'][posture_key]      # KeyError: unmeasured posture, fail closed
        self.key = posture_key
        geometry = plan['beam_geometry']
        half_len, half_w, half_h = (float(v) for v in geometry['half_extents_m'])
        grasp_x = abs(float(geometry['grasps']['end_neg']['xyz_m'][0]))
        self.sheet = tuple(float(v) for v in plan['sheet']['beam_xyyaw'])
        self.goal = tuple(float(v) for v in goal_xyyaw)
        self.derivation = predicted_bands(Projector(record), self.goal, self.sheet, half_len_m=half_len,
                                          half_w_m=half_w, height_m=2*half_h, main_half_len_m=grasp_x-BAND_HALF_LEN_M, margin_px=margin_px)
        self.bands_px = self.derivation['bands_px']

    def check(self, frame_bgr):
        return decide(observe_silhouette(frame_bgr), self.bands_px)


def _plain(value):
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


class ViewConfirmedArrival:
    """Mixin placed in front of the guarded pair approach driver (``adopt``)."""
    arrival_view: ArrivalView | None = None

    def observe(self, now, rgb):
        self._av_frame = (float(now), rgb)
        return super().observe(now, rgb)

    def on_command(self, row):
        kind = row.get('kind')
        if kind in ('arm', 'look', 'initial_servo_command') or (
                kind == 'mecanum' and any(row.get(k, 0.) != 0. for k in ('forward', 'left', 'turn'))):
            self._av_changed = float(row['t'])
            self._av_wait_since = None        # the settle wait restarts with the new command (review #363 P1-1)
        return super().on_command(row)

    def _av_settled_frame(self, now):
        """The cached own frame (BGR) if captured after arm and base settled, in the measured posture; else None."""
        frame = getattr(self, '_av_frame', None)
        if frame is None or camera_key(self.servo) != self.arrival_view.key:
            return None
        t_obs, rgb = frame
        if now-t_obs > CONFIRM_WAIT_S or t_obs-getattr(self, '_av_changed', -1e9) < FRAME_SETTLE_S-1e-9:
            return None
        return np.ascontiguousarray(rgb[..., ::-1])

    def _arrive(self, now):
        if self.arrival_view is None:
            raise RuntimeError('arrival view not configured (zone_pair_highpose_arrival_confirm.configure)')
        since = getattr(self, '_av_wait_since', None)
        frame = self._av_settled_frame(now)
        if frame is None:
            self._av_wait_since = since = now if since is None else since
            if now-since <= CONFIRM_WAIT_S:
                return [{'kind': 'hold'}]
            verdict = {'ok': False, 'reasons': ['NO_SETTLED_FRAME'], 'observed': None,
                       'bands_px': self.arrival_view.bands_px}
        else:
            verdict = self.arrival_view.check(frame)
        self._av_wait_since = None
        rejected = getattr(self, 'view_rejections', 0)
        detail = _plain({'reasons': verdict['reasons'], 'observed': verdict['observed'],
                         'bands_px': verdict['bands_px'], 'posture_key': self.arrival_view.key,
                         'rejections_before': rejected, 'max_retries': MAX_VIEW_RETRIES,
                         'decided_by': 'own RGB + measured camera model + static order sheet (not the PF)'})
        if verdict['ok']:
            self._event(now, 'arrival_view_confirmed', **detail)
            return super()._arrive(now)
        self.view_rejections = rejected+1
        self._event(now, 'arrival_view_rejected', **detail)
        if self.view_rejections > MAX_VIEW_RETRIES:
            return self._finish(now, OUTCOME)
        # approach again: relocalization voids the fix receipt, after a one-shot belief expansion (expansion resetting), then looks
        self.arrival_checked, self.rotated, self.hold_yaw = False, False, None
        self.arrival_rechecks, self.path, self.last_look = 0, None, None
        pose = getattr(self, '_shared_pose', None)
        request_belief_expansion(pose)
        try:
            return self._relocalize(now)
        finally:
            clear_belief_expansion(pose)             # the request never outlives this relocalization (e.g. a delayed-provider branch)


def request_belief_expansion(pose) -> bool:
    """Arrival-rejection path only: arm the own provider's one-shot belief expansion for the coming relocalization.

    ``pose`` is the driver's shared pose source (the delayed wrapper exposes the provider as ``.provider``); a source without
    the hook (fakes, older providers) is left unchanged and False is returned. Nothing else (DR checkpoint, look-around) arms it.
    """
    provider = getattr(pose, 'provider', pose)
    arm = getattr(provider, 'arm_expansion', None)
    if arm is None:
        return False
    arm()
    return True


def clear_belief_expansion(pose) -> None:
    provider = getattr(pose, 'provider', pose)
    disarm = getattr(provider, 'disarm_expansion', None)
    if disarm is not None:
        disarm()


_CACHE: dict = {}


def adopt(cls):
    """Driver class with the arrival view check; one class object per base so ``type(driver)`` stays stable."""
    if cls not in _CACHE:
        _CACHE[cls] = type('ViewConfirmed' + cls.__name__, (ViewConfirmedArrival, cls), {})
    return _CACHE[cls]


def configure(driver, plan, calibration):
    """Fix the bands of one driver from its goal, the plan's order sheet / beam spec and the measured calibration."""
    driver.arrival_view = ArrivalView(calibration, camera_key(driver.drive_pose), (*driver.goal, driver.goal_yaw), plan)
    driver.view_rejections = 0
    return driver.arrival_view


def record() -> dict:
    return {'id': ID, 'scope': 'unloaded approach arrival only (before the approach barrier, below the comm layer)',
            'new_threshold': False, 'tolerance': tolerance(), 'margin_px': MARGIN_PX,
            'margin_source': 'recorded truth-labelled projection residual <= 0.3 px + 1 px mask quantisation',
            'min_component_px': v1.MIN_POINTS, 'max_view_retries': MAX_VIEW_RETRIES,
            'max_view_retries_source': 'run_m2_pair.MAX_REAPPROACH', 'confirm_wait_s': CONFIRM_WAIT_S,
            'confirm_wait_source': 'blind_close.HOVER_CONFIRM_MAX_S', 'frame_settle_s': FRAME_SETTLE_S,
            'wait_restarts_on_own_command': True,
            'retry_relocalization': 'one-shot belief expansion (expansion resetting: particles displaced uniformly by +-(0.1 m, 0.1 m, '
                                    '0.2 rad), weights reset; Ueda 2004 / emcl2 defaults) then begin_relocalization (fix receipt voided); '
                                    'sigma is widened by the expansion, not a fresh localizer; no ground truth, no PF sigma input',
            'outcome': OUTCOME, 'failure': FAILURE, 'cause': CAUSE, 'band_half_len_m': BAND_HALF_LEN_M,
            'inputs': 'own RGB + measured camera model of the drive posture + static order sheet / beam spec',
            'not_inputs': 'ground truth, simulator state, PF sigma, partner pose, shared top camera',
            'references': list(REFERENCES)}
