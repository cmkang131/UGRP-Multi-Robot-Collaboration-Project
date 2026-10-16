"""Own-keyframe retrieval and bounded active views after an open setdown.

Place candidates never certify a pose. The original ORB/RANSAC, CSM and
three-frame correction gate remains the only producer of a receipt.
"""
import copy
import math
from types import MethodType

OPTIONS = ('view5_v1', 'view5_pan_v1', 'view5_restore_v1')
VERSIONS = dict(zip(OPTIONS, (275, 276, 277)))
PARAMS = dict(candidates=5, features_min=12, pan_period_s=2.4,
              pan_pulses=[1500,1250,1750], view_period_s=12.,
              camera_move_s=.3, settle_s=.6, body_settle_s=.45,
              own_prior_only=True, metric_gate_unchanged=True,
              three_consistent_frames_required=True)


def eligible(relook, now):
    from harness.owncam_pair_beam_v2 import pose_of
    nodes=[]
    for n in relook.goal.graph.nodes:
        h=relook.history.get(n['frame_id']);s=(h or {}).get('servo',{})
        f=(h or {}).get('features',{}).get('descriptors')
        if n['t']>=now or f is None or len(f)<PARAMS['features_min']:
            continue
        if not any(all(s.get(k)==pose_of(tag)[k] for k in (3,4,5))
                   for tag in ('search','p45','inspect')):
            continue
        if not 1000<=s.get(6,0)<=2000:
            continue
        nodes.append(n)
    pose=relook.goal.explorer.local_pose
    return sorted(nodes,key=lambda n:(math.dist(n['pose'][:2],pose[:2]),n['id']))[:PARAMS['candidates']]


def install(tr, option):
    if option=='off':
        return tr
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_RELOOK_SEARCH')
    tr.relook_search=option
    for rid in ('r1','r2'):
        r=tr.robots[rid];rl=r.goal.e2e_relook
        receive,request,observe=r.goal.receive,rl.request,rl.observe
        def received(*, _receive=receive, _rl=rl, **kw):
            result=_receive(**kw)
            _rl.current['servo']=copy.deepcopy(kw['servo'])
            return result
        r.goal.receive=received
        def requested(self, now, *, seg, epoch, _request=request):
            if self.pending is not None:
                return
            _request(now,seg=seg,epoch=epoch)
            pool=eligible(self,now)
            self.pending['candidate_nodes']=[n['id'] for n in pool]
            self.pending['view_node']=None
            self.pending['matches']=[]
            self.pending['node']=pool[0]['id'] if pool else None
            # Own prior features must survive eviction while this task waits.
            self.search_history={n['frame_id']:self.history[n['frame_id']] for n in pool}
            self.emit(dict(event='e2e_relook_candidates',t=now,seg=seg,
                           nodes=self.pending['candidate_nodes'],option=option,
                           receipt=False))
        rl.request=MethodType(requested,rl)
        def observed(self, sample, now, _observe=observe):
            p=self.pending;cur=self.current
            if p is None or cur is None:
                return
            self.history.update(getattr(self,'search_history',{}))
            # No correction can be minted from a moving/pre-settle image.
            if now<getattr(self,'search_until',-1.) or cur['ref']['t_sim']<getattr(self,'search_until',-1.):
                return
            ids=p.get('candidate_nodes',[])
            ordered=([p['node']] if p['node'] in ids else [])+[i for i in ids if i!=p['node']]
            for node in ordered:
                if node!=p['node']:
                    p['matches']=[]
                    p['node']=node
                before=len(self.events)
                _observe(sample,now)
                if self.receipt is not None:
                    return
                if len(self.events)>before and self.events[-1].get('metric_status')=='accepted':
                    return
            p['matches']=[]
        rl.observe=MethodType(observed,rl)
    original=tr.step
    def stepped(now):
        out=original(now)
        if tr.state=='relook' and not tr.queue and now>=tr.queue_until:
            out+=actions(tr,now)
        return out
    tr.step=stepped
    return tr


def actions(tr, now):
    mode=tr.relook_search
    if mode=='view5_v1':
        return []
    out=[]
    from harness.owncam_pair_beam_v2 import pose_of
    from harness.e2e_rpp_path import command as rpp_command
    for rid in ('r1','r2'):
        r=tr.robots[rid];rl=r.goal.e2e_relook;p=rl.pending
        if rl.receipt is not None or not p:
            continue
        if r.servo.get(1,0)<1900:
            out.append((rid,dict(kind='hold')))
            continue
        elapsed=now-p['t']
        if mode=='view5_pan_v1':
            index=int(elapsed//PARAMS['pan_period_s'])
            if p.get('view_index')!=index:
                p['view_index']=index
                pose=pose_of('search')|{6:PARAMS['pan_pulses'][index%3]}
                tr._poses(rid,now,[(pose,PARAMS['camera_move_s'],PARAMS['settle_s'])])
                rl.search_until=tr.robot_queue_until[rid]
                tr.event(now,'own_relook_active_view',robot_id=rid,pose=pose,receipt=False)
            out.append((rid,dict(kind='hold')))
        else:
            ids=p['candidate_nodes']
            if not ids:
                out.append((rid,dict(kind='hold')))
                continue
            node=ids[int(elapsed//PARAMS['view_period_s'])%len(ids)]
            n=rl.goal.graph.nodes[node]
            pose={k:rl.search_history[n['frame_id']]['servo'][k] for k in (3,4,5,6)}
            if any(r.servo.get(k)!=v for k,v in pose.items()):
                tr._poses(rid,now,[(pose,PARAMS['camera_move_s'],PARAMS['settle_s'])])
                rl.search_until=tr.robot_queue_until[rid]
                tr.event(now,'own_relook_restore_camera',robot_id=rid,node=node,pose=pose,receipt=False)
                out.append((rid,dict(kind='hold')))
                continue
            current=r.goal.explorer.local_pose
            command,diag=rpp_command(dict(coordinate_frame=rid+'/own_odom',path_m=[current[:2].tolist()],
                status='goal_approach',heading_rad=float(n['pose'][2])),current,tr.profiles,robot_id=rid)
            if command['kind']=='mecanum':
                rl.search_until=now+command['duration_s']+PARAMS['body_settle_s']
                tr.event(now,'own_relook_restore_heading',robot_id=rid,node=node,rpp=diag,receipt=False)
            out.append((rid,command))
    return out


def compose(bundle, option):
    if option=='off':
        return ()
    if option not in OPTIONS or bundle['execution_bundle_id']!='e2e18-v273':
        raise ValueError('RELOOK_SEARCH_REQUIRES_V273')
    version=VERSIONS[option]
    bundle['e2e_options']['relook_search']=option
    bundle['relook_search_parameters']=copy.deepcopy(PARAMS)
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}',execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)
