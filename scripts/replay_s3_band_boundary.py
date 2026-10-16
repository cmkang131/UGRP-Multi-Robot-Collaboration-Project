"""Saved RGB counterfactual, default-off boundary correction; Oracle x86 only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
import hashlib
from pathlib import Path
import platform
import cv2
from harness.zone_final_pair_vision import PairVision
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_s3_coarse_fine import yaw_calibration
from harness.zone_s3_alignment_ownership import band_vision
from scripts.diagnose_s3_endpoint_visibility import events


def replay(raw,out):
    b=json.loads((raw/'bundle.json').read_text())
    calibration=camera_calibration(json.loads(Path(b['calibration']).read_text()))
    ev=list(events(json.loads((raw/'student_record.json').read_text())))
    result={};out.mkdir(parents=True,exist_ok=False)
    for rid in ('r1','r2'):
        frames={round(f['sim_time'],6):f for f in map(json.loads,(raw/f'robots/{rid}/frames.jsonl').read_text().splitlines())}
        cache={};counts=Counter();rows=[]
        for e in ev:
            if e['robot_id']!=rid:continue
            f=frames[round(e['sim_s'],6)]
            if hashlib.sha256((raw/f['path']).read_bytes()).hexdigest()!=f['sha256']:raise ValueError('input hash mismatch')
            servo={int(k):v for k,v in f['commanded_servo'].items()};pan=servo[6]
            if pan not in cache:cache[pan]=band_vision(PairVision(yaw_calibration(calibration,pan)))
            got=cache[pan].observe_beam(cv2.imread(str(raw/f['path'])),servo)
            key=f'{e["reason"]}->{got["reason"]}';counts[key]+=1
            rows.append(dict(t=e['sim_s'],frame_id=f['frame_id'],input_sha256=f['sha256'],before=e['reason'],after=got['reason'],end_visible=got['end_visible'],band=got.get('band')))
        (out/f'{rid}.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows));result[rid]=dict(counts)
    return raw.parent.name,result


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise RuntimeError('oracle-x86 only')
    cv2.setNumThreads(1);a.output.mkdir(parents=True,exist_ok=False)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(replay,raw,a.output/raw.parent.name) for raw in sorted(a.cohort.glob('*pair*/raw'))]
        result=dict(f.result() for f in futures)
    (a.output/'summary.json').write_text(json.dumps(dict(host='oracle-x86',cases=result),indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
