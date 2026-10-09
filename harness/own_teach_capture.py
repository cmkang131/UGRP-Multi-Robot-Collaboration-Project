"""VT&R camera keyframe capture adapted to own monocular wall submaps.

Vertex decision adapted from ASRL VT&R3 (Apache-2.0), commit bdb40d8a,
simple_vertex_test_module.cpp and bumblebee_grizzly_default.yaml.
Copyright 2021 Autonomous Space Robotics Lab; license and modifications:
experiments/2026-10-09-teach-capture/references/LICENSE.vtr3 and README.md.
No GT, peer map, new image capture, or teach motion command is used here.
"""
import copy
import math
import numpy as np
from harness.own_traversal_graph import TraversalGraph,TraversalReturn,own_sample,BAD_STATUS,OPTIONS
from harness.own_traversal_reconnection import ReconnectedGraph
from harness.self_map_return_repeat import Return360
from harness.self_pose_graph import between,wrap

OPTION='vtr_keyframes_v1'
MIN_DISTANCE=.05
CREATE_DISTANCE=.30
MAX_DISTANCE=2.
MIN_ROTATION=3.
MAX_ROTATION=20.


def vertex_decision(relative):
    """VT&R uses the SE(3) log norm; use its planar SE(2) restriction."""
    x,y,theta=map(float,relative)
    if abs(theta)>1e-8:
        a=math.sin(theta)/theta;b=(1-math.cos(theta))/theta
        x,y=(a*x+b*y)/(a*a+b*b),(-b*x+a*y)/(a*a+b*b)
    distance=math.hypot(x,y);angle=abs(math.degrees(theta))
    if distance<MIN_DISTANCE and angle<MIN_ROTATION:return 'candidate'
    if distance>MAX_DISTANCE or angle>MAX_ROTATION:return 'uncertain_jump'
    if distance>CREATE_DISTANCE or angle>MIN_ROTATION:return 'vertex'
    return 'candidate'  # stereo inlier counts are not wall-point counts


def dense(s):
    return {k:copy.deepcopy(s[k]) for k in ('t','frame_id','pose','frame_sha256','covariance','uncertainty_reasons')}


class TeachGraph(TraversalGraph):
    def __init__(self,robot_id):
        super().__init__(robot_id)
        self.pinned_candidates={}
        self.capture_events=[]
        self.candidate=None

    def observe(self,sample,goal=None,candidates=()):
        if self.sealed:raise ValueError('PREFIX_ALREADY_SEALED')
        s=copy.deepcopy(sample)
        if self.last and (s['t']<=self.last['t'] or s['frame_id']<=self.last['frame_id']):raise ValueError('NON_CAUSAL_SAMPLE')
        if not np.isfinite(s['pose']).all():raise ValueError('FINITE_OWN_POSE_REQUIRED')
        reason=s.get('excluded_reason') or next((x for x in BAD_STATUS if x in s['status'].lower()),None)
        s['uncertainty_reasons']=[reason] if reason else []
        if reason:self.breaks.append(dict(t=s['t'],frame_id=s['frame_id'],reason=reason,retained=True))
        decision='vertex' if self.anchor is None else vertex_decision(between(self.nodes[self.anchor]['pose'],s['pose']))
        if decision=='uncertain_jump':
            # VT&R promotes the latest valid candidate when odometry fails.
            # User-authorized difference: retain the new uncertain edge as well.
            if self.candidate and self.candidate['frame_id']!=self.nodes[self.anchor]['frame_id']:
                self._node(self.candidate)
            s['uncertainty_reasons'].append('vtr_motion_discontinuity')
        self.frames+=1;self.last=s
        self.pending.append(dense(s))
        # Preserve overlapping history across recovery, unlike egomap51.
        if s['segments'] and (not self.recent or s['t']-self.recent[-1]['t']>=OPTIONS.keyframe_interval_s-1e-8):self.recent.append(s)
        while self.recent and (s['t']-self.recent[0]['t']>OPTIONS.submap_age_s or len(self.recent)>OPTIONS.submap_keyframes):self.recent.popleft()
        fresh=[]
        for c in candidates:
            key=(str(c['id']),float(c['first_t']))
            if key not in self.pinned_candidates:
                if c['first_t']!=s['t']:raise ValueError('FIRST_B_FRAME_NOT_CAPTURED')
                fresh.append((key,c))
        if self.anchor is None or decision!='candidate' or fresh:self._node(s)
        else:self.candidate=s
        for key,c in fresh:
            self.pinned_candidates[key]=self.anchor
            self.nodes[self.anchor].setdefault('B_first_observations',[]).append(copy.deepcopy(c))
        if goal is not None and self.goal_node is None:
            if goal['source']!='own' or goal['first_t']>goal['t_sim'] or goal['t_sim']>s['t']:raise ValueError('CAUSAL_OWN_GOAL_REQUIRED')
            key=(str(goal['candidate_id']),float(goal['first_t']))
            if key not in self.pinned_candidates:raise ValueError('CONFIRMED_B_MISSING_FIRST_KEYFRAME')
            self.goal=copy.deepcopy(goal);self.goal_node=self.pinned_candidates[key]
            self.nodes[self.goal_node]['entities']=[copy.deepcopy(goal)]
        self.capture_events.append(dict(t=s['t'],frame_id=s['frame_id'],decision=decision,node=self.anchor,uncertain=bool(s['uncertainty_reasons'])))

    def _node(self,s,isolated=False):
        if self.nodes and self.nodes[-1]['frame_id']==s['frame_id']:return
        # A promoted earlier candidate cannot see subsequent patch observations.
        future=[r for r in self.recent if r['t']>s['t']]
        if future:raise ValueError('FUTURE_PATCH_IN_CANDIDATE')
        super()._node(s,isolated=False)
        n=self.nodes[-1]
        n['rgb_ref']=dict(robot_id=self.robot_id,frame_id=s['frame_id'],sha256=s['frame_sha256'],source='retained own RGB frames manifest')
        n['capture_option']=OPTION
        if self.edges:
            e=self.edges[-1]
            if e['b']==n['id']:
                reasons=sorted({v for row in e['samples'] for v in row.get('uncertainty_reasons',[])})
                e.update(kind='temporal',uncertain=bool(reasons),uncertainty_reasons=reasons,
                    covariance=(np.asarray(self.nodes[e['a']]['covariance'])+np.asarray(n['covariance'])).tolist(),
                    metric_verified=False)
        self.pending=[dense(s)];self.candidate=None

    # Existing local matcher, same nearest-five and acceptance rules as egomap52.
    match=ReconnectedGraph.match

    def snapshot(self):
        out=super().snapshot()
        out.update(option=OPTION,pinned_B_candidates=[dict(candidate_id=k[0],first_t=k[1],node=v) for k,v in self.pinned_candidates.items()],
            capture_events=copy.deepcopy(self.capture_events),uncertain_edges=sum(e['uncertain'] for e in self.edges))
        return out


class TeachReturn(TraversalReturn):
    """VT&R not-localized => zero command, retry with later own observations."""
    def __init__(self,graph):
        super().__init__(graph);self.blocked=True

    def localize(self,sample):
        result=super().localize(sample)
        if result is not None:
            self.blocked=result['status']!='accepted'
            self.sweep_start=None  # no active turn or 360-degree sweep
        return result

    def twist(self,pose,t):
        if self.failure:return np.zeros(3),self.failure
        if self.blocked:return np.zeros(3),'teach_localization_wait'
        return super().twist(pose,t)


class Teach360(Return360):
    def lose(self,t,frame_id):
        self.traversal_graph.seal()
        super().lose(t,frame_id)
        self.traversal=TeachReturn(self.traversal_graph)

    def receive(self,**kw):
        command,trace=super().receive(**kw)
        if trace['stage']=='explore':
            g=self.explorer.memory.self_map
            bad=next((e['reason'] for e in self.explorer.navigator.events if e['t']>=kw['t']-.200001 and e['reason'] in
                ('controller_no_progress','navigation_action_aborted')),None)
            self.traversal_graph.observe(own_sample(trace,kw['observation'],rgb=kw['rgb'],frame_sha256=kw['frame_sha256'],
                covariance=g.odom.covariance,excluded_reason=bad),self.goal,trace['goal']['candidates'])
        trace['teach']=dict(nodes=len(self.traversal_graph.nodes),edges=len(self.traversal_graph.edges),
            goal_node=self.traversal_graph.goal_node,uncertain_edges=sum(e['uncertain'] for e in self.traversal_graph.edges),
            match=None if self.traversal is None else self.traversal.last_match,
            failure=None if self.traversal is None else self.traversal.failure)
        return command,trace


def attach(controller,*,teach_capture='off'):
    if teach_capture=='off':return controller
    if teach_capture!=OPTION:raise ValueError('UNKNOWN_TEACH_CAPTURE')
    if type(controller) is not Return360:raise ValueError('FROZEN_RETURN360_REQUIRED')
    if 'receive' in controller.__dict__:raise ValueError('ATTACH_TEACH_BEFORE_RECEIVE_WRAPPER')
    controller.__class__=Teach360;controller.traversal_graph=TeachGraph(controller.robot_id);controller.traversal=None
    return controller
