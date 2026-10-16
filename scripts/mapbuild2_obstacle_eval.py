"""Evaluation-only reset-cargo occupancy targets, separate from static-map score."""
import argparse
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--vision-source',type=Path,required=True);p.add_argument('--maps',type=Path,required=True)
    p.add_argument('--labels',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('NEW_EVALUATION_OUTPUT_REQUIRED')
    # Predictions already exist; evaluator truth never goes to their producer.
    predictions={f.name.removesuffix('-predicted.json'):json.loads(f.read_text()) for f in a.maps.glob('*-predicted.json')}
    if len(predictions)!=4:raise ValueError('FOUR_SAVED_PREDICTIONS_REQUIRED')
    sys.path.insert(0,str(a.vision_source))
    import numpy as np
    import mujoco
    from scripts import probe_scene_tex2 as tools
    from scripts.generate_scene_textures import MAPS
    from mapbuild2_map_eval import raster
    from score_mapbuild1 import score
    m,scene,*_=tools.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    d=mujoco.MjData(m);d.qpos[:]=np.load(a.input/'eval-state.npz')['qpos'][0,0];mujoco.mj_forward(m,d)
    roots={m.body(item['body_name']).id for item in scene.config['setup_only']['objects'].values()}
    roots.add(m.body('cargo_tex2_beam').id)
    static=json.loads(MAPS[0].read_text());extra=[];excluded=[]
    for gid in range(m.ngeom):
        body=int(m.geom_bodyid[gid])
        while body and body not in roots:body=int(m.body_parentid[body])
        if body not in roots or not (m.geom_contype[gid] or m.geom_conaffinity[gid]):continue
        if m.geom_type[gid]!=mujoco.mjtGeom.mjGEOM_BOX:
            excluded.append(m.geom(gid).name);continue
        rotation=d.geom_xmat[gid].reshape(3,3)
        extra.append(dict(id='reset_eval_'+m.geom(gid).name,kind='reset_cargo',center_m=d.geom_xpos[gid,:2].tolist(),
            half_extents_m=m.geom_size[gid,:2].tolist(),yaw_rad=float(np.arctan2(rotation[1,0],rotation[0,0])),height_m=float(2*m.geom_size[gid,2])))
    static['obstacles']+=extra;origins=json.loads(a.labels.read_text())['first_origin']
    results={name:score(pred,raster(static,origins[name],pred['resolution_m'])) for name,pred in predictions.items()}
    a.output.write_text(json.dumps(dict(scope='evaluation only, actual reset cargo collision boxes; no actor change',
        reference_time_sim=0,cargo_motion_not_assumed_static_during_future_exploration=True,rectangles=extra,
        excluded_non_box_geoms=excluded,scores=results),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
