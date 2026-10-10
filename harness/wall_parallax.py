"""Default-off, robot-private temporal wall-point triangulation.

OpenCV LK/DLT and ORB-SLAM2 geometric checks; no scene, pose truth, measured
servo, floor intersection or peer data. References: wall-parallax/REFERENCES.md.
Pose mean/covariance MUST come from the caller's own command odometry.
"""
from collections import Counter
import math
import cv2
import numpy as np

OPTION='parallax_v1'
LK=dict(winSize=(15,15),maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,10,.03))
FEATURE=dict(maxCorners=500,qualityLevel=.3,minDistance=7,blockSize=7)
PARAMETERS=dict(history=10,detect_interval=5,fb_px=1.,roi_px=3.,max_gap_s=.5,
                parallax_cos=.9998,reprojection_chi2=5.991,pixel_sigma=1.,
                common_pitch_sigma_deg=3.,range_m=4.,cell_m=.1)


def rz(a):
    c,s=np.cos(a),np.sin(a)
    return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])


def camera(pose,origin,rotation,pitch=0.):
    c,s=np.cos(pitch),np.sin(pitch)
    ry=np.array([[c,0.,s],[0.,1.,0.],[-s,0.,c]])
    r=rz(pose[2])
    return r@origin+[*pose[:2],0.],r@ry@rotation


def projection(k,centre,rotation):
    return k@np.column_stack([rotation.T,-rotation.T@centre])


def solve(uv0,uv1,pose0,pose1,origin,rotation,k,pitch=0.):
    """Return current body-local 3D point; no assumption on its height."""
    c0,r0=camera(pose0,origin,rotation,pitch)
    c1,r1=camera(pose1,origin,rotation,pitch)
    value=cv2.triangulatePoints(projection(k,c0,r0),projection(k,c1,r1),
                               np.asarray(uv0,float).reshape(2,1),np.asarray(uv1,float).reshape(2,1))[:,0]
    if not np.isfinite(value).all() or abs(value[3])<1e-12:return None
    world=value[:3]/value[3]
    return rz(pose1[2]).T@(world-[*pose1[:2],0.])


def joint_pose_covariance(pose0,cov0,pose1,cov1):
    """Same transition F as V7CommandOdometry; retain common-history covariance."""
    delta=np.asarray(pose1)-pose0
    transition=np.eye(3)
    transition[:2,2]=[-delta[1],delta[0]]
    cross=cov0@transition.T
    out=np.block([[cov0,cross],[cross.T,cov1]])
    values,vectors=np.linalg.eigh((out+out.T)/2)
    if values.min() < -1e-7:raise ValueError('INCONSISTENT_COMMAND_POSE_COVARIANCE')
    return (vectors*np.maximum(values,0.))@vectors.T


def point_covariance(a,b,origin,rotation,k):
    # [pose_a(3), pose_b(3), uv_a(2), uv_b(2), shared extrinsic pitch(1)].
    mean=np.r_[a['pose'],b['pose'],a['uv'],b['uv'],0.]
    sigma=np.zeros((11,11))
    sigma[:6,:6]=joint_pose_covariance(a['pose'],a['cov'],b['pose'],b['cov'])
    sigma[6:10,6:10]=np.eye(4)*PARAMETERS['pixel_sigma']**2
    sigma[10,10]=math.radians(PARAMETERS['common_pitch_sigma_deg'])**2
    def evaluate(x):return solve(x[6:8],x[8:10],x[:3],x[3:6],origin,rotation,k,x[10])
    jacobian=np.zeros((3,11))
    for i in range(11):
        eps=1e-3 if 6<=i<10 else 1e-5
        plus,minus=mean.copy(),mean.copy()
        plus[i]+=eps
        minus[i]-=eps
        x,y=evaluate(plus),evaluate(minus)
        if x is None or y is None:return None
        jacobian[:,i]=(x-y)/(2*eps)
    out=jacobian@sigma@jacobian.T
    return (out+out.T)/2


def triangulate(history,origin,rotation,k):
    """ORB geometric checks on a tracked point, with command pose uncertainty."""
    if len(history)<3:return None,'insufficient_views'
    a,b=history[0],history[-1]
    c0,r0=camera(a['pose'],origin,rotation)
    c1,r1=camera(b['pose'],origin,rotation)
    baseline=float(np.linalg.norm(c1-c0))
    if baseline<1e-8:return None,'zero_baseline'
    ki=np.linalg.inv(k)
    d0=r0@ki@np.r_[a['uv'],1.]
    d1=r1@ki@np.r_[b['uv'],1.]
    cosine=float(d0@d1/(np.linalg.norm(d0)*np.linalg.norm(d1)))
    if not 0.<cosine<PARAMETERS['parallax_cos']:return None,'low_parallax'
    local=solve(a['uv'],b['uv'],a['pose'],b['pose'],origin,rotation,k)
    if local is None:return None,'nonfinite'
    world=rz(b['pose'][2])@local+[*b['pose'][:2],0.]
    for h in history:
        centre,rot=camera(h['pose'],origin,rotation)
        optical=rot.T@(world-centre)
        if optical[2]<=0:return None,'behind_camera'
        pixel=k@optical
        error=pixel[:2]/pixel[2]-h['uv']
        if error@error>PARAMETERS['reprojection_chi2']:return None,'reprojection'
    radius=float(np.linalg.norm(local-origin))
    if radius>PARAMETERS['range_m']:return None,'beyond_4m'
    cov=point_covariance(a,b,origin,rotation,k)
    if cov is None or not np.isfinite(cov).all():return None,'nonfinite_covariance'
    ray=(local-origin)/max(radius,1e-12)
    sigma=math.sqrt(max(0.,float(ray@cov@ray)))
    s0=PARAMETERS['cell_m']**2/12
    confidence=float(s0/(s0+np.trace(cov[:2,:2])/2))
    return dict(uv=b['uv'].tolist(),xyz=local.tolist(),xy=local[:2].tolist(),range_m=radius,
        covariance=cov.tolist(),depth_sigma_m=sigma,inverse_depth_sigma=sigma/max(radius**2,1e-12),
        confidence=confidence,baseline_m=baseline,parallax_deg=math.degrees(math.acos(np.clip(cosine,-1,1))),
        views=len(history),anchor_frame=a['frame_id']), 'accepted'


def roi_mask(shape,columns,rows):
    """Only interpolate adjacent valid legacy contact columns; never bridge gaps."""
    mask=np.zeros(shape[:2],np.uint8)
    for i in range(len(columns)-1):
        if not np.isfinite(rows[i:i+2]).all():continue
        for x in range(max(0,math.ceil(columns[i])),min(shape[1]-1,math.floor(columns[i+1]))+1):
            y=rows[i]+(x-columns[i])*(rows[i+1]-rows[i])/(columns[i+1]-columns[i])
            lo,hi=max(0,math.ceil(y-3)),min(shape[0],math.floor(y+3)+1)
            mask[lo:hi,x]=255
    return mask


class ParallaxWallDetector:
    def __init__(self,robot_id,*,intrinsic,wall_detector='off'):
        if wall_detector not in ('off',OPTION):raise ValueError('UNKNOWN_WALL_DETECTOR')
        self.option,self.robot_id=wall_detector,robot_id
        self.k=np.asarray(intrinsic,float).copy()
        self.previous=None
        self.tracks=[]
        self.key=None
        self.last_t=-math.inf
        self.last_frame=-1
        self.step=0
        self.next_id=0

    def reset(self):
        self.previous=None
        self.tracks=[]
        self.key=None
        self.step=0

    def observe(self,und_bgr,*,robot_id,frame_id,t,pose,covariance,camera_origin,camera_rotation,
                columns,boundary_rows,servo_key):
        if self.option!=OPTION:raise ValueError('PARALLAX_REQUIRES_EXPLICIT_OPT_IN')
        if robot_id!=self.robot_id:raise ValueError('PARALLAX_PEER_INPUT_FORBIDDEN')
        if t<=self.last_t or frame_id<=self.last_frame:raise ValueError('PARALLAX_NON_MONOTONIC_FRAME')
        pose,cov=np.asarray(pose,float),np.asarray(covariance,float)
        if pose.shape!=(3,) or cov.shape!=(3,3) or not np.isfinite(pose).all() or not np.isfinite(cov).all():
            raise ValueError('INVALID_OWN_COMMAND_POSE')
        origin,rotation=np.asarray(camera_origin,float),np.asarray(camera_rotation,float)
        key=tuple(servo_key)
        counts=Counter()
        if key!=self.key or t-self.last_t>PARAMETERS['max_gap_s']:
            counts['reset_tracks']=len(self.tracks)
            self.reset()
        self.key,self.last_t,self.last_frame=key,float(t),int(frame_id)
        gray=cv2.cvtColor(und_bgr,cv2.COLOR_BGR2GRAY)
        roi=roi_mask(gray.shape,columns,boundary_rows)
        def sample(uv):return dict(uv=np.asarray(uv,float),pose=pose.copy(),cov=cov.copy(),frame_id=int(frame_id))
        kept,points=[],[]
        if self.tracks and self.previous is not None:
            p0=np.float32([h[-1]['uv'] for _,h in self.tracks]).reshape(-1,1,2)
            p1,status,_=cv2.calcOpticalFlowPyrLK(self.previous,gray,p0,None,**LK)
            back,back_status,_=cv2.calcOpticalFlowPyrLK(gray,self.previous,p1,None,**LK)
            good=(status.ravel()!=0)&(back_status.ravel()!=0)&(np.abs(p0-back).reshape(-1,2).max(-1)<1.)
            for (tid,history),uv,valid in zip(self.tracks,p1.reshape(-1,2),good):
                if not valid or not np.isfinite(uv).all():
                    counts['lk_failure']+=1
                    continue
                x,y=np.rint(uv).astype(int)
                if not (0<=x<gray.shape[1] and 0<=y<gray.shape[0]) or not roi[y,x]:
                    counts['outside_wall_roi']+=1
                    continue
                history=(history+[sample(uv)])[-PARAMETERS['history']:]
                value,reason=triangulate(history,origin,rotation,self.k)
                counts[reason]+=1
                if value is not None:
                    points.append(dict(track_id=tid,**value))
                kept.append((tid,history))
        self.tracks=kept
        if self.step%PARAMETERS['detect_interval']==0:
            mask=roi.copy()
            for _,h in kept:cv2.circle(mask,tuple(np.rint(h[-1]['uv']).astype(int)),5,0,-1)
            features=cv2.goodFeaturesToTrack(gray,mask=mask,**FEATURE)
            if features is not None:
                for uv in features.reshape(-1,2):
                    self.tracks.append((self.next_id,[sample(uv)]))
                    self.next_id+=1
                    counts['seeded']+=1
        self.previous=gray
        self.step+=1
        return dict(points=points,counts=dict(counts),active_tracks=len(self.tracks))


def detect(legacy,*,wall_detector='off',state=None,**kwargs):
    """Lazy option boundary: off returns the identical object without inspecting inputs."""
    if wall_detector=='off':return legacy
    if wall_detector!=OPTION or state is None:raise ValueError('EXPLICIT_PARALLAX_STATE_REQUIRED')
    return state.observe(**kwargs)
