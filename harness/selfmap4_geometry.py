"""Own RGB line contacts, plane flow and authored-map registration adapters.

No start pose, live state, evaluator or top-camera input. The legacy detector,
calibration, LK/SE(2) implementation and AMCL sensor models remain unchanged.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np

from harness.active_camera import transform as camera_transform
from harness.active_wall_vision import modules
from harness.natural_floor_slam import compose, transform

PROFILE = 'selfmap4_recovery_v1'
MAP_PATH = Path(__file__).resolve().parents[1]/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json'


def static_input(path=MAP_PATH):
    """Only authored geometry crosses the boundary; discard camera/task metadata."""
    raw = Path(path).read_bytes()
    source = json.loads(raw)
    keys = ('map_id', 'version', 'frame', 'bounds_m', 'obstacles', 'regions', 'passages')
    return {k: copy.deepcopy(source[k]) for k in keys}, hashlib.sha256(raw).hexdigest()


def robust_segment(points):
    """Consensus + TLS, not the first/last two noisy column intersections.

    2.5 cm is the existing metric SE(2) residual gate. Require >=60% support
    and >=6 columns; endpoints are restricted to actual inlier support.
    """
    points = np.asarray(points, float).reshape(-1, 2)
    if len(points) < 6:
        return None
    best = None
    indices = np.unique(np.linspace(0, len(points)-1, min(12, len(points))).astype(int))
    for i in indices:
        for j in indices:
            d = points[j]-points[i]
            if np.linalg.norm(d) < .12:
                continue
            n = np.array([-d[1], d[0]])/np.linalg.norm(d)
            keep = abs((points-points[i])@n) <= .025
            if best is None or keep.sum() > best.sum():
                best = keep
    if best is None or best.sum() < max(6, math.ceil(.6*len(points))):
        return None
    p = points[best]; mid = p.mean(0)
    _, _, vt = np.linalg.svd(p-mid, full_matrices=False)
    tangent = vt[0]; along = (p-mid)@tangent
    ends = mid+np.array([along.min(), along.max()])[:, None]*tangent
    if np.linalg.norm(ends[1]-ends[0]) < .12:
        return None
    return ends


def observe(rgb, servo, sensor, *, reloc9_wall_height_guard_v1=False):
    """Fit wall-floor lines in metric ground plane; reuse zone/door observations."""
    mp, hfw, _ = modules()
    origin, rotation = camera_transform(servo)
    cm = mp.ColumnModel(tuple(sorted(servo.items())), 0., mp.column_positions(96, 2),
                        camera_transform=(origin, rotation))
    und = mp.undistort(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    params = dict(floor_patch_max_m=.81, run_step_window=3, top_edge_px=4)
    scan = hfw.detect(und, cm, params=params, loaded=False)
    from harness.reloc9_wall_guard import validate, supported_columns
    validate(reloc9_wall_height_guard_v1)
    wall_audit = None
    if reloc9_wall_height_guard_v1:
        keep, wall_audit = supported_columns(und, cm, scan['vb'][:, 0], scan['vt'][:, 0])
        scan = copy.deepcopy(scan)
        for value in scan.values():
            if isinstance(value, np.ndarray) and value.shape[:1] == keep.shape:
                value[~keep] = np.nan
    contacts = cm.floor_point(cm.t_of_row(scan['vb'][:, 0]))
    segments, accepted_columns = [], []
    for line in hfw.link_segments(scan, params):
        ix = np.arange(line['col_first'], line['col_last']+1)
        p = contacts[ix]
        from harness.wall_projection_guard import floor_depths
        # Keep the legacy whole-face range/cheirality contract. A discarded
        # long/behind-camera face cannot become a new wall by trimming it.
        ends = p[[0, -1]]
        if (not np.isfinite(ends).all() or np.linalg.norm(ends-origin[:2], axis=1).max() >= 4.
                or not floor_depths(ends, origin, rotation)[2].all()):
            continue
        valid = np.isfinite(p).all(1) & (np.linalg.norm(p-origin[:2], axis=1) < 4.)
        fitted = robust_segment(p[valid])
        if (fitted is not None and np.linalg.norm(fitted-origin[:2], axis=1).max() < 4.
                and floor_depths(fitted, origin, rotation)[2].all()):
            segments.append(fitted.tolist())
            # Do not clear beneath rejected/outlier boundary columns.
            d = fitted[1]-fitted[0]; n = np.array([-d[1], d[0]])/np.linalg.norm(d)
            accepted_columns.extend(ix[valid & (abs((p-fitted[0])@n) <= .025)].tolist())
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    pixels = []
    for j in accepted_columns:
        u = int(cm.columns[j]); v0 = int(math.ceil(scan['vb'][j, 0]))+3
        for v in range(max(0, v0), mp.HEIGHT-4, 12):
            if hsv[v, u, 1] <= 128 and hsv[v, u, 2] >= 30:
                pixels.append([u, v])
    from harness.own_map_amcl_vendor.landmarks import ground
    floor, valid, _ = ground(cm, pixels, mp.K_INV)
    floor = floor[valid & (np.linalg.norm(floor-origin[:2], axis=1) < 4.)]
    columns = np.flatnonzero(np.isfinite(scan['vb'][:, 0]))
    features = sensor.measure(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), servo,
        dict(columns=columns, uv=np.c_[cm.columns[columns], scan['vb'][columns, 0]]))
    return dict(camera=origin[:2].tolist(), segments=segments, floor_xy=floor.tolist(),
                features=features, raw_columns=len(columns), fitted_columns=len(accepted_columns),
                **({'wall_height_guard': wall_audit} if wall_audit is not None else {}))


class PlaneFlow:
    """Existing floor LK + homography gate, including checker intersections.

    Repeated grid cells have no absolute IDs. Only short, same-servo consecutive
    pairs are tracked; missing images never become zero-motion measurements.
    """
    def __init__(self):
        self.previous = None

    def step(self, rgb, servo, t, settled, delta, covariance):
        from harness.e2e_rgb_vo import ground_pair, fuse, PARAMS
        previous, self.previous = self.previous, (rgb.copy(), dict(servo), t, settled)
        row = dict(status='unavailable_pair')
        if settled and previous is not None:
            before, old_servo, old_t, old_settled = previous
            if old_settled and old_servo == servo and 0 < t-old_t <= PARAMS['max_pair_gap_s']:
                row = ground_pair(before, rgb, servo, vo_floor_mask='homography_v1')
                if row['status'] == 'measured':
                    delta, covariance, nis, source = fuse(delta, covariance,
                        row['delta'], row['covariance'])
                    row.update(nis=nis, fusion=source)
        return delta, covariance, row


def inverse(pose):
    x, y, a = pose; c, s = math.cos(a), math.sin(a)
    return np.array([-c*x-s*y, s*x-c*y, -a])


class StaticRegistration:
    """Use PR507's unchanged global AMCL adapter, without any start hint.

    Require a resolved full posterior, a dominant cluster and colored geometry.
    Unresolved hypotheses can propose look directions but cannot clip/clear maps
    or lower pose covariance. Registration has to survive three distinct views.
    """
    def __init__(self, static, *, multiframe_registration='off', correction_safety='off', active_relocalization='off', reloc10_registration_v1=False, reloc11_wall_field_v1=False, reloc12_raw_cov_gate_v1=False, reloc12_ransac_hypotheses_v1=False, reloc13_execution_cov_v1=False, reloc13_execution_frame_v1=False, reloc13_live_r7_v1=False, reloc14_continuous_tracking_v1=False):
        from harness.e2e_static_rgb_localizer import create
        from harness.self_map_landmark_sensor import Sensor
        if set(static) != {'map_id', 'version', 'frame', 'bounds_m', 'obstacles', 'regions', 'passages'}:
            raise ValueError('SELFMAP4_STATIC_GEOMETRY_ALLOWLIST')
        if type(reloc11_wall_field_v1) is not bool:
            raise ValueError('reloc11 wall field must be bool')
        for value in (reloc12_raw_cov_gate_v1, reloc12_ransac_hypotheses_v1):
            if type(value) is not bool or (value and multiframe_registration == 'off'):
                raise ValueError('reloc12 requires multiframe registration and bool toggles')
        if type(reloc13_execution_cov_v1) is not bool or (reloc13_execution_cov_v1 and not reloc12_raw_cov_gate_v1):
            raise ValueError('reloc13 execution covariance requires raw gate')
        if type(reloc13_execution_frame_v1) is not bool or (reloc13_execution_frame_v1 and not reloc13_execution_cov_v1):
            raise ValueError('reloc13 execution frame requires execution covariance')
        if type(reloc13_live_r7_v1) is not bool or (reloc13_live_r7_v1 and not reloc13_execution_frame_v1):
            raise ValueError('live R7 requires the execution frame')
        if type(reloc14_continuous_tracking_v1) is not bool or (reloc14_continuous_tracking_v1 and not reloc13_live_r7_v1):
            raise ValueError("continuous tracking requires live R7")
        self.continuous_tracking = reloc14_continuous_tracking_v1
        self.tracking_state = "GLOBAL"
        self.last_tracking_failure = None
        self.live_r7 = reloc13_live_r7_v1
        self.execution_r7_admitted = False
        self.execution_frame = reloc13_execution_frame_v1
        self.command_registration_anchor = None
        self.execution_handoff = False
        self.execution_cov = reloc13_execution_cov_v1
        self.raw_cov_gate = reloc12_raw_cov_gate_v1
        self.ransac_hypotheses = reloc12_ransac_hypotheses_v1
        self.hypothesis_cache = None
        self.wall_field = reloc11_wall_field_v1
        self.pf = create(static, option='static_walls_v1' if self.wall_field else 'static_landmarks_v1', seed=5064)
        if self.wall_field:
            # The AMCL distance field uses observed wall-floor endpoints only.
            # Keep colored geometry for the unchanged independent admission gate;
            # do not multiply a sparse/possibly misleading color likelihood into PF.
            from harness.own_map_amcl_vendor.landmarks import MapFeatures
            self.pf.landmark_map = MapFeatures(static)
        self.sensor = Sensor(self.pf.landmark_map.hues)
        self.static = static
        self.map_from_own = None
        self.confirmations = []
        self.last = {}
        self.multiframe_registration = multiframe_registration
        self.evidence = None
        self.confirmation_views = set()
        self.correction_safety = correction_safety
        self.active_relocalization = active_relocalization
        self.active_hypotheses = []
        self.command_anchor = None
        self.reloc10_registration = reloc10_registration_v1
        if multiframe_registration != 'off':
            from harness.selfmap5_registration import OPTION, RecoveryPolicy, MultiFrameEvidence
            if multiframe_registration != OPTION:
                raise ValueError('UNKNOWN_MULTIFRAME_REGISTRATION')
            self.pf.policy = RecoveryPolicy()
            self.evidence = MultiFrameEvidence()
            self.evidence.trace_edge_ids = correction_safety != 'off'
            self.evidence.rolling = reloc10_registration_v1

    def begin_sweep(self, t):
        if self.evidence is not None:
            self.evidence.begin(t)
            self.confirmations.clear(); self.confirmation_views.clear()

    def end_sweep(self):
        if self.evidence is not None:
            self.evidence.end()

    def geometry_supported(self, observation, pose):
        """PF confidence is not evidence of a correct mode in a repeated room.

        Validate finite line extents, hue, directed normal and independent axes
        against this view. Parallel walls alone cannot resolve all of SE(2).
        """
        normals, residuals = [], []
        for f in observation['features']:
            if f['kind'] != 'floor_line':
                continue
            ends = transform(f['endpoints'], pose)
            angle = math.atan2(f['normal'][1], f['normal'][0])+pose[2]
            candidates = []
            for e in self.pf.landmark_map.edges:
                hd = abs(e['hue']-f['hue']); hd = min(hd, 180-hd)
                da = abs(math.atan2(math.sin(angle-math.atan2(e['normal'][1], e['normal'][0])),
                                   math.cos(angle-math.atan2(e['normal'][1], e['normal'][0]))))
                if hd > 12 or da > math.radians(5):
                    continue
                vec = e['b']-e['a']
                along = np.clip((ends-e['a'])@vec/(vec@vec), 0, 1)
                residual = float(np.linalg.norm(ends-e['a']-along[:, None]*vec, axis=1).max())
                candidates.append((residual, e['normal']))
            if candidates:
                error, normal = min(candidates, key=lambda q:q[0])
                if error <= .05:
                    normals.append(normal); residuals.append(error)
        rank = len(normals) >= 2 and np.linalg.eigvalsh(np.asarray(normals).T@np.asarray(normals)).min() >= .5
        return bool(rank), dict(supported_floor_lines=len(normals),
            independent_line_axes=bool(rank), max_line_error_m=max(residuals, default=None))

    def step(self, observation, delta, servo, t, own_pose, *, execution_pose=None):
        from harness.self_map_csm import sample_segments
        row = self.pf.step(t=t, points=sample_segments(observation['segments']),
                           delta=delta, servo=servo, features=observation['features'])
        if self.continuous_tracking and self.map_from_own is not None and self.tracking_state == 'TRACKING':
            from harness.reloc14_tracking import track
            result, handled = track(self, row, observation, own_pose, t)
            if handled:
                return result
        cov = np.asarray(row['covariance'])
        if self.evidence is not None:
            from harness.selfmap5_registration import calibrated_covariance
            cov = calibrated_covariance(cov)
            self.evidence.add(observation, own_pose, t)
            supported, geometry = self.evidence.supported(self.pf.landmark_map.edges,
                row['pose'], own_pose, cov)
            # Stale cached lines cannot count as a fresh confirming observation.
            supported = supported and any(f['kind'] == 'floor_line' for f in observation['features'])
        else:
            supported, geometry = self.geometry_supported(observation, row['pose'])
        gate_cov = np.asarray(row['covariance']) if self.raw_cov_gate else cov
        reliable = (row['updated'] and row['resolved'] and row['cluster']['mass'] >= .9
                    and np.linalg.eigvalsh(gate_cov[:2, :2]).max() <= .15**2
                    and gate_cov[2, 2] <= math.radians(5)**2
                    and supported)
        if self.correction_safety != 'off':
            from harness.selfmap6_safety import OPTION, registration_hypotheses
            if self.correction_safety != OPTION or self.evidence is None:
                raise ValueError('INVALID_SELFMAP6_REGISTRATION')
            if self.ransac_hypotheses:
                from harness.reloc12_registration import ransac_hypotheses as registration_hypotheses
            def search_now():
                if self.ransac_hypotheses and not row['updated'] and self.hypothesis_cache is not None:
                    from harness.active_relocalization import relative_candidates
                    saved, previous_own = self.hypothesis_cache
                    return dict(saved, candidates=[p.tolist() for p in relative_candidates(
                        saved['candidates'], previous_own, own_pose)] if saved['candidates'] else [], refresh='command_propagation_between_PF_updates')
                found = registration_hypotheses(self.evidence, self.pf.landmark_map.edges, own_pose, cov)
                if self.ransac_hypotheses:
                    found['refresh'] = 'fresh_PF_update'
                    self.hypothesis_cache = (dict(found), np.asarray(own_pose).copy())
                return found
            search = None
            ambiguity = dict(candidate_count=0, unique=False, candidates=[], evaluated=False)
            if reliable:
                ambiguity = search_now()
                search = ambiguity
                ambiguity['evaluated'] = True
                unique_pose = np.asarray(ambiguity['candidates'][0]) if ambiguity['unique'] else None
                reliable = (unique_pose is not None and np.linalg.norm(unique_pose[:2]-np.asarray(row['pose'])[:2]) <= .15
                    and abs(math.atan2(math.sin(unique_pose[2]-row['pose'][2]), math.cos(unique_pose[2]-row['pose'][2]))) <= math.radians(10))
            geometry['ambiguity'] = ambiguity
            if self.active_relocalization != 'off':
                from harness.active_relocalization import conditioned_modes, relative_candidates
                search = search if search is not None else search_now()
                candidates = search['candidates'] or [row['pose']]
                if self.command_anchor is not None:
                    previous_world, previous_own = self.command_anchor
                    predicted = relative_candidates([previous_world], previous_own, own_pose)[0]
                    modes = conditioned_modes(candidates, np.zeros(len(candidates)), predicted, cov,
                        complete=search['search_complete'])
                    self.active_hypotheses = modes['hypotheses'] or [dict(pose=p) for p in candidates]
                    geometry['reloc8_search'] = modes
                else:
                    self.active_hypotheses = [dict(pose=p) for p in candidates]
                if reliable and self.map_from_own is not None:
                    self.command_anchor = (np.asarray(row['pose']).copy(), np.asarray(own_pose).copy())
        view = (tuple(sorted(servo.items())), int(math.floor(own_pose[2]/math.radians(10))))
        if reliable and (self.evidence is None or view not in self.confirmation_views):
            anchor = compose(row['pose'], inverse(own_pose))
            if self.confirmations and (np.linalg.norm(anchor[:2]-self.confirmations[-1][:2]) > .1
                    or abs(math.atan2(math.sin(anchor[2]-self.confirmations[-1][2]),
                                      math.cos(anchor[2]-self.confirmations[-1][2]))) > math.radians(5)):
                self.confirmations.clear(); self.confirmation_views.clear()
            self.confirmations.append(anchor)
            self.confirmation_views.add(view)
            if len(self.confirmations) >= 3 and self.map_from_own is None:
                self.command_registration_anchor = anchor.copy()
                # R1 GCP: command odometry and the live ORB frame differed by
                # 11-13deg. Use commands to test R7 anchor stability, but map
                # the *execution* frame to world at registration. No truth and
                # no correction-gate bypass; the first local fix has zero jump.
                self.map_from_own = (compose(row['pose'], inverse(execution_pose))
                    if self.execution_frame and execution_pose is not None else anchor.copy())
        elif row['updated'] and not reliable:
            self.confirmations.clear(); self.confirmation_views.clear()
        if self.live_r7 and row['updated'] and self.map_from_own is not None:
            # R2: sigma remained small after R7 became unresolved; execution
            # drift reached .762m. Reuse the existing R7 geometry/agreement/
            # three-view rule after registration too; no new numeric cutoff.
            self.execution_r7_admitted = bool(reliable and len(self.confirmations) >= 3)
        rejection = []
        if self.reloc10_registration:
            checks = dict(no_sensor_update=not row['updated'], pf_unresolved=not row['resolved'],
                cluster_mass=row['cluster']['mass'] < .9,
                xy_covariance=np.linalg.eigvalsh(gate_cov[:2, :2]).max() > .15**2,
                yaw_covariance=gate_cov[2, 2] > math.radians(5)**2,
                geometry=not supported,
                ambiguity_pending_upstream=self.correction_safety != 'off' and not geometry.get('ambiguity', {}).get('evaluated', False),
                geometric_ambiguity=geometry.get('ambiguity', {}).get('evaluated', False) and not geometry['ambiguity']['unique'])
            rejection = [k for k, failed in checks.items() if failed]
        self.last = dict(updated=row['updated'], resolved=bool(reliable),
            confirmations=len(self.confirmations), registered=self.map_from_own is not None,
            execution_r7_admitted=self.execution_r7_admitted if self.live_r7 else None,
            world_pose=row['pose'], covariance=row['covariance'], cluster=row['cluster'],
            feature_count=len(observation['features']), geometry=geometry)
        if self.reloc10_registration:
            from collections import Counter
            self.last['reloc10_diagnostics'] = dict(rejection_reasons=rejection,
                evidence_reference='issued_command_odometry',
                feature_kinds=dict(Counter(f['kind'] for f in observation['features'])),
                **({'scene_floor_mask':self.sensor.last_scene_floor_mask} if getattr(self.sensor,'last_scene_floor_mask',{}).get('option','off')!='off' else {}),
                wall_segments=len(observation['segments']), raw_columns=observation.get('raw_columns'),
                fitted_columns=observation.get('fitted_columns'),
                wall_guard=observation.get('wall_height_guard'), sensor_reason=row.get('reason'))
        if self.evidence is not None:
            self.last.update(pf_resolved=bool(row['resolved']), raw_covariance=row['covariance'],
                covariance=cov.tolist(), pf_sensor=row['sensor'],
                multiframe_registration=self.multiframe_registration)
        if self.raw_cov_gate or self.ransac_hypotheses:
            from harness.reloc12_registration import replay_packet
            self.last['reloc12'] = dict(raw_cov_gate=self.raw_cov_gate,
                ransac_hypotheses=self.ransac_hypotheses,
                reliable_gate_covariance=gate_cov.tolist(),
                residual_covariance=cov.tolist(),
                registered_world_pose=None if self.map_from_own is None else compose(
                    self.command_registration_anchor if self.execution_frame else self.map_from_own, own_pose).tolist(),
                map_from_execution=None if self.map_from_own is None else self.map_from_own.tolist(),
                execution_frame_v1=self.execution_frame,
                replay=replay_packet(self.evidence, own_pose, observation, t),
                rejection=dict(category=rejection[0] if rejection else 'accepted',
                    blocked_object='static_registration_evidence', minimum_gap_m=None,
                    gap_status='not_applicable_localization_gate'))
        if self.wall_field:
            self.last['reloc11_wall_field'] = dict(model='AMCL_likelihood_field',
                pf_particles=self.pf.n, sensor_landmarks='off',
                wall_points=len(sample_segments(observation['segments'])),
                geometry_and_covariance_gates='unchanged', input='own_RGB_wall_floor_segments')
        if self.continuous_tracking:
            if self.execution_r7_admitted:
                self.tracking_state = 'TRACKING'
            self.last['tracking'] = dict(state=self.tracking_state,measurement=bool(row['updated']),
                global_confirmations_required=True,last_failure=self.last_tracking_failure)
        if reliable and self.map_from_own is not None and (not self.live_r7 or self.execution_r7_admitted):
            local = compose(inverse(self.map_from_own), row['pose'])
            c, s = math.cos(self.map_from_own[2]), math.sin(self.map_from_own[2])
            R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
            # reloc13: PF raw covariance is an execution estimate, not the x36
            # residual search envelope. R7 still admits the pose; sigma is no
            # accuracy classifier (const-audit: Spearman -0.04, reloc12 446/446 blocked).
            execution_cov = np.asarray(row['covariance']) if self.execution_cov else cov
            self.last['execution_covariance'] = (R@execution_cov@R.T).tolist()
            return local, R@execution_cov@R.T
        return None

    def look_pans(self, pose):
        """Aim at authored corners, door jambs and colored region boundaries.

        An unregistered PF hypothesis is explicitly a search hypothesis. The
        remaining full sweep still runs; these bearings do not authorize drive.
        """
        from harness.active_camera import SEARCH, transform as camera
        if not self.last:
            return [1500, 1000, 2000, 1500]
        world = (compose(self.map_from_own, pose) if self.map_from_own is not None
                 else np.asarray(self.last['world_pose']))
        points = []
        for o in self.static['obstacles']:
            x, y = o['center_m']; a, b = o['half_extents_m']
            points.extend([[x-a, y-b], [x+a, y+b]])
        points.extend(p['center_m'] for p in self.static['passages'])
        points.extend(r['center_m'] for r in self.static['regions'].values())
        ranked = sorted(points, key=lambda p: np.linalg.norm(np.asarray(p)-world[:2]))
        pans = []
        for point in ranked:
            d = np.asarray(point)-world[:2]
            if not .2 < np.linalg.norm(d) < 4.:
                continue
            bearing = math.atan2(d[1], d[0])-world[2]
            def error(p):
                rot = camera({**SEARCH, 6:p})[1]
                yaw = math.atan2(rot[1, 2], rot[0, 2])
                return abs(math.atan2(math.sin(bearing-yaw), math.cos(bearing-yaw)))
            pan = min(range(1000, 2001, 125), key=error)
            if pan not in pans:
                pans.append(pan)
            if len(pans) == 3:
                break
        return list(dict.fromkeys(pans+[1000, 2000]))+[1500]

    def contains(self, cells, resolution):
        if self.map_from_own is None:
            return np.ones(len(cells), bool)
        points = transform((np.asarray(cells)+.5)*resolution, self.map_from_own)
        a, b, c, d = self.static['bounds_m']
        return (points[:, 0] >= a) & (points[:, 0] < b) & (points[:, 1] >= c) & (points[:, 1] < d)
