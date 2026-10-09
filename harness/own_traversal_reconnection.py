"""Default-off recovery bridges and local place recognition, egomap52.

Acceptance is the existing match_loop via egomap48 GraphCache, unchanged.
Only own observations are accepted; GT never enters this module.
"""
import copy
import math
import numpy as np
from harness.own_traversal_graph import TraversalGraph,TraversalReturn,Traversal360,BAD_STATUS
from harness.self_map_return_repeat import Return360
from harness.self_pose_graph import GraphOptions,between,compose,wrap,insert_row
from harness.self_graph_cache import GraphCache
from harness.self_odom_grid import OdomGrid,transform

OPTION='traversal_graph_reconnect_v1'
K=5
PLACE_RADIUS=.30  # existing node spacing, defines a place candidate, not a match score
PARTIAL_ANGLE=math.radians(54.5/2)  # camera v3 half horizontal FOV
PARTIAL_TIMEOUT=10.  # existing Nav2 spin recovery allowance
LOOP_OPTIONS=GraphOptions()


def compact(s):
    return {k:copy.deepcopy(s[k]) for k in ('t','frame_id','pose','frame_sha256')}


def match_nearest_nodes(graph,sample,node_id=None):
    """Shared adapter; no zero-argument super tied to a different graph class."""
    if node_id is not None:return TraversalGraph.match(graph,sample,node_id)
    candidates=sorted(range(len(graph.nodes)),key=lambda i:(math.dist(sample['pose'][:2],graph.nodes[i]['pose'][:2]),i))[:K]
    trials=[]
    for i in candidates:
        e=TraversalGraph.match(graph,sample,i)
        e.update(node_distance_m=math.dist(sample['pose'][:2],graph.nodes[i]['pose'][:2]),
            node_heading_difference_deg=math.degrees(float(wrap(sample['pose'][2]-graph.nodes[i]['pose'][2]))))
        trials.append(e)
    winner=next((e for e in trials if e['status']=='accepted'),None)
    if winner is None:
        winner=trials[0] if trials else dict(status='rejected',reason='empty_graph')
    return dict(winner,candidate_attempts=trials,candidates_checked=len(trials))


class ReconnectedGraph(TraversalGraph):
    def __init__(self,robot_id):
        super().__init__(robot_id)
        self.cache=GraphCache(robot_id)
        self.submaps={}
        self.reconnections=[]
        self.gaps=[]
        self.gap=None
        self.attempted=set()
        self.all_samples=[]

    def observe(self,sample,goal=None):
        if self.sealed:raise ValueError('PREFIX_ALREADY_SEALED')
        if self.last and (sample['t']<=self.last['t'] or sample['frame_id']<=self.last['frame_id']):
            raise ValueError('NON_CAUSAL_SAMPLE')
        bad=sample.get('excluded_reason') or next((s for s in BAD_STATUS if s in sample['status'].lower()),None)
        if bad and self.gap is None and self.anchor is not None:
            # Preserve the immediate pre-recovery endpoint, not a distant keyframe.
            if self.nodes[self.anchor]['frame_id']!=self.last['frame_id']:self._node(self.last)
            self.gap=dict(a=self.anchor,samples=[compact(self.last)],reason=bad)
        if self.gap is not None:self.gap['samples'].append(compact(sample))
        self.all_samples.append(compact(sample))
        super().observe(sample,goal)

    def _node(self,s,isolated=False):
        super()._node(s,isolated)
        n=self.nodes[-1];n['scan']=dict(robot_id=self.robot_id,frame_id=s['frame_id'],t=s['t'],
            pose=s['pose'],camera=s['camera'],segments=copy.deepcopy(s['segments']))
        grid=OdomGrid(self.robot_id);segments=[]
        for row in self.recent:
            if math.dist(row['pose'][:2],s['pose'][:2])>6.:continue
            local=between(s['pose'],row['pose'])
            insert_row(grid,dict(camera=row['camera'],segments=row['segments']),local)
            segments.extend(transform(np.asarray(row['segments']).reshape(-1,2),local).reshape(-1,2,2))
        self.submaps[n['id']]=dict(pose=np.asarray(s['pose']),grid=grid,segments=np.asarray(segments).reshape(-1,2,2),
            members=[r['frame_id'] for r in self.recent],interval=[r['t'] for r in self.recent])
        if isolated:return
        if self.gap is not None:
            gap=self.gap;self.gap=None
            gap['b']=n['id']
            event=self.connect(gap['a'],n['id'],'recovery_bridge',gap['samples'])
            gap['accepted']=event['accepted'];gap['match_reason']=event['reason'];self.gaps.append(gap)
        # No proximity-only join. Same place proposal, original temporal separation.
        old=[q for q in self.nodes[:-1] if s['t']-q['t']>=LOOP_OPTIONS.separation_s and
            math.dist(q['pose'][:2],s['pose'][:2])<=PLACE_RADIUS]
        old.sort(key=lambda q:(math.dist(q['pose'][:2],s['pose'][:2]),q['id']))
        linked={tuple(sorted((e['a'],e['b']))) for e in self.edges}
        for q in old[:K]:
            if tuple(sorted((q['id'],n['id']))) in linked:continue
            self.connect(q['id'],n['id'],'place_recognition',[
                compact(q),compact(n)])

    def pair_match(self,a,b):
        sm=self.submaps[a];row=self.nodes[b]['scan']
        if row['frame_id'] in sm['members']:
            return dict(accepted=False,reason='member_scan')
        if not sm['grid'].cells or not len(sm['segments']):
            return dict(accepted=False,reason='empty_reference')
        self.cache.prepare([sm],self.robot_id)
        try:
            initial=between(self.nodes[a]['pose'],self.nodes[b]['pose'])
            return self.cache.match(sm,row,initial,LOOP_OPTIONS)
        finally:
            # Do not pin evicted fields through the submap dictionary.
            sm.pop('_prepared',None)
            sm.pop('_cached_key',None)

    def connect(self,a,b,kind,samples):
        key=(a,b)
        if key in self.attempted:
            return next(e for e in self.reconnections if (e['a'],e['b'])==key)
        self.attempted.add(key)
        result=self.pair_match(a,b)
        event=dict(result,a=a,b=b,kind=kind,t=self.nodes[b]['t'])
        self.reconnections.append(event)
        if result['accepted']:
            self.edges.append(dict(a=a,b=b,kind=kind,length_m=sum(math.dist(x['pose'][:2],y['pose'][:2]) for x,y in zip(samples,samples[1:])),
                samples=copy.deepcopy(samples),relative_pose=result['relative_pose'],covariance=result['covariance'],
                match_index=len(self.reconnections)-1))
        return event

    def snapshot(self):
        out=super().snapshot()
        out.update(option=OPTION,reconnections=copy.deepcopy(self.reconnections),gaps=copy.deepcopy(self.gaps),
            unfinished_gap=copy.deepcopy(self.gap),cache=self.cache.stats(),retained_frames=len(self.all_samples))
        return out

    def match(self,sample,node_id=None):
        return match_nearest_nodes(self,sample,node_id)


class PartialReturn(TraversalReturn):
    def __init__(self,graph):
        super().__init__(graph)
        self.partial_used=set()
        self.partial_direction=1.
        self.partial_target=PARTIAL_ANGLE
        self.partial_key=None

    def localize(self,sample):
        if self.failure:return None
        key='entry' if self.route is None else self.route['nodes'][self.node_cursor]
        result=super().localize(sample)
        if result is not None and result['status']!='accepted' and self.partial_key!=key:
            self.partial_key=key
            if key in self.partial_used:
                self.failure='node_match_failed_after_partial_turn'
                return result
            self.partial_used.add(key)
            n=self.graph.nodes[result['node']] if 'node' in result else None
            angle=0. if n is None else float(wrap(n['pose'][2]-sample['pose'][2]))
            self.partial_direction=1. if angle>=0 else -1.
            # A zero difference still needs a changed view; fixed half FOV bound.
            self.partial_target=min(abs(angle),PARTIAL_ANGLE) if abs(angle)>1e-6 else PARTIAL_ANGLE
        return result

    def twist(self,pose,t):
        if self.failure:return np.zeros(3),self.failure
        if self.sweep_start is not None:
            self.sweep_rotation+=abs(float(wrap(pose[2]-self.sweep_yaw)))
            self.sweep_yaw=pose[2]
            if self.sweep_rotation>=self.partial_target or t-self.sweep_start>=PARTIAL_TIMEOUT:
                self.failure='node_match_failed_after_partial_turn'
                return np.zeros(3),self.failure
            return np.array([0.,0.,self.partial_direction*.5]),'node_match_partial_turn'
        return super().twist(pose,t)


class Reconnected360(Traversal360):
    def lose(self,t,frame_id):
        self.traversal_graph.seal()
        Return360.lose(self,t,frame_id)
        self.traversal=PartialReturn(self.traversal_graph)


def attach(controller,*,return_policy='off'):
    if return_policy=='off':return controller
    if return_policy!=OPTION:raise ValueError('UNKNOWN_RETURN_POLICY')
    if type(controller) is not Return360:raise ValueError('FROZEN_RETURN360_REQUIRED')
    controller.__class__=Reconnected360
    controller.traversal_graph=ReconnectedGraph(controller.robot_id)
    controller.traversal=None
    return controller
