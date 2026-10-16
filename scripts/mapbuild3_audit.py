"""Read-only cross-cohort setup audit on gcp2 CPU; no integration or actor input.

Saved tick0 states and authored/pre-settle starts are separate denominators.
Missing exact tick0 is UNKNOWN, never silently replaced by an authored reset.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim.spawn_overlap_check import check,OPTION
from scripts.mapbuild3_prepare import named_sets


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')


def run(a):
    if platform.system()!='Linux' or not platform.node().startswith('ugrp-sim-gcp2'):
        raise ValueError('GCP2_CPU_ONLY')
    if not a.spawn_overlap_check_v1:raise ValueError('DEFAULT_OFF')
    import numpy as np
    import mujoco
    a.output.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.renderer_source));sys.path.insert(1,str(a.renderer_source/'scripts'))
    import scripts,sim
    scripts.__path__.insert(0,str(a.renderer_source/'scripts'));sim.__path__.insert(0,str(a.renderer_source/'sim'))
    os.chdir(a.renderer_source)
    from scripts import probe_scene_tex2 as st
    from scripts.generate_scene_textures import MAPS
    from scripts.zone_teacher import FOLDED
    _,_,hardware,_,_=st.build_model(MAPS[0],'walls_floor_contrast_v5_indigo110_s80')
    protocol=json.loads(a.protocol.read_text());selected=set(protocol['train_seeds']+protocol['validation_seeds'])
    final=set(protocol['final_evaluation_seeds']);rows=[];manifest={}
    specs=[]
    for group,seeds,directory in [('act16w_record',selected,'act16w-resume2-record-references'),
                                  ('act16w_heldout',final,'act16w-resume2-final40-references')]:
        base=a.act_inputs/directory
        for planpath in sorted(base.glob('case-*/world-000/plan.json')):
            plan=json.loads(planpath.read_text())
            if plan['seed'] in seeds:specs.append((group,planpath,planpath.parent/'scene.xml',None))
    # Exact saved native/Warp evaluator tick0 rows, where already flushed.
    states={}
    for path in a.act_inputs.glob('act16w-resume2-data-r2/group-*/controller/world-*-states.npz'):
        index=int(path.stem.split('-')[1]);planpath=path.parent/f'world-{index:03d}'/'plan.json'
        if planpath.is_file():states[json.loads(planpath.read_text())['seed']]=path
    for group,base in [('warp8_beam',a.warp_inputs/'beam40-r2'),
                       *[('warp8_release_A',a.warp_inputs/('releaseA-'+tag+'-c312')) for tag in ('s1','s3','s6')]]:
        for planpath in sorted(base.glob('world-*/raw/plan.json')):
            index=int(planpath.parent.parent.name.split('-')[1]);state=base/f'world-{index:03d}-states.npz'
            specs.append((group,planpath,planpath.parent/'scene.xml',state if state.is_file() else None))
    for group,planpath,xmlpath,statepath in specs:
        plan=json.loads(planpath.read_text());seed=plan['seed']
        if not xmlpath.is_file():raise ValueError('MISSING_ORIGINAL_XML:'+str(xmlpath))
        tree=ET.fromstring(xmlpath.read_text());asset_remaps=[]
        for node in tree.iter():
            file=node.get('file','')
            if file.startswith('/') and '/sim/assets/' in file:
                replacement=a.renderer_source/'sim/assets'/file.split('/sim/assets/',1)[1]
                if not replacement.is_file():raise ValueError('MISSING_SOURCE_ASSET:'+file)
                asset_remaps.append(dict(original=file,resolved=str(replacement),sha256=digest(replacement)))
                node.set('file',str(replacement))
        m=mujoco.MjModel.from_xml_string(ET.tostring(tree,encoding='unicode'));d=mujoco.MjData(m);sets=named_sets(m)
        # Reconstruct authored reset: same explicit spawn poses, FOLDED command
        # joint targets and original per-plan beam placement, with zero stepping.
        for rid,spawn in plan['spawns'].items():
            st._free_pose(m,d,rid+'__robot',spawn[:3],spawn[3]);st.set_arm(m,d,rid,FOLDED,hardware)
        if 'beam_pose' in plan:
            x,y,yaw=plan['beam_pose'];body='cargo_beam_1'
            st._free_pose(m,d,body,(x,y,st.default_free_z(m,body)),yaw)
        report=check(m,d,**sets,option=OPTION)
        rows.append(dict(cohort=group,seed=seed,state_scope='authored_reset_before_native_settle',
            original_task_tick0=False,asset_remaps=asset_remaps,plan=str(planpath),xml=str(xmlpath),**report))
        statepath=states.get(seed) if group=='act16w_record' else statepath
        if statepath:
            saved=np.load(statepath)
            if int(saved['ticks'][0])!=0:raise ValueError('NONZERO_FIRST_SAVED_TICK')
            if saved['qpos'].shape[1]!=m.nq:raise ValueError('EXACT_STATE_MODEL_DIM_REQUIRED')
            d.qpos[:]=saved['qpos'][0];d.qvel[:]=saved['qvel'][0]
            report=check(m,d,**sets,option=OPTION)
            rows.append(dict(cohort=group,seed=seed,state_scope='saved_task_tick0',original_task_tick0=True,
                state=str(statepath),plan=str(planpath),xml=str(xmlpath),**report))
            manifest[str(statepath)]=digest(statepath)
        manifest[str(xmlpath)]=digest(xmlpath);manifest[str(planpath)]=digest(planpath)
        write(a.output/'audit-progress.json',dict(completed_seed_n=len({(r['cohort'],r['seed']) for r in rows}),
            overlapping_rows=[dict(cohort=r['cohort'],seed=r['seed'],scope=r['state_scope'],pairs=r['pair_count']) for r in rows if not r['accepted']]))
        print(group,seed,report['status'],report['pair_count'],flush=True)
    counts=[]
    for group in ('act16w_record','act16w_heldout','warp8_beam','warp8_release_A'):
        expected=40
        for scope in ('authored_reset_before_native_settle','saved_task_tick0'):
            sub=[r for r in rows if r['cohort']==group and r['state_scope']==scope]
            counts.append(dict(cohort=group,scope=scope,planned_n=expected,checked_n=len(sub),
                missing_unknown_n=expected-len(sub),overlapping_n=sum(not r['accepted'] for r in sub),
                accepted_n=sum(r['accepted'] for r in sub),reasons=dict(Counter(k for r in sub for k in r['reasons'])),
                stages=[dict(stage='planned',cumulative_pass_n=expected,rejected_n=0),
                        dict(stage='available_state',cumulative_pass_n=len(sub),rejected_n=expected-len(sub)),
                        dict(stage='nonpenetrating',cumulative_pass_n=sum(r['accepted'] for r in sub),rejected_n=sum(not r['accepted'] for r in sub))]))
    write(a.output/'audit-rows.json',rows);write(a.output/'input-sha256.json',manifest)
    write(a.output/'rejection_table.json',dict(raw=[str(a.act_inputs),str(a.warp_inputs)],reproduction=sys.argv,cohorts=counts,
        reasons=dict(Counter(k for r in rows for k in r['reasons']))))
    write(a.output/'summary.json',dict(status='AUDITED_WITH_EXPLICIT_UNKNOWN',mujoco=mujoco.__version__,
        cpu_integration_steps=0,model_calls=0,other_worker_code_changes=0,counts=counts,
        native_contact_scope='gcp2 native mj_forward; source XML and saved state hashes, not Warp solver or model success',
        saved_tick0_scope='post-setup recorded state; authored/pre-settle audit separately; missing original tick0 unknown'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('act-inputs','warp-inputs','protocol','renderer-source','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--spawn-overlap-check-v1',action='store_true');run(p.parse_args())
