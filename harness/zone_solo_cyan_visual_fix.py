"""S2-only rejected-scan isolation and RGB pulse-stall audit (both default off).

No calibration is fitted from evaluation poses. The existing residual/support/
rank gate is retained. Failure of that gate means prediction without a visual
weight update during loaded HIGH. Unloaded acquisition is unchanged.

The flow monitor follows OpenCV's pyramidal LK + forward/backward check. It
compares stopped views around own issued pulses, masks cargo/image borders,
requires spatially distributed texture, and only logs possible stalls in DEV.
It is not metric VO, a slip ratio, or proof of contact. No GT input exists here.
"""
import copy
import cv2
import numpy as np
from harness.zone_solo_cyan_pulse_cal import Runtime as Previous, profile_key
from harness import zone_pair_highpose as high
from harness.zone_pair_highpose_partial_fix import scan_quality
from harness import vision_loc_protocol as vp

UPDATE='accepted_scan_v1'
STALL='lk_pulse_v1'
FLOW=dict(min_tracks=6,min_cells=2,fb_max_px=1.,median_max_px=1.,p90_max_px=2.,
          minimum_expected_m=.05,minimum_expected_rad=.05)


def install(pf,vl):
    """Gate BEFORE weight mutation, only on this S2 instance's loaded HIGH."""
    original=pf.update_obs
    stats=dict(candidates=0,accepted=0,rejected=0)
    def update(t,obs,pose):
        if (pf.load.loaded and high.at_high(pose) and pf.initialized and obs is not None
            and pf.settled(t) and int(obs.informative.sum())>=int(pf.measurement['min_columns'])):
            pf.predict_to(t)
            quality=scan_quality(vl,pf,obs,pose)
            stats['candidates']+=1
            if not quality['informative']:
                # No apply_scan, recovery injection, or measurement reweighting.
                # Keep the normal predict/map-prior/resample path for None RGB.
                out=original(t,None,pose)
                pf.partial_fix_last={**quality,'visual_weight_update':False,'s2_gate':UPDATE}
                stats['rejected']+=1
                return out
            stats['accepted']+=1
        return original(t,obs,pose)
    pf.update_obs=update
    return stats


def flow_pair(before,after):
    """Own RGB only; insufficient texture is UNKNOWN, never a stationary verdict."""
    if before.shape!=(480,640,3) or after.shape!=before.shape:raise ValueError('640x480 RGB required')
    def mask(rgb):
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        # Keep a broad central scene region; borders/lens ring and near-field
        # gripper/cargo are excluded, then all strongly coloured regions too.
        m=np.zeros((480,640),np.uint8);m[40:380,64:576]=255
        occluded=(hsv[:,:,1]>100)|(hsv[:,:,2]<25)
        m[cv2.dilate(occluded.astype(np.uint8),np.ones((11,11),np.uint8))>0]=0
        return m
    ma,mb=mask(before),mask(after)
    a=cv2.cvtColor(before,cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(after,cv2.COLOR_RGB2GRAY)
    pts=cv2.goodFeaturesToTrack(a,maxCorners=120,qualityLevel=.01,minDistance=10,mask=ma,blockSize=7)
    unknown=dict(status='unknown_texture',tracks=0,cells=0,median_px=None,p90_px=None)
    if pts is None:return unknown
    cfg=dict(winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    nxt,ok,_=cv2.calcOpticalFlowPyrLK(a,b,pts,None,**cfg)
    if nxt is None:return unknown
    back,ok2,_=cv2.calcOpticalFlowPyrLK(b,a,nxt,None,**cfg)
    if back is None:return unknown
    p=pts[:,0];q=nxt[:,0];fb=np.max(abs(p-back[:,0]),axis=1)
    xy=np.rint(q).astype(int);inside=(xy[:,0]>=0)&(xy[:,0]<640)&(xy[:,1]>=0)&(xy[:,1]<480)
    good=ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(fb<FLOW['fb_max_px'])&inside
    good[inside]&=mb[xy[inside,1],xy[inside,0]]>0
    p,q=p[good],q[good]
    cells=len(set((int(x)//160,int(y)//120) for x,y in p))
    if len(p)<FLOW['min_tracks'] or cells<FLOW['min_cells']:
        return {**unknown,'tracks':len(p),'cells':cells}
    d=np.linalg.norm(q-p,axis=1);med,p90=np.quantile(d,[.5,.9])
    stationary=med<=FLOW['median_max_px'] and p90<=FLOW['p90_max_px']
    return dict(status='stationary_view' if stationary else 'changed_view',tracks=len(p),cells=cells,
                median_px=float(med),p90_px=float(p90))


class Runtime(Previous):
    def __init__(self,*args,visual_update='off',visual_stall='off',**kwargs):
        if visual_update not in ('off',UPDATE) or visual_stall not in ('off',STALL):raise ValueError('unsupported visual option')
        if (visual_update!='off' or visual_stall!='off') and kwargs.get('pulse_motion_model')!='v7_pulse_cal_v1':
            raise ValueError('S2 visual options require calibrated pulse stack')
        super().__init__(*args,**kwargs)
        self.visual_update,self.visual_stall=visual_update,visual_stall
        if visual_update!='off':self.visual_stats=install(self.pose.provider.loc._pf,vp.load_vis3()[0])
        if visual_stall!='off':
            self.flow_pending=None;self.flow_frame=None;self.flow_frame_t=None;self.flow_rows=[];self.flow_streak=0
        if visual_update!='off' or visual_stall!='off':
            inner=self.pose.provider
            inner.runtime_contract['s2_visual_options']=dict(visual_update=visual_update,visual_stall=visual_stall,flow=FLOW)
            from harness.zone_solo_cyan_v106 import hp
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_visual:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def on_command(self,rid,now,action):
        super().on_command(rid,now,action)
        if self.visual_stall=='off':return
        if action['kind'] in ('arm','look'):
            self.flow_pending=None;self.flow_streak=0;self.flow_frame=None
        if action['kind']=='mecanum' and any(action.get(k,0) for k in ('forward','left','turn')):
            if self.state=='carry' and high.at_high(self.servo) and self.flow_frame is not None:
                p=self.pulse_profiles[profile_key(action,True)]
                if self.flow_pending is None:
                    self.flow_pending=dict(t=now,end=now,before=self.flow_frame.copy(),before_t=self.flow_frame_t,
                        servo=dict(self.servo),commands=[],expected_delta=[0.,0.,0.])
                pending=self.flow_pending
                old=np.asarray(pending['expected_delta']);delta=np.asarray(p['mean_delta'])
                co,si=np.cos(old[2]),np.sin(old[2])
                old[:2]+=np.array([[co,-si],[si,co]])@delta[:2];old[2]+=delta[2]
                pending['expected_delta']=old.tolist();pending['end']=now+p['times'][-1]
                pending['commands'].append(dict(t=now,**copy.deepcopy(action)))
            else:self.flow_pending=None;self.flow_streak=0

    def on_frames(self,now,frames):
        super().on_frames(now,frames)
        if self.visual_stall=='off':return
        obs,rgb=frames[self.robot_id]
        pending=self.flow_pending
        if pending is not None and now>=pending['end']-1e-9:
            d=pending['expected_delta']
            expected=np.linalg.norm(d[:2])>=FLOW['minimum_expected_m'] or abs(d[2])>=FLOW['minimum_expected_rad']
            # Short pulses need accumulation: 1 cm can project below one pixel.
            # Compose net SE(2), not path length, so reversals do not fake motion.
            if expected:
                self.flow_pending=None
                if self.state=='carry' and pending['servo']==self.servo:
                    result=flow_pair(pending['before'],rgb)
                    self.flow_streak=self.flow_streak+1 if result['status']=='stationary_view' else 0
                    row={k:v for k,v in pending.items() if k not in ('before','servo')}
                    row.update(after_t=now,frame_id=obs['frame_id'],**result,stationary_streak=self.flow_streak,
                               would_stop=result['status']=='stationary_view',policy='DEV log only')
                    self.flow_rows.append(row)
                    if row['would_stop']:self.soft('VISUAL_STALL_SUSPECTED',now)
        self.flow_frame=rgb.copy() if self.state=='carry' and high.at_high(self.servo) else None
        self.flow_frame_t=now

    def record(self):
        out=super().record()
        if self.visual_update!='off':out['visual_update']=dict(option=self.visual_update,scope='S2 loaded HIGH only',counts=dict(self.visual_stats),calibration_unchanged=True)
        if self.visual_stall!='off':out['visual_stall']=dict(option=self.visual_stall,config=FLOW,rows=self.flow_rows,control_feedback=False,policy='DEV log only; unknown is not stall')
        return out
