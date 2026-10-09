"""Own traversed edges + local metric places (Kuipers SSH / teach-and-repeat).

No file/scene/GT input. Frozen preregistration: egomap51 README. A gap is NOT a
loop closure: disconnected components remain disconnected without evidence.
"""
from collections import Counter, deque
import copy
import heapq
import math
import cv2
import numpy as np
from harness.self_map_csm import CSMOptions, CorrelativeMatcher, sample_segments
from harness.self_pose_graph import between, compose, wrap
from harness.self_odom_grid import transform

OPTION = 'traversal_graph_v1'
OPTIONS = CSMOptions(yaw_window_deg=20.)
BAD_STATUS = ('recover', 'backup', 'clear', 'no_progress', 'aborted', 'collision', 'contact')


def own_sample(trace, observation, *, rgb, frame_sha256, covariance=None, excluded_reason=None):
    pose = trace.get('local_pose', trace.get('pose'))
    if pose is None:
        raise ValueError('OWN_POSE_REQUIRED')
    return dict(t=float(trace['t']), frame_id=int(trace['frame_id']), pose=list(pose),
        covariance=(OPTIONS.floor() if covariance is None else np.asarray(covariance)).tolist(),
        status=trace.get('status', ''), excluded_reason=excluded_reason,
        segments=copy.deepcopy(observation['segments']), camera=copy.deepcopy(observation['camera']),
        frame_sha256=frame_sha256,
        rgb_summary=cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (16, 12), interpolation=cv2.INTER_AREA).tolist())


class TraversalGraph:
    def __init__(self, robot_id):
        self.robot_id = robot_id
        self.nodes, self.edges, self.breaks = [], [], []
        self.recent = deque()
        self.pending = []
        self.last = None
        self.anchor = None
        self.goal_node = None
        self.goal = None
        self.sealed = False
        self.frames = 0

    def observe(self, sample, goal=None):
        if self.sealed:
            raise ValueError('PREFIX_ALREADY_SEALED')
        s = copy.deepcopy(sample)
        if self.last and (s['t'] <= self.last['t'] or s['frame_id'] <= self.last['frame_id']):
            raise ValueError('NON_CAUSAL_SAMPLE')
        if not np.isfinite(s['pose']).all():
            raise ValueError('FINITE_OWN_POSE_REQUIRED')
        self.frames += 1
        reason = s.get('excluded_reason') or next((x for x in BAD_STATUS if x in s['status'].lower()), None)
        if reason:
            self.breaks.append(dict(t=s['t'], frame_id=s['frame_id'], reason=reason))
            self.anchor = None
            self.pending = []
            self.recent.clear()
        if s['segments'] and (not self.recent or s['t']-self.recent[-1]['t'] >= OPTIONS.keyframe_interval_s-1e-8):
            self.recent.append(s)
        while self.recent and (s['t']-self.recent[0]['t'] > OPTIONS.submap_age_s or len(self.recent)>OPTIONS.submap_keyframes):
            self.recent.popleft()
        new_goal = goal is not None and self.goal_node is None
        if new_goal:
            if goal['source'] != 'own' or goal['t_sim'] > s['t'] or goal['first_t'] > goal['t_sim']:
                raise ValueError('CAUSAL_OWN_GOAL_REQUIRED')
            self.goal = copy.deepcopy(goal)
        self.last = s
        # Retain the bad observation as a B place if necessary, never as a link.
        if reason:
            if new_goal:
                self._node(s, isolated=True)
                self.goal_node = len(self.nodes)-1
                self.nodes[-1]['entities'] = [copy.deepcopy(self.goal)]
            return
        self.pending.append(dict(t=s['t'], frame_id=s['frame_id'], pose=s['pose'], frame_sha256=s['frame_sha256']))
        a = self.nodes[self.anchor] if self.anchor is not None else None
        due = a is None or np.linalg.norm(np.array(s['pose'])[:2]-a['pose'][:2]) >= .30 or abs(float(wrap(s['pose'][2]-a['pose'][2]))) >= math.radians(20)
        if due or new_goal:
            self._node(s)
            if new_goal:
                self.goal_node = len(self.nodes)-1
                self.nodes[-1]['entities'] = [copy.deepcopy(self.goal)]

    def _node(self, s, isolated=False):
        patch, sources = [], []
        for row in self.recent:
            if np.linalg.norm(np.array(row['pose'])[:2]-s['pose'][:2]) > OPTIONS.submap_radius_m:
                continue
            patch.extend(transform(np.asarray(row['segments']).reshape(-1, 2), between(s['pose'], row['pose'])).reshape(-1, 2, 2).tolist())
            sources.append(dict(t=row['t'], frame_id=row['frame_id'], frame_sha256=row['frame_sha256']))
        idx = len(self.nodes)
        node = dict(id=idx, t=s['t'], frame_id=s['frame_id'], pose=s['pose'], covariance=s['covariance'],
                    frame_sha256=s['frame_sha256'], rgb_summary=s['rgb_summary'], patch=patch, patch_sources=sources, entities=[])
        self.nodes.append(node)
        if self.anchor is not None and not isolated:
            dense = copy.deepcopy(self.pending)
            length = sum(math.dist(a['pose'][:2], b['pose'][:2]) for a, b in zip(dense, dense[1:]))
            self.edges.append(dict(a=self.anchor, b=idx, length_m=length, samples=dense,
                relative_pose=between(self.nodes[self.anchor]['pose'], s['pose']).tolist()))
        if not isolated:
            self.anchor = idx
            self.pending = [dict(t=s['t'], frame_id=s['frame_id'], pose=s['pose'], frame_sha256=s['frame_sha256'])]

    def seal(self):
        if not self.sealed:
            if self.anchor is not None and self.last['frame_id'] != self.nodes[self.anchor]['frame_id']:
                self._node(self.last)
            self.sealed = True
        return self.snapshot()

    def snapshot(self):
        return copy.deepcopy(dict(option=OPTION, robot_id=self.robot_id, coordinate_frame=f'{self.robot_id}/own_odom',
            nodes=self.nodes, edges=self.edges, breaks=self.breaks, goal=self.goal, goal_node=self.goal_node,
            last_node=self.anchor, frames=self.frames, sealed=self.sealed))

    def route(self, start, goal=None):
        goal = self.goal_node if goal is None else goal
        if start is None or goal is None:
            return None
        adjacency = {n['id']: [] for n in self.nodes}
        for i,e in enumerate(self.edges):
            adjacency[e['a']].append((e['b'], i))
            adjacency[e['b']].append((e['a'], i))
        todo, seen = [(0., start, [start], [])], set()
        while todo:
            cost, at, path, edges = heapq.heappop(todo)
            if at in seen:
                continue
            seen.add(at)
            if at == goal:
                samples = []
                for a, eid in zip(path, edges):
                    e = self.edges[eid]
                    part = e['samples'] if e['a'] == a else list(reversed(e['samples']))
                    samples.extend(copy.deepcopy(part if not samples else part[1:]))
                return dict(nodes=path, edges=edges, length_m=cost, samples=samples)
            for nxt,eid in adjacency[at]:
                if nxt not in seen:
                    heapq.heappush(todo, (cost+self.edges[eid]['length_m'], nxt, path+[nxt], edges+[eid]))
        return None

    def match(self, sample, node_id=None):
        if not self.nodes:
            return dict(status='rejected', reason='empty_graph')
        if node_id is None:
            node_id = min(range(len(self.nodes)), key=lambda i: np.linalg.norm(np.array(self.nodes[i]['pose'])[:2]-sample['pose'][:2]))
        n = self.nodes[node_id]
        event = dict(node=node_id, t=sample['t'], frame_id=sample['frame_id'], status='rejected')
        if sample['t'] <= n['t']:
            return dict(event, reason='query_not_after_node')
        if math.dist(sample['pose'][:2], n['pose'][:2]) > OPTIONS.translation_window_m:
            return dict(event, reason='outside_local_neighborhood')
        points = sample_segments(sample['segments'])
        if len(points) < OPTIONS.min_points or not n['patch']:
            return dict(event, reason='insufficient_points')
        # Matcher runs in the node frame. Rotate the query covariance accordingly.
        c,s = math.cos(n['pose'][2]), math.sin(n['pose'][2])
        R = np.array([[c,s,0],[-s,c,0],[0,0,1]])
        result = CorrelativeMatcher(OPTIONS).match(between(n['pose'], sample['pose']),
            R@np.asarray(sample['covariance'])@R.T, points, np.asarray(sample['camera']), n['patch'],
            R@np.asarray(n['covariance'])@R.T)
        result['pose'] = compose(n['pose'], result['pose']).tolist()
        result['covariance'] = (R.T@np.asarray(result['covariance'])@R).tolist()
        return dict(result, node=node_id, t=sample['t'], frame_id=sample['frame_id'])


class TraversalReturn:
    """Localize at each taught node; no arbitrary route or mission blacklist."""
    def __init__(self, graph):
        self.graph = graph
        self.route = None
        self.node_cursor = 0
        self.sample_cursor = 0
        self.match_events = []
        self.last_match = None
        self.sweep_start = None
        self.sweep_yaw = None
        self.sweep_rotation = 0.
        self.matched_node = None
        self.failure = None

    @property
    def at_goal_node(self):
        return self.route is not None and self.node_cursor == len(self.route['nodes'])-1 and self.matched_node == self.graph.goal_node and self.failure is None

    def localize(self, sample):
        wanted = None if self.route is None else self.route['nodes'][self.node_cursor]
        if wanted is not None and self.matched_node == wanted:
            return None
        if wanted is not None and math.dist(sample['pose'][:2],self.graph.nodes[wanted]['pose'][:2]) > .5:
            return None
        result = self.graph.match(sample, wanted)
        self.last_match = result
        self.match_events.append(result)
        if result['status'] == 'accepted':
            self.matched_node = result['node']
            self.sweep_start = None
            if self.route is None:
                self.route = self.graph.route(result['node'])
                if self.route is None:
                    self.failure = 'disconnected_B_route'
        elif self.sweep_start is None:
            self.sweep_start = sample['t']
            self.sweep_yaw = sample['pose'][2]
            self.sweep_rotation = 0.
        return result

    def twist(self, pose, t):
        if self.failure:
            return np.zeros(3), self.failure
        if self.sweep_start is not None:
            self.sweep_rotation += abs(float(wrap(pose[2]-self.sweep_yaw)))
            self.sweep_yaw = pose[2]
            if self.sweep_rotation >= 2*math.pi-.02 or t-self.sweep_start >= 30.:
                self.failure = 'node_match_failed_after_sweep'
                return np.zeros(3), self.failure
            return np.array([0.,0.,.5]), 'node_match_sensor_sweep'
        if self.route is None:
            return np.zeros(3), 'await_node_match'
        nodes = self.route['nodes']
        target_id = nodes[self.node_cursor]
        if self.matched_node != target_id:
            return np.zeros(3), 'await_node_match'
        if math.dist(pose[:2],self.graph.nodes[target_id]['pose'][:2]) <= .05:
            if self.node_cursor+1 < len(nodes):
                self.node_cursor += 1
                target_id = nodes[self.node_cursor]
        # Follow all sampled path geometry, never shortcut the taught corner.
        points = self.route['samples']
        while self.sample_cursor < len(points) and math.dist(pose[:2], points[self.sample_cursor]['pose'][:2]) <= .05:
            self.sample_cursor += 1
        if self.sample_cursor < len(points):
            target = points[self.sample_cursor]['pose'][:2]
        elif self.node_cursor == len(nodes)-1 and self.matched_node == nodes[-1]:
            target = self.graph.goal['center_m']
        else:
            return np.zeros(3), 'await_node_match'
        d = np.asarray(target)-pose[:2]
        angle = float(wrap(math.atan2(d[1],d[0])-pose[2]))
        # Alignment within the camera FOV; reuse egomap50 frontal tolerance.
        if abs(angle) > math.radians(10):
            return np.array([0.,0.,float(np.clip(angle/.1,-.5,.5))]), 'traversal_rotate_forward'
        return np.array([min(.12,float(np.linalg.norm(d))/.2),0.,0.]), 'traversal_forward'


def attach(controller, *, return_policy='off'):
    if return_policy == 'off':
        return controller
    if return_policy == 'traversal_graph_reconnect_v1':
        from harness.own_traversal_reconnection import attach as reconnect
        return reconnect(controller, return_policy=return_policy)
    if return_policy != OPTION:
        raise ValueError('UNKNOWN_RETURN_POLICY')
    from harness.self_map_return_repeat import Return360
    if type(controller) is not Return360:
        raise ValueError('FROZEN_RETURN360_REQUIRED')
    controller.__class__ = Traversal360
    controller.traversal_graph = TraversalGraph(controller.robot_id)
    controller.traversal = None
    return controller


from harness.self_map_return_repeat import Return360


class Traversal360(Return360):
    def lose(self, t, frame_id):
        self.traversal_graph.seal()
        super().lose(t, frame_id)
        self.traversal = TraversalReturn(self.traversal_graph)

    def receive(self, **kw):
        cmd, trace = super().receive(**kw)
        if trace['stage'] == 'explore':
            g = self.explorer.memory.self_map
            events = self.explorer.navigator.events
            bad = next((e['reason'] for e in events if e['t'] >= kw['t']-.200001 and e['reason'] in
                        ('controller_no_progress','navigation_action_aborted')), None)
            self.traversal_graph.observe(own_sample(trace, kw['observation'], rgb=kw['rgb'],
                frame_sha256=kw['frame_sha256'], covariance=g.odom.covariance, excluded_reason=bad), self.goal)
        trace['traversal'] = dict(nodes=len(self.traversal_graph.nodes), edges=len(self.traversal_graph.edges),
            goal_node=self.traversal_graph.goal_node,
            match=None if self.traversal is None else self.traversal.last_match,
            failure=None if self.traversal is None else self.traversal.failure)
        return cmd, trace
