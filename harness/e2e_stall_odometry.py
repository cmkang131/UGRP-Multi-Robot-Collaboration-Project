"""Own-RGB disparity gate, Nav2 backup/replan and AMCL motion-Q comparator.

No evaluator input. Detection uses an independent, UNGATED command predictor:
zeroing the control prediction cannot disable the detector's release test.
Unknown texture / camera motion never means zero motion. This is binary visual
stationarity, not metric VO, a calibrated slip ratio, or an IMU ZUPT filter.
"""
from collections import deque
from dataclasses import asdict, dataclass
import copy
import math
import cv2
import numpy as np

GATE = 'rgb_gate_v1'
PULSE_GATE = 'rgb_pulse_gate_v1'
VO = 'rgb_vo_v1'  # metric own-RGB ground VO fused with commands: harness/e2e_rgb_vo.py
RECOVERY = 'backup_replan_v1'
NOISE = 'amcl_alpha_v1'
FLOW = dict(min_tracks=6, min_cells=2, fb_max_px=1., median_max_px=1., p90_max_px=2.,
            minimum_expected_m=.05, max_window_s=1.4, maximum_expected_yaw_rad=.02)
PROGRESS = dict(movement_time_allowance_s=10., backup_distance_m=.30, backup_time_allowance_s=10.)


@dataclass(frozen=True)
class Options:
    stall_odometry: str = 'off'
    stall_recovery: str = 'off'
    stall_noise: str = 'off'

    def __post_init__(self):
        for key, value in zip(asdict(self), (GATE, RECOVERY, NOISE)):
            allowed=('off',value,PULSE_GATE,VO) if key=='stall_odometry' else ('off',value)
            if getattr(self, key) not in allowed:
                raise ValueError('UNKNOWN_STALL_OPTION:'+key)
        if self.stall_odometry==VO and (self.stall_recovery!='off' or self.stall_noise!='off'):
            # The binary-gate recovery/noise comparators are not defined for VO.
            raise ValueError('RGB_VO_REQUIRES_RECOVERY_AND_NOISE_OFF')

    @property
    def enabled(self):
        return any(v != 'off' for v in asdict(self).values())


def flow_pair(before, after):
    """OpenCV LK forward/backward; same texture thresholds as S2 LK monitor."""
    if before.shape != (480,640,3) or after.shape != before.shape:
        raise ValueError('640x480 RGB required')
    def mask(rgb):
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
        m=np.zeros((480,640),np.uint8);m[40:380,64:576]=255
        occluded=(hsv[:,:,1]>100)|(hsv[:,:,2]<25)
        m[cv2.dilate(occluded.astype(np.uint8),np.ones((11,11),np.uint8))>0]=0
        return m
    ma,mb=mask(before),mask(after)
    a=cv2.cvtColor(before,cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(after,cv2.COLOR_RGB2GRAY)
    valid=(ma>0)&(mb>0)
    mad=float(np.mean(np.abs(a.astype(float)-b)[valid])) if valid.any() else None
    unknown=dict(status='unknown_texture',tracks=0,cells=0,median_px=None,p90_px=None,mean_abs_diff=mad)
    pts=cv2.goodFeaturesToTrack(a,maxCorners=120,qualityLevel=.01,minDistance=10,mask=ma,blockSize=7)
    if pts is None:return unknown
    cfg=dict(winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,30,.01))
    nxt,ok,_=cv2.calcOpticalFlowPyrLK(a,b,pts,None,**cfg)
    if nxt is None:return unknown
    back,ok2,_=cv2.calcOpticalFlowPyrLK(b,a,nxt,None,**cfg)
    if back is None:return unknown
    p,q=pts[:,0],nxt[:,0];xy=np.rint(q).astype(int)
    inside=(xy[:,0]>=0)&(xy[:,0]<640)&(xy[:,1]>=0)&(xy[:,1]<480)
    good=inside&ok.ravel().astype(bool)&ok2.ravel().astype(bool)&(np.max(abs(p-back[:,0]),axis=1)<FLOW['fb_max_px'])
    good[inside]&=mb[xy[inside,1],xy[inside,0]]>0
    p,q=p[good],q[good]
    cells=len(set((int(x)//160,int(y)//120) for x,y in p))
    if len(p)<FLOW['min_tracks'] or cells<FLOW['min_cells']:
        return {**unknown,'tracks':len(p),'cells':cells}
    med,p90=np.quantile(np.linalg.norm(q-p,axis=1),[.5,.9])
    still=med<=FLOW['median_max_px'] and p90<=FLOW['p90_max_px']
    return dict(status='stationary_view' if still else 'changed_view',tracks=len(p),cells=cells,
                median_px=float(med),p90_px=float(p90),mean_abs_diff=mad)


def relative(a, b):
    d=np.asarray(b,float)-a;c,s=math.cos(a[2]),math.sin(a[2])
    d[:2]=np.array([[c,s],[-s,c]])@d[:2]
    d[2]=math.atan2(math.sin(d[2]),math.cos(d[2]))
    return d


def alpha_extra(delta, suspect):
    """AMCL omni squared-motion Q: alpha .2 -> 2.0 only on suspect frames.

    Added to existing RBPF nominal Q, never recursively scaled. The 10x choice
    is a registered DEV comparator, not an adaptive rule supplied by Nav2.
    """
    if not suspect:return np.zeros(3)
    x,y,yaw=delta;trans2=x*x+y*y;rot2=yaw*yaw
    return 1.8*np.array([trans2+rot2,trans2+rot2,rot2+trans2])


class Detector:
    def __init__(self, driver, mode=GATE):
        if mode not in (GATE,PULSE_GATE):raise ValueError('UNKNOWN_RGB_DETECTOR')
        self.minimum_expected_m=.01 if mode==PULSE_GATE else FLOW['minimum_expected_m']
        self.confirmations=3 if mode==PULSE_GATE else 1
        self.streak=0;self.mode=mode
        # A bound step_callback owns the entire RBPF graph. Clone only the
        # predictor state, never that graph (or callbacks into the live owner).
        self.nominal=copy.copy(driver)
        self.nominal.__dict__=copy.deepcopy({k:v for k,v in vars(driver).items()
                                            if k not in ('step_callback','motion_filter')})
        self.nominal.step_callback=None;self.nominal.motion_filter=None
        self.frames=deque();self.last_nominal=np.asarray(self.nominal.pose)
        self.last_t=None;self.last_frame=None;self.direction=None;self.stationary_since=None
        self.suppressed=False;self.last={};self.stationary_frames=0

    def command(self,row):
        self.nominal.command(row)
        translation=row['kind'] in ('mecanum','drive') and abs(row.get('forward',0))+abs(row.get('left',0))>0 and not row.get('turn',0)
        direction=(row.get('forward',0),row.get('left',0)) if translation else None
        if row['kind'] in ('arm','look','initial_servo_command') or not translation or direction!=self.direction:
            self.frames.clear();self.stationary_since=None;self.streak=0;self.suppressed=False
        self.direction=direction

    def observe(self, *, t, frame_id, rgb, servo, sha256):
        if self.last_t is not None and (t<=self.last_t or frame_id<=self.last_frame):
            raise ValueError('FRESH_MONOTONIC_OWN_RGB_REQUIRED')
        self.nominal.advance(t);now=np.asarray(self.nominal.pose)
        delta=relative(self.last_nominal,now);self.last_nominal=now.copy()
        while self.frames and t-self.frames[0]['t']>FLOW['max_window_s']+1e-8:self.frames.popleft()
        row=dict(status='warming_up',t=t,frame_id=frame_id,sha256=sha256,nominal_delta=delta.tolist(),
                 tracks=0,cells=0,median_px=None,p90_px=None,mean_abs_diff=None)
        # Nearest earlier image providing a resolvable commanded displacement.
        for before in reversed(self.frames):
            d=relative(before['pose'],now)
            if np.linalg.norm(d[:2])<self.minimum_expected_m:continue
            if before['servo']!=servo or abs(d[2])>FLOW['maximum_expected_yaw_rad']:
                row['status']='unknown_camera_or_rotation';break
            row.update(flow_pair(before['rgb'],rgb),before_t=before['t'],before_frame_id=before['frame_id'],
                before_sha256=before['sha256'],window_expected_delta=d.tolist(),window_s=t-before['t'])
            break
        translating=self.direction is not None and np.linalg.norm(delta[:2])>1e-6
        stationary=translating and row['status']=='stationary_view'
        self.streak=self.streak+1 if stationary else 0
        self.suppressed=stationary and self.streak>=self.confirmations
        if self.suppressed:
            if self.stationary_since is None:self.stationary_since=t
            self.stationary_frames+=1
        else:self.stationary_since=None
        row.update(stationary=self.suppressed,stationary_streak=self.streak,mode=self.mode,stationary_since=self.stationary_since,
                   stationary_duration_s=0. if self.stationary_since is None else t-self.stationary_since)
        self.frames.append(dict(t=t,frame_id=frame_id,sha256=sha256,rgb=rgb.copy(),servo=dict(servo),pose=now.copy()))
        self.last_t=t;self.last_frame=frame_id;self.last=row
        return row


class Backup:
    def __init__(self):
        self.started=None;self.start_pose=None;self.events=[]

    def begin(self,t,pose):
        if self.started is None:
            self.started=t;self.start_pose=np.asarray(pose).copy()
            self.events.append(dict(t=t,event='visual_progress_timeout_backup'))

    def update(self,t,pose,stationary_s):
        if self.started is None and stationary_s>=PROGRESS['movement_time_allowance_s']:
            self.begin(t,pose)
        if self.started is None:return 'idle'
        distance=math.dist(pose[:2],self.start_pose[:2])
        done=distance>=PROGRESS['backup_distance_m']
        timeout=t-self.started>=PROGRESS['backup_time_allowance_s']
        if done or timeout:
            self.events.append(dict(t=t,event='backup_complete_replan' if done else 'backup_timeout_replan',distance_m=distance))
            self.started=None;return 'replan'
        return 'backup'


def install(goal,options=Options()):
    if not options.enabled:return goal
    if options.stall_odometry==VO:
        from harness.e2e_rgb_vo import install as vo_install
        return vo_install(goal)
    grid=goal.explorer.memory.self_map;odom=grid.odom;base=getattr(odom,'base',odom);driver=base.driver
    from harness.self_pulse_odom import PulseOdometry
    if not isinstance(driver,PulseOdometry) or driver.motion_filter is not None:
        raise ValueError('UNMODIFIED_PULSE_ODOMETRY_REQUIRED')
    detector=Detector(driver,options.stall_odometry if options.stall_odometry!='off' else GATE)
    backup=Backup();goal.e2e_stall=detector
    navigator=goal.explorer.navigator
    action_failed=navigator.action_failed
    if options.stall_recovery!='off':
        def failed(t,reason):
            # The existing ten-second progress checker otherwise blacklists
            # and emits hold before the visual window can reach ten seconds.
            if reason=='progress_timeout_blacklist' and detector.suppressed:
                backup.begin(t,driver.pose)
                navigator.progress_time=t
                return
            return action_failed(t,reason)
        navigator.action_failed=failed
    active=False
    def motion_filter(delta,variance):
        if active and options.stall_odometry!= 'off' and detector.suppressed:
            return np.zeros(3),variance  # no false certainty: Q is kept/inflated
        return delta,variance
    driver.motion_filter=motion_filter
    command=goal.command
    def commanded(row):
        detector.command(row);return command(row)
    goal.command=commanded
    receive=goal.receive
    def received(**kw):
        nonlocal active
        if kw['robot_id']!=goal.robot_id:raise ValueError('SELF_MAP_PEER_INPUT_FORBIDDEN')
        row=detector.observe(t=kw['t'],frame_id=kw['frame_id'],rgb=kw['rgb'],servo=kw['servo'],sha256=kw['frame_sha256'])
        active=True
        before=np.asarray(driver.pose)
        try:odom.advance(kw['t'])
        finally:active=False
        row['applied_delta']=relative(before,np.asarray(driver.pose)).tolist()
        row['translation_gated']=bool(options.stall_odometry!='off' and detector.suppressed)
        suspect=row['stationary'] or row['status'].startswith('unknown_')
        extra=alpha_extra(row['nominal_delta'],suspect) if options.stall_noise!='off' else np.zeros(3)
        if np.any(extra):
            for i,yaw in enumerate(grid.poses[:,2]):
                c,s=math.cos(yaw),math.sin(yaw);R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
                grid.pending_cov[i]+=R@np.diag(extra)@R.T
            c,s=math.cos(driver.pose[2]),math.sin(driver.pose[2]);R=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
            driver.covariance+=R@np.diag(extra)@R.T
            if hasattr(odom,'reporter'):odom.reporter.predict(np.zeros(3),np.diag(extra))
        row['extra_body_variance']=extra.tolist()
        action,trace=receive(**kw)
        if options.stall_recovery!='off':
            phase=backup.update(kw['t'],driver.pose,row['stationary_duration_s'])
            if phase=='backup':
                # Existing calibrated reverse pulse; no invented mixed-axis gain.
                action=dict(t=kw['t'],kind='mecanum',forward=-.35,left=0.,turn=0.,duration_s=.1)
                row['recovery']='backup'
                trace['pre_recovery_pulse']=trace.get('pulse')
                trace['pulse']=dict(reason='visual_stall_backup',blocked=False,
                    predicted_delta=driver.profiles['0:forward:-0.35:0.10']['mean_delta'])
            elif phase=='replan':
                action_failed(kw['t'],'visual_stall_after_backup')
                goal.explorer.plan=None;goal.explorer.last_plan_t=-math.inf
                detector.stationary_since=None;detector.frames.clear()
                action=dict(t=kw['t'],kind='hold');row['recovery']='replan'
                trace['pre_recovery_pulse']=trace.get('pulse')
                trace['pulse']=dict(reason='visual_stall_replan',blocked=False,predicted_delta=[0.,0.,0.])
            else:row['recovery']='idle'
        row['recovery_events']=backup.events[:];backup.events.clear()
        trace['stall_odometry']=dict(options=asdict(options),**copy.deepcopy(row))
        trace['command']=action
        goal.last_trace=copy.deepcopy(trace)
        return action,trace
    goal.receive=received
    return goal
