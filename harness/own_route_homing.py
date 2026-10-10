"""Default-off own-RGB homing gate and optional route PnP correction.

Compose the existing accelerated receive; never replace its captured base.
The original .20m / five-current-frame arrival gate remains, with visual
verification added. Rejected visual estimates never move particles.
"""
import copy
import math
from types import MethodType
import numpy as np
from harness.active_wall_mapping import compose,inverse
from harness.own_rgb_homing import OPTION,PARAMS,Memory
from harness.own_teach_capture import vertex_decision
from harness.self_pose_graph import between


def apply_pose(controller,sample,pose,t,reference):
    g=controller.explorer.memory.self_map
    delta=compose(pose,inverse(sample['pose']))
    g.poses=np.asarray([compose(delta,p) for p in g.poses])
    c,s=math.cos(delta[2]),math.sin(delta[2])
    R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
    g.pending_cov=R@g.pending_cov@R.T  # correlated own map: no variance shrink
    sample['pose']=list(g.odom.pose)
    sample['covariance']=g.odom.covariance.tolist()
    controller.offsets.append(dict(t=t,delta=delta.tolist(),source='own_rgb_pnp'))
    controller.event(t,'own_rgb_loop_correction',reference_frame=reference,delta=delta.tolist(),reset=False)
    if controller._traversed is not None:
        controller._traversed.add(sample['pose'],sample['frame_id'])
    return delta.tolist()


def install(c,*,visual_homing='off',visual_loop='off',memory=None):
    if visual_homing=='off' and visual_loop=='off':
        return c
    if visual_homing!=OPTION or visual_loop not in ('off',OPTION):
        raise ValueError('HOMING_REQUIRED_UNKNOWN_VISUAL_OPTION')
    if not getattr(c,'reference_options',None) or not c.reference_options.return_own_free_astar:
        raise ValueError('OWN_FREE_REFERENCE_REQUIRED')
    bank=memory if memory is not None else Memory(c.robot_id)
    c.visual_memory=bank
    c._visual_loop=visual_loop
    c._homing_current=None;c._homing_result=None;c._homing_verified=False
    c._homing_last_loop=-math.inf;c._homing_calls=0;c._homing_corrections=[]
    c._homing_start=np.asarray(c.graph.nodes[0]['pose']).copy()
    base_receive,base_localize,base_target,base_heading,base_snapshot=c.receive,c._localize,c._return_target,c.heading_host.command,c.snapshot

    def localize(self,sample,t):
        base_localize(sample,t)
        self._homing_executed['localize']=True
        near=math.dist(sample['pose'][:2],self._homing_start[:2])<=PARAMS['arrival_m']
        teach=self.stage!='return' and (not bank.frames or vertex_decision(between(bank.frames[-1].pose,sample['pose']))!='candidate')
        route=self.stage=='return' and visual_loop==OPTION and t-self._homing_last_loop>=PARAMS['match_interval_s']
        home=self.stage=='return' and near
        self._homing_verified=False;self._homing_result=None
        if not (teach or route or home):
            return
        kw=self._homing_input
        f=bank.extract(kw['rgb'],kw['servo'],sample['pose'],t,sample['frame_id'],kw['frame_sha256'])
        result=None
        if home:
            self._homing_executed['home_match']=True
            result=bank.recognize(f,kw['servo'],home=True)
            self._homing_verified=(result['status']=='accepted' and math.dist(result['pose'][:2],self._homing_start[:2])<=PARAMS['arrival_m'])
        elif route:
            self._homing_executed['route_match']=True
            result=bank.recognize(f,kw['servo'])
        if result is not None:
            self._homing_result=result
            if visual_loop==OPTION and result['status']=='accepted' and t-self._homing_last_loop>=PARAMS['match_interval_s']:
                delta=apply_pose(self,sample,result['pose'],t,result['reference_frame'])
                self._homing_corrections.append(dict(t=t,frame_id=sample['frame_id'],delta=delta,reference_frame=result['reference_frame']))
                self._homing_executed['loop_correction']=True
            if route or self._homing_executed.get('loop_correction'):
                self._homing_last_loop=t
        if teach:
            bank.add(f)

    def target(self,pose):
        point=base_target(pose)
        self._homing_executed['arrival_gate']=True
        if not self._homing_verified:
            self.cursor=0  # existing five-frame streak resets; no false event rollback
        return point

    def heading(host,**kw):
        if c.stage=='return' and math.dist(kw['pose'][:2],c._homing_start[:2])<=PARAMS['arrival_m'] and not c._homing_verified:
            # Fixed wrist FOV needs the saved view direction. One orientation,
            # no panorama sweep, no blind translation / inferred success.
            error=math.atan2(math.sin(c._homing_start[2]-kw['pose'][2]),math.cos(c._homing_start[2]-kw['pose'][2]))
            if abs(error)<=.06:
                return dict(t=kw['t'],kind='hold'),dict(reason='homing_unverified_hold',predicted_delta=[0.,0.,0.])
            p=np.asarray(kw['pose'][:2])+.6*np.array([math.cos(c._homing_start[2]),math.sin(c._homing_start[2])])
            # Reference own-free wrapper substitutes _return_path, so supply
            # the single view-alignment target there for this one call too.
            saved=c._return_path
            c._return_path=[p.tolist()]
            try:
                return base_heading(**{**kw,'path':[p],'goal':p})
            finally:
                c._return_path=saved
        return base_heading(**kw)

    def receive(**kw):
        c._homing_input=kw;c._homing_calls+=1;c._homing_executed=dict(receive=True)
        cmd,tr=base_receive(**kw)
        tr['visual_homing']=dict(option=visual_homing,loop=visual_loop,calls=c._homing_calls,
            executed=dict(c._homing_executed),verified_current=c._homing_verified,
            keyframes=len(bank.frames),home_keyframes=len(bank.home),
            match=copy.deepcopy(c._homing_result),corrections=len(c._homing_corrections))
        c.last_trace=copy.deepcopy(tr)
        return cmd,tr

    def snapshot(self):
        return dict(base_snapshot(),visual_homing=dict(memory=bank.snapshot(),corrections=c._homing_corrections))

    c._localize=MethodType(localize,c);c._return_target=MethodType(target,c)
    c.heading_host.command=MethodType(heading,c.heading_host)
    c.receive=receive;c.snapshot=MethodType(snapshot,c)
    return c
