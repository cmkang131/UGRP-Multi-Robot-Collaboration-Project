"""Opt-in multi-view vertical-plane confirmation for PR405 observations.

Own RGB only. Floor homography estimates relative camera motion; a legacy
contact is never itself evidence of a wall. Three-view reprojection, parallax,
3D plane extent, verticality and distinct-baseline persistence are required.
No confirmation falls back to the legacy detector. Default off is identity.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np

OPTION = 'strict_motion_planes_v2'

@dataclass(frozen=True)
class Parameters:
    floor_y: float = .68
    reprojection_px: float = 2.45  # sqrt(PR405's 5.991 chi-square bound)
    min_floor: int = 24
    min_baseline_m: float = .02
    distinct_baseline_m: float = .008
    max_rotation_deg: float = 10.
    min_plane: int = 12
    plane_distance_m: float = .025
    vertical_tolerance_deg: float = 15.
    min_height_m: float = .08
    min_width_m: float = .10
    min_parallax_deg: float = 1.15
    max_range_m: float = 4.


def project(k, xyz):
    p = np.asarray(xyz) @ k.T
    return p[:, :2] / p[:, 2, None]


def floor_motion(p0, p1, floor, k, origin, axes, params=Parameters()):
    """Plane-induced H decomposition, constrained by the known floor normal.

    Scale uses PR405's provisional camera height; it is not measured odometry.
    """
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    floor = np.asarray(floor, bool)
    if floor.sum() < params.min_floor:
        return None, 'few_floor_tracks'
    # Bottom-of-image features can include a board or wall. Peel off coherent
    # planes and use the floor-normal constraint, rather than assuming the
    # largest feature group is the floor. A floor may be a minority plane.
    expected = -np.asarray(axes).T @ np.array([0., 0., 1.])
    remaining=np.flatnonzero(floor)
    choices=[]
    for model_index in range(3):
        if len(remaining)<params.min_floor:break
        h,inliers=cv2.findHomography(p0[remaining],p1[remaining],cv2.RANSAC,
            params.reprojection_px,maxIters=3000,confidence=.995)
        if h is None or inliers is None or inliers.sum()<params.min_floor:break
        matched=inliers.ravel().astype(bool)
        _,rotations,translations,normals=cv2.decomposeHomographyMat(h,k)
        for r,t,normal in zip(rotations,translations,normals):
            alignment=float(normal.ravel()@expected)
            angle=math.degrees(math.acos(np.clip((np.trace(r)-1)/2,-1,1)))
            if alignment<math.cos(math.radians(20)) or angle>params.max_rotation_deg:continue
            t=t.ravel()*float(origin[2]);centre=-r.T@t
            if np.linalg.norm(centre)>.30:continue
            score=angle+20*(1-alignment)
            choices.append((score,dict(H=h,R=r,t=t,centre=centre,
                baseline_m=float(np.linalg.norm(centre)),floor_inliers=int(matched.sum()),
                floor_model_index=model_index)))
        remaining=remaining[~matched]
    if not choices:return None,'floor_pose_ambiguous'
    return min(choices,key=lambda v:v[0])[1],'ok'


def reconstruct(p0, p1, previous_uv, motion, previous_motion, k, origin, axes,
                params=Parameters()):
    """Triangulate and verify the same points against a third, past view."""
    n = len(p0)
    if motion is None or motion['baseline_m'] < params.min_baseline_m:
        return np.empty((0, 3)), np.zeros(n, bool), 'insufficient_translation'
    if previous_motion is None or np.linalg.norm(motion['centre']-previous_motion['centre']) < params.distinct_baseline_m:
        return np.empty((0, 3)), np.zeros(n, bool), 'need_distinct_third_view'
    p0, p1, previous_uv = map(lambda v: np.asarray(v, float), (p0, p1, previous_uv))
    r, t = motion['R'], motion['t']
    p_a = k @ np.c_[np.eye(3), np.zeros(3)]
    p_b = k @ np.c_[r, t]
    homogeneous = cv2.triangulatePoints(p_a, p_b, p0.T, p1.T).T
    with np.errstate(divide='ignore', invalid='ignore'):
        x = homogeneous[:, :3] / homogeneous[:, 3, None]
        current = x @ r.T + t
        past = x @ previous_motion['R'].T + previous_motion['t']
        b0 = np.c_[p0, np.ones(n)] @ np.linalg.inv(k).T
        b1 = (np.c_[p1, np.ones(n)] @ np.linalg.inv(k).T) @ r
        cosine = (b0*b1).sum(1)/(np.linalg.norm(b0, axis=1)*np.linalg.norm(b1, axis=1))
        error0 = np.linalg.norm(project(k, x)-p0, axis=1)
        error1 = np.linalg.norm(project(k, current)-p1, axis=1)
        error2 = np.linalg.norm(project(k, past)-previous_uv, axis=1)
    keep = (np.isfinite(x).all(1) & (x[:, 2] > 0) & (current[:, 2] > 0) & (past[:, 2] > 0)
            & (np.linalg.norm(current, axis=1) < params.max_range_m)
            & (cosine > 0) & (cosine < math.cos(math.radians(params.min_parallax_deg)))
            & (error0 < params.reprojection_px) & (error1 < params.reprojection_px)
            & (error2 < params.reprojection_px))
    world = x @ np.asarray(axes).T + np.asarray(origin)
    return world[keep], keep, 'ok'


def vertical_planes(points, params=Parameters()):
    """RANSAC+SVD planes; require a 2D patch above the floor, not a line."""
    points = np.asarray(points, float).reshape(-1, 3)
    points = points[np.isfinite(points).all(1) & (points[:, 2] > .05)]
    remaining = points.copy()
    rng = np.random.default_rng(1401)
    result = []
    for _ in range(3):
        if len(remaining) < params.min_plane:
            break
        best = None
        for _ in range(180):
            a, b, c = remaining[rng.choice(len(remaining), 3, replace=False)]
            normal = np.cross(b-a, c-a)
            size = np.linalg.norm(normal)
            if size < 1e-5:
                continue
            normal /= size
            if abs(normal[2]) > math.sin(math.radians(params.vertical_tolerance_deg)):
                continue
            d = -normal @ a
            ids = abs(remaining @ normal+d) < params.plane_distance_m
            if best is None or ids.sum() > best.sum():
                best = ids
        if best is None or best.sum() < params.min_plane:
            break
        support = remaining[best]
        centre = np.mean(support, axis=0)
        _, singular, vt = np.linalg.svd(support-centre, full_matrices=False)
        normal = vt[-1]
        d = -float(normal @ centre)
        tangent = np.array([-normal[1], normal[0], 0.])
        tangent /= np.linalg.norm(tangent)
        along = support @ tangent
        width = float(np.quantile(along, .9)-np.quantile(along, .1))
        height = float(np.quantile(support[:, 2], .9)-np.quantile(support[:, 2], .1))
        rms = float(np.sqrt(np.mean((support @ normal+d)**2)))
        if (abs(normal[2]) <= math.sin(math.radians(params.vertical_tolerance_deg))
                and width >= params.min_width_m and height >= params.min_height_m
                and singular[1] > .03 and rms < params.plane_distance_m):
            # Ground intersection, bounded by the observed plane patch's span.
            closest = -d*normal[:2]/(normal[:2] @ normal[:2])
            ends = np.array([closest+t*tangent[:2] for t in np.quantile(along, [.1, .9])])
            result.append(dict(normal=normal, d=d, segment=ends, support=len(support),
                               width_m=width, height_m=height, rms_m=rms))
        remaining = remaining[~best]
    return result


def distinct_past_view(history, motion, ids, params=Parameters()):
    """Use an older separated camera position when consecutive frames are close."""
    for old in reversed(history):
        if (np.linalg.norm(old['motion']['centre']) >= params.distinct_baseline_m
                and np.linalg.norm(old['motion']['centre']-motion['centre']) >= params.distinct_baseline_m):
            lookup={int(i): uv for i,uv in zip(old['ids'],old['uv'])}
            uv=np.array([lookup.get(int(i),[np.nan,np.nan]) for i in ids],float)
            return old['motion'],uv
    return None,None


def balanced_corners(gray):
    """Give low-texture wall regions feature slots independent of floor contrast."""
    corners=[]
    height,width=gray.shape
    for row in range(6):
        for col in range(8):
            x0=max(10,col*width//8);x1=min(width-10,(col+1)*width//8)
            y0=max(10,row*height//6);y1=min(height-10,(row+1)*height//6)
            if x1-x0<8 or y1-y0<8:continue
            pts=cv2.goodFeaturesToTrack(gray[y0:y1,x0:x1],maxCorners=25,
                qualityLevel=.01,minDistance=7,blockSize=7)
            if pts is not None:corners.extend(pts.reshape(-1,2)+[x0,y0])
    return np.asarray(corners,np.float32).reshape(-1,2)


def contact_support(segment_uv, floor_uv, gray, floor_direction):
    """A visible floor contact crosses the toward-floor direction and has
    independently tracked floor pixels immediately below a real image edge.
    An upright board's side/occlusion edge cannot pass by projection alone.
    """
    uv=np.asarray(segment_uv,float);floor=np.asarray(floor_uv,float).reshape(-1,2)
    if not np.isfinite(uv).all():return False,'invisible_contact'
    tangent=uv[1]-uv[0];length=float(np.linalg.norm(tangent))
    direction=np.asarray(floor_direction,float)
    if length<15 or np.linalg.norm(direction)<1e-6:return False,'contact_too_short'
    direction/=np.linalg.norm(direction)
    cross=abs(tangent[0]*direction[1]-tangent[1]*direction[0])/length
    if cross<math.sin(math.radians(20)):return False,'occluding_side_edge'
    samples=np.linspace(uv[0],uv[1],16)
    height,width=gray.shape
    visible=(samples[:,0]>8)&(samples[:,0]<width-9)&(samples[:,1]>8)&(samples[:,1]<height-9)
    if visible.sum()<12:return False,'invisible_contact'
    if len(floor)<3:return False,'no_adjacent_observed_floor'
    along=(floor-uv[0])@tangent/(length*length)
    nearest=uv[0]+along[:,None]*tangent
    below=(floor-nearest)@direction
    selected=(along>=0)&(along<=1)&(below>3)&(below<60)
    if selected.sum()<3 or np.ptp(along[selected])<.3:return False,'no_adjacent_observed_floor'
    samples=samples[visible]
    upper=np.rint(samples-direction*4).astype(int);lower=np.rint(samples+direction*4).astype(int)
    contrast=abs(gray[upper[:,1],upper[:,0]].astype(float)-gray[lower[:,1],lower[:,0]].astype(float))
    if (contrast>=6).mean()<.5:return False,'no_observed_contact_edge'
    return True,'observed_floor_contact'


class StrictWallVerifier:
    def __init__(self, robot_id, *, parameters=Parameters()):
        self.robot_id, self.parameters = robot_id, parameters
        self.anchor = None
        self.previous_time = -math.inf
        self.previous_frame = -1
        self.planes = []

    def _seed(self, gray, servo):
        self.uv0 = balanced_corners(gray)
        self.uv = self.uv0.copy()
        self.anchor = gray.copy()
        self.previous = gray.copy()
        self.servo = dict(servo)
        self.previous_motion = None
        self.history = []
        self.ids = np.arange(len(self.uv))
        self.planes = []
        self.age = 0

    def verify(self, observation, *, rgb, servo, robot_id, frame_id, t, camera_model=None):
        if robot_id != self.robot_id:
            raise ValueError('STRICT_WALL_PEER_INPUT_FORBIDDEN')
        if frame_id <= self.previous_frame or t <= self.previous_time:
            raise ValueError('STRICT_WALL_NON_MONOTONIC_FRAME')
        gap = t-self.previous_time
        self.previous_frame, self.previous_time = frame_id, t
        from harness.active_wall_vision import modules
        mp, _, _ = modules()
        if camera_model is not None:
            from harness.wall_lens_residual import bind_camera
            mp=bind_camera(mp,camera_model)
        image = mp.undistort(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        origin = np.asarray(observation['camera_origin'], float)
        axes = np.asarray(observation['camera_rotation'], float)
        diag = dict(frame_id=frame_id, legacy_segments=len(observation['segments']),
                    accepted_planes=0, held_planes=0, floor_pixels=[], nonfloor_pixels=[],
                    confirmed_pixels=[], baseline_m=0., status='collecting_views')
        output = dict(observation, segments=[], features=[], floor_xy=[], verification=diag)
        if self.anchor is None or servo != self.servo or gap > 2.5 or len(self.uv) < 50:
            self._seed(gray, servo)
            return output
        from harness.wall_parallax import LK
        points = self.uv.astype(np.float32).reshape(-1, 1, 2)
        nxt, ok, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, points, None, **LK)
        back, reverse, _ = cv2.calcOpticalFlowPyrLK(gray, self.previous, nxt, None, **LK)
        q = nxt.reshape(-1, 2)
        keep = (ok.ravel().astype(bool) & reverse.ravel().astype(bool)
                & (abs(back.reshape(-1, 2)-self.uv).max(1) < 1.)
                & np.isfinite(q).all(1) & (q[:, 0] > 5) & (q[:, 0] < gray.shape[1]-5)
                & (q[:, 1] > 5) & (q[:, 1] < gray.shape[0]-5))
        old, current, anchor = self.uv[keep], q[keep], self.uv0[keep]
        self.uv0, self.uv = anchor, current
        self.ids = self.ids[keep]
        self.previous = gray.copy()
        self.age += 1
        floor = ((anchor[:, 1] > gray.shape[0]*self.parameters.floor_y)
                 & (current[:, 1] > gray.shape[0]*.65))
        motion, reason = floor_motion(anchor, current, floor, mp.K, origin, axes, self.parameters)
        diag.update(status=reason, tracked=len(current), floor_tracks=int(floor.sum()))
        if motion is None:
            self.previous_motion = None
            return output
        diag.update(baseline_m=motion['baseline_m'])
        history_entry=dict(motion=motion,ids=self.ids.copy(),uv=current.copy())
        if motion['baseline_m'] < self.parameters.min_baseline_m:
            diag['status'] = 'insufficient_translation'
            self.history=(self.history+[history_entry])[-60:]
            self.previous_motion = motion
            return output
        predicted = cv2.perspectiveTransform(anchor.reshape(-1, 1, 2), motion['H']).reshape(-1, 2)
        residual = np.linalg.norm(predicted-current, axis=1)
        nonfloor = residual > self.parameters.reprojection_px
        diag['floor_pixels'] = current[floor & ~nonfloor].tolist()
        diag['nonfloor_pixels'] = current[nonfloor].tolist()
        past_motion,past_uv=distinct_past_view(self.history,motion,self.ids,self.parameters)
        xyz, valid, reason = reconstruct(anchor, current, old if past_uv is None else past_uv, motion, past_motion,
                                         mp.K, origin, axes, self.parameters)
        self.history=(self.history+[history_entry])[-60:]
        self.previous_motion = motion
        diag.update(status=reason, triangulated=int(valid.sum()))
        # Only tracked, floor-model-consistent pixels clear space.
        pix = current[floor & ~nonfloor]
        if len(pix):
            rays = np.c_[pix, np.ones(len(pix))] @ np.linalg.inv(mp.K).T @ axes.T
            with np.errstate(divide='ignore', invalid='ignore'):
                depth = -origin[2]/rays[:, 2]
                pts = origin+rays*depth[:, None]
            good = (depth > 0) & np.isfinite(pts).all(1) & (np.linalg.norm(pts-origin, axis=1) < 4)
            output['floor_xy'] = pts[good, :2].tolist()
        if not valid.any():
            return output
        xyz = xyz[nonfloor[valid]]
        proposed = vertical_planes(xyz, self.parameters)
        diag['held_planes'] = len(proposed)
        next_planes = []
        verified = []
        for plane in proposed:
            matches = [p for p in self.planes if abs(p['normal'] @ plane['normal']) > math.cos(math.radians(10))
                       and np.linalg.norm(p['segment'].mean(0)-plane['segment'].mean(0)) < .12]
            previous = min(matches, key=lambda p: abs(abs(p['d'])-abs(plane['d']))) if matches else None
            plane['hits'] = 1
            plane['centre'] = motion['centre'].copy()
            if previous is not None:
                distinct = np.linalg.norm(motion['centre']-previous['centre']) >= self.parameters.distinct_baseline_m
                plane['hits'] = previous['hits']+int(distinct)
                if not distinct:
                    plane['centre'] = previous['centre']
            next_planes.append(plane)
            if plane['hits'] < 2:
                continue
            xyz0 = np.c_[plane['segment'], np.zeros(2)]
            optical0 = (xyz0-origin) @ axes
            optical1 = optical0 @ motion['R'].T + motion['t']
            local = origin+optical1 @ axes.T
            if (optical1[:, 2] <= 0).any() or np.linalg.norm(local-origin, axis=1).max() >= 4:
                continue
            verified.append(local[:, :2].tolist())
            uv = project(mp.K, optical1)
            # Require the proposed ground intersection to be actually visible,
            # with floor tracks below it. Do not invent a contact from a side edge.
            middle=local.mean(0);close=middle.copy()
            close[:2]=origin[:2]+.85*(middle[:2]-origin[:2]);close[2]=0.
            optical_close=(close-origin)@axes
            floor_direction=project(mp.K,optical_close.reshape(1,3))[0]-uv.mean(0)
            contact_ok,contact_reason=contact_support(uv,diag['floor_pixels'],gray,floor_direction)
            if not contact_ok:
                verified.pop()
                diag.setdefault('contact_rejections',[]).append(contact_reason)
                continue
            diag['confirmed_pixels'].append(uv.tolist())
            samples = np.linspace(uv[0], uv[1], 16).round().astype(int)
            samples[:, 0] = np.clip(samples[:, 0], 1, gray.shape[1]-2)
            samples[:, 1] = np.clip(samples[:, 1], 4, gray.shape[0]-5)
            u, v = samples.T
            values = gray.astype(float)
            output['features'].append(dict(height_m=float(origin[2]), fy=mp.FY,
                contrast=float(np.median(abs(values[v-3, u]-values[v+3, u]))),
                band_std=float(np.std(values[v, u])),
                sharpness=float(np.median(abs(values[v-1, u]-values[v+1, u]))), body_settling=.7))
        self.planes = next_planes
        output['segments'] = verified
        diag.update(accepted_planes=len(verified), held_planes=len(proposed)-len(verified),
                    status='confirmed' if verified else 'no_confirmed_vertical_plane')
        return output


def verify_output(legacy, *, wall_verification='off', state=None, **kwargs):
    if wall_verification == 'off':
        return legacy
    if wall_verification != OPTION or not isinstance(state, StrictWallVerifier):
        raise ValueError('EXPLICIT_STRICT_WALL_STATE_REQUIRED')
    return state.verify(legacy, **kwargs)
