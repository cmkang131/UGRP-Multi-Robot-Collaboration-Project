"""Freeze an RGB-selected floor scale and estimation hashes before truth opens.

Polygon coordinates are a manually documented floor ROI, not a tuned tracking
acceptance threshold. Height/normal come only from fixed external calibration.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import cv2
import numpy as np

from mast3rcmp_evaluate import digest, freeze_scale


def seal(run, calibration, polygon, output):
    run, calibration, output = Path(run), Path(calibration), Path(output)
    trajectory = run/'probe/trajectory.json'
    summary = json.loads((run/'probe/summary.json').read_text())
    launch = json.loads((run/'launch.json').read_text())
    rows = json.loads(trajectory.read_text())['frames']
    if launch['returncode'] or summary['total_frames'] != len(rows):
        raise ValueError('completed_full_denominator_required')
    output.mkdir(exist_ok=False)
    pointmap = run/'probe/initial-pointmap.npz'
    p = np.load(pointmap)
    mask = np.zeros(p['rgb'].shape[:2], np.uint8)
    cv2.fillPoly(mask, [np.asarray(polygon, np.int32)], 255)
    cv2.imwrite(str(output/'floor-mask.png'), mask)
    cal = json.loads(calibration.read_text())
    reference = dict(camera_height_m=cal['camera_height_m'],
        floor_normal_camera=cal['floor_normal_camera'], mask_path='floor-mask.png',
        mask_sha256=digest(output/'floor-mask.png'), polygon_xy=polygon,
        selected_pixels=int(np.count_nonzero(mask)),
        fixed_calibration_sha256=digest(calibration),
        selection='manual own RGB frame0 floor interior; chosen before truth; no depth-based mask tuning',
        calibration_limit=cal['limitations'], truth_reads=0)
    (output/'floor-reference.json').write_text(json.dumps(reference,indent=2)+'\n')
    frozen = freeze_scale(pointmap, output/'floor-reference.json', output/'allowed-scale.json')
    rgb = cv2.cvtColor(np.round(p['rgb']*255).astype('uint8'), cv2.COLOR_RGB2BGR)
    annotated = rgb.copy()
    cv2.polylines(annotated, [np.asarray(polygon,np.int32)], True, (0,255,0), 2)
    cv2.putText(annotated,'Frozen floor ROI / own RGB frame 0',(8,20),0,.5,(0,255,0),1)
    cv2.imwrite(str(output/'floor-roi-montage.png'),np.concatenate((rgb,annotated),axis=1))
    receipt = dict(sealed_utc=datetime.now(timezone.utc).isoformat(),truth_reads=0,
        command_reads=0,top_reads=0,total_frames=len(rows),
        scale=frozen['scale'],scale_method=frozen['method'],
        hashes={str(f):digest(f) for f in [trajectory,run/'probe/summary.json',run/'launch.json',
            pointmap,calibration,output/'floor-mask.png',output/'floor-reference.json',output/'allowed-scale.json']})
    (output/'estimation-scale-seal.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','calibration','output','polygon'):p.add_argument('--'+name,required=True)
    a=p.parse_args()
    print(json.dumps(seal(a.run,a.calibration,json.loads(a.polygon),a.output),indent=2))
