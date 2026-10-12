"""Own-RGB keyframe recognition and metric PnP, opt-in egomap68.

Independent OpenCV implementation of ORB-SLAM2's matching / triangulation /
relocalization gates; not a port of DBoW2 or a complete ORB-SLAM system.
Metric scale comes ONLY from the stored own-motion poses. Two-view E alone
does not supply metric translation. No world map, simulator or peer input.
"""
import hashlib
import math
from dataclasses import dataclass, field
import cv2
import numpy as np
from harness.active_camera import transform
from harness.own_teach_capture import vertex_decision
from harness.self_pose_graph import between

OPTION = 'orb_pnp_v1'
PARAMS = dict(features=1000, scale_factor=1.2, levels=8, ratio=.75,
              min_matches=15, min_pose_inliers=50, chi2=5.991,
              confidence=.99, iterations=300, max_cos_parallax=.9998,
              neighbor_keyframes=20, candidate_keyframes=5,
              match_interval_s=10., arrival_m=.20, arrival_frames=5,
              homography_px=3., essential_px=1., metric_scale='own_motion_only')


def camera_pose(pose, servo):
    """T_own_camera: camera +z forward, body +x forward / +y left / yaw CCW."""
    origin, axes = transform(servo)
    c, s = math.cos(pose[2]), math.sin(pose[2])
    body = np.array([[c,-s,0],[s,c,0],[0,0,1.]])
    T = np.eye(4)
    T[:3,:3] = body @ axes
    T[:3,3] = body @ origin + [pose[0], pose[1], 0.]
    return T


def body_pose(T, servo):
    origin, axes = transform(servo)
    body = T[:3,:3] @ axes.T
    xy = T[:3,3] - body @ origin
    return np.array([xy[0], xy[1], math.atan2(body[1,0],body[0,0])])


@dataclass
class Frame:
    frame_id: int
    t: float
    pose: np.ndarray
    camera: np.ndarray
    uv: np.ndarray
    descriptors: np.ndarray
    variance: np.ndarray
    sha256: str
    points: dict = field(default_factory=dict)


def matches(a, b):
    if len(a) < 2 or len(b) < 2:
        return []
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    # Mutual ratio check avoids many-to-one assignments in repeated tape/tiles.
    forward = {m.queryIdx:m.trainIdx for pair in matcher.knnMatch(a,b,k=2)
               if len(pair)==2 for m,n in [pair] if m.distance < PARAMS['ratio']*n.distance}
    reverse = {m.queryIdx:m.trainIdx for pair in matcher.knnMatch(b,a,k=2)
               if len(pair)==2 for m,n in [pair] if m.distance < PARAMS['ratio']*n.distance}
    return [(i,j) for i,j in forward.items() if reverse.get(j)==i]


def projection(T, K):
    return K @ np.linalg.inv(T)[:3]


def reprojection(points, T, K):
    C = (points-T[:3,3]) @ T[:3,:3]
    q = C @ K.T
    with np.errstate(divide='ignore',invalid='ignore'):
        uv = q[:,:2]/q[:,2:]
    return uv, C[:,2]


def triangulate(a, b, K):
    pairs = matches(a.descriptors,b.descriptors)
    if not pairs:
        return 0
    ia,ib = np.asarray(pairs).T
    p,q = a.uv[ia],b.uv[ib]
    rays = []
    for uv,T in ((p,a.camera),(q,b.camera)):
        v = np.column_stack([uv,np.ones(len(uv))]) @ np.linalg.inv(K).T @ T[:3,:3].T
        rays.append(v/np.linalg.norm(v,axis=1)[:,None])
    cosine = np.sum(rays[0]*rays[1],axis=1)
    X = cv2.triangulatePoints(projection(a.camera,K),projection(b.camera,K),p.T,q.T).T
    with np.errstate(divide='ignore',invalid='ignore'):
        X = X[:,:3]/X[:,3:]
    valid = np.isfinite(X).all(1)&(cosine>0)&(cosine<PARAMS['max_cos_parallax'])
    for f,uv,ix in ((a,p,ia),(b,q,ib)):
        projected,z = reprojection(X,f.camera,K)
        valid &= (z>0)&(np.sum((projected-uv)**2,axis=1)<=PARAMS['chi2']*f.variance[ix])
    da,db = np.linalg.norm(X-a.camera[:3,3],axis=1),np.linalg.norm(X-b.camera[:3,3],axis=1)
    ratio = db/np.maximum(da,1e-12)
    octave = np.sqrt(a.variance[ia]/b.variance[ib])
    factor = 1.5*PARAMS['scale_factor']  # LocalMapping::CreateNewMapPoints
    valid &= (ratio*factor>=octave)&(ratio<=octave*factor)
    for i,j,point in zip(ia[valid],ib[valid],X[valid]):
        a.points.setdefault(int(i),point.copy())
        b.points.setdefault(int(j),point.copy())
    return int(valid.sum())


def estimate(reference, current, K, servo):
    pairs = [(i,j) for i,j in matches(reference.descriptors,current.descriptors) if i in reference.points]
    event = dict(status='rejected',reason='insufficient_3d_matches',reference_frame=reference.frame_id,
                 matches=len(pairs),inliers=0)
    if len(pairs)<PARAMS['min_matches']:
        return event
    ia,ib = np.asarray(pairs).T
    a,b = reference.uv[ia].astype(np.float32),current.uv[ib].astype(np.float32)
    _,hm = cv2.findHomography(a,b,cv2.RANSAC,PARAMS['homography_px'],
                              maxIters=PARAMS['iterations'],confidence=PARAMS['confidence'])
    _,em = cv2.findEssentialMat(a,b,K,method=cv2.RANSAC,prob=PARAMS['confidence'],threshold=PARAMS['essential_px'])
    event['two_view_inliers'] = max(int(hm.sum()) if hm is not None else 0,int(em.sum()) if em is not None else 0)
    if event['two_view_inliers']<PARAMS['min_matches']:
        return dict(event,reason='two_view_ransac')
    points = np.asarray([reference.points[int(i)] for i in ia],np.float64)
    # OpenCV EPNP RANSAC + LM is the available solver; no new g2o dependency.
    ok,rv,tv,indices = cv2.solvePnPRansac(points,b,K,None,iterationsCount=PARAMS['iterations'],
        reprojectionError=math.sqrt(PARAMS['chi2']),confidence=PARAMS['confidence'],flags=cv2.SOLVEPNP_EPNP)
    if not ok or indices is None or len(indices)<4:
        return dict(event,reason='pnp_ransac')
    use = indices.ravel()
    rv,tv = cv2.solvePnPRefineLM(points[use],b[use],K,None,rv,tv)
    T = np.eye(4);R=cv2.Rodrigues(rv)[0]
    T[:3,:3]=R.T;T[:3,3]=-R.T@tv.ravel()
    predicted,z = reprojection(points,T,K)
    errors = np.sum((predicted-b)**2,axis=1)
    good = (z>0)&(errors<=PARAMS['chi2']*current.variance[ib])
    event.update(inliers=int(good.sum()),reprojection_rmse_px=float(np.sqrt(errors[good].mean())) if good.any() else None)
    if event['inliers']<PARAMS['min_pose_inliers']:
        return dict(event,reason='fewer_than_50_pose_inliers')
    pose = body_pose(T,servo)
    if not np.isfinite(pose).all():
        return dict(event,reason='nonfinite_pose')
    return dict(event,status='accepted',reason='pnp_verified',pose=pose.tolist(),
                relative_to_reference=between(reference.pose,pose).tolist())


class Memory:
    def __init__(self, robot_id='r3'):
        from harness.active_wall_vision import modules
        self.camera = modules()[0]
        self.K = self.camera.K.copy()
        self.robot_id=robot_id
        self.frames=[];self.home=[];self.attempts=[];self.triangulated=0
        self.orb=cv2.ORB_create(nfeatures=PARAMS['features'],scaleFactor=PARAMS['scale_factor'],nlevels=PARAMS['levels'])
        self.masks={}

    def extract(self,rgb,servo,pose,t,frame_id,sha256):
        from harness.floor_goal_self_mask import body_envelopes,project_envelopes
        image=self.camera.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        key=tuple(sorted(servo.items()))
        if key not in self.masks:
            origin,axes=transform(servo)
            mask=project_envelopes(body_envelopes(servo,'camera_v3'),origin,axes.T,rgb.shape[1],rgb.shape[0])
            und=self.camera.undistort(np.repeat((mask.astype(np.uint8)*255)[:,:,None],3,axis=2))
            self.masks[key]=(und[:,:,0]==0).astype(np.uint8)*255
        k,d=self.orb.detectAndCompute(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),self.masks[key])
        return Frame(int(frame_id),float(t),np.asarray(pose).copy(),camera_pose(pose,servo),
                     np.asarray([p.pt for p in k],float).reshape(-1,2),
                     np.empty((0,32),np.uint8) if d is None else d,
                     np.asarray([PARAMS['scale_factor']**(2*p.octave) for p in k]),sha256)

    def add(self,frame,force=False):
        if self.frames and frame.frame_id<=self.frames[-1].frame_id:
            raise ValueError('CAUSAL_KEYFRAMES_REQUIRED')
        if not force and self.frames and vertex_decision(between(self.frames[-1].pose,frame.pose))=='candidate':
            return False
        for other in self.frames[-PARAMS['neighbor_keyframes']:]:
            self.triangulated+=triangulate(other,frame,self.K)
        if not self.frames or math.dist(frame.pose[:2],self.frames[0].pose[:2])<=PARAMS['arrival_m']:
            self.home.append(frame)
        self.frames.append(frame)
        return True

    def recognize(self,current,servo,*,home=False):
        bank=self.home if home else self.frames
        candidates=sorted(bank,key=lambda f:len(matches(f.descriptors,current.descriptors)),reverse=True)[:PARAMS['candidate_keyframes']]
        trials=[estimate(f,current,self.K,servo) for f in candidates]
        accepted=[r for r in trials if r['status']=='accepted']
        # Conflicting geometrically valid aliases are not averaged into a pose.
        if any(math.dist(a['pose'][:2],b['pose'][:2])>PARAMS['arrival_m'] for i,a in enumerate(accepted) for b in accepted[i+1:]):
            result=dict(status='rejected',reason='inconsistent_candidates')
        else:
            result=max(accepted,key=lambda r:r['inliers']) if accepted else max(trials,key=lambda r:r['inliers'],default=dict(status='rejected',reason='no_reference'))
        result=dict(result,t=current.t,frame_id=current.frame_id,scope='home' if home else 'route',trials=trials)
        self.attempts.append(result)
        return result

    def snapshot(self):
        return dict(option=OPTION,robot_id=self.robot_id,params=PARAMS,frames=len(self.frames),home_frames=len(self.home),
                    triangulated_pairs=self.triangulated,points=sum(len(f.points) for f in self.frames),
                    keyframes=[dict(frame_id=f.frame_id,t=f.t,pose=f.pose.tolist(),sha256=f.sha256,features=len(f.uv),points=len(f.points)) for f in self.frames],
                    attempts=self.attempts)
