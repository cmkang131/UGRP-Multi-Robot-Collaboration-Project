"""Evaluation-only static-map raster and first-origin alignment, never actor input."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scripts.score_mapbuild1 import score


def intersects(centres, cell_yaw, resolution, rectangle):
    """Exact separating-axis box/cell overlap; half-cell is geometry, not a gate."""
    angle=float(rectangle.get('yaw_rad',0))
    rotation=lambda a:np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    cell=rotation(cell_yaw);box=rotation(angle);half=np.asarray(rectangle['half_extents_m'])
    delta=np.asarray(centres)-rectangle['center_m'];result=np.ones(len(delta),bool)
    for axis in [*cell.T,*box.T]:
        extent=resolution/2*np.abs(cell.T@axis).sum()+np.abs(box.T@axis)@half
        result &= np.abs(delta@axis)<=extent
    return result


def raster(static, origin, resolution=.1):
    x,y,yaw=map(float,origin);c,s=math.cos(yaw),math.sin(yaw);rot=np.array([[c,-s],[s,c]])
    left,right,bottom,top=static['bounds_m']
    corners=(np.array([[left,bottom],[left,top],[right,bottom],[right,top]])-[x,y])@rot
    low=np.floor(corners.min(0)/resolution).astype(int);high=np.ceil(corners.max(0)/resolution).astype(int)
    ix,iy=np.meshgrid(np.arange(low[0],high[0]),np.arange(low[1],high[1]))
    keys=np.column_stack((ix.ravel(),iy.ravel()));local=(keys+.5)*resolution;world=local@rot.T+[x,y]
    inside=(world[:,0]>=left)&(world[:,0]<=right)&(world[:,1]>=bottom)&(world[:,1]<=top)
    keys,local,world=keys[inside],local[inside],world[inside]
    occupied=np.zeros(len(keys),bool);classes={k:np.zeros(len(keys),bool) for k in ('wall','door','obstacle','destination')}
    for rectangle in static['obstacles']:
        hit=intersects(world,yaw,resolution,rectangle);occupied |=hit
        classes['wall' if rectangle.get('kind')=='wall' or rectangle['id'].startswith('wall_') else 'obstacle'] |=hit
    for rectangle in static.get('passages',[]):classes['door']|=intersects(world,yaw,resolution,rectangle)
    for name,rectangle in static['regions'].items():
        if name.startswith('zone_'):classes['destination']|=intersects(world,yaw,resolution,rectangle)
    return dict(frame='r1/start',resolution_m=resolution,
        cells=[[int(a),int(b),'occupied' if hit else 'free'] for (a,b),hit in zip(keys,occupied)],
        **{name:local[mask].tolist() for name,mask in classes.items()})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--predicted',type=Path,required=True)
    p.add_argument('--static-map',type=Path,required=True);p.add_argument('--origin',nargs=3,type=float,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_EVALUATION_OUTPUT_REQUIRED')
    predicted=json.loads(a.predicted.read_text());truth=raster(json.loads(a.static_map.read_text()),a.origin,predicted['resolution_m'])
    result=score(predicted,truth)
    # Known/observed-area confusion is reported separately from full-map recall.
    known={(x,y) for x,y,_ in predicted['cells']}
    observed={**truth,'cells':[row for row in truth['cells'] if tuple(row[:2]) in known]}
    result.update(observed_area_confusion=score(predicted,observed),static_map_sha256=hashlib.sha256(a.static_map.read_bytes()).hexdigest(),
        origin_alignment='reset first SE(2) only; no optimized scale or trajectory fitting',origin=a.origin,
        truth_dynamic_cargo='not included in static raster; static obstacle category only',
        raw_predicted_sha256=hashlib.sha256(a.predicted.read_bytes()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
