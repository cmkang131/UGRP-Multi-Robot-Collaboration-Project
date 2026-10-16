"""Evaluation-only exact body-heading labels; estimates must already be saved."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--analysis',type=Path,required=True);p.add_argument('--vision-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_EVALUATION_OUTPUT_REQUIRED')
    trajectories={name:json.loads((a.analysis/(name+'-trajectory.json')).read_text()) for name in
        ('legacy','orange-columns-fast7','command')}
    # Only after loading saved causal trajectories, open evaluator state.
    sys.path.insert(0,str(a.vision_source))
    import numpy as np
    from mapbuild1_replay import score,dump
    from harness.e2e_rgb_vo import between
    from scripts import probe_scene_tex2 as scene_tools
    from scripts.generate_scene_textures import MAPS
    m,*_=scene_tools.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    adr=int(m.jnt_qposadr[int(m.body_jntadr[m.body('r1__robot').id])])
    states=np.load(a.input/'eval-state.npz')['qpos']
    manifest=json.loads((a.input/'own.json').read_text());old=json.loads((a.input/'eval-only.json').read_text())
    names=list(dict.fromkeys(r['sequence'] for r in manifest['frames']));origins={};labels=[];heading_errors=[]
    old_by={(r['sequence'],r['frame_id']):r for r in old['frames']}
    for frame in manifest['frames']:
        name=frame['sequence'];q=states[frame['frame_id'],names.index(name),adr:adr+7]
        w,x,y,z=q[3:]/np.linalg.norm(q[3:])
        yaw=float(np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z)))
        pose=np.array([q[0],q[1],yaw]);origins.setdefault(name,pose.copy())
        relative=between(origins[name],pose)
        labels.append(dict(sequence=name,frame_id=frame['frame_id'],t=frame['t'],pose=relative.tolist()))
        diff=relative[2]-old_by[name,frame['frame_id']]['pose'][2]
        heading_errors.append(float(np.arctan2(np.sin(diff),np.cos(diff))))
    a.output.mkdir(parents=True)
    dump(a.output/'labels.json',dict(frames=labels,first_origin={k:v.tolist() for k,v in origins.items()},
        scope='evaluation-only quaternion body-axis heading; first-origin SE(2); no scale fit'))
    dump(a.output/'scores.json',dict(metrics={name:score(rows,dict(frames=labels)) for name,rows in trajectories.items()},
        raw_label_heading_definition='2*atan2(qz,qw); retained original',
        corrected_heading_definition='atan2(R10,R00) from normalized actual body quaternion',
        heading_correction_abs_max_deg=float(np.degrees(np.max(np.abs(heading_errors)))),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__=='__main__':main()
