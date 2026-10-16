"""Evaluation-only map geometry/coverage scoring; never imported by actors.

Separate wall/door/obstacle/destination point sets in metres and occupied/free
cell labels. No success radius is fitted: symmetric nearest distances and exact
cell confusion are reported. Empty predictions retain omissions/unknowns.
"""
import argparse
import json
import math
from pathlib import Path
import numpy as np

KINDS=('wall','door','obstacle','destination')


def nearest(a,b):
    if not len(a) or not len(b):return []
    # Chunked comparisons bound temporary memory by target count x 256.
    return np.concatenate([np.sqrt(((a[i:i+256,None]-b[None])**2).sum(2)).min(1)
                           for i in range(0,len(a),256)]).tolist()


def distribution(values):
    return dict(n=len(values),p50=float(np.median(values)),p95=float(np.percentile(values,95)),max=float(max(values))) if values else dict(n=0,p50=None,p95=None,max=None)


def points(value):
    a=np.asarray(value,float)
    if not a.size:return np.empty((0,2))
    if a.ndim!=2 or a.shape[1]!=2 or not np.isfinite(a).all():raise ValueError('FINITE_XY_REQUIRED')
    return a


def score(predicted,truth):
    if predicted['resolution_m']!=truth['resolution_m']:raise ValueError('EXACT_GRID_RESOLUTION_REQUIRED')
    if predicted['frame']!=truth['frame']:raise ValueError('EVALUATOR_MUST_ALIGN_START_FRAME_ONLY')
    resolution=float(truth['resolution_m'])
    if not math.isfinite(resolution) or resolution<=0:raise ValueError('POSITIVE_GRID_RESOLUTION_REQUIRED')
    def cells(rows):
        out={}
        for x,y,label in rows:
            if type(x) is not int or type(y) is not int or label not in ('free','occupied'):raise ValueError('INTEGER_GRID_AND_KNOWN_LABEL_REQUIRED')
            if (x,y) in out:raise ValueError('DUPLICATE_GRID_CELL')
            out[x,y]=label
        return out
    p,t=cells(predicted['cells']),cells(truth['cells'])
    known=set(p)&set(t)
    tp=sum(p[c]=='occupied' and t[c]=='occupied' for c in known)
    fp=sum(p[c]=='occupied' and t[c]=='free' for c in known)
    fn=sum(t[c]=='occupied' and p.get(c)!='occupied' for c in t)
    geometry={}
    for kind in KINDS:
        a,b=points(predicted.get(kind,[])),points(truth.get(kind,[]))
        geometry[kind]=dict(predicted_n=len(a),truth_n=len(b),
            predicted_to_truth_m=distribution(nearest(a,b)),truth_to_predicted_m=distribution(nearest(b,a)),
            status='unobserved' if not len(a) and len(b) else 'no_truth_target' if not len(b) else 'measured')
    return dict(geometry=geometry,total_truth_cells=len(t),observed_truth_cells=len(known),
        coverage=len(known)/len(t) if t else None,unknown_truth_cells=len(set(t)-set(p)),
        out_of_truth_cells=len(set(p)-set(t)),occupied_tp=tp,occupied_fp=fp,occupied_fn_including_unknown=fn,
        occupied_iou=tp/(tp+fp+fn) if tp+fp+fn else None,
        wrong_free_cells=sum(p[c]=='free' and t[c]=='occupied' for c in known),
        false_occupied_area_m2=fp*resolution**2,missed_occupied_area_m2=fn*resolution**2,
        geometry_missing_false_counts='grid confusion only; object instance identity not inferred from sample points')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--predicted',type=Path,required=True);p.add_argument('--truth',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    a.output.write_text(json.dumps(score(json.loads(a.predicted.read_text()),json.loads(a.truth.read_text())),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
