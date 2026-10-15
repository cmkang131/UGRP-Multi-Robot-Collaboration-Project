"""Default-off natural-floor pose -> own occupancy -> frontier proposal.

No simulator, peer pose or cargo-world-position input. Authored static geometry
is accepted only by the explicit selfmap4 profile. This is a
mapping/navigation proposal seam, not an actuator or an ACT grasp replacement.
PR496 is imported verbatim; design/provenance: docs/self_map_integration.md.
"""
from dataclasses import dataclass
import copy
import json
import math
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_dilation, label

from harness.natural_floor_slam import NaturalFloorSLAM, Observation, compose, extract
from harness.self_odom_grid import OdomGrid, ray_cells, transform
from harness.own_map_navigation import ObservedGrid, NavigationOptions, frontier_candidates
from harness.self_pulse_odom import command_odometry

OPTION = 'natural_floor_frontier_v1'


@dataclass(frozen=True)
class Options:
    self_map_integration: str = 'off'
    resolution_m: float = .1
    motion_model: str = 's2_pulse_v122_rotL_v1'
    max_sigma_xy_m: float = .15
    max_sigma_yaw_rad: float = math.radians(5)
    stable_views: int = 5
    required_zones: tuple = ('B',)
    pose_rebuild: str = 'off'
    navigation_support: str = 'off'
    bootstrap: str = 'off'
    recovery_profile: str = 'off'

    def __post_init__(self):
        if self.self_map_integration not in ('off', OPTION):
            raise ValueError('UNKNOWN_SELF_MAP_INTEGRATION')
        if any(not math.isfinite(v) or v <= 0 for v in
               (self.resolution_m, self.max_sigma_xy_m, self.max_sigma_yaw_rad)):
            raise ValueError('INVALID_SELF_MAP_OPTIONS')
        if type(self.stable_views) is not int or self.stable_views < 2:
            raise ValueError('INVALID_STABLE_VIEWS')
        if not self.required_zones or any(z != 'B' for z in self.required_zones):
            raise ValueError('V1_SUPPORTS_B_ZONE_ONLY')
        if self.pose_rebuild not in ('off', 'refit_history_v1'):
            raise ValueError('UNKNOWN_POSE_REBUILD')
        if self.navigation_support not in ('off', 'current_footprint_v1'):
            raise ValueError('UNKNOWN_NAVIGATION_SUPPORT')
        if self.bootstrap not in ('off', 'command_prior_v1'):
            raise ValueError('UNKNOWN_SELF_MAP_BOOTSTRAP')
        if self.recovery_profile not in ('off', 'selfmap4_recovery_v1'):
            raise ValueError('UNKNOWN_SELF_MAP_RECOVERY')


def make_mapper(legacy=None, *, options=None, **kwargs):
    options = options or Options()
    if options.self_map_integration == 'off':
        return legacy  # no dependency construction, file IO, or changed legacy bytes
    return SelfMapIntegration(options=options, **kwargs)


class PoseGrid:
    """Reuse OdomGrid's inverse sensor model; expose it to the existing planner.

    Natural features localize; they are never obstacle endpoints. Floor-only rays
    clear to their measured endpoint. One update per frame/cell, hit wins.
    """
    def __init__(self, robot_id, resolution, registration=None):
        self.occupancy = OdomGrid(robot_id, resolution_m=resolution)
        self.navigation = ObservedGrid(robot_id, resolution)
        self.registration = registration

    def insert(self, *, frame_id, pose, camera, segments, floor_xy):
        grid, nav = self.occupancy, self.navigation
        if frame_id in nav.seen:
            raise ValueError('SELF_MAP_DUPLICATE_FRAME')
        pose, camera = np.asarray(pose, float), np.asarray(camera, float)
        segments = np.asarray(segments, float).reshape(-1, 2, 2)
        floor = np.asarray(floor_xy, float).reshape(-1, 2)
        if (pose.shape != (3,) or camera.shape != (2,) or
                not all(np.isfinite(a).all() for a in (pose, camera, segments, floor))):
            raise ValueError('SELF_MAP_FINITE_GEOMETRY_REQUIRED')
        if (len(segments) and np.linalg.norm(segments-camera, axis=2).max() > 4.) or (
                len(floor) and np.linalg.norm(floor-camera, axis=1).max() > 4.):
            raise ValueError('SELF_MAP_RAY_RANGE_EXCEEDED')
        origin = transform([camera], pose)[0]
        world_segments = [transform(s, pose) for s in segments]
        hits, wall_rays = set(), set()
        for a, b in world_segments:
            n = max(2, math.ceil(np.linalg.norm(b-a)/(grid.resolution_m/2))+1)
            for p in np.linspace(a, b, n):
                ray = ray_cells(origin, p, grid.resolution_m)
                wall_rays.update(ray)
                hits.add(ray[-1])
        free = set()
        for p in transform(floor, pose):
            free.update(ray_cells(origin, p, grid.resolution_m))
        before_cells = grid.cells.copy() if self.registration is not None else None
        grid.insert(origin, world_segments)
        for cell in free-wall_rays:
            grid.cells[cell] = max(grid.lo, min(grid.hi, grid.cells.get(cell, 0.)+grid.miss))
        free = (free | wall_rays)-hits
        rejected = set()
        if self.registration is not None and self.registration.map_from_own is not None:
            cells = sorted(set(grid.cells) | free | hits)
            rejected = {c for c, ok in zip(cells, self.registration.contains(cells, grid.resolution_m)) if not ok}
            for c in rejected:
                if c in before_cells:
                    grid.cells[c] = before_cells[c]
                else:
                    grid.cells.pop(c, None)
            free -= rejected
            hits -= rejected
        for cells, provenance in ((free, nav.floor_frames), (hits, nav.wall_frames)):
            for cell in cells:
                provenance.setdefault(cell, set()).add(frame_id)
        nav.odds = grid.cells.copy()
        nav.seen.add(frame_id)
        nav.view_poses[frame_id] = pose.copy()
        nav.revision += 1
        result = {'free_cells': len(free), 'hit_cells': len(hits)}
        if self.registration is not None:
            result['outside_cells_rejected'] = len(rejected)
        return result


def raw_frontier_count(grid, pose):
    """Unfiltered reachable free/unknown edges: no blacklist or min-size loophole."""
    state, lo = grid.dense(pose)
    x, y = np.asarray(grid.cell(pose[:2]))-lo
    components, _ = label(state == -1)
    if components[y, x] == 0:
        return None  # unobserved robot support is not exploration exhaustion
    component = components == components[y, x]
    return int(np.count_nonzero(component & binary_dilation(state == 0)))


class SelfMapIntegration:
    def __init__(self, robot_id, *, start_time=0., options=None, static_map=None):
        self.options = options or Options()
        if self.options.self_map_integration != OPTION:
            raise ValueError('EXPLICIT_SELF_MAP_INTEGRATION_REQUIRED')
        self.robot_id = robot_id
        self.recovery = self.options.recovery_profile != 'off'
        self.registration = None
        if self.recovery:
            from harness.selfmap4_geometry import StaticRegistration, PlaneFlow
            if static_map is None:
                raise ValueError('SELFMAP4_AUTHORED_STATIC_MAP_REQUIRED')
            self.registration = StaticRegistration(static_map)
            self.flow = PlaneFlow()
        elif static_map is not None:
            raise ValueError('STATIC_MAP_REQUIRES_SELFMAP4_PROFILE')
        self.slam = NaturalFloorSLAM(robot_id)
        if self.options.bootstrap != 'off':
            from harness.self_map_bootstrap import PriorBootstrapSLAM
            self.slam = PriorBootstrapSLAM(robot_id,
                max_sigma_xy_m=self.options.max_sigma_xy_m,
                max_sigma_yaw_rad=self.options.max_sigma_yaw_rad)
        self.odom = command_odometry(start_time, motion_model=self.options.motion_model)
        self.odom.step_callback = self._motion
        self.delta, self.Q = np.zeros(3), np.zeros((3, 3))
        self.servo = {}
        self.grid = PoseGrid(robot_id, self.options.resolution_m, self.registration)
        self.nav_options = NavigationOptions(exploration='own_frontier_v1',
                                             partial_planning='own_astar_v1')
        from harness.active_camera import goal_detector
        from harness.floor_goal_v3 import FloorGoalMemoryV3
        selected = Path(__file__).resolve().parents[1]/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json'
        self.zones = FloorGoalMemoryV3(robot_id, options=json.loads(selected.read_text())['selected']['options'])
        self.zones.detector = goal_detector()
        self.sectors, self.events = set(), []
        self.stable = 0
        self.last_states = None
        self.rebuild_required = False
        self.history, self.rebuilds = [], []
        self.last_rebuild_t = -math.inf
        self.prior_frames = set()
        self.rebuild_cause = None

    def planning_grid(self):
        """Current body support only; never changes occupancy/coverage evidence."""
        nav = self.grid.navigation
        if self.options.navigation_support == 'off':
            return nav
        from harness.public_navigation_unknown import footprint_cells
        result = copy.copy(nav)
        result.odds = nav.odds.copy()
        result.support = set(nav.support)
        for cell in footprint_cells(nav, self.slam.pose):
            if nav.state(cell) != 1:  # observed obstacles always win
                result.odds[cell] = -1.
                result.support.add(cell)
        return result

    def rebuild(self, t):
        """Refit each saved body observation, then atomically rasterize anew.

        No rigid shifting of raster cells or invented historical poses. A failed
        fit keeps the previous map quarantined and completion blocked. This is
        landmark-bank refitting, not a claim of global pose-graph optimization.
        """
        if self.recovery and (len(self.rebuilds) >= 2 or t-self.last_rebuild_t < 20.):
            return dict(t=float(t), committed=False, deferred=True,
                        reason='selfmap4_rebuild_budget_or_cooldown')
        if self.recovery and self.rebuild_cause == 'static_frame_correction':
            # The ORB bank has no independent static constraint on old poses.
            # Its self-fit cannot certify a static-frame correction. Preserve
            # the confirmed map and request more views instead of clearing the
            # quarantine with a circular re-fit.
            self.last_rebuild_t = float(t)
            receipt = dict(t=float(t), frames=len(self.history), refitted=0,
                unresolved=[r['observation'].frame_id for r in self.history],
                committed=False, reason='static_history_not_independently_refitted')
            self.rebuilds.append(receipt)
            return receipt
        replacement = PoseGrid(self.robot_id, self.options.resolution_m, self.registration)
        poses, unresolved = [], []
        for record in self.history:
            obs = record['observation']
            if record['anchor']:
                pose = record['pose'].copy()  # preserve the arbitrary start frame
            else:
                pose, _, detail = self.slam._fit(obs.points_body, obs.descriptors,
                                                record['pose'], obs.frame_id)
                if pose is not None:
                    cov = detail['covariance']
                    if (np.linalg.eigvalsh(cov[:2, :2]).max() > self.options.max_sigma_xy_m**2
                            or cov[2, 2] > self.options.max_sigma_yaw_rad**2):
                        pose = None
            if pose is None:
                unresolved.append(obs.frame_id)
                continue
            replacement.insert(frame_id=obs.frame_id, pose=pose, **record['rays'])
            poses.append(pose.copy())
        self.last_rebuild_t = float(t)
        receipt = dict(t=float(t), frames=len(self.history), refitted=len(poses),
                       unresolved=unresolved, committed=not unresolved)
        self.rebuilds.append(receipt)
        if unresolved:
            return receipt
        self.grid = replacement
        self.prior_frames.clear()
        for record, pose in zip(self.history, poses):
            record['pose'] = pose
        self.rebuild_required = False
        self.rebuild_cause = None
        self.stable, self.last_states = 0, None
        # Old zone coordinates/confirmation must not survive a map revision.
        self.zones.tracks.clear()
        self.sectors.clear()  # require a fresh admitted sweep after rebuilding
        return receipt

    def _motion(self, delta, variance):
        # Accumulate calibrated command increments in the previous RGB body frame.
        c, s = math.cos(self.delta[2]), math.sin(self.delta[2])
        R = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
        d = R@delta
        F = np.eye(3)
        F[:2, 2] = [-d[1], d[0]]
        self.Q = F@self.Q@F.T + R@np.diag(variance)@R.T
        self.delta = compose(self.delta, delta)

    def command(self, row):
        # Exact allowlist: actuator/GT/peer fields cannot silently enter the adapter.
        fields = {'initial_servo_command': {'pulses'}, 'arm': {'servo_id', 'pulse'},
                  'look': {'pan_pulse'}, 'mecanum': {'forward', 'left', 'turn', 'duration_s'},
                  'drive': {'forward', 'turn', 'duration_s'}, 'hold': set(), 'stop': set()}
        kind = row.get('kind')
        if kind not in fields or set(row) != fields[kind] | {'t', 'kind'}:
            raise ValueError('SELF_MAP_COMMAND_ALLOWLIST')
        self.odom.command(row)
        if kind == 'initial_servo_command':
            self.servo = {int(k): int(v) for k, v in row['pulses'].items()}
        elif kind == 'arm':
            self.servo[int(row['servo_id'])] = int(row['pulse'])
        elif kind == 'look':
            self.servo[6] = int(row['pan_pulse'])

    def receive(self, *, robot_id, t, frame_id, rgb, sha256=''):
        if robot_id != self.robot_id:
            raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        if (type(frame_id) is not int or not math.isfinite(t) or
                (self.events and (frame_id <= self.events[-1]['frame_id'] or t <= self.events[-1]['t']))):
            raise ValueError('CAUSAL_SELF_MAP_FRAMES_REQUIRED')
        image = np.asarray(rgb)
        if image.shape != (480, 640, 3) or image.dtype != np.uint8:
            raise ValueError('SELF_MAP_REQUIRES_640X480_RGB')
        self.odom.advance(t)
        held = self.servo.get(1, 2000) <= 1600  # conservative issued-command state
        settled = bool(self.servo) and t-self.odom.servo_since >= (.25 if not held else 2.25)
        if settled and not held:
            observation = extract(image, self.servo, frame_id=frame_id, t=t, sha256=sha256)
        else:
            observation = Observation(frame_id, t, np.empty((0, 2)), np.empty((0, 32), np.uint8), sha256)
        prior = compose(self.slam.pose, self.delta)
        wall_observation, flow_row, static_pose = None, None, None
        if self.recovery:
            self.delta, self.Q, flow_row = self.flow.step(image, self.servo, t,
                settled and not held, self.delta, self.Q)
            if settled and not held:
                from harness.selfmap4_geometry import observe
                wall_observation = observe(image, self.servo, self.registration.sensor)
            else:
                wall_observation = dict(camera=[0., 0.], segments=[], floor_xy=[], features=[])
            static_pose = self.registration.step(wall_observation, self.delta, self.servo,
                                                 t, compose(self.slam.pose, self.delta))
            prior = compose(self.slam.pose, self.delta)
        event = self.slam.step(observation, command_delta=self.delta, command_covariance=self.Q)
        if static_pose is not None:
            self.slam.pose, self.slam.covariance = static_pose
            event.update(status='visual_relocalized', reason='selfmap4_static_lines',
                         pose=self.slam.pose.tolist(), covariance=self.slam.covariance.tolist())
            self.slam.trajectory[-1].update(pose=event['pose'], covariance=event['covariance'],
                                            source=event['status'])
        self.delta, self.Q = np.zeros(3), np.zeros((3, 3))
        pose, cov = self.slam.pose, self.slam.covariance
        sigma_xy = math.sqrt(max(0., float(np.linalg.eigvalsh(cov[:2, :2]).max())))
        sigma_yaw = math.sqrt(max(0., float(cov[2, 2])))
        visual = event['status'] in ('visual_update', 'visual_relocalized')
        bootstrap = event['status'] == 'bootstrap' and event['landmark_count'] >= self.slam.options.min_inliers
        # PR496 does not supply revised historical poses. Do not silently smear or
        # rigidly shift old occupied cells after a discontinuous relocalization.
        innovation = np.linalg.norm(pose[:2]-prior[:2])
        yaw_jump = abs((pose[2]-prior[2]+math.pi) % (2*math.pi)-math.pi)
        if self.grid.navigation.seen and visual and (
                innovation > self.options.resolution_m or yaw_jump > self.options.max_sigma_yaw_rad):
            self.rebuild_required = True
            if self.recovery and self.rebuild_cause != 'static_frame_correction':
                self.rebuild_cause = 'static_frame_correction' if static_pose is not None else 'orb_pose_revision'
        if self.rebuild_required and self.options.pose_rebuild == 'refit_history_v1' and (
                visual and t-self.last_rebuild_t >= (20. if self.recovery else 5.)) and (
                not self.recovery or len(self.rebuilds) < 2):
            self.rebuild(t)
        reasons = []
        if held: reasons.append('commanded_grip_closed')
        if not settled: reasons.append('camera_unsettled')
        prior_insertion = self.options.bootstrap != 'off' and not (visual or bootstrap)
        if not (visual or bootstrap or prior_insertion): reasons.append('visual_pose_unavailable')
        if sigma_xy > self.options.max_sigma_xy_m or sigma_yaw > self.options.max_sigma_yaw_rad:
            reasons.append('pose_uncertain')
        if self.rebuild_required: reasons.append('pose_revision_requires_rebuild')
        counts, candidates = {}, []
        if not reasons:
            from harness.active_wall_vision import observe
            obs = wall_observation if self.recovery else observe(image, self.servo, body_settling=t-self.odom.servo_since)
            counts = self.grid.insert(frame_id=frame_id, pose=pose, camera=obs['camera'],
                                      segments=obs['segments'], floor_xy=obs['floor_xy'])
            if prior_insertion:
                self.prior_frames.add(frame_id)
            if self.options.pose_rebuild != 'off':
                self.history.append(dict(observation=observation, pose=pose.copy(),
                    anchor=not self.history and (bootstrap or prior_insertion),
                    rays=copy.deepcopy({k: obs[k] for k in ('camera', 'segments', 'floor_xy')})))
            self.zones.observe(image, robot_id=robot_id, frame_id=frame_id, t=t,
                               pose=pose, servo=self.servo, profile='camera_v3', settled=True)
            if counts['free_cells'] or counts['hit_cells']:
                self.sectors.add(int((pose[2] % (2*math.pi))/(math.pi/4)))
            candidates = frontier_candidates(self.planning_grid(), pose, self.nav_options)
        frontier_reason = None
        if self.recovery:
            # Diagnose actual geometry even when insertion is quarantined; do
            # not misreport "not evaluated" as an exhausted frontier set.
            from harness.own_map_navigation import Footprint, footprint_clearance, reachable
            grid = self.planning_grid()
            state, clear, _, lo = footprint_clearance(grid, Footprint(),
                self.nav_options.pose_margin_m, yaw=pose[2])
            start = np.asarray(grid.cell(pose[:2]))-lo
            reach = reachable(clear, tuple(start))
            geometric = candidates if not reasons else frontier_candidates(grid, pose, self.nav_options)
            frontier_reason = ('pose_or_revision_quarantined' if reasons else
                'start_footprint_blocked' if not clear[start[1], start[0]] else
                'no_observed_frontier' if not geometric else 'reachable')
        nav = self.grid.navigation
        states = {c: nav.state(c) for c in nav.odds}
        self.stable = self.stable+1 if not reasons and states and states == self.last_states else 0
        self.last_states = states
        edges = raw_frontier_count(self.planning_grid(), pose)
        zone_ok = any(track['confirmed_t'] is not None for track in self.zones.tracks)
        blockers = list(reasons)
        if prior_insertion or self.prior_frames: blockers.append('prior_map_unverified')
        if edges is None or edges: blockers.append('unresolved_observed_boundary')
        if self.stable < self.options.stable_views: blockers.append('map_not_stable')
        if len(self.sectors) < 8: blockers.append('incomplete_view_sweep')
        if not nav.wall_frames: blockers.append('no_observed_obstacles')
        if not zone_ok: blockers.append('required_zone_unconfirmed')
        complete = not blockers
        proposal = candidates[0] if candidates else None
        result = dict(t=float(t), frame_id=frame_id, sha256=sha256,
                      pose=pose.tolist(), covariance=cov.tolist(), pose_source=event['status'],
                      features=event['features'], sigma_xy_m=sigma_xy,
                      visual_reason=event['reason'], matches=event['matches'], inliers=event['inliers'],
                      rebuild_count=len(self.rebuilds), rebuild_required=self.rebuild_required,
                      map_updated=not reasons, insertion_blockers=reasons, **counts,
                      status='self_map_complete' if complete else 'frontier' if proposal else 'observation_required',
                      complete=complete, completion_blockers=blockers, raw_frontier_cells=edges,
                      selected_frontier=proposal, candidate_count=len(candidates),
                      path_m=[] if proposal is None else proposal['path_m'],
                      zone_confirmed=zone_ok, observed_cells=len(states),
                      stop_reason='self_map_complete' if complete else None)
        self.events.append(result)
        if self.options.bootstrap != 'off':
            result.update(mapping_pose_quality='command_prior' if prior_insertion else 'visual',
                          prior_map_frames=len(self.prior_frames),
                          landmark_count=event['landmark_count'],
                          prior_landmarks_added=event['prior_landmarks_added'],
                          sigma_yaw_rad=sigma_yaw)
        if self.recovery:
            result.update(recovery_profile=self.options.recovery_profile,
                plane_flow=flow_row, static_registration=self.registration.last,
                rebuild_commits=sum(r['committed'] for r in self.rebuilds),
                rebuild_budget_remaining=max(0, 2-len(self.rebuilds)),
                frontier_reason=frontier_reason, geometric_candidate_count=len(geometric),
                reachable_footprint_cells=int(reach.sum()),
                recovery_candidate=dict(skill='relocalize',
                    pans=self.registration.look_pans(pose)) if reasons or not candidates else None)
        return result

    def snapshot(self):
        nav = self.grid.navigation
        zones = self.zones.snapshot()
        zones['coordinate_frame'] = self.robot_id+'/natural_floor_origin'
        result = dict(schema='ugrp.self_map_integration.v1', robot_id=self.robot_id,
                    coordinate_frame=self.robot_id+'/natural_floor_origin', mode='self_only',
                    resolution_m=nav.resolution, support_cells_counted=False,
                    cells=[[int(x), int(y), float(v)] for (x, y), v in sorted(nav.odds.items())],
                    floor_cells=[[int(v) for v in c] for c in sorted(nav.floor_frames)],
                    wall_cells=[[int(v) for v in c] for c in sorted(nav.wall_frames)],
                    rebuild_required=self.rebuild_required, rebuilds=self.rebuilds, zones=zones,
                    slam=self.slam.snapshot(), latest=self.events[-1] if self.events else None)
        if self.options.bootstrap != 'off':
            result.update(bootstrap=self.options.bootstrap, prior_frame_ids=sorted(self.prior_frames),
                prior_cells=[[int(v) for v in c] for c in sorted(set(nav.floor_frames) | set(nav.wall_frames))
                    if (nav.floor_frames.get(c, set()) | nav.wall_frames.get(c, set())) & self.prior_frames],
                uncertainty_note='command prior contributions; not independent visual confirmation')
        if self.recovery:
            result.update(recovery_profile=self.options.recovery_profile,
                static_registration=self.registration.last,
                map_from_own=None if self.registration.map_from_own is None else self.registration.map_from_own.tolist())
        return result
