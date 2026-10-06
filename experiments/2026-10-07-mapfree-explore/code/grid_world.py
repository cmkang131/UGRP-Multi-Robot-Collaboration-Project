"""Privileged pure-2D environment. Only Observation payloads cross to the actor.

Reads authored geometry and measured error tables, never imports a physics engine.
Floor visibility is an explicit idealized semantic channel (see preregistration).
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import binary_dilation, label

from harness.floor_goal import commanded_camera
from harness.self_map_prob import V7CommandOdometry
from harness.self_odom_grid import transform
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
SEARCH = {1:2000,3:740,4:2320,5:1320,6:1500}
CLOSE = {1:2000,3:807,4:1897,5:2187,6:1500}


def inverse(points,pose):
    xy = np.asarray(points)-np.asarray(pose[:2])
    c,s = math.cos(pose[2]),math.sin(pose[2])
    return xy@np.array([[c,-s],[s,c]])


def project(points,servo):
    origin,axes = commanded_camera(servo,'camera_v3')
    xyz = np.column_stack([points,np.zeros(len(points))])
    optical = (xyz-origin)@axes.T
    positive = optical[:,2] > 1e-6
    uv = np.full((len(points),2),np.nan)
    if positive.any():
        uv[positive] = cv2.fisheye.projectPoints(optical[positive].reshape(-1,1,3),np.zeros(3),np.zeros(3),
                             scaled_camera_matrix(640,480),np.asarray(CAMERA_FISHEYE_D))[0].reshape(-1,2)
    valid = positive & (uv[:,0]>=0)&(uv[:,0]<640)&(uv[:,1]>=0)&(uv[:,1]<480)
    valid &= np.linalg.norm(points-origin[:2],axis=1) <= 4.
    return uv,valid,origin


def ray_hits(origin,angles,rectangles,max_range=4.):
    """Analytic first intersection with oriented rectangles; normalized XY rays."""
    directions = np.stack([np.cos(angles),np.sin(angles)],axis=1)
    nearest = np.full(len(angles),max_range)
    for rect in rectangles:
        c,s = math.cos(rect['yaw']),math.sin(rect['yaw'])
        rot = np.array([[c,-s],[s,c]])
        start = (np.asarray(origin)-rect['center'])@rot
        delta = directions@rot
        safe = np.where(abs(delta)<1e-12,1e-12,delta)
        t1 = (-np.asarray(rect['half'])-start)/safe
        t2 = (np.asarray(rect['half'])-start)/safe
        near,far = np.minimum(t1,t2).max(1),np.maximum(t1,t2).min(1)
        hit = (far >= np.maximum(near,0)) & (far >= 0)
        nearest = np.minimum(nearest,np.where(hit,np.maximum(near,0),max_range))
    return nearest


def boxes_occupied(points,rects,padding=0.):
    occupied = np.zeros(len(points),bool)
    for r in rects:
        local = inverse(points,(*r['center'],r['yaw']))
        occupied |= np.all(np.abs(local) <= np.asarray(r['half'])+padding,axis=1)
    return occupied


def load_layout(index):
    p = next((ROOT/'configs/zone_study_scenarios_v4').glob(f's{index}_*.json'))
    scenario = json.loads(p.read_text())
    mid = scenario['map_id']
    mp = ROOT/('maps/zones_final_v3' if 'final_v3' in mid else 'maps/zones')/(mid+'.json')
    static = json.loads(mp.read_text())
    if hashlib.sha256(mp.read_bytes()).hexdigest() != scenario['eval']['setup']['map_file_sha256']:
        raise ValueError('SCENARIO_MAP_HASH_MISMATCH')
    # Fixed object dimensions from sim/zone_cargo.py; neither engine nor scene builder imported.
    halves = {'can':(.019,.019),'tile':(.03,.02),'long_beam':(.30,.02),'heavy_crate':(.12,.05),
              'trio_frame':(.27,.27),'tripod':(.27,.27),'irregular_can':(.017,.02)}
    rects = [dict(id=o['id'],center=o['center_m'],half=o['half_extents_m'],yaw=0.,kind='wall')
             for o in static['obstacles'] if not o.get('traversable',False)]
    for item in scenario['eval']['setup']['placements']:
        kind = item['kind']
        if kind not in halves and kind not in ('cyan','red','green','yellow','tri_frame'):
            raise ValueError('UNKNOWN_CARGO_GEOMETRY: '+kind)
        half = halves.get(kind,(.27,.27) if kind=='tri_frame' else (.02,.02))
        rects.append(dict(id=item['item_id'],center=item['pose_m'][:2],half=half,yaw=item['pose_m'][2],kind='object'))
    return scenario,static,rects,{'scenario_path':str(p.relative_to(ROOT)),
        'scenario_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'map_path':str(mp.relative_to(ROOT)),
        'map_sha256':hashlib.sha256(mp.read_bytes()).hexdigest()}


class GridWorld:
    def __init__(self,index,start,seed,split):
        self.scenario,self.static,self.rects,self.sources = load_layout(index)
        self.start,self.pose = np.array(start,float),np.array(start,float)
        self.model = json.loads((EXP/'sensor-model.json').read_text())
        data = np.load(EXP/'sensor-errors.npz')
        if hashlib.sha256((EXP/'sensor-errors.npz').read_bytes()).hexdigest() != self.model['sensor_errors_sha256']:
            raise ValueError('SENSOR_MODEL_CHANGED')
        self.errors = data['wall_'+split]
        self.b_errors = data['B_errors_'+split]
        self.b_model = self.model['B'][split]
        self.sensor_rng = np.random.default_rng(seed)
        self.motion_rng = np.random.default_rng(seed+1_000_000)
        self.motion = V7CommandOdometry()
        self.motion.step_callback = self._motion_step
        self.distance = 0.
        self.collisions = 0
        self.path = [self.pose.tolist()]
        self.events_applied = set()
        self.sensor_counters = {'visible_wall_rays':0,'detected_wall_rays':0,'row_correct_draws':0,
                                'B_positive_frames':0,'B_detections':0,'B_false_components':0}
        x0,x1,y0,y1 = self.static['bounds_m']
        xs = np.arange(math.floor(x0/.1),math.ceil(x1/.1))*.1+.05
        ys = np.arange(math.floor(y0/.1),math.ceil(y1/.1))*.1+.05
        x,y = np.meshgrid(xs,ys)
        self.floor = np.stack([x.ravel(),y.ravel()],1)
        self.floor_shape = x.shape
        blocked = boxes_occupied(self.floor,self.rects).reshape(x.shape)
        labels,_ = label(~blocked)
        j = int(np.argmin(np.linalg.norm(self.floor-self.start[:2],axis=1)))
        self.reachable_floor = (labels.ravel()==labels.ravel()[j]) & ~blocked.ravel()
        self.seen_floor = set()
        self.door_attempts,self.wrong_doors = 0,0
        self.candidate_attempts,self.false_candidate_attempts = 0,0
        self.last_attempt = {}
        self.collision_latched = False

    def collision(self,xy):
        # Robot's conservative empty circumscribed footprint, no pose noise margin in truth.
        radius = math.hypot(.12,.10)
        for r in self.rects:
            local = inverse([xy],(*r['center'],r['yaw']))[0]
            delta = np.maximum(abs(local)-r['half'],0.)
            if np.linalg.norm(delta) <= radius:
                return True
        x0,x1,y0,y1 = self.static['bounds_m']
        return not (x0+radius < xy[0] < x1-radius and y0+radius < xy[1] < y1-radius)

    def _motion_step(self,body_delta,variance):
        if self.collision_latched:
            return
        delta = body_delta+self.motion_rng.normal(size=3)*np.sqrt(variance)
        before = self.pose.copy()
        self.pose[:2] = transform([delta[:2]],before)[0]
        self.pose[2] += delta[2]
        self.distance += float(np.linalg.norm(self.pose[:2]-before[:2]))
        self.path.append(self.pose.tolist())
        if self.collision(self.pose[:2]):
            self.collisions += 1
            self.collision_latched = True
    def passage_intent(self,plan,estimated_pose,t):
        """Evaluation of issued short path, including blocked attempts before centre crossing."""
        path = plan.get('path_m',[])
        if len(path)<2:
            return
        local = inverse([path[min(2,len(path)-1)]],estimated_pose)[0]
        local *= min(1.,.12/max(1e-9,np.linalg.norm(local)))
        end = transform([local],self.pose)[0]
        radius = math.hypot(.12,.10)
        for p in self.static.get('passages',[]):
            if p['kind'] not in ('door','corridor'):
                continue
            axis = 0 if p['axis']=='x' else 1
            center = p['center_m']
            approaching = abs(end[axis]-center[axis]) < abs(self.pose[axis]-center[axis])
            near = abs(end[axis]-center[axis])<=radius+.05
            within = abs(end[1-axis]-center[1-axis])<=p['width_m']/2+radius
            if approaching and near and within and t-self.last_attempt.get(p['id'],-100)>3.:
                self.door_attempts += 1
                samples = np.linspace(self.pose[:2],end,9)
                if any(self.collision(xy) for xy in samples):
                    self.wrong_doors += 1
                self.last_attempt[p['id']] = t
        for p in plan.get('doors',[]):
            center = transform([p['center_m']],self.start)[0]
            if np.linalg.norm(end-center)<.3 and t-self.last_attempt.get(p['id'],-100)>3.:
                self.candidate_attempts += 1
                matched = any(np.linalg.norm(center-np.array(q['center_m']))<.3 for q in self.static.get('passages',[]))
                if not matched:
                    self.false_candidate_attempts += 1
                self.last_attempt[p['id']] = t

    def advance(self,command,end):
        self.motion.command(command)
        self.motion.advance(end)
        self.events(end)

    def events(self,t):
        for e in self.scenario['eval']['hidden_events']:
            if e['event_id'] in self.events_applied or e['trigger'].get('at_sim_s',math.inf)>t:
                continue
            if e['kind']=='passage_blocked':
                o = e['target']['obstacle']
                self.rects.append(dict(id=o['obstacle_id'],center=o['center_m'],half=o['half_extents_m'],yaw=0.,kind='object'))
            elif e['kind']=='item_moved':
                for r in self.rects:
                    if r['id']==e['target']['item_id']:
                        r['center'] = e['target']['to_pose_m'][:2]
                        r['yaw'] = e['target']['to_pose_m'][2]
            self.events_applied.add(e['event_id'])

    def visibility(self,points,servo):
        local = inverse(points,self.pose)
        uv,valid,origin = project(local,servo)
        camera = transform([origin[:2]],self.pose)[0]
        vec = points-camera
        ranges = np.linalg.norm(vec,axis=1)
        angles = np.arctan2(vec[:,1],vec[:,0])
        hits = ray_hits(camera,angles,self.rects,4.01)
        valid &= ranges < hits-.015
        return local,uv,valid

    def observe(self,frame_id):
        floor = []
        pattern = self.errors[self.sensor_rng.integers(len(self.errors))]
        residuals = pattern[:,2][(pattern[:,0]==1)&np.isfinite(pattern[:,2])]
        common_error = float(np.median(residuals)) if len(residuals) else 0.
        for servo in (SEARCH,CLOSE):
            local,_,visible = self.visibility(self.floor,servo)
            visible &= ~boxes_occupied(self.floor,self.rects)
            self.seen_floor.update(np.flatnonzero(visible).tolist())
            p = local[visible]
            if len(p):
                # Same view projection bias, not a perfect GT metric free grid.
                radius = np.linalg.norm(p,axis=1)
                p = p*(1+common_error/np.maximum(radius,.1))[:,None]
                floor.extend(p.tolist())
        origin,axes = commanded_camera(SEARCH,'camera_v3')
        camera = transform([origin[:2]],self.pose)[0]
        # Conservative K-pinhole horizontal span; every resulting contact is checked against raw fisheye too.
        angles = np.linspace(-math.radians(54.535)/2,math.radians(54.535)/2,96)+self.pose[2]
        ranges = ray_hits(camera,angles,self.rects,4.01)
        endpoints = camera+np.stack([np.cos(angles),np.sin(angles)],1)*ranges[:,None]
        body = inverse(endpoints,self.pose)
        _,valid,_ = project(body,SEARCH)
        valid &= ranges <= 4.
        self.sensor_counters['visible_wall_rays'] += int(valid.sum())
        keep = valid & (pattern[:,0]==1)
        noisy = ranges+np.nan_to_num(pattern[:,2],nan=0.)
        keep &= (noisy>0)&(noisy<=4.)
        self.sensor_counters['detected_wall_rays'] += int(keep.sum())
        self.sensor_counters['row_correct_draws'] += int((keep & (pattern[:,1]==1)).sum())
        wall_world = camera+np.stack([np.cos(angles),np.sin(angles)],1)*noisy[:,None]
        wall = inverse(wall_world[keep],self.pose).tolist()
        patches,truth = self.goal_patches()
        return {'robot_id':'r1','frame_id':frame_id,'floor_xy':floor,'wall_xy':wall,
                'floor_source':'floor_visible'},patches,truth

    def goal_patches(self):
        region = self.static['regions']['zone_B']
        cx,cy = region['center_m']
        hx,hy = region['half_extents_m']
        x,y = np.meshgrid(np.arange(cx-hx,cx+hx+.001,.025),np.arange(cy-hy,cy+hy+.001,.025))
        points = np.stack([x.ravel(),y.ravel()],1)
        body,uv,valid = self.visibility(points,SEARCH)
        visible = body[valid]
        patches,truth = [],[]
        pixels = 0.
        if valid.sum()>=3:
            # Polygon proxy only: partial occlusion can make hull area optimistic, explicitly reported.
            pixels = cv2.contourArea(cv2.convexHull(uv[valid].astype(np.float32)))
        if pixels>=256:
            self.sensor_counters['B_positive_frames'] += 1
            if self.sensor_rng.random()<self.b_model['recall']:
                e = float(self.sensor_rng.choice(self.b_errors))
                a = self.sensor_rng.uniform(-math.pi,math.pi)
                visible += e*np.array([math.cos(a),math.sin(a)])
                hull = cv2.convexHull(visible.astype(np.float32)).reshape(-1,2)
                patches.append(dict(component=1,pixels=int(pixels),center_body_m=visible.mean(0).tolist(),
                                    hull_body_m=hull.tolist(),_points_body_m=visible.tolist(),confidence=.9))
                truth.append(True)
                self.sensor_counters['B_detections'] += 1
        if self.sensor_rng.random()<self.b_model['fp_rate']:
            p = copy.deepcopy(self.sensor_rng.choice(self.model['B_false_patches']))
            p['_points_body_m'] = p['hull_body_m']
            p['component'] = len(patches)+1
            patches.append(p)
            truth.append(False)
            self.sensor_counters['B_false_components'] += 1
        return patches,truth

    def coverage(self):
        seen = np.zeros(len(self.floor),bool)
        seen[list(self.seen_floor)] = True
        return float((seen & self.reachable_floor).sum()/max(1,self.reachable_floor.sum()))
