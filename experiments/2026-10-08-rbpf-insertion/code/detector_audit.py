"""JPEG-only upstream re-detection diagnostic; not byte-exact runtime RGB."""
from collections import Counter
import math
import cv2
import numpy as np
from audit import RAW, EXP, rows, dump, BINS, bin_id
from harness.active_wall_vision import modules
from harness.active_camera import transform
from harness.wall_projection_guard import filter_segments


def main():
    mp, hfw, ewm = modules()
    frames = {r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
    params = {'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4}
    models, result = {}, {}
    for row in rows(RAW/'own-contacts.jsonl'):
        frame = frames[row['frame_id']]
        servo = {int(k):v for k,v in frame['commanded_servo'].items()}
        key = tuple(sorted(servo.items()))
        if key not in models:
            origin, rotation = transform(servo)
            models[key] = (mp.ColumnModel(key,0.,mp.column_positions(96,2),camera_transform=(origin,rotation)),origin,rotation)
        cm, origin, rotation = models[key]
        scan = hfw.detect(mp.undistort(cv2.imread(str(RAW/frame['path']))),cm,params=params,loaded=False)
        linked = hfw.link_segments(scan,params)
        counts = Counter(frames=1,columns=96,contact_columns=int(np.isfinite(scan['vb'][:,0]).sum()),
                         zero_column_frames=int(not np.isfinite(scan['vb'][:,0]).any()),
                         linked_segments=len(linked),linked_zero_frames=int(not linked))
        ranges = [Counter() for _ in BINS]
        for seg in linked:
            r,a,s,b,_ = ewm.segment_to_chassis(seg,cm.origin[:2],0.)
            ends = np.array([[r*math.cos(a),r*math.sin(a)],[s*math.cos(b),s*math.sin(b)]])
            distance = np.linalg.norm(ends-origin[:2],axis=1).max()
            bucket = ranges[bin_id(distance)]
            bucket['linked'] += 1
            if distance >= 4.:
                counts['range_rejected_segments'] += 1
                bucket['range_rejected'] += 1
                continue
            valid,_ = filter_segments([ends],wall_projection_guard='positive_depth_v1',camera_origin=origin,camera_rotation=rotation)
            counts['positive_depth_rejected_segments'] += int(not len(valid))
            bucket['depth_rejected' if not len(valid) else 'passed'] += 1
        for group in ['all']+(['after_36_1'] if row['t']>36.1+1e-8 else []):
            if group not in result:result[group] = dict(counts=Counter(),ranges=[Counter() for _ in BINS])
            result[group]['counts'].update(counts)
            for a,b in zip(result[group]['ranges'],ranges):a.update(b)
    dump(EXP/'results/jpeg-detector-audit.json',dict(groups=result,bins=BINS,
         qualification='Saved lossy JPEG re-detection diagnostic only; authoritative runtime contacts counted separately. No instance masks: other-robot occlusion unlabelled. No explicit sloped-wall rejection; linking enforces continuity and minimum four columns.'))
    print({key:dict(value['counts']) for key,value in result.items()},flush=True)


if __name__=='__main__':main()
