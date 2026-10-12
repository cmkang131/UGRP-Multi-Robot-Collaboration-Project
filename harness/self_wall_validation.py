"""Own-map multi-view support gate. No GT, scene, peers, or sensor re-fitting.

Open3D v0.19.0 unit observation weight and strict surface extraction threshold
are transplanted to existing 2D occupied candidates. This is not a TSDF solver.
See egomap35 README for the explicit view-separation/clearing adaptations.
"""
from __future__ import annotations
import copy
import math
import numpy as np
from harness.self_odom_grid import OdomGrid, ray_cells, transform
from harness.self_pose_graph import insert_row, validate_rows

OPTION='multiview_weight_v1'
WEIGHT_THRESHOLD=3.


def independent_view(camera,previous,cell,resolution):
    center=(np.asarray(cell)+.5)*resolution
    a,b=center-np.asarray(camera),center-np.asarray(previous)
    shift=float(np.linalg.norm(np.asarray(camera)-previous))
    angle=abs(math.atan2(a[0]*b[1]-a[1]*b[0],float(a@b)))
    return shift>=resolution or angle>=math.atan2(resolution,min(np.linalg.norm(a),np.linalg.norm(b)))


def hit_cells(row,resolution):
    camera=transform([row['camera']],row['pose'])[0]
    hits=set()
    weights=row.get('insertion_weights',[1.]*len(row['segments']))
    if len(weights)!=len(row['segments']) or any(not math.isfinite(w) or not 0<=w<=1 for w in weights):
        raise ValueError('INVALID_WALL_VALIDATION_WEIGHTS')
    for segment,weight in zip(row['segments'],weights):
        if weight<=0:continue
        ends=transform(segment,row['pose'])
        n=max(2,int(math.ceil(np.linalg.norm(ends[1]-ends[0])/(resolution/2)))+1)
        for point in np.linspace(*ends,n):hits.add(ray_cells(camera,point,resolution)[-1])
    return camera,hits


def validated_grid(legacy,ledger,*,robot_id,wall_validation='off'):
    """Return (map export, support). Off is object identity, no input inspection.

    On replays only the saved own pose lineage. Unsupported positive cells are
    absent (unknown), never negative (free). Retained cell values are unchanged.
    Intended for memory/output validation, not feedback into pose estimation.
    """
    if wall_validation not in ('off',OPTION):raise ValueError('UNKNOWN_WALL_VALIDATION')
    if wall_validation=='off':return legacy,None
    if legacy['robot_id']!=robot_id:raise ValueError('WALL_VALIDATION_PEER_INPUT_FORBIDDEN')
    validate_rows(ledger,robot_id)
    r=legacy['resolution_m']
    grid=OdomGrid(robot_id,resolution_m=r)
    views={};events=[]
    for row in ledger:
        camera,hits=hit_cells(row,r)
        insert_row(grid,row,row['pose'])
        cleared=[k for k in views if grid.cells.get(k,0.)<=0]
        for k in cleared:del views[k]
        added=correlated=0
        for key in sorted(hits):
            if grid.cells[key]<=0:continue
            previous=views.setdefault(key,[])
            if all(independent_view(camera,old,key,r) for old in previous):
                previous.append(camera.tolist());added+=1
            else:correlated+=1
        events.append(dict(frame_id=row['frame_id'],t=row['t'],new_support=added,
                           correlated_support_skipped=correlated,cleared_support=len(cleared)))
    # Reject a mismatched ledger instead of validating a different map silently.
    if grid.export()['cells']!=legacy['cells']:raise ValueError('WALL_VALIDATION_LEDGER_MAP_MISMATCH')
    retained={k for k,v in grid.cells.items() if v>0 and len(views.get(k,[]))>WEIGHT_THRESHOLD}
    result=copy.deepcopy(legacy)
    result['cells']=[c for c in result['cells'] if c[2]<=0 or tuple(c[:2]) in retained]
    evidence=dict(option=OPTION,weight_threshold=WEIGHT_THRESHOLD,comparison='strictly_greater',
        semantics='distinct-view support count; NOT a calibrated wall probability',
        minimum_translation_m=r,angular_separation='atan2(resolution, min(view ranges))',
        candidates=sum(v>0 for v in grid.cells.values()),confirmed=len(retained),events=events,
        cells=[dict(cell=[int(x) for x in k],weight=len(v),confirmed=k in retained,cameras=v) for k,v in sorted(views.items())])
    result['wall_validation']={k:v for k,v in evidence.items() if k not in ('events','cells')}
    return result,evidence
