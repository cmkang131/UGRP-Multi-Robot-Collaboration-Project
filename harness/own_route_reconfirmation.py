"""Default-off RGB gates before B arrival, corridor match and return claim.

Corridor means an accepted remembered graph-node match, not newly certified
free space. Finite view acquisition reuses the existing pulse/coast host.
"""
import copy
import math
from types import MethodType
import numpy as np
from harness.own_rgb_homing import Memory
from harness.own_rgb_reconfirmation import OPTION, TwoViewGate, angle_difference
from harness.own_route_zone_arrival import confirm_component
from harness.own_traversal_reconnection import PARTIAL_ANGLE, PARTIAL_TIMEOUT


def current_B(c, pose, rgb, t, *, entity=None):
    """Current own candidate, same track/metric association, hue and full size."""
    entity = c.entities.get('B') if entity is None else entity
    if entity is None or c.labels is None:
        return False, dict(reason='no_current_B')
    candidate = entity.get('observation', {}).get('candidate_id')
    tracks = {p['id']: p for p in c.explorer.goal.tracks}
    rows = []
    for patch in c.current_patches:
        track = tracks.get(patch.get('track_id'), {})
        same = (patch.get('track_id') == candidate and patch.get('confirmed_t') is not None
            and abs(track.get('last_t', -math.inf)-t) <= 1e-8
            and 'center_odom_m' in patch
            and math.dist(patch['center_odom_m'], entity['center_m']) <= c.explorer.goal.options.temporal_center_max_m)
        if not same:
            continue
        check = confirm_component(rgb, c.labels == patch['component'], patch)
        rows.append(check)
    return any(r['accepted'] for r in rows), dict(candidate_id=candidate, current_components=rows)


def install(c, *, rgb_reconfirmation='off', memory=None, fresh_home=False):
    if rgb_reconfirmation == 'off':
        return c  # identity, including no input reads or wrappers
    if rgb_reconfirmation != OPTION:
        raise ValueError('UNKNOWN_RGB_RECONFIRMATION')
    if c.heading_host is None:
        raise ValueError('FINITE_HEADING_HOST_REQUIRED')
    bank = memory if memory is not None else Memory(c.robot_id)
    if bank.robot_id != c.robot_id:
        raise ValueError('OWN_RGB_MEMORY_REQUIRED')
    if fresh_home and (bank.frames or bank.home or c.graph.nodes):
        raise ValueError('FRESH_HOME_REQUIRES_EMPTY_OWN_MEMORY')
    gate = TwoViewGate(bank.K)
    # Prefix home references stay immutable; a drifted new observation must
    # not be promoted to a home reference using its own estimated proximity.
    home = tuple(bank.home)
    c._rgb_reconfirmation_calls = 0
    c._rgb_reconfirmation_captures = 0
    c._rgb_reconfirmation_gate = gate
    c._rgb_reconfirmation_acquisitions = []
    c._rgb_reconfirmation_latest = {}
    inputs = {}; frame_cache = {}; acquisition = None; attempted = set()
    base_receive, base_localize = c.receive, c._localize
    base_arrival, base_target, base_entity = c._arrival, c._return_target, c._entity
    base_match, base_heading, base_snapshot = c.graph.match, c.heading_host.command, c.snapshot

    def frame(pose):
        if not frame_cache:
            frame_cache['current'] = bank.extract(inputs['rgb'], inputs['servo'], pose,
                inputs['t'], inputs['frame_id'], inputs['frame_sha256'])
        return frame_cache['current']

    def check(key, pose, *, references=None, semantic=True, evidence=None):
        nonlocal acquisition
        result = gate.observe(key, frame(pose), references=references, semantic=semantic, evidence=evidence)
        c._rgb_reconfirmation_latest[str(key)] = result
        if result['accepted']:
            if acquisition is not None and acquisition['key'] == str(key):
                acquisition.update(status='confirmed', ended_t=inputs['t'])
                acquisition = None
        elif str(key) not in attempted:
            # Each hypothesis gets one bounded +/- half-FOV attempt. Existing
            # DEV navigation resumes after exhaustion; declaration stays gated.
            if acquisition is None:
                attempted.add(str(key))
                acquisition = dict(key=str(key), started_t=inputs['t'], yaw=float(pose[2]), index=0,
                    status='acquiring', phase_started_t=inputs['t'])
                c._rgb_reconfirmation_acquisitions.append(acquisition)
        return result['accepted']

    def match(graph, sample, node_id=None):
        proposal = base_match(sample, node_id)
        if proposal.get('status') != 'accepted':
            return proposal
        node = c.graph.nodes[proposal['node']]
        # Temporal correspondence to an existing own node, not a whole-bank
        # search that could choose a different spatial alias.
        references = sorted((f for f in bank.frames if 0 <= node['t']-f.t <= PARTIAL_TIMEOUT
            and math.dist(f.pose[:2], node['pose'][:2]) <= .30),
            key=lambda f: abs(f.frame_id-node['frame_id']))[:3]
        accepted = check(('corridor', proposal['node']), sample['pose'], references=references)
        if not accepted:
            return dict(proposal, status='rejected', reason='rgb_reconfirmation_required',
                ungated_status='accepted', rgb_reconfirmation=copy.deepcopy(c._rgb_reconfirmation_latest[str(('corridor', proposal['node']))]))
        return dict(proposal, rgb_reconfirmation='two_view_confirmed')

    def localize(self, sample, t):
        # The graph wrapper vetoes before base_localize mutates particles,
        # match_nodes, offsets or any accepted-match event.
        value = base_localize(sample, t)
        inputs['_pose'] = sample['pose']
        return value

    def entity(self, name, center, t, frame_id, sha, **evidence):
        if name == 'B' and name not in self.entities:
            # Delay the new own_entity_confirmed event and graph/cue insertion,
            # rather than undoing a declaration after its side effects.
            proposal = dict(center_m=center, observation=evidence.get('observation', {}))
            pose = inputs['_pose']
            valid, detail = current_B(self, pose, inputs['rgb'], t, entity=proposal)
            key = ('B', proposal['observation'].get('candidate_id'))
            if not check(key, pose, semantic=valid, evidence=detail):
                return
        return base_entity(name, center, t, frame_id, sha, **evidence)

    def arrival(self, t, frame_id, pose, box_visible):
        if self.active != 'B':
            return base_arrival(t, frame_id, pose, box_visible)
        if math.dist(pose[:2], self.entities['B']['center_m']) > .20:
            return base_arrival(t, frame_id, pose, box_visible)
        valid, evidence = current_B(self, pose, inputs['rgb'], t)
        key = ('B', self.entities['B'].get('observation', {}).get('candidate_id'))
        if not check(key, pose, semantic=valid, evidence=evidence):
            self.streak = 0
            if hasattr(self, '_zone_streak'):
                self._zone_streak = 0
            return
        return base_arrival(t, frame_id, pose, box_visible)

    def target(self, pose):
        point = base_target(pose)
        if math.dist(pose[:2], self.graph.nodes[0]['pose'][:2]) <= .20:
            if not check(('return', 0), pose, references=home):
                self.cursor = 0  # prevents the existing five-frame declaration
        return point

    def heading(host, **kw):
        nonlocal acquisition
        if acquisition is None:
            return base_heading(**kw)
        request = acquisition
        if kw['t']-request['started_t'] >= 2*PARTIAL_TIMEOUT:
            request.update(status='exhausted', ended_t=kw['t'])
            acquisition = None
            return base_heading(**kw)
        angles = (PARTIAL_ANGLE, -PARTIAL_ANGLE)
        yaw = request['yaw']+angles[request['index']]
        if angle_difference(yaw, kw['pose'][2]) <= .06 or kw['t']-request['phase_started_t'] >= PARTIAL_TIMEOUT:
            if request['index'] == 0:
                request.update(index=1, phase_started_t=kw['t'])
                yaw = request['yaw']+angles[1]
            else:
                request.update(status='exhausted', ended_t=kw['t'])
                acquisition = None
                return base_heading(**kw)
        p = np.asarray(kw['pose'][:2])+.6*np.array([math.cos(yaw), math.sin(yaw)])
        # Existing return wrapper substitutes _return_path. Feed it the same
        # temporary alignment target and preserve the actual planned path.
        saved = getattr(c, '_return_path', None)
        if saved is not None:
            c._return_path = [p.tolist()]
        try:
            command, diagnostic = base_heading(**{**kw, 'path':[p], 'goal':p})
        finally:
            if saved is not None:
                c._return_path = saved
        # At most a rotation, never blind translation toward an alignment ray.
        if command.get('kind') == 'mecanum' and (command.get('forward', 0) or command.get('left', 0)):
            command = dict(t=float(kw['t']), kind='hold')
            diagnostic = dict(reason='rgb_view_alignment_hold', predicted_delta=[0., 0., 0.])
        return command, dict(diagnostic, rgb_view_acquisition=dict(request))

    def receive(**kw):
        nonlocal home
        inputs.clear(); inputs.update(kw); frame_cache.clear()
        c._rgb_reconfirmation_calls += 1
        command, trace = base_receive(**kw)
        # Approach planners may skip the heading host when no path exists.
        # The bounded pure-turn acquisition must still execute in that case.
        if acquisition is not None and not c.done and not trace.get('pulse', {}).get('rgb_view_acquisition'):
            from harness.public_navigation_unknown import from_observed_grid
            from harness.self_map_csm import sample_segments
            e = c.explorer
            command, trace['pulse'] = heading(c.heading_host, t=kw['t'], pose=trace['local_pose'], path=[],
                goal=trace['local_pose'][:2], costmap=from_observed_grid(e.grid, e.pose, e.latest, set()),
                core=c.navigator.core, points=sample_segments(kw['observation']['segments']),
                map_pose=e.pose, dev_light=c.dev_light)
            trace['command'] = command
        trace['rgb_reconfirmation'] = dict(option=OPTION, calls=c._rgb_reconfirmation_calls,
            latest=copy.deepcopy(c._rgb_reconfirmation_latest), acquisition=copy.deepcopy(acquisition),
            references=len(bank.frames), home_references=len(home))
        # Teach newly reached graph nodes only AFTER this frame's declarations
        # and match checks. Its features can be a reference for future frames,
        # never for itself. The separate frozen home tuple cannot grow here.
        if (not c.graph.sealed and c.graph.nodes and c.graph.nodes[-1]['frame_id'] == kw['frame_id']
                and (not bank.frames or bank.frames[-1].frame_id < kw['frame_id'])):
            captured = frame(trace['local_pose'])
            if not np.array_equal(captured.pose, trace['local_pose']):
                captured = bank.extract(kw['rgb'], kw['servo'], trace['local_pose'],
                    kw['t'], kw['frame_id'], kw['frame_sha256'])
            # No triangulation: this adapter needs descriptors, not 3D points.
            bank.frames.append(captured)
            c._rgb_reconfirmation_captures += 1
            # A fresh run freezes ONLY its first observed home keyframe, after
            # this frame's decisions. Never promote later estimated proximity.
            if fresh_home and not home:
                home = (captured,)
                bank.home.append(captured)
        trace['rgb_reconfirmation']['home_references'] = len(home)
        trace['rgb_reconfirmation'].update(references=len(bank.frames), captured=c._rgb_reconfirmation_captures)
        c.last_trace = copy.deepcopy(trace)
        return command, trace

    def snapshot(self):
        return dict(base_snapshot(), rgb_reconfirmation=dict(option=OPTION, rows=copy.deepcopy(gate.rows),
            acquisitions=copy.deepcopy(c._rgb_reconfirmation_acquisitions)))

    c.graph.match = MethodType(match, c.graph)
    c._localize = MethodType(localize, c)
    c._entity = MethodType(entity, c)
    c._arrival = MethodType(arrival, c)
    c._return_target = MethodType(target, c)
    c.heading_host.command = MethodType(heading, c.heading_host)
    c.receive = receive; c.snapshot = MethodType(snapshot, c)
    return c
