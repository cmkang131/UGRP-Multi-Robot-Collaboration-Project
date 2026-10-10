"""Ulrich & Nourbakhsh AAAI 2000 sections 3-6, dynamic-only assistive mode.

Per-robot candidate/reference histogram queues; own command odometry only.
Unspecified numerical details and platform adaptations are preregistered in
experiments/2026-10-08-ulrich-floor-contact/README.md. No morphology is in the paper.
"""
from collections import deque
import hashlib
import math
import cv2
import numpy as np
from harness.wall_floor_boundary import hsi, histograms, _plane, to_scan

OPTION = 'floor_appearance_ulrich_v1'
CONFIG = dict(process_size=[320,260], gaussian_kernel=5, histogram_bins=256,
              histogram_window=5, hue_count_threshold=60, intensity_count_threshold=80,
              min_intensity=10/255, min_saturation=.1, reference_forward_m=[0.,1.],
              reference_half_width_m=.30, promotion_distance_m=1., reject_angle_deg=18.,
              reference_queue_length=10, max_range_m=4., mode='assistive_dynamic_only',
              morphology='none')


def first_contacts(floor, support, columns, self_top):
    """First non-floor from a supported floor seed. Never jump masked gaps."""
    uv, ids = [], []
    censored = 0
    for j, u in enumerate(columns):
        valid = np.flatnonzero(support[:,u])
        if not len(valid):
            continue
        bottom = int(valid[-1])
        if bottom >= self_top[j] or not floor[bottom,u]:
            censored += 1
            continue
        v = bottom
        while v >= 0 and support[v,u] and floor[v,u]:
            v -= 1
        if v >= 0 and support[v,u]:
            ids.append(j)
            uv.append((int(u),v))
    return np.array(ids,int), np.array(uv,float).reshape(-1,2), censored


class UlrichFloorState:
    """One state per robot/episode. No implicit global state or static map inputs."""
    def __init__(self, robot_id):
        if not isinstance(robot_id,str) or not robot_id:
            raise ValueError('EXPLICIT_OWN_ROBOT_REQUIRED')
        self.robot_id = robot_id
        self.candidates = []
        self.references = deque(maxlen=CONFIG['reference_queue_length'])
        self.last_frame = None
        self.last_fingerprint = None
        self.last_result = None

    def update(self, frame_id, pose, hue_histogram, intensity_histogram):
        """Paper §5: reject turns BEFORE promoting distance; §6: last ten."""
        pose = np.asarray(pose,float)
        if pose.shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('FINITE_OWN_ODOMETRY_REQUIRED')
        self.candidates.append(dict(frame_id=frame_id,pose=pose.copy(),
            hue=np.array(hue_histogram,copy=True),intensity=np.array(intensity_histogram,copy=True)))
        remaining, rejected, promoted = [], [], []
        for item in self.candidates:
            angle = abs(math.atan2(math.sin(pose[2]-item['pose'][2]),math.cos(pose[2]-item['pose'][2])))
            if angle > math.radians(CONFIG['reject_angle_deg']):
                rejected.append(item['frame_id'])
            elif np.linalg.norm(pose[:2]-item['pose'][:2]) > CONFIG['promotion_distance_m']:
                self.references.append(item)
                promoted.append(item['frame_id'])
            else:
                remaining.append(item)
        self.candidates = remaining
        accepted_hue = np.zeros(CONFIG['histogram_bins'],bool)
        accepted_intensity = np.zeros_like(accepted_hue)
        for item in self.references:
            # Histogram OR means acceptance by ANY validated reference, not sum.
            accepted_hue |= item['hue'] >= CONFIG['hue_count_threshold']
            accepted_intensity |= item['intensity'] >= CONFIG['intensity_count_threshold']
        return accepted_hue, accepted_intensity, dict(promoted=promoted,rejected_turn=rejected,
            candidate_count=len(remaining),reference_frame_ids=[r['frame_id'] for r in self.references])

    def detect(self, image, cm, *, frame_id, odometry_pose, valid_image, self_top):
        if type(frame_id) is not int or frame_id < 0:
            raise ValueError('INTEGER_FRAME_ID_REQUIRED')
        pose = np.asarray(odometry_pose,float)
        if pose.shape != (3,) or not np.isfinite(pose).all():
            raise ValueError('FINITE_OWN_ODOMETRY_REQUIRED')
        image = np.asarray(image)
        if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
            raise ValueError('UINT8_BGR_REQUIRED')
        if np.asarray(valid_image).shape != image.shape[:2]:
            raise ValueError('VALID_IMAGE_SHAPE')
        identity = hashlib.sha256(image.tobytes()+pose.tobytes()+np.asarray(cm.origin).tobytes()
            +np.asarray(cm._rot).tobytes()+np.asarray(cm.columns).tobytes()
            +np.asarray(self_top).tobytes()+np.asarray(valid_image).tobytes()).hexdigest()
        if frame_id == self.last_frame:
            if identity != self.last_fingerprint:
                raise ValueError('SAME_FRAME_CHANGED')
            return self.last_result
        if self.last_frame is not None and frame_id < self.last_frame:
            raise ValueError('MONOTONIC_FRAMES_REQUIRED')
        from harness.active_wall_vision import modules
        intrinsic = modules()[0].K
        width,height = CONFIG['process_size']
        scale = np.array([[width/image.shape[1],0,0],[0,height/image.shape[0],0],[0,0,1.]])
        # OpenCV resize uses pixel centers: u'=(u+.5)*sx-.5.
        scale[:2,2] = (np.diag(scale)[:2]-1)/2
        k = scale@intrinsic
        filtered = cv2.GaussianBlur(cv2.resize(image,(width,height),interpolation=cv2.INTER_AREA),(5,5),0)
        support = cv2.resize(np.asarray(valid_image,np.uint8),(width,height),interpolation=cv2.INTER_NEAREST)
        support = cv2.erode(support,np.ones((5,5),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
        xyz,_,positive,_ = _plane((height,width),tuple(cm.origin),tuple(cm._rot.ravel()),tuple(k.ravel()))
        lo,hi = CONFIG['reference_forward_m']
        reference = support & positive & (xyz[...,0]>=lo) & (xyz[...,0]<=hi) & (abs(xyz[...,1])<=CONFIG['reference_half_width_m'])
        hue,_,intensity,valid_hue = hsi(filtered)
        hh,ih,h,i = histograms(hue,intensity,valid_hue,reference)
        ah,ai,diagnostics = self.update(frame_id,pose,hh,ih)
        learned = bool(self.references)
        obstacle = ((valid_hue & ~ah[h]) | ~ai[i]) & support if learned else np.zeros_like(support)
        # Restore the classification grid to the unchanged camera/scan ABI.
        native_support = cv2.resize(support.astype(np.uint8),image.shape[1::-1],interpolation=cv2.INTER_NEAREST).astype(bool) & valid_image
        native_obstacle = cv2.resize(obstacle.astype(np.uint8),image.shape[1::-1],interpolation=cv2.INTER_NEAREST).astype(bool) & native_support
        native_floor = native_support & ~native_obstacle if learned else np.zeros_like(native_support)
        ids,uv,censored = first_contacts(native_floor,native_support,np.asarray(cm.columns,int),self_top)
        xyz_native,ranges,positive,_ = _plane(image.shape[:2],tuple(cm.origin),tuple(cm._rot.ravel()),tuple(intrinsic.ravel()))
        vi=uv[:,1].astype(int);ui=uv[:,0].astype(int)
        behind = ~positive[vi,ui]
        far = ranges[vi,ui]>=CONFIG['max_range_m']
        keep = ~behind & ~far
        ids,uv,vi,ui = ids[keep],uv[keep],vi[keep],ui[keep]
        diagnostics.update(robot_id=self.robot_id,frame_id=frame_id,odometry_pose=pose.tolist(),
            reason='classified' if learned else 'untrained',reference_pixels=int(reference.sum()),
            hue_accepted_bins=int(ah.sum()),intensity_accepted_bins=int(ai.sum()),
            local_intensity_histogram=ih.tolist(),accepted_intensity_bins=np.flatnonzero(ai).tolist(),
            border_censored_columns=censored,behind_camera_rejected=int(behind.sum()),beyond_range_rejected=int(far.sum()))
        result=dict(uv=uv,xy=xyz_native[vi,ui,:2].copy(),ranges=ranges[vi,ui].copy(),column_ids=ids,
            diagnostics=diagnostics,obstacle=native_obstacle,support=native_support,floor=native_floor,
            reference=cv2.resize(reference.astype(np.uint8),image.shape[1::-1],interpolation=cv2.INTER_NEAREST).astype(bool))
        self.last_frame,self.last_fingerprint,self.last_result = frame_id,identity,result
        return result
