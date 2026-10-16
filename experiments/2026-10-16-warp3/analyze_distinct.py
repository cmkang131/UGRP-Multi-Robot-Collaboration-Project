"""Verify sixteen actual initialized worlds, never count replicated seeds."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image


def verify(run, out):
    summary = json.loads((run/'summary.json').read_text())
    proof = json.loads((run/'initial-world-state.json').read_text())
    plans = [json.loads((run/f'world-{i:03d}/plan.json').read_text()) for i in range(16)]
    assert summary['status'] == 'initialization_complete', summary.get('error')
    assert summary['nworld'] == 16
    assert len({json.dumps(p['spawns'], sort_keys=True) for p in plans}) == 16
    assert all(r['qpos_match'] and r['expected_qpos_sha256'] == r['actual_qpos_sha256'] for r in proof['rows'])
    assert proof['expected_unique_qpos'] == proof['measured_unique_qpos'] == proof['first_rgb_unique'] == 16
    pixels = [np.asarray(Image.open(run/f'first-rgb/world-{i:03d}.jpg').convert('RGB'), dtype=np.int16) for i in range(16)]
    pairs = []
    for a,b in itertools.combinations(range(16), 2):
        delta = np.abs(pixels[a]-pixels[b])
        pairs.append(dict(a=a,b=b,different_pixels=int(np.any(delta,axis=2).sum()),mean_abs_channel_delta=float(delta.mean())))
    assert all(r['different_pixels'] > 0 for r in pairs)
    out.mkdir(parents=True,exist_ok=True)
    montage = out/'distinct-first-rgb.jpg'
    command = ['ffmpeg','-y','-loglevel','error','-framerate','1','-i',str(run/'first-rgb/world-%03d.jpg'),
        '-vf',"scale=320:240,drawtext=text='world %{n}':x=8:y=8:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.7,tile=4x4",
        '-frames:v','1',str(montage)]
    subprocess.run(command,check=True)
    result = dict(status='PASS',stage='DISTINCT_STARTS',source_sha=summary['source_sha'],nworld=16,
        scene='walls_floor_contrast_v5_indigo110_s80 + original v1 floor + no_mip_v1',
        unique_start_manifests=16,unique_actual_qpos=16,unique_first_rgb=16,qpos_match_count=16,
        compared_image_pairs=len(pairs),minimum_different_pixels=min(r['different_pixels'] for r in pairs),
        minimum_mean_abs_channel_delta=min(r['mean_abs_channel_delta'] for r in pairs),pairs=pairs,
        raw=str(run),proof_sha256=hashlib.sha256((run/'initial-world-state.json').read_bytes()).hexdigest(),
        montage_sha256=hashlib.sha256(montage.read_bytes()).hexdigest(),montage_command=command,
        counting_scope='initialization correctness only; independent teacher episodes=0; all older N>1 results excluded')
    (out/'distinct-proof.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('pairs','montage_command')},indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();verify(a.run,a.out)
