"""Recorded-qpos forward kinematics and ray intersections ONLY; no rendering.

No mj_step, mj_forward, renderer, viewer, rollout, or modified scene. Output is
a new JSON file. The grid uses the original measured fisheye pixel rays.
"""
import collections
import json
from pathlib import Path
import sys

import mujoco
import numpy as np

from diagnose import ROOT, RAW, native
from harness.owncam_view import _pixel_rays


def box_entry(model, data, gid, origin, ray):
    rotation = data.geom_xmat[gid].reshape(3, 3)
    o = rotation.T @ (origin-data.geom_xpos[gid])
    v = rotation.T @ ray
    half = model.geom_size[gid]
    with np.errstate(divide='ignore'):
        a, b = (-half-o)/v, (half-o)/v
    enter = float(np.max(np.minimum(a,b)))
    leave = float(np.min(np.maximum(a,b)))
    return enter if leave >= max(0.,enter) else None


def main(path):
    assert not path.exists()
    xs,ys,normal,valid = _pixel_rays(20)
    roi = valid & (xs>=140)&(xs<500)&(ys>=40)&(ys<300)
    ray_camera = np.column_stack((normal[roi],np.ones(roi.sum())))
    ray_camera /= np.linalg.norm(ray_camera,axis=1,keepdims=True)
    result = {'mujoco_version': mujoco.__version__, 'method': 'mj_kinematics + mj_camlight + mj_ray; no renderer/step/forward dynamics',
              'roi_sample_rays': int(roi.sum()), 'samples': []}
    for profile in ('loaded','unloaded','fine'):
        folder = RAW[profile]/'zone_wide_two_doors_final_v3'
        model = mujoco.MjModel.from_xml_path(str(folder/'scene.xml'))
        data = mujoco.MjData(model)
        trace = [json.loads(l) for l in (folder/'eval_only/trajectory.jsonl').read_text().splitlines()]
        times = [15.,178.,320.] if profile=='loaded' else [331.6,334.6]
        for sec in times:
            row = trace[round(sec/.05)]
            data.qpos[:] = row['qpos']
            mujoco.mj_kinematics(model,data)
            mujoco.mj_camlight(model,data)
            for rid in ('r1','r2'):
                cid = model.camera(rid+'__robot_cam').id
                origin = data.cam_xpos[cid].copy()
                axes = data.cam_xmat[cid].reshape(3,3) @ np.diag([1.,-1.,-1.])
                forward = axes[:,2]
                rays = ray_camera @ axes.T
                hits = collections.Counter()
                depths = []
                beam_front_after_near = 0
                near = float(model.vis.map.znear*model.stat.extent)
                beam_gids = [model.geom('cargo_beam__'+part).id for part in ('bar','band_neg','band_pos')]
                for ray in rays:
                    gid = np.array([-1],np.int32)
                    distance = mujoco.mj_ray(model,data,origin,ray,np.array([1,1,1,1,0,0],np.uint8),1,-1,gid)
                    name = model.geom(int(gid[0])).name if gid[0]>=0 else 'none'
                    hits[name] += 1
                    if name.startswith('cargo_beam__'):
                        depths.append(float(distance*(ray@forward)))
                    # Entry face faces the camera. An exit from a clipped box
                    # interior is a back face, not new front-face evidence.
                    entries = [box_entry(model,data,g,origin,ray) for g in beam_gids]
                    beam_front_after_near += any(x is not None and x*(ray@forward)>=near for x in entries)
                result['samples'].append({'profile':profile,'robot':rid,'relative_s':sec,
                    'extent_m':model.stat.extent,'znear_multiplier':model.vis.map.znear,'near_m':near,
                    'camera_xyz_m':origin,'optical_axis_world':forward,
                    'first_intersection_counts_without_clip':dict(hits),
                    'beam_front_depth_min_max_m': [min(depths),max(depths)] if depths else None,
                    'beam_front_faces_after_near':int(beam_front_after_near)})
    path.write_text(json.dumps(result,indent=2,default=native)+'\n')


if __name__=='__main__':
    main(Path(sys.argv[1]))
