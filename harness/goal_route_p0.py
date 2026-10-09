"""Default-off sensor-only RouteMap P0 adapters. No scene or GT readers."""
import copy,math
from collections import defaultdict
import numpy as np
from scipy.optimize import brentq
from harness.self_odom_grid import OdomGrid,ray_cells,transform
from harness.self_pose_graph import between,compose
from harness.own_teach_capture import vertex_decision
from harness.wall_confidence import confidence,weighted_insert

HYGIENE='observed_support_v1'
ACCUMULATE='keyframe_submap_v1'
SEQUENCE='color_sequence_v1'
PITCH='ultrasonic_v1'


def color_sequence(features_by_time,t):
    """Own detector vocabulary, dominant observed line length; no map hue lookup."""
    seq=[]
    for row in features_by_time:
        if row['t']>t:break
        sizes=defaultdict(float)
        for f in row['features']:
            if f['kind']=='floor_line':
                sizes[float(f['hue'])]+=float(np.linalg.norm(np.diff(np.asarray(f['endpoints']),axis=0)))
        if sizes:
            hue=max(sizes,key=lambda h:(sizes[h],-h))
            if not seq or seq[-1]!=hue:seq.append(hue)
    return seq[-3:]


def gate_match(legacy,a,b,*,place_gate='off'):
    if place_gate=='off':return legacy
    if place_gate!=SEQUENCE:raise ValueError('UNKNOWN_PLACE_GATE')
    out=copy.deepcopy(legacy)
    agree=len(a)==len(b)==3 and (a==b or a==list(reversed(b)))
    out['color_sequence']=dict(a=a,b=b,passed=agree)
    if out['accepted'] and not agree:
        out.update(accepted=False,reason='color_sequence_insufficient' if min(len(a),len(b))<3 else 'color_sequence_mismatch')
    return out


def keyframe_ids(rows):
    anchor=None;node=-1;out={}
    for row in rows:
        pose=np.asarray(row['pose'])
        if anchor is None or vertex_decision(between(anchor,pose))!='candidate':
            node+=1;anchor=pose
        out[row['frame_id']]=node
    return out


def footprint_cells(pose,resolution=.1):
    # Existing own_navigation.Footprint: .24 x .20 m; no inflation counted as seen.
    from harness.own_map_navigation import Footprint
    fp=Footprint();center=np.asarray(pose[:2]);r=fp.radius+resolution/math.sqrt(2)
    lo=np.floor((center-r)/resolution).astype(int);hi=np.floor((center+r)/resolution).astype(int)
    c,s=math.cos(pose[2]),math.sin(pose[2]);rotation=np.array([[c,-s],[s,c]])
    for x in range(lo[0],hi[0]+1):
        for y in range(lo[1],hi[1]+1):
            q=((np.array([x,y])+.5)*resolution-center)@rotation
            if abs(q[0])<=fp.half_length_m+resolution/2 and abs(q[1])<=fp.half_width_m+resolution/2:yield (x,y)


def hygiene(legacy,ledger,poses,*,route_hygiene='off'):
    if route_hygiene=='off':return legacy
    if route_hygiene!=HYGIENE:raise ValueError('UNKNOWN_ROUTE_HYGIENE')
    g=OdomGrid(legacy['robot_id'],resolution_m=legacy['resolution_m']);support=defaultdict(set)
    nodes=keyframe_ids(poses);scan_ids=[];far=near=0
    for row in ledger:
        camera=np.asarray(row['camera']);world_camera=transform([camera],row['pose'])[0]
        hit,free={},{}
        weights=row.get('insertion_weights',[1.]*len(row['segments']))
        for seg,weight in zip(row['segments'],weights):
            a,b=np.asarray(seg);n=max(2,int(math.ceil(np.linalg.norm(b-a)/(g.resolution_m/2)))+1)
            for point in np.linspace(a,b,n):
                d=np.linalg.norm(point-camera);inside=d<=2.5
                endpoint=point if inside else camera+(point-camera)*2.5/d
                keys=ray_cells(world_camera,transform([endpoint],row['pose'])[0],g.resolution_m)
                for cell in keys[:-1] if inside else keys:free[cell]=max(free.get(cell,0.),weight)
                if inside:
                    hit[keys[-1]]=max(hit.get(keys[-1],0.),weight);near+=1
                else:far+=1
        for cell,w in free.items():
            if cell not in hit:g.cells[cell]=max(g.lo,min(g.hi,g.cells.get(cell,0.)+g.miss*w))
        for cell,w in hit.items():
            support[cell].add(nodes[row['frame_id']]);g.cells[cell]=max(g.lo,min(g.hi,g.cells.get(cell,0.)+g.hit*w))
        g.frames+=1;scan_ids.append(row['frame_id'])
    # A positive single-node candidate is unknown, never manufactured free.
    for cell,value in list(g.cells.items()):
        if value>0 and len(support[cell])<2:del g.cells[cell]
    swept=set()
    sequence=[dict(pose=[0.,0.,0.])]+poses
    for i,row in enumerate(sequence):
        previous=sequence[max(0,i-1)]['pose'];delta=between(previous,row['pose'])
        count=max(1,math.ceil(np.linalg.norm(delta[:2])/(g.resolution_m/2)),math.ceil(abs(delta[2])/math.radians(3)))
        for alpha in np.linspace(0,1,count+1):swept.update(footprint_cells(compose(previous,np.asarray(delta)*alpha),g.resolution_m))
    for cell in swept:g.cells[cell]=g.lo
    out=copy.deepcopy(legacy);out['cells']=[[int(x),int(y),v] for (x,y),v in sorted(g.cells.items())]
    out['route_hygiene']=dict(option=HYGIENE,scans=len(scan_ids),near_samples=near,far_free_samples=far,
        swept_cells=[list(c) for c in sorted(swept)],min_nodes=2,max_hit_range_m=2.5,
        range_variance='unchanged frozen insertion_weights; existing camera sigma proportional d squared')
    return out


def accumulate(legacy,ledger,observations,poses,dr_poses,decisions,*,scan_accumulation='off'):
    if scan_accumulation=='off':return legacy
    if scan_accumulation!=ACCUMULATE:raise ValueError('UNKNOWN_SCAN_ACCUMULATION')
    g=OdomGrid(legacy['robot_id'],resolution_m=legacy['resolution_m'])
    observations={r['frame_id']:r for r in observations};poses={r['frame_id']:r for r in poses}
    decisions={r['frame_id']:r for r in decisions};flush={r['frame_id']:r for r in ledger}
    pending=[];used=[];dropped=0
    for fid,obs in sorted(observations.items()):
        if fid not in poses or fid not in decisions:continue
        reason=decisions[fid]['reason']
        if reason=='gmapping_motion_gate':pending.append(fid)
        elif fid not in flush:dropped+=1
        if fid not in flush:continue
        key=flush[fid]
        # ProbabilityGrid inserter: a cell is updated once per accumulated scan.
        # Preserve the individual (deskewed) ray origins, unlike a single-origin
        # fan, and retain strongest evidence with hit taking precedence.
        occupied,free={},{}
        for f in pending+[fid]:
            row=observations[f]
            pose=key['pose'] if f==fid else compose(key['pose'],between(dr_poses[fid],dr_poses[f]))
            contributed=False
            if f==fid:
                source=zip(key['segments'],key.get('insertion_weights',[1.]*len(key['segments'])))
            else:
                source=((s,confidence(s,row['camera'],feature,poses[f]['covariance'],pose[2])['weight'])
                        for s,feature in zip(row['segments'],row['features']))
            for s,weight in source:
                if np.linalg.norm(np.asarray(s)-row['camera'],axis=1).max()>4:continue
                a,b=transform(s,pose);camera=transform([row['camera']],pose)[0]
                for p in np.linspace(a,b,max(2,math.ceil(np.linalg.norm(b-a)/(g.resolution_m/2))+1)):
                    cells=ray_cells(camera,p,g.resolution_m)
                    occupied[cells[-1]]=max(occupied.get(cells[-1],0.),weight)
                    for cell in cells[:-1]:free[cell]=max(free.get(cell,0.),weight)
                contributed=True
            if contributed:used.append(f)
        for evidence,increment in (({k:v for k,v in free.items() if k not in occupied},g.miss),(occupied,g.hit)):
            for cell,w in evidence.items():g.cells[cell]=min(g.hi,max(g.lo,g.cells.get(cell,0.)+w*increment))
        g.frames+=1
        pending=[]
    out=copy.deepcopy(legacy);out['cells']=[[int(x),int(y),v] for (x,y),v in sorted(g.cells.items())]
    out['scan_accumulation']=dict(option=ACCUMULATE,keyframes=len(flush),integrated_observations=len(used),
        integrated_frame_ids=used,unflushed=len(pending),rejected_frames=dropped,pose_estimation_changed=False)
    return out


def pitch_sample(legacy,*,reading,camera_origin,nominal_ray,wall_normal,pitch_bias='off'):
    if pitch_bias=='off':return legacy
    if pitch_bias!=PITCH:raise ValueError('UNKNOWN_PITCH_BIAS')
    from harness.ultrasonic_model import DEFAULT_SPEC,ray_pattern,first_echo
    spec=DEFAULT_SPEC
    if not reading['valid'] or reading['range_m'] is None:return dict(accepted=False,reason='invalid_range')
    if reading['range_m']<1:return dict(accepted=False,reason='near_range')
    n=np.asarray(wall_normal,float);n=n/np.linalg.norm(n)
    if n[0]<0:n=-n
    if math.acos(np.clip(n[0],-1,1))>math.radians(20):return dict(accepted=False,reason='oblique_wall')
    dirs,alpha=ray_pattern(spec);normal=np.r_[n,0.]
    dot=dirs@normal
    distance=np.divide(1.,dot,out=np.full_like(dot,np.inf),where=dot>0)
    beta=np.arccos(np.clip(dot,-1,1))
    scale=first_echo(distance,alpha,beta,spec)
    if scale is None:return dict(accepted=False,reason='no_plane_echo')
    plane=float(n@np.array([spec.face_x_m,spec.mount_y_m])+reading['range_m']/scale)
    origin=np.asarray(camera_origin);ray=np.asarray(nominal_ray)
    def residual(angle):
        c,s=math.cos(angle),math.sin(angle)
        rotated=ray@np.array([[c,0,s],[0,1,0],[-s,0,c]])  # positive elevation/pitch
        if rotated[2]>=0:return float('nan')
        p=origin-origin[2]/rotated[2]*rotated
        return float(n@p[:2]-plane)
    low,high=map(math.radians,(-5,5))
    if not np.isfinite([residual(low),residual(high)]).all() or residual(low)*residual(high)>0:
        return dict(accepted=False,reason='pitch_root_outside_bounds')
    angle=brentq(residual,low,high,xtol=1e-12)
    return dict(accepted=True,pitch_offset_rad=angle,reason='own_range_plane_root')
