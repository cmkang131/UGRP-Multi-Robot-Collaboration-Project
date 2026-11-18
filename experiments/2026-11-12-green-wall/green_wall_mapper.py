"""Finite ras1 RGB-only floor tracking and user-specified green-wall boundary map.

Reuses PR405 native fisheye K/D and nominal command-camera chain. This is a
DEV semantic/contact mapper, NOT the strict 3-D wall-plane verifier or SLAM.
No motor-command distance is used as measured odometry. Map units are nominal
camera heights; scale, camera mount and vertical-wall geometry are unverified.
"""
import argparse
import hashlib
import json
import math
import signal
import socket
import sys
import time
from pathlib import Path

import cv2
import numpy as np

K = np.array([[619.5194540517232,0,287.68910608896766],
              [0,622.1654884818748,218.69686648455726],[0,0,1.]])
D = np.array([-.0199819517209417,-.1707593617153504,-.2568318201202376,.9650933421665181])
POSE = {1:2000,3:740,4:2320,5:1320,6:1500}
RUNTIME = Path('/home/ras1/MasterPi/tools/.ugrp_versions/strict-wall-20261014')


def camera_geometry():
    """PR405 structural command chain, copied without live joint measurements."""
    chain=json.loads(Path(__file__).with_name('camera-chain.json').read_text())
    deviation={3:54,4:53,5:89};scale=2000/180
    angle={6:math.radians((POSE[6]-1500)/scale),
           5:math.radians(90-(POSE[5]-deviation[5]-1500)/scale),
           4:math.radians(-(POSE[4]-deviation[4]-1500)/scale),
           3:math.radians((POSE[3]-deviation[3]-1500)/scale)}
    def fixed(v):
        w,x,y,z=v['quaternion_wxyz'];t=np.eye(4)
        t[:3,3]=v['translation_m']
        t[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                    [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                    [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
        return t
    t=np.eye(4);t[:3,3]=chain['floor_to_chassis_translation_m']
    for link in chain['chain']:
        t=t@fixed(link)
        if 'servo' in link:
            a=np.array(link['joint_axis'],float);a/=np.linalg.norm(a)
            x,y,z=a;b=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
            q=np.eye(4);v=angle[link['servo']]
            q[:3,:3]=np.eye(3)+math.sin(v)*b+(1-math.cos(v))*(b@b);t=t@q
    t=t@fixed(chain['camera'])
    return t[:3,3],t[:3,:3]@np.diag([1.,-1.,-1.])


def camera_axes():return camera_geometry()[1]


def axes_for_floor_normal(n):
    n=np.asarray(n,float)
    if n.shape!=(3,) or not np.isfinite(n).all() or not np.isclose(np.linalg.norm(n),1.,atol=1e-5):
        raise ValueError('invalid fixed floor normal')
    forward=np.array([0.,0.,1.])-n*n[2]
    forward/=np.linalg.norm(forward)
    return np.array([forward,-np.cross(n,forward),-n])


def masks(image):
    """User-specified green target; floor must be visibly below its bottom.

    HSV limits are explicit DEV colour heuristics, not learned scene truth.
    Closing spans 5px sensor/texture gaps. Raw green support is still required.
    """
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    raw=cv2.inRange(hsv,(32,45,15),(95,255,255))
    closed=cv2.morphologyEx(raw,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(closed)
    green=np.zeros_like(raw)
    if count>1:
        i=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        if stats[i,cv2.CC_STAT_AREA]>=1000:green[labels==i]=255
    contact=[];floor=np.zeros_like(raw)
    for x in range(12,628):
        ys=np.flatnonzero(green[:,x]);
        if len(ys)<15:continue
        y=int(ys[-1])
        if not 20<y<430:continue
        # Reject a side silhouette: continuous green above, gray below, and
        # no green farther down. Do not extend invisible/out-of-frame contacts.
        above=(raw[max(0,y-14):y-2,x]>0).mean()
        below=hsv[y+6:y+22,x]
        if above<.7 or len(below)<16 or (below[:,1]<145).mean()<.7:continue
        contact.append([x,y])
    contact=np.asarray(contact,np.float32).reshape(-1,2)
    if len(contact)>12:
        # A green object's upright side can also have gray pixels below it.
        # Exclude steep local silhouettes instead of mapping them as a foot.
        # 0.5 slope is an explicit level-camera DEV heuristic, not a universal
        # wall criterion. The camera stays fixed throughout this capture.
        left=np.maximum(0,np.arange(len(contact))-5)
        right=np.minimum(len(contact)-1,np.arange(len(contact))+5)
        slope=np.abs(contact[right,1]-contact[left,1])/np.maximum(1.,contact[right,0]-contact[left,0])
        contact=contact[slope<.5]
    else:contact=np.empty((0,2),np.float32)
    for x,y in contact.astype(int):floor[y+10:462,x]=255
    floor[(hsv[:,:,1]>=145)|(hsv[:,:,2]<20)]=0
    floor=cv2.erode(floor,np.ones((5,5),np.uint8))
    return green,floor,contact


def floor_tracks(a,b,mask_a,mask_b):
    p=cv2.goodFeaturesToTrack(a,600,.01,7,mask=mask_a,blockSize=7)
    if p is None:return None,dict(reason='no_floor_corners',tracks=0)
    q,s,_=cv2.calcOpticalFlowPyrLK(a,b,p,None,winSize=(25,25),maxLevel=4)
    if q is None:return None,dict(reason='forward_tracking_failed',tracks=0)
    back,t,_=cv2.calcOpticalFlowPyrLK(b,a,q,None,winSize=(25,25),maxLevel=4)
    if back is None:return None,dict(reason='backward_tracking_failed',tracks=0)
    uv=q[:,0];xy=np.rint(uv).astype(int)
    inside=(xy[:,0]>=0)&(xy[:,0]<640)&(xy[:,1]>=0)&(xy[:,1]<480)
    keep=(s[:,0]>0)&(t[:,0]>0)&inside&(np.linalg.norm(back[:,0]-p[:,0],axis=1)<1.)
    keep[inside]&=mask_b[xy[inside,1],xy[inside,0]]>0
    p,q=p[keep,0],q[keep,0]
    info=dict(tracks=len(p),reason='few_floor_tracks')
    # Keep PR405 strict-path minimum24 and reprojection sqrt(chi-square5.991).
    lk_count=len(p)
    def fit(p,q,method):
        info=dict(tracks=len(p),lk_tracks=lk_count,method=method,reason='few_floor_tracks')
        if len(p)<24:return None,info
        h,inliers=cv2.findHomography(p,q,cv2.RANSAC,2.45,maxIters=3000,confidence=.995)
        if h is None or inliers is None:return None,dict(info,reason='homography_failed')
        ok=inliers[:,0]>0;p,q=p[ok],q[ok]
        if len(p)<24:return None,dict(info,reason='few_floor_inliers',inliers=len(p))
        hull=cv2.contourArea(cv2.convexHull(p))
        if hull<3000:return None,dict(info,reason='floor_support_not_spread',hull_px2=hull)
        flow=float(np.median(np.linalg.norm(q-p,axis=1)))
        error=np.linalg.norm(cv2.perspectiveTransform(p[:,None],h)[:,0]-q,axis=1)
        return (h,p,q),dict(info,inliers=len(p),hull_px2=hull,
                           median_flow_px=flow,reprojection_median_px=float(np.median(error)),reason='ok')
    result,info=fit(p,q,'LK-forward-backward')
    if result is not None:return result,info
    # Same strict geometric gate after photometrically robust descriptors.
    # Hamming + mutual best matches and Lowe .75 ratio: OpenCV tutorial.
    # Added after real exposure45->142 broke LK but ORB recovered97 inliers.
    orb=cv2.ORB_create(nfeatures=2000,edgeThreshold=10,fastThreshold=10)
    ka,da=orb.detectAndCompute(a,mask_a);kb,db=orb.detectAndCompute(b,mask_b)
    if da is None or db is None or len(da)<2 or len(db)<2:return None,dict(info,reason='no_floor_descriptors')
    matcher=cv2.BFMatcher(cv2.NORM_HAMMING)
    reverse={v.queryIdx:v.trainIdx for v in matcher.match(db,da)}
    pairs=matcher.knnMatch(da,db,k=2)
    matched=[m for pair in pairs if len(pair)==2 for m,n in [pair]
             if m.distance<.75*n.distance and reverse.get(m.trainIdx)==m.queryIdx]
    p=np.float32([ka[m.queryIdx].pt for m in matched]).reshape(-1,2)
    q=np.float32([kb[m.trainIdx].pt for m in matched]).reshape(-1,2)
    return fit(p,q,'ORB-mutual-ratio')


def relative_pose(h,axes,camera_offset):
    """Calibrated floor H -> R,t/d, using positive depth and floor normal.

    Malis/Vargas decomposition as exposed by OpenCV; same nominal normal20deg
    and rotation10deg bounds as the existing strict-wall path. d=1 camera
    height, NOT metres. No actuator command or measured encoder is read.
    """
    _,rotations,translations,normals=cv2.decomposeHomographyMat(h,K)
    expected=-axes.T@np.array([0.,0.,1.]);candidates=[]
    for r,t,n in zip(rotations,translations,normals):
        angle=float(np.degrees(np.arccos(np.clip((np.trace(r)-1)/2,-1,1))))
        alignment=float(n.ravel()@expected)
        if alignment<math.cos(math.radians(20)) or angle>10:continue
        # Floor normal points toward the visible plane; forward-facing floor
        # rays must stay positive in the second view as well.
        ray=np.linalg.inv(K)@np.array([320.,420.,1.]);den=float(n.ravel()@ray)
        if den<=0 or (r@(ray/den)+t.ravel())[2]<=0:continue
        camera_delta=axes@(-r.T@t).ravel()
        body_r=axes@r.T@axes.T
        body_delta=camera_delta+(np.eye(3)-body_r)@camera_offset
        candidates.append(dict(x=float(body_delta[0]),y=float(body_delta[1]),
            yaw_deg=float(np.degrees(np.arctan2(body_r[1,0],body_r[0,0]))),
            camera_height_change=float(camera_delta[2]),floor_normal_alignment=alignment,
            camera_x=float(camera_delta[0]),camera_y=float(camera_delta[1]),
            camera_rotation_initial_to_current=r.tolist(),
            rotation_deg=angle,unit='initial nominal camera height',metric_verified=False))
    if len(candidates)!=1:return None,('pose_ambiguous' if candidates else 'pose_floor_normal_mismatch')
    return candidates[0],'nominal_floor_pose'


class Mapper:
    def __init__(self,profile=None):
        origin,self.axes=camera_geometry();self.offset=origin/origin[2]
        if profile is not None:
            if profile['pose']!={str(k):v for k,v in POSE.items()}:raise ValueError('floor profile camera pose differs')
            if profile['K']!=K.tolist() or profile['D']!=D.tolist():raise ValueError('floor profile lens differs')
            self.axes=axes_for_floor_normal(profile['floor_normal_camera'])
        self.to_anchor=np.eye(3);self.pose_history=[dict(x=0.,y=0.,yaw_deg=0.)]
        self.previous=None;self.previous_floor=None;self.lost=False
        self.boundaries=[];self.views=[];self.accepted=0
        self.maps=cv2.fisheye.initUndistortRectifyMap(K,D,np.eye(3),K,(640,480),cv2.CV_32FC1)

    def ground(self,p):
        rays=np.c_[p,np.ones(len(p))]@np.linalg.inv(K).T@self.axes.T
        valid=rays[:,2]<-.03
        out=np.full((len(p),2),np.nan)
        out[valid]=rays[valid,:2]/(-rays[valid,2,None])
        return out

    def update(self,raw):
        image=cv2.remap(raw,*self.maps,cv2.INTER_LINEAR)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        green,floor,contact=masks(image)
        info=dict(reason='anchor',tracks=0,inliers=0,contact_pixels=len(contact))
        evidence=None
        if self.previous is not None and not self.lost:
            evidence,info=floor_tracks(self.previous,gray,self.previous_floor,floor)
            info['contact_pixels']=len(contact)
            if evidence is None:self.lost=True
            else:
                h,p,q=evidence
                self.to_anchor=self.to_anchor@np.linalg.inv(h)
                self.to_anchor/=self.to_anchor[2,2]
                self.accepted+=1
                for a,b in zip(p[::6],q[::6]):
                    cv2.line(image,tuple(np.rint(a).astype(int)),tuple(np.rint(b).astype(int)),(255,200,0),1)
                    cv2.circle(image,tuple(np.rint(b).astype(int)),2,(255,200,0),-1)
        elif self.lost:info['reason']='tracking_lost_map_frozen'
        if not self.lost and len(contact)>=32:
            uv=cv2.perspectiveTransform(contact[::8,None],self.to_anchor)[:,0]
            points=self.ground(uv)
            valid=np.isfinite(points).all(1)&(np.linalg.norm(points,axis=1)<8)
            self.boundaries.append(points[valid])
            self.views.append(dict(view=len(self.views),to_anchor=self.to_anchor.tolist(),
                                   boundary_points=points[valid].tolist(),tracking=info))
        if evidence is not None:
            pose,reason=relative_pose(np.linalg.inv(self.to_anchor),self.axes,self.offset)
            info['pose_status']=reason;info['pose']=pose
            if pose is not None:self.pose_history.append(pose)
        tint=image.copy();tint[green>0]=(0,220,0)
        image=cv2.addWeighted(image,.82,tint,.18,0)
        for x,y in contact[::4].astype(int):cv2.circle(image,(x,y),2,(0,180,255),-1)
        cv2.putText(image,'GREEN: colour candidate / ORANGE: observed contact',(8,22),0,.43,(255,255,255),1)
        cv2.putText(image,'CYAN: floor tracks  '+info['reason'],(8,45),0,.46,(255,255,255),1)
        if info.get('pose') is not None:
            v=info['pose'];text='Visual pose: x%+.3f y%+.3f yaw%+.1f (height units)'%(v['x'],v['y'],v['yaw_deg'])
            cv2.putText(image,text,(8,67),0,.41,(255,255,255),1)
        self.previous=gray;self.previous_floor=floor
        return image,info

    def canvas(self):
        out=np.full((480,480,3),30,np.uint8)
        cv2.putText(out,'LOCAL CONTACT MAP - PROVISIONAL',(12,24),0,.49,(255,255,255),1)
        cv2.putText(out,'Units: nominal camera heights; mount unverified',(12,45),0,.38,(210,210,210),1)
        cv2.putText(out,'Orange: green-wall contact / unseen is unknown',(12,64),0,.38,(210,210,210),1)
        # Origin is initial camera ground projection, not measured chassis pose.
        cv2.putText(out,'White: nominal body path; current robot=0,0',(12,83),0,.4,(210,210,210),1)
        last=self.pose_history[-1];yaw=math.radians(last['yaw_deg'])
        rotation=np.array([[math.cos(yaw),math.sin(yaw)],[-math.sin(yaw),math.cos(yaw)]])
        def pixel(p):
            p=rotation@(np.asarray(p)-[last['x'],last['y']])
            return int(240-p[1]*75),int(445-p[0]*75)
        for f in range(5):
            cv2.line(out,(15,445-f*75),(465,445-f*75),(55,55,55),1)
        for pts in self.boundaries:
            for p in pts:
                x,y=pixel(p+self.offset[:2])
                if 0<=x<480 and 100<=y<470:cv2.circle(out,(x,y),2,(0,180,255),-1)
        for a,b in zip(self.pose_history,self.pose_history[1:]):
            cv2.line(out,pixel([a['x'],a['y']]),pixel([b['x'],b['y']]),(255,255,255),2)
        last=self.pose_history[-1]
        cv2.drawMarker(out,pixel([last['x'],last['y']]),(255,255,255),cv2.MARKER_TRIANGLE_UP,14,2)
        cv2.putText(out,'3-D vertical wall NOT independently verified',(10,474),0,.4,(0,200,255),1)
        return out


def run():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--move',action='store_true',help='enable finite chassis pulses')
    p.add_argument('--pairs',type=int,default=3,choices=range(1,7))
    p.add_argument('--output',type=Path,default=Path.home()/'green-wall-runs')
    p.add_argument('--control-runtime',type=Path,default=RUNTIME)
    p.add_argument('--floor-profile',type=Path,help='explicit fixed RGB-fitted floor orientation; default structural nominal')
    a=p.parse_args();root=a.output/time.strftime('%Y%m%d-%H%M%S');root.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.control_runtime));import masterpi_control as c
    if socket.gethostname()!='ras1':raise RuntimeError('ras1 only')
    lease=c.acquire_actuator_lease(owner='codex:green-wall-floor-map')
    motors=c.MotorTransport();c._active_motor_transport=motors
    profile=json.loads(a.floor_profile.read_text()) if a.floor_profile else None
    cap=None;writer=None;errors=[];frames=[];commands=[];mapper=Mapper(profile);stopped=False
    def interrupt(*_):raise RuntimeError('signal/watchdog interrupted capture')
    for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP,signal.SIGALRM):signal.signal(s,interrupt)
    signal.alarm(90)  # Host watchdog, not a success criterion or policy timeout.
    try:
        c.stop_all(motors,context='green-map-start')
        if c.load_pose_state()!=POSE:raise RuntimeError('Expected fixed search camera pose; run --help and setup first')
        probe=c.probe_hardware()
        cap=cv2.VideoCapture(0,cv2.CAP_V4L2);cap.set(3,640);cap.set(4,480)
        if not cap.isOpened():raise RuntimeError('camera busy or unavailable')
        # Initial5 frames were not enough: real exposure changed45->142.
        # Drain45 frames before choosing the anchor; raw exposure remains logged.
        for _ in range(45):
            ok,_=cap.read()
            if not ok:raise RuntimeError('camera warmup failed')
        writer=cv2.VideoWriter(str(root/'overlay-map.avi'),cv2.VideoWriter_fourcc(*'MJPG'),3,(1120,480))
        if not writer.isOpened():raise RuntimeError('video writer unavailable')
        def observe():
            # Drain the driver buffer after each bounded movement, using fresh
            # settled frames rather than a pre-motion V4L2 buffered image.
            for _ in range(5):ok,raw=cap.read()
            if not ok or raw.shape[:2]!=(480,640):raise RuntimeError('fresh native camera frame missing')
            name='frame-%03d.jpg'%len(frames);cv2.imwrite(str(root/name),raw)
            overlay,info=mapper.update(raw)
            row=dict(image=name,sha256=hashlib.sha256((root/name).read_bytes()).hexdigest(),
                     monotonic_s=time.monotonic(),gray_mean=float(cv2.cvtColor(raw,cv2.COLOR_BGR2GRAY).mean()),tracking=info)
            frames.append(row);writer.write(np.hstack([overlay,mapper.canvas()]))
            cv2.imwrite(str(root/'latest-overlay-map.jpg'),np.hstack([overlay,mapper.canvas()]))
            print(json.dumps(dict(frame=len(frames),**info)),flush=True)
            return info
        first=observe()
        if a.move and first['contact_pixels']<32:raise RuntimeError('No visible green/gray contact; no automatic motion')
        # Same proven runtime; short65 lateral pulses, standard35 longitudinal.
        # Durations are actuator limits only, never metric distance estimates.
        # Observe wall once; then repeated forward/back motion estimates pose.
        plan=[('backward',35,.10),('forward',35,.10)]*a.pairs if a.move else []
        for direction,speed,duration in plan:
            if mapper.lost:raise RuntimeError('floor tracking lost; stopped before next pulse')
            if c.load_pose_state()!=POSE:raise RuntimeError('camera commands changed')
            command=dict(direction=direction,speed=speed,duration_s=duration,started=time.monotonic())
            commands.append(command)
            c._run_motion(motors,c.drive_speeds(direction,speed),duration)
            command['stopped']=time.monotonic();time.sleep(.2);observe()
        cv2.imwrite(str(root/'map.png'),mapper.canvas())
    except BaseException as e:errors.append(repr(e));print('ERROR '+repr(e),flush=True)
    finally:
        signal.alarm(0)
        try:c.stop_all(motors,context='green-map-final');stopped=True
        finally:
            if cap is not None:cap.release()
            if writer is not None:writer.release()
            lease.close()
        cv2.imwrite(str(root/'map.png'),mapper.canvas())
        result=dict(class_='dev',hostname=socket.gethostname(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    frames=frames,commands=commands,errors=errors,stopped=stopped,
                    accepted_floor_updates=mapper.accepted,map_frozen=mapper.lost,
                    views=mapper.views,poses=mapper.pose_history,wall_geometry_confirmed=False,
                    floor_profile=profile,camera_body_extrinsic_verified=False,
                    map_kind='user-labelled green wall contact / floor homography / nominal camera-height units',
                    metric_scale_verified=False,raw_location=str(root))
        (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print('OUTPUT '+str(root),flush=True)
    return bool(errors)


if __name__=='__main__':raise SystemExit(run())
