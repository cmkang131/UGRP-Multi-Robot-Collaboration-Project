"""Default-off own-RGB/static-map S2 landmarks; no simulator/evaluation inputs.

Probabilistic Robotics (2005) 6.6/Table 6.4: Gaussian range/bearing/signature;
7.5: maximum-likelihood unknown correspondence. A partial floor edge is a
normal-distance/orientation line observation, NOT its visible midpoint posed
as a known map point. OpenCV HSV/Hough features are the camera adapter.
"""
import copy
from dataclasses import dataclass

import cv2
import numpy as np

from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_amcl_sensor import endpoints, likelihood as wall_likelihood

OPTION = 'floor_zones_doors_v1'
PARAMS = dict(hue_tolerance=12, saturation_min=20, saturation_max=150, value_min=35,
    min_component_px=300, min_line_px=40, hough_votes=30, hough_gap_px=8,
    side_offset_px=5, side_support=.8, min_segment_m=.12, max_range_m=6.,
    max_ground_fit_m=.03, max_floor_lines=4, sigma_line_m=.1,
    sigma_line_angle_rad=float(np.deg2rad(5)), sigma_range_m=.2,
    sigma_bearing_rad=float(np.deg2rad(3)), sigma_width_m=.1,
    random_fraction=.05, door_depth_jump_m=.25, door_width_m=[.2, 1.],
    door_edge_support=.45, canny=[30, 80])


def wrap(a):
    return np.arctan2(np.sin(a), np.cos(a))


def gaussian(error, sigma):
    return np.exp(-.5*(error/sigma)**2)/(np.sqrt(2*np.pi)*sigma)


def hue(rgb):
    return float(cv2.cvtColor(np.array([[rgb]], np.float32), cv2.COLOR_RGB2HSV)[0, 0, 0]/2)


class MapFeatures:
    def __init__(self, static):
        self.edges = []
        for name, r in static['regions'].items():
            color = np.fromstring(r['rgba'], sep=' ') if isinstance(r['rgba'], str) else r['rgba']
            x, y = r['center_m']; a, b = r['half_extents_m']; h = hue(color[:3])
            corners = np.array([[x-a,y-b],[x+a,y-b],[x+a,y+b],[x-a,y+b]])
            for j in range(4):
                p, q = corners[j], corners[(j+1)%4]; d = q-p
                normal = np.array([-d[1], d[0]])/np.linalg.norm(d)  # toward colored interior
                self.edges.append(dict(region=name, hue=h, a=p, b=q, normal=normal))
        self.doors = [dict(center=np.array(p['center_m']), width=float(p['width_m']))
                      for p in static.get('passages', []) if p.get('kind') == 'door']
        self.hues = sorted(set(e['hue'] for e in self.edges))


def ground(cm, pixels, K_inv):
    uv = np.asarray(pixels, float).reshape(-1, 2)
    rays = np.c_[uv, np.ones(len(uv))] @ K_inv.T @ cm._rot.T
    with np.errstate(divide='ignore', invalid='ignore'):
        scale = -cm.origin[2]/rays[:, 2]
        xyz = cm.origin+scale[:, None]*rays
    valid = (rays[:, 2] < -1e-6) & (scale > 0) & np.isfinite(xyz).all(1)
    valid &= np.linalg.norm(xyz[:, :2]-cm.origin[:2], axis=1) <= PARAMS['max_range_m']
    return xyz[:, :2], valid, scale


def project(cm, xyz, K):
    cam = (np.asarray(xyz)-cm.origin) @ cm._rot
    q = cam @ K.T
    return q[:, :2]/q[:, 2, None]


def floor_features(image, cm, K_inv, mapped, clear):
    """Only actual colored/noncolored boundaries; image/mask borders excluded.

    One longest line per geometric edge (duplicate Hough votes merged). Pixel
    support on BOTH sides prevents masked/black-image edges being landmarks.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV); h,s,v = np.moveaxis(hsv.astype(float), -1, 0)
    visible = clear & (v >= PARAMS['value_min']) & (s <= PARAMS['saturation_max'])
    candidates = []
    for target in mapped.hues:
        diff = abs(h-target); diff = np.minimum(diff, 180-diff)
        mask = (visible & (diff <= PARAMS['hue_tolerance']) & (s >= PARAMS['saturation_min'])).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= PARAMS['min_component_px']); keep = keep[keep != 0]
        mask = np.isin(labels, keep).astype(np.uint8)
        edge = cv2.morphologyEx(mask, cv2.MORPH_GRADIENT, np.ones((3,3), np.uint8))*255
        lines = cv2.HoughLinesP(edge, 1, np.pi/180, PARAMS['hough_votes'],
            minLineLength=PARAMS['min_line_px'], maxLineGap=PARAMS['hough_gap_px'])
        if lines is None: continue
        for line in lines.reshape(-1, 4):
            p, q = line[:2].astype(float), line[2:].astype(float); d=q-p; length=np.linalg.norm(d)
            normal = np.array([-d[1],d[0]])/length
            uv = p+(q-p)*np.linspace(.05,.95,15)[:,None]
            sides = [uv+sign*PARAMS['side_offset_px']*normal for sign in (1,-1)]
            ii = [np.rint(z).astype(int) for z in sides]
            if any((z[:,0]<1).any() or (z[:,0]>=image.shape[1]-1).any() or
                   (z[:,1]<1).any() or (z[:,1]>=image.shape[0]-1).any() for z in ii): continue
            if any(np.mean(visible[z[:,1],z[:,0]]) < PARAMS['side_support'] for z in ii): continue
            fractions = [np.mean(mask[z[:,1],z[:,0]]) for z in ii]
            if max(fractions) < PARAMS['side_support'] or min(fractions) > 1-PARAMS['side_support']: continue
            xy, valid, _ = ground(cm, uv, K_inv)
            if not valid.all(): continue
            midpoint=xy.mean(0); _,_,vt=np.linalg.svd(xy-midpoint, full_matrices=False)
            tangent=vt[0]; norm=np.array([-tangent[1],tangent[0]])
            if np.max(abs((xy-midpoint)@norm)) > PARAMS['max_ground_fit_m']: continue
            if np.linalg.norm(xy[-1]-xy[0]) < PARAMS['min_segment_m']: continue
            inside, ok, _ = ground(cm, sides[int(np.argmax(fractions))][7:8], K_inv)
            if not ok[0]: continue
            if (inside[0]-midpoint)@norm < 0: norm=-norm
            # Pixel hue is only a signature; same-blue regions remain candidates.
            z=ii[int(np.argmax(fractions))]; observed_hue=float(np.median(h[z[:,1],z[:,0]]))
            candidates.append(dict(kind='floor_line', hue=observed_hue,
                endpoints=[xy[0].tolist(),xy[-1].tolist()], normal=norm.tolist(),
                pixels=[p.tolist(),q.tolist()], support_px=float(length)))
    selected=[]
    for f in sorted(candidates, key=lambda f:-f['support_px']):
        normal=np.array(f['normal']); mid=np.mean(f['endpoints'],axis=0)
        duplicate=any(abs(normal[0]*g['normal'][1]-normal[1]*g['normal'][0]) < np.sin(np.deg2rad(5)) and
            abs((mid-np.mean(g['endpoints'],axis=0))@normal) < .05 for g in selected)
        if not duplicate:selected.append(f)
        if len(selected) == PARAMS['max_floor_lines']:break
    return selected


def door_features(image, cm, obs, K, clear):
    """Paired range discontinuities AND vertical image edges at both jambs.

    No doorway inferred from a blank column. Both base points, visible farther
    floor returns inside the opening, and both vertical edges are required.
    """
    points=cm.floor_point(cm.t_of_row(obs.b_lo)); ranges=np.linalg.norm(points-cm.origin[:2],axis=1)
    valid=(obs.b_kind==1)&np.isfinite(points).all(1)&(ranges<PARAMS['max_range_m'])
    rows=np.rint(np.nan_to_num(obs.b_lo)).astype(int).clip(0,image.shape[0]-1)
    valid &= clear[rows, obs.columns.astype(int)]
    jumps=np.diff(ranges); pairs=valid[:-1]&valid[1:]
    left=np.flatnonzero(pairs&(jumps>PARAMS['door_depth_jump_m']))
    right=np.flatnonzero(pairs&(jumps < -PARAMS['door_depth_jump_m']))+1
    edges=cv2.Canny(image,*PARAMS['canny']); near=cv2.dilate(edges,np.ones((7,7),np.uint8))>0
    out=[]
    for i in left:
        for j in right:
            if j-i < 3:continue
            a,b=points[i],points[j]; width=float(np.linalg.norm(a-b))
            if not PARAMS['door_width_m'][0]<=width<=PARAMS['door_width_m'][1]:continue
            inside=ranges[i+1:j][valid[i+1:j]]
            if len(inside)<2 or np.median(inside) < max(ranges[i],ranges[j])+PARAMS['door_depth_jump_m']:continue
            supports=[]
            for point in (a,b):
                uv=project(cm,np.c_[np.tile(point,(24,1)),np.linspace(.025,.35,24)],K)
                z=np.rint(uv).astype(int); ok=(z[:,0]>=0)&(z[:,0]<image.shape[1])&(z[:,1]>=0)&(z[:,1]<image.shape[0])
                supports.append(float(near[z[ok,1],z[ok,0]].mean()) if ok.sum()>=12 else 0.)
            if min(supports) < PARAMS['door_edge_support']:continue
            center=(a+b)/2
            out.append(dict(kind='door', center=center.tolist(), width=width,
                pixels=[[float(obs.columns[i]),float(obs.b_lo[i])],[float(obs.columns[j]),float(obs.b_lo[j])]],
                edge_support=supports))
    return sorted(out,key=lambda q:-min(q['edge_support']))[:1]


def landmark_likelihood(mapped, px, features):
    """Gaussian feature likelihood; ML same-signature correspondence, no GT.

    Floor lines use (normal distance, normal bearing), partial endpoints only
    for finite-segment extent. Door features use (range,bearing,width). The
    fixed 5% random component handles false detections; absent features give1.
    """
    px=np.asarray(px); c,s=np.cos(px[:,2]),np.sin(px[:,2]); result=np.ones(len(px))
    for f in features:
        candidates=[]
        if f['kind']=='floor_line':
            endpoints=np.asarray(f['endpoints']); normal=np.asarray(f['normal'])
            world=np.stack((px[:,0,None]+c[:,None]*endpoints[:,0]-s[:,None]*endpoints[:,1],
                            px[:,1,None]+s[:,None]*endpoints[:,0]+c[:,None]*endpoints[:,1]),axis=-1)
            angle=px[:,2]+np.arctan2(normal[1],normal[0])
            for e in mapped.edges:
                hd=abs(e['hue']-f['hue']); hd=min(hd,180-hd)
                if hd>PARAMS['hue_tolerance']:continue
                vec=e['b']-e['a']; frac=np.clip(((world-e['a'])@vec)/(vec@vec),0,1)
                closest=e['a']+frac[:,:,None]*vec
                distance=np.sqrt(np.mean(np.sum((world-closest)**2,axis=-1),axis=1))
                da=wrap(angle-np.arctan2(e['normal'][1],e['normal'][0]))
                candidates.append(gaussian(distance,PARAMS['sigma_line_m'])*gaussian(da,PARAMS['sigma_line_angle_rad']))
            random=1/(PARAMS['max_range_m']*2*np.pi)
        else:
            xy=np.asarray(f['center']); r=np.linalg.norm(xy); bearing=np.arctan2(xy[1],xy[0])
            for d in mapped.doors:
                offset=d['center']-px[:,:2]; predicted=np.linalg.norm(offset,axis=1)
                da=wrap(bearing-(np.arctan2(offset[:,1],offset[:,0])-px[:,2]))
                candidates.append(gaussian(r-predicted,PARAMS['sigma_range_m'])*gaussian(da,PARAMS['sigma_bearing_rad'])*
                    gaussian(f['width']-d['width'],PARAMS['sigma_width_m']))
            random=1/(PARAMS['max_range_m']*2*np.pi*PARAMS['door_width_m'][1])
        hit=np.maximum.reduce(candidates) if candidates else np.zeros(len(px))
        result *= (1-PARAMS['random_fraction'])*hit+PARAMS['random_fraction']*random
    return result


@dataclass
class Measurement:
    wall: np.ndarray
    features: list
    # Mixed observation count, not fabricated floor endpoints.
    def __len__(self): return len(self.wall)+len(self.features)


def install(runtime, static):
    inner=runtime.pose.provider; pf=inner.loc._pf; previous=inner.on_frame
    mapped=MapFeatures(static); state=dict(image=None, pose=None, t=None)
    audit=dict(option=OPTION, parameters=copy.deepcopy(PARAMS), gt_inputs=False,
        association='ML over same-color map segments / mapped doors', rows=[], measured=[])
    from harness import vision_loc_protocol as vp
    mp=vp.load_vis3()[0].mp
    def frame(now,rgb):
        state['t']=float(now)
        state['image']=None if rgb is None else mp.undistort(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        return previous(now,rgb)
    inner.on_frame=frame
    update=pf.update_obs
    if update.__module__ not in ('harness.zone_solo_cyan_amcl_update','harness.zone_solo_cyan_augmented_start'):
        raise ValueError('S2 motion-triggered AMCL update required')
    visibility=runtime.visibility; original_apply=visibility.apply
    def apply(pf,obs,pose,t):
        masked=original_apply(pf,obs,pose,t)
        if masked is not None:return masked
        # Empty wall data still permits independently observed floor landmarks.
        empty=copy.deepcopy(obs);empty.b_kind[:]=0;empty.t_kind[:]=0
        return empty
    visibility.apply=apply
    def measure(cm,obs):
        pts=endpoints(cm,obs);image=state['image'];features=[]
        if image is not None:
            height,width=image.shape[:2]; yy,xx=np.indices((height,width))
            _,valid,depth=ground(cm,np.c_[xx.ravel(),yy.ravel()],mp.K_INV)
            shadow=visibility.depth_image(cm,state['pose'])
            idx=np.argmin(abs(np.arange(width)[:,None]-cm.columns[None,:]),axis=1)
            clear=valid.reshape(height,width)&(depth.reshape(height,width)<shadow[:,idx])
            if visibility.cargo is not None:clear &= ~visibility.cargo
            features=floor_features(image,cm,mp.K_INV,mapped,clear)+door_features(image,cm,obs,np.linalg.inv(mp.K_INV),clear)
        packet=Measurement(pts,features)
        audit['rows'].append(dict(t=state['t'],wall_count=len(pts),features=copy.deepcopy(features),wall_points=pts.tolist()))
        return packet
    def score(field,px,packet):
        value=wall_likelihood(field,px,packet.wall)*landmark_likelihood(mapped,px,packet.features)
        audit['measured'].append(dict(t=state['t'],features=len(packet.features),wall_count=len(packet.wall),
            score_min=float(value.min()),score_max=float(value.max())))
        return value
    selected=bind(update,endpoints=measure,likelihood=score)
    def selected_update(t,obs,pose):
        state['pose']=dict(pose)
        return selected(t,obs,pose)
    pf.update_obs=selected_update
    from harness.zone_solo_cyan_v106 import hp
    inner.runtime_contract['s2_sensor_landmarks']=dict(option=OPTION,parameters=copy.deepcopy(PARAMS))
    inner.identity_sha256=hp.base.digest(inner.runtime_contract)
    inner.source='owncam_pf_s2_landmarks:'+inner.identity_sha256[:8];runtime.pose.source=inner.source
    return audit


def runtime_class(previous):
    class Runtime(previous):
        def __init__(self,*args,sensor_landmarks='off',**kwargs):
            if sensor_landmarks not in ('off',OPTION):raise ValueError('unknown sensor_landmarks')
            if sensor_landmarks!='off' and (kwargs.get('amcl_update')!='ros_motion_v1' or
                    kwargs.get('visibility_policy')!='nav2_observed_v1'):
                raise ValueError('S2 observed AMCL required')
            super().__init__(*args,**kwargs);self.sensor_landmarks=sensor_landmarks
            if sensor_landmarks!='off':
                try:self.landmark_audit=install(self,args[0] if args else kwargs['static'])
                except Exception:self.close();raise
        def record(self):
            out=super().record()
            if self.sensor_landmarks!='off':out['sensor_landmarks']=copy.deepcopy(self.landmark_audit)
            return out
    return Runtime
