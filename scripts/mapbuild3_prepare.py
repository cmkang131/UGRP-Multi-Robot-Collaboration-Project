"""New setup fixture only: audit original, bounded robot-start search, no rollout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim.spawn_overlap_check import check,OPTION


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def named_sets(m):
    # Explicit original scene names/types, saved in every audit. Only planes
    # named floor/ground are floor; no ramp, wall or worldbody blanket exemption.
    import mujoco
    floor={m.geom(i).name for i in range(m.ngeom) if int(m.geom_type[i])==int(mujoco.mjtGeom.mjGEOM_PLANE)
           and any(word in m.geom(i).name.lower() for word in ('floor','ground'))}
    cargo={m.body(i).name for i in range(m.nbody) if m.body(i).name.startswith(('cargo_','beam_'))}
    wall={m.geom(i).name for i in range(m.ngeom) if 'wall' in m.geom(i).name.lower()}
    if not floor or not cargo or not wall:raise ValueError('EXPLICIT_SCENE_CLASSIFICATION_REQUIRED')
    return dict(floor_geoms=floor,cargo_bodies=cargo,wall_geoms=wall)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--renderer-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--spawn-overlap-check-v1',action='store_true');a=p.parse_args()
    if not a.spawn_overlap_check_v1:p.error('default off; explicit toggle required')
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-act-l4-gcp5','ugrp-sim-gcp2')):
        p.error('approved setup/audit hosts only; Mac physics0')
    a.output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.renderer_source));sys.path.insert(1,str(a.renderer_source/'scripts'))
    import scripts,sim
    scripts.__path__.insert(0,str(a.renderer_source/'scripts'));sim.__path__.insert(0,str(a.renderer_source/'sim'))
    os.chdir(a.renderer_source)
    import numpy as np
    import mujoco
    from scripts import probe_scene_tex2 as st
    from scripts.generate_scene_textures import MAPS
    m,scene,hardware,xml,audit=st.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    d=mujoco.MjData(m);view=st.wall_views(scene.config['static_map'])[0];sets=named_sets(m)
    dump(a.output/'classifications.json',{k:sorted(v) for k,v in sets.items()})
    records=[];selected={};arrays={}
    for pose in ('drive','high'):
        pwm,setup=st.fixture(m,d,scene,view,pose,hardware)
        original=d.qpos.copy();report=check(m,d,**sets,option=OPTION)
        records.append(dict(pose=pose,candidate='original_mapbuild2',**report))
        # Seal the original distribution before considering any changed start.
        dump(a.output/'original-rejection-table.json',dict(raw=str(a.output),reproduction=sys.argv,rows=records.copy(),
            stages=[dict(stage='original_starts',cumulative_pass_n=len(records),rejected_n=0),
                    dict(stage='nonpenetrating',cumulative_pass_n=sum(r['accepted'] for r in records),
                         rejected_n=sum(not r['accepted'] for r in records))]))
        bid=m.body('r1__robot').id;adr=int(m.jnt_qposadr[int(m.body_jntadr[bid])])
        # Search spacing derives from the original robot's complete horizontal
        # geom bounding radii, not an acceptance tolerance. 5x5 is a finite25
        # setup-check budget. Neither geometry nor cargo state is modified.
        robot=[i for i in range(m.ngeom) if m.body(int(m.geom_bodyid[i])).name.startswith('r1__')]
        radius=max(float(np.linalg.norm(d.geom_xpos[i,:2]-d.qpos[adr:adr+2]))+float(m.geom_rbound[i]) for i in robot)
        spacing=2*radius
        offsets=sorted(((x,y) for x in range(-2,3) for y in range(-2,3)),key=lambda xy:(xy[0]**2+xy[1]**2,xy))
        for index,(x,y) in enumerate(offsets):
            d.qpos[:]=original;d.qpos[adr:adr+2]+=spacing*np.array([x,y]);d.qvel[:]=0
            result=check(m,d,**sets,option=OPTION)
            records.append(dict(pose=pose,candidate=f'lattice-{index}',offset_cells=[x,y],spacing_m=spacing,**result))
            dump(a.output/'spawn-rejection-table.json',dict(raw=str(a.output),reproduction=sys.argv,rows=records,
                stages=[dict(stage='tested_starts',cumulative_pass_n=len(records),rejected_n=0),
                        dict(stage='nonpenetrating',cumulative_pass_n=sum(r['accepted'] for r in records),rejected_n=sum(not r['accepted'] for r in records))]))
            if result['accepted']:
                d.ctrl[:]=0
                for i in range(m.nu):
                    if '__servo_' in m.actuator(i).name:d.ctrl[i]=d.qpos[int(m.jnt_qposadr[int(m.actuator_trnid[i,0])])]
                arrays[pose+'_qpos']=d.qpos.copy();arrays[pose+'_ctrl']=d.ctrl.copy()
                selected[pose]=dict(pwm=pwm,setup=setup,offset_cells=[x,y],spacing_m=spacing,
                    original_xy=original[adr:adr+2].tolist(),selected_xy=d.qpos[adr:adr+2].tolist(),admission=result)
                break
        else:raise ValueError('NO_CLEAN_START_WITHIN_25_CHECKS')
    np.savez_compressed(a.output/'fixture.npz',**arrays)
    dump(a.output/'fixture.json',dict(selected=selected,scene_xml_sha256=hashlib.sha256(xml.encode()).hexdigest(),
        fixture_sha256=hashlib.sha256((a.output/'fixture.npz').read_bytes()).hexdigest(),original_scene_files_modified=False,
        changes='r1 initial XY only; original authored cargo, robots2/3, model, camera, physics unchanged',cpu_integration_steps=0))
    print(json.dumps(dict(output=str(a.output),selected={k:v['selected_xy'] for k,v in selected.items()})),flush=True)


if __name__=='__main__':main()
