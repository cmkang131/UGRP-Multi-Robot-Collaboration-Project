"""Default-off ACT17 v7 scene/plan adapter; frozen teacher/backend files unchanged.

The canonical v7 scenario dictionary is passed to the existing Scene factory.
This avoids the frozen teacher's v4-only string lookup. Only appearance and
authored setup change; no teacher motion rule, camera or physical score changes.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import runpy
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
B=Path('/home/ugrp/ugrp-sim')
Q=B/'src/f0db6b1abb842ea65b71c433738210254f300a7c'
T=B/'src/warp1-teacher-snapshot-6f057f7e'
KINDS=('cyan','red','green','yellow')
PROFILE='grasp_act_teal_blue_v1'
SCENE='walls_floor_contrast_v5_indigo110_s80'
SCENARIOS=('s1_normal_mixed_v7','s2_unmapped_blockage_v7','s3_late_rendezvous_v7',
           's5_moved_dropped_item_v7','s6_novel_relation_v7','s7_pair_with_solo_v7','s8_mixed_tiers_v7')


def scenario(sid):
    if sid not in SCENARIOS:
        raise ValueError('registered v7 training scenario required; s4 remains held out')
    path=ROOT/'configs/zone_study_scenarios_v7'/(sid+'.json')
    value=json.loads(path.read_text())
    if value['scenario_id']!=sid or any(p['kind'] not in (*KINDS,'long_beam') for p in value['eval']['setup']['placements']):
        raise ValueError('v7 inventory must exclude can/tile/crate/frame')
    return value,path


def color_xml(xml):
    root=ET.fromstring(xml)
    present=[]
    for suffix,rgba in [('band_neg','.02 .95 .60 1'),('band_pos','.02 .02 .95 1')]:
        geoms=root.findall('.//geom')
        found=[g for g in geoms if g.get('name')=='cargo_beam_1__'+suffix]
        if len(found)>1:
            raise ValueError('duplicate beam end band')
        present.append(bool(found))
        for geom in found:
            geom.set('rgba',rgba)
    if any(present) and not all(present):
        raise ValueError('incomplete long-beam end colors')
    custom=root.find('custom')
    if custom is None:
        custom=ET.SubElement(root,'custom')
    # Explicit declaration is paired with scenario/source hashes and actual
    # band/color audit; the text alone is not runtime appearance proof.
    for name,value in [('scene_profile',SCENE),('end_color_scene',PROFILE)]:
        matches=[e for e in custom.findall('text') if e.get('name')==name]
        if len(matches)>1:
            raise ValueError('duplicate scene declaration')
        element=matches[0] if matches else ET.SubElement(custom,'text',name=name)
        element.set('data',value)
    return ET.tostring(root,encoding='unicode')


@contextmanager
def installed():
    sys.path.insert(0,str(Q/'scripts'))
    sys.path.insert(0,str(T))
    import sim
    sim.__path__.append(str(Q/'sim'))
    sim.__path__.append(str(ROOT/'sim'))
    import warp_act_scene
    original=warp_act_scene.make_scene
    def make_scene(plan):
        data,path=scenario(plan['scenario_id'])
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if plan.get('scenario_source_sha256')!=digest or plan['kind'] not in KINDS:
            raise ValueError('plan/scenario source mismatch or non-BOX target')
        # Scene.from_scenario(dict, seed) performs its existing validation and
        # setup without trying the frozen v4 filename route.
        scene=original({**plan,'scenario_id':data,'end_color_scene':'off'})
        transform=scene.robot_transform
        def wrapped(xml,**kwargs):
            return color_xml(transform(xml,**kwargs))
        scene.robot_transform=wrapped
        scene.manifest['act17_v7']=dict(scenario_id=plan['scenario_id'],scenario_sha256=digest,
            cargo_version='v6',scenario_version='v7',end_color_scene=PROFILE,
            heavy_crate=False,excluded_cargo=['can','tile','heavy_crate','tri_frame'],
            scene_profile=SCENE,adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        return scene
    warp_act_scene.make_scene=make_scene
    try:
        yield
    finally:
        warp_act_scene.make_scene=original


def plans(split,protocol,out):
    from act16w_runtime import require_gcp2,frozen_source
    require_gcp2(training=True);source=frozen_source(ROOT)
    sys.path.insert(0,str(T))
    from scripts import make_solo_teacher_plan as original
    def candidates(kind):
        rows=[]
        for sid in SCENARIOS:
            value,path=scenario(sid)
            rows.extend((sid,path,value,p) for p in value['eval']['setup']['placements'] if p['kind']==kind)
        return rows
    original.candidates=candidates
    seeds=protocol[split+'_seeds'];counts=Counter();rows=[]
    for i,seed in enumerate(seeds):
        kind=KINDS[i%len(KINDS)]
        row=original.episode(counts[kind],kind,seed,'heldout_start' if split=='final' else 'train')
        counts[kind]+=1
        row.update(episode_id='act17-v7-'+str(seed),batch='act17-v7-'+split,pr=539,
            end_color_scene=PROFILE,negative_probe=False,gate_eligible=split=='gate',
            training_eligible=split=='record',act17_v7=True)
        rows.append(row)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:
        json.dump(dict(schema='ugrp.act17.v7.plans.v1',source_sha=source,split=split,
            episodes=rows,distribution=dict(counts),s4_heldout=True),f,indent=2)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--action',choices=['plans','launch'],required=True)
    p.add_argument('--split',choices=['gate','record','final'])
    p.add_argument('--protocol',type=Path)
    p.add_argument('--out',type=Path)
    p.add_argument('runner',nargs=argparse.REMAINDER)
    a=p.parse_args()
    if not a.enabled:
        p.error('ACT17 v7 is default OFF')
    from act16w_runtime import require_gcp2,frozen_source
    require_gcp2(training=True);frozen_source(ROOT)
    if a.action=='plans':
        if not a.split or not a.protocol or not a.out:
            p.error('plans require split, protocol and new output')
        return plans(a.split,json.loads(a.protocol.read_text()),a.out)
    runner=a.runner[1:] if a.runner[:1]==['--'] else a.runner
    target=ROOT/'scripts/act16w_native_run.py'
    sys.argv=[str(target),*runner]
    with installed():
        runpy.run_path(str(target),run_name='__main__')


if __name__=='__main__':
    main()
