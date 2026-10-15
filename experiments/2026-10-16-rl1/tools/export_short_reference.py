"""Finite C3.12 asset export for the exact rl1b shared-scene reset XML.

No teacher object, task actions, policy, GPU physics or training is created.
L4 paths match the subsequent owner's asset references byte for byte.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from simalt_host import gcp2_identity


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    for key in ('teacher-source','plan','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();host=gcp2_identity()
    if not a.enabled or host['instance']!='ugrp-act-l4-gcp2':p.error('explicit L4 asset export only')
    sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    teacher_sha=subprocess.check_output(['git','-C',str(a.teacher_source),'rev-parse','HEAD'],text=True).strip()
    if teacher_sha!='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8':p.error('exact frozen scene required')
    for source in (ROOT,a.teacher_source):
        if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no']):p.error('clean source required')
    import mujoco
    if mujoco.__version__!='3.12.0':p.error('C3.12 reference compiler required')
    sys.path.insert(0,str(a.teacher_source))
    from sim.grasp_act_scene import make_scene
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.s2_realism_camera_binding import bind_camera
    from simalt_compiled_compat import export_reference,export_geometry
    plan=json.loads(a.plan.read_text())['episodes'][0]
    if plan.get('shared_scene_seed_v1')!=919015:p.error('prefit sealed shared-scene profile required')
    a.out.mkdir(parents=True,exist_ok=False)
    os.environ['UGRP_SIM_OBSERVER_WIDTH']='320';os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
    world=None
    report=dict(status='running',source_sha=sha,teacher_sha=teacher_sha,host=host,
        geometry_seed=plan['shared_scene_seed_v1'],reset_seed=plan['seed'],task_actions=0,gpu_steps=0,
        scope='compiler assets only; scene initialization is not a task rollout',reproduce=sys.argv)
    try:
        scene=make_scene({**plan,'end_color_scene':'off'})
        scene.config['setup_only']['spawns'].update(plan['spawns'])
        world=build_world(scene,drive_profile=PROFILE,seed=plan['shared_scene_seed_v1'],width=640,height=480,
            render=False,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,
            roller_collision='mesh',idle_robot_contacts='off')
        for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        xml=a.out/'runtime-scene.xml';xml.write_text(world.scene_xml)
        export_reference(world.model,xml,mujoco.__version__,a.out/'compiled-312.json')
        export_geometry(world.model,xml,mujoco.__version__,a.out/'compiled-geometry312.npz')
        report.update(status='compiled_export_only',initialization_sim_time_s=float(world.data.time))
    except BaseException as error:
        report.update(status='HOST_ERROR',error_type=type(error).__name__,error=str(error));raise
    finally:
        if world is not None:world.close()
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
