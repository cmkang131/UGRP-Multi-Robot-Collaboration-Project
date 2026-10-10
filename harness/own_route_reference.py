"""Default-off egomap66 reference adapters, using only the robot's own memory.

RPP circle/segment lookahead and bounded path pruning, VT&R segment projection,
vendored NavFn on observed free space, and a stateful visual verification stage.
Sources, fixed values and monocular/finite-pulse adaptations: egomap66 prereg.
The frozen controller and its checkpoint admission hashes remain unchanged.
"""
import copy
import math
from dataclasses import dataclass, asdict
from types import MethodType
import numpy as np
from harness.goal_route_continuous import GoalRoute
from harness.active_wall_mapping import compose, inverse
from harness.self_odom_grid import transform
from harness.public_navigation_unknown import from_observed_grid
from harness.public_navigation.costmap import Costmap
from harness.public_navigation.native import PublicCore
from harness.own_traversal_graph import TraversalGraph
from harness.own_traversal_reconnection import PARTIAL_ANGLE, PARTIAL_TIMEOUT

LOOKAHEAD = .6  # Nav2 Jazzy RPP default lookahead_dist, not fitted to these seeds.


@dataclass(frozen=True)
class Options:
    progress_lookahead: bool = False
    return_local_vtr: bool = False
    return_own_free_astar: bool = False
    arrival_verify_fsm: bool = False

    def __post_init__(self):
        if any(type(x) is not bool for x in asdict(self).values()):
            raise ValueError('BOOLEAN_OPTIONS_REQUIRED')
        if self.return_local_vtr and self.return_own_free_astar:
            raise ValueError('DISTINCT_RETURN_COMPARATORS')


def project(point, a, b):
    d = np.asarray(b)-a
    u = float(np.dot(np.asarray(point)-a, d)/np.dot(d, d)) if np.dot(d, d)>1e-12 else 1.
    return u, np.asarray(a)+np.clip(u, 0., 1.)*d


def carrot(path, xy, radius=LOOKAHEAD):
    """RPP first outside point + circle/segment intersection, no extrapolation."""
    points = np.asarray(path, float).reshape(-1, 2)
    if not len(points):
        return None
    for i, p in enumerate(points):
        if np.linalg.norm(p-xy) < radius:
            continue
        if not i:
            return p.copy()
        a = points[i-1]-xy
        d = p-points[i-1]
        aa, bb, cc = float(d@d), float(2*a@d), float(a@a-radius**2)
        if aa < 1e-12:
            return p.copy()
        u = (-bb+math.sqrt(max(0., bb*bb-4*aa*cc)))/(2*aa)
        return points[i-1]+np.clip(u, 0., 1.)*d
    return points[-1].copy()


class Progress:
    """Monotonic adjacent-segment projection; never nearest-over-whole-route."""
    def __init__(self, points):
        self.points = np.asarray(points, float).reshape(-1, 2)
        self.index = 0
        self.fraction = 0.
        self.lengths = np.linalg.norm(np.diff(self.points, axis=0), axis=1)
        self.distance = 0.

    def update(self, xy):
        while self.index < len(self.points)-1:
            i = self.index
            u, p = project(xy, self.points[i], self.points[i+1])
            if u >= 1. or math.dist(xy, self.points[i+1]) <= .05:
                self.index += 1
                self.fraction = 0.
                continue
            self.fraction = max(self.fraction, float(np.clip(u, 0., 1.)))
            break
        self.distance = float(self.lengths[:self.index].sum())
        if self.index < len(self.lengths):
            self.distance += self.fraction*self.lengths[self.index]
        if self.index >= len(self.points)-1:
            return self.points[-1:].copy()
        p = self.points[self.index]+self.fraction*(self.points[self.index+1]-self.points[self.index])
        return np.vstack([p, self.points[self.index+1:]])

    @property
    def ratio(self):
        return min(1., self.distance/max(float(self.lengths.sum()), 1e-12))


def free_plan(core, costmap, pose, goal):
    """Existing NavFn Dijkstra search (A* family comparator), allow_unknown=false.

    No invented free corridor or static goal. Only the start planner cell is
    cleared as NavfnPlanner::clearRobotCell; sensor evidence is never changed.
    """
    start, end = costmap.world_to_map(pose[:2]), costmap.world_to_map(goal)
    if start is None or end is None or costmap.raw[end[1], end[0]] != 0:
        return []
    costs = costmap.costs.copy()
    costs[costmap.raw == 255] = 254
    costs[start[1], start[0]] = 0
    if start == end:
        return [list(pose[:2]), list(goal)]
    cells = core.plan(costs, start, end)
    if not len(cells):
        return []
    return np.vstack([pose[:2], costmap.map_to_world(cells), goal]).tolist()


class ReferenceRoute(GoalRoute):
    def route_progress(self, pose):
        if self._reference_route is not self.route:
            self._reference_route = self.route
            self._progress = Progress([r['pose'][:2] for r in self.route['samples']])
        tail = self._progress.update(pose[:2])
        self.cursor = self._progress.index
        if len(tail) == 1 and math.dist(pose[:2], tail[-1]) <= .20:
            self.cursor = len(self.route['samples'])
        self._return_path = tail.tolist()
        return tail

    def _return_target(self, pose):
        self._reference_executed['return_target'] = True
        o = self.reference_options
        if o.return_own_free_astar:
            e = self.explorer
            observed = from_observed_grid(e.grid, e.pose, e.latest, set())
            cm = (Costmap(observed.raw.copy(), observed.origin, observed.resolution)
                  if self._traversed is None else self._traversed.overlay(observed, e.map_to_odom))
            self._free_costmap = cm if self._traversed is not None else None
            end = self.graph.nodes[0]['pose'][:2]
            target = compose(e.map_to_odom, [*end, 0.])[:2]
            path = free_plan(self._free_core, cm, e.pose, target)
            self._return_path = transform(path, inverse(e.map_to_odom)).tolist() if path else []
            self._free_status = 'observed_free_path' if path else 'no_observed_free_path'
            self._free_remaining = sum(math.dist(a,b) for a,b in zip(path,path[1:])) if path else None
            if self._free_initial is None and self._free_remaining is not None:
                self._free_initial = self._free_remaining
            self.cursor = len(self.route['samples']) if path and math.dist(pose[:2], end)<=.20 else 0
            return carrot(self._return_path, pose[:2]) if path else pose[:2]
        if o.progress_lookahead or o.return_local_vtr:
            return carrot(self.route_progress(pose), pose[:2])
        return super()._return_target(pose)

    def _localize(self, sample, t):
        self._reference_executed['localize'] = True
        if not self.reference_options.return_local_vtr or self.stage != 'return' or not self.route:
            value = super()._localize(sample, t)
            if self._traversed is not None:
                self._traversed.add(sample['pose'], sample['frame_id'])
            return value
        self.route_progress(sample['pose'])
        if t-self.last_localize < 10.:
            return
        self.last_localize = t
        # Temporal trunk nearest the current progress frame, not a spatially
        # nearby future branch at a crossing. Existing CSM gates are unchanged.
        frame = self.route['samples'][min(self.cursor, len(self.route['samples'])-1)]['frame_id']
        ids = self.route['nodes']
        k = min(range(len(ids)), key=lambda j:abs(self.graph.nodes[ids[j]]['frame_id']-frame))
        candidates = ids[max(0,k-2):k+3]
        trials = [TraversalGraph.match(self.graph, sample, i) for i in candidates]
        accepted = next((r for r in trials if r['status']=='accepted'), None)
        event = dict(accepted or trials[0], trigger='repeat_local_segment', candidate_attempts=trials)
        self.matches.append(event)
        self._repeat_blocked = accepted is None
        if accepted is None:
            self._repeat_reason = event.get('reason', 'rejected')
            return
        self._repeat_reason = 'accepted'
        g = self.explorer.memory.self_map
        delta = compose(accepted['pose'], inverse(sample['pose']))
        g.poses = np.array([compose(delta, p) for p in g.poses])
        c, s = math.cos(delta[2]), math.sin(delta[2])
        R = np.array([[c,-s,0],[s,c,0],[0,0,1]])
        g.pending_cov = R@g.pending_cov@R.T
        self.offsets.append(dict(t=t, delta=delta.tolist()))
        self.event(t, 'route_local_match', node=accepted['node'], delta=delta.tolist(), reset=False)
        sample['pose'] = list(g.odom.pose)
        sample['covariance'] = g.odom.covariance.tolist()

    def _arrival(self, t, frame_id, pose, box_visible):
        self._reference_executed['arrival'] = True
        if not self.reference_options.arrival_verify_fsm or self.active != 'B':
            return super()._arrival(t, frame_id, pose, box_visible)
        near = math.dist(pose[:2], self.entities['B']['center_m']) <= .20
        if near and self._verify is None:
            self._verify = dict(start=t, yaw=float(pose[2]), index=0, phase_start=t, state='verify')
        # Associate CURRENT confirmed RGB patch to the remembered B; memory
        # alone is never a new observation and never increments the streak.
        patches = self.current_patches
        tracks = {p['id']:p for p in self.explorer.goal.tracks}
        matched = [p for p in patches if p.get('confirmed_t') is not None and
                   abs(tracks.get(p.get('track_id'),{}).get('last_t',-math.inf)-t)<=1e-8 and
                   'center_odom_m' in p and math.dist(p['center_odom_m'], self.entities['B']['center_m']) <=
                   self.explorer.goal.options.temporal_center_max_m]
        lower = 0 if self.labels is None else int(np.count_nonzero(self.labels[2*self.labels.shape[0]//3:]))
        self._visual_reason = ('outside_20cm' if not near else 'no_current_patch' if not patches else
                               'unconfirmed_or_other_B' if not matched else 'lower_pixels' if
                               lower < self.explorer.goal.options.min_pixels else 'current_evidence')
        self.current_patches = matched
        try:
            super()._arrival(t, frame_id, pose, box_visible)
        finally:
            self.current_patches = patches

    def receive(self, **kw):
        self._reference_calls += 1
        self._reference_executed = {'receive': True}
        cmd, trace = self._reference_base_receive(**kw)
        # Near-goal NavFn can produce no local path, so its host call may have
        # been skipped. Visual verification still owns that command slot.
        if (not self.done and self.reference_options.arrival_verify_fsm and self._verify
                and self.stage=='approach' and self.active=='B' and self._host_t != kw['t']):
            from harness.self_map_csm import sample_segments
            e = self.explorer
            cmd, trace['pulse'] = self.heading_host.command(t=kw['t'], pose=trace['local_pose'],
                path=[], goal=self.entities['B']['center_m'],
                costmap=from_observed_grid(e.grid,e.pose,e.latest,set()), core=self.navigator.core,
                points=sample_segments(kw['observation']['segments']), map_pose=e.pose, dev_light=self.dev_light)
            trace['command'] = cmd
        trace['reference_navigation'] = dict(options=asdict(self.reference_options),
            execution=dict(version='receive_composed_v1', calls=self._reference_calls,
                           dispatched=asdict(self.reference_options),
                           exercised=dict(self._reference_executed)),
            traversed_free=None if self._traversed is None else self._traversed.diagnostics(),
            return_progress=None if self._progress is None else self._progress.ratio,
            free_remaining_m=self._free_remaining, free_initial_m=self._free_initial,
            free_path=self._free_status, visual_gate=self._visual_reason,
            repeat_match=self._repeat_reason, verify=copy.deepcopy(self._verify))
        self.last_trace = copy.deepcopy(trace)
        return cmd, trace

    def snapshot(self):
        return dict(super().snapshot(), reference_navigation=asdict(self.reference_options))


def install(controller, options=Options(), *, traversed_free='off'):
    if traversed_free not in ('off', 'footprint_history_v1'):
        raise ValueError('UNKNOWN_TRAVERSED_FREE')
    if traversed_free != 'off' and not options.return_own_free_astar:
        raise ValueError('TRAVERSED_REQUIRES_OWN_FREE')
    if not any(asdict(options).values()):
        return controller  # no reads or wrappers on off, frozen output identity
    if type(controller) is not GoalRoute or controller.heading_host is None:
        raise ValueError('FROZEN_CONTINUOUS_HEADING_HOST_REQUIRED')
    # Preserve the checkpoint's instance scalar_rays wrapper as the BASE call.
    # Class replacement alone leaves instance attributes shadowing methods.
    base_receive = controller.receive
    controller.__class__ = ReferenceRoute
    controller._reference_base_receive = base_receive
    controller.receive = MethodType(ReferenceRoute.receive, controller)
    controller._reference_calls = 0
    controller._reference_executed = {}
    controller._traversed = None
    controller._free_costmap = None
    if traversed_free != 'off':
        from harness.own_traversed_free import TraversedFree
        controller._traversed = TraversedFree.from_graph(controller.graph)
    controller.reference_options = options
    controller._reference_route = controller._progress = controller._verify = None
    controller._return_path = []
    controller._free_initial = controller._free_remaining = controller._host_t = None
    controller._free_core = PublicCore() if options.return_own_free_astar else None
    controller._free_status = controller._visual_reason = controller._repeat_reason = 'not_active'
    controller._repeat_blocked = True
    original = controller.heading_host.command

    def command(host, **kw):
        c = controller
        c._reference_executed['heading'] = True
        c._host_t = kw['t']
        pose = np.asarray(kw['pose'])
        def hold(reason):
            return dict(t=float(kw['t']), kind='hold'), dict(reason=reason, predicted_delta=[0.,0.,0.])
        if c.stage == 'return':
            if options.return_local_vtr and c._repeat_blocked:
                return hold('repeat_localization_wait')
            if options.return_own_free_astar and not c._return_path:
                return hold('no_observed_free_path')
            if c._free_costmap is not None:
                kw['costmap'] = c._free_costmap
            if options.progress_lookahead or options.return_local_vtr or options.return_own_free_astar:
                kw['path'] = c._return_path
        if options.arrival_verify_fsm and c.stage == 'approach' and c.active == 'B' and c._verify:
            v = c._verify
            if c._visual_reason == 'current_evidence':
                return hold('arrival_verify_current_evidence')
            # Limited own-view reacquisition. Three fixed camera half-FOV
            # orientations, original partial-turn timeout, no 360 or translation.
            angles = (0., PARTIAL_ANGLE, -PARTIAL_ANGLE)
            while v['index'] < len(angles):
                yaw = v['yaw']+angles[v['index']]
                error = math.atan2(math.sin(yaw-pose[2]), math.cos(yaw-pose[2]))
                if abs(error) <= .06 or kw['t']-v['phase_start'] >= PARTIAL_TIMEOUT:
                    v['index'] += 1
                    v['phase_start'] = kw['t']
                    continue
                p = pose[:2]+LOOKAHEAD*np.array([math.cos(yaw), math.sin(yaw)])
                kw.update(path=[p], goal=p)
                break
            else:
                v['state'] = 'verify_exhausted'
                return hold('arrival_verify_exhausted')
        if options.progress_lookahead or (c.stage=='return' and options.return_local_vtr):
            path = np.asarray(kw['path'], float).reshape(-1,2)
            if not len(path):
                return hold('empty_reference_path')
            # Incoming replans start at the current pose. Return paths already
            # use monotonic pruning; never search the entire temporal route.
            kw['path'] = [carrot(path, pose[:2])]
        return original(**kw)

    controller.heading_host.command = MethodType(command, controller.heading_host)
    return controller
