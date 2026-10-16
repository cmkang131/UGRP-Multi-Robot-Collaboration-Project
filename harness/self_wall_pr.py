"""Fixed-geometry support filtering for grid/segments. No ground truth input.

Operating points are explicit. The frozen multiview_weight_v1 and segments_v1
implementations remain unchanged. Development selection lives in eval code.
"""
import copy
import hashlib
import json
import math
import numpy as np
from harness.self_odom_grid import transform
from harness.self_pose_graph import validate_rows
from harness.self_wall_validation import validated_grid,independent_view

OPTION='pr_support_v1'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def angular_span(target,cameras):
    rays=np.asarray(target)-np.asarray(cameras,float).reshape(-1,2)
    span=0.
    for i,a in enumerate(rays):
        for b in rays[:i]:
            span=max(span,abs(math.atan2(a[0]*b[1]-a[1]*b[0],float(a@b))))
    return math.degrees(span)


def distinct_cameras(target,cameras,resolution=.1):
    # Use the exact existing per-view independence predicate at a continuous target.
    key=np.asarray(target)/resolution-.5
    selected=[]
    for camera in cameras:
        if all(independent_view(camera,old,key,resolution) for old in selected):selected.append(list(camera))
    return selected


def grid_support(legacy,ledger,*,robot_id):
    _,evidence=validated_grid(legacy,ledger,robot_id=robot_id,wall_validation='multiview_weight_v1')
    r=legacy['resolution_m']
    return dict(robot_id=robot_id,source_sha256=fingerprint(legacy),representation='grid',
        candidates=[dict(id=s['cell'],views=s['weight'],angle_deg=angular_span((np.array(s['cell'])+.5)*r,s['cameras'])) for s in evidence['cells']])


def segment_support(legacy,ledger,*,robot_id):
    if legacy['robot_id']!=robot_id:raise ValueError('PR_SUPPORT_PEER_FORBIDDEN')
    validate_rows(ledger,robot_id)
    poses={r['frame_id']:transform([r['camera']],r['pose'])[0].tolist() for r in ledger}
    candidates=[]
    for i,line in enumerate(legacy['segments']):
        target=np.array(line['endpoints_m']).mean(0)
        cameras=distinct_cameras(target,[poses[f] for f in line['frame_ids']])
        candidates.append(dict(id=i,views=len(cameras),angle_deg=angular_span(target,cameras)))
    return dict(robot_id=robot_id,source_sha256=fingerprint(legacy),representation='segments',candidates=candidates)


def apply(legacy,support=None,*,wall_validation='off',min_views=None,min_angle_deg=None):
    """Default is identity, including JSON bytes; on requires an explicit point."""
    if wall_validation not in ('off',OPTION):raise ValueError('UNKNOWN_PR_WALL_VALIDATION')
    if wall_validation=='off':return legacy
    if (type(min_views) is not int or min_views<1 or type(min_angle_deg) not in (float,int)
            or not math.isfinite(min_angle_deg) or not 0<=min_angle_deg<=180):
        raise ValueError('EXPLICIT_VALID_PR_OPERATING_POINT_REQUIRED')
    if legacy['robot_id']!=support['robot_id']:raise ValueError('PR_SUPPORT_PEER_FORBIDDEN')
    if fingerprint(legacy)!=support['source_sha256']:raise ValueError('PR_SUPPORT_SOURCE_MISMATCH')
    out=copy.deepcopy(legacy)
    admitted=[c['id'] for c in support['candidates'] if c['views']>=min_views and c['angle_deg']>=min_angle_deg]
    if support['representation']=='grid':
        ids=set(map(tuple,admitted))
        out['cells']=[c for c in out['cells'] if c[2]<=0 or tuple(c[:2]) in ids]
    elif support['representation']=='segments':
        out['segments']=[s for i,s in enumerate(out['segments']) if i in admitted]
    else:raise ValueError('UNKNOWN_PR_REPRESENTATION')
    out['wall_validation']=dict(option=OPTION,min_views=min_views,min_angle_deg=min_angle_deg,
        semantics='observation support; NOT calibrated wall probability')
    return out
