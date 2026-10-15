"""gcp2 CPU-only bounded static starts, no simulator construction.

Narrow short cohort BEFORE seeing any new outcomes: S1 cyan_1, frozen ACT15
appearance/physics. Scene-v5 ACT16w and other kinds/maps remain separate.
Sampling predicates/count bounds are the existing ACT14 frozen distribution.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from simalt_host import gcp2_identity


def fingerprint(plan):
    return hashlib.sha256(json.dumps({k:plan[k] for k in ('scenario_id','item_id','spawns')},sort_keys=True).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('teacher-source','actor-source','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();host=gcp2_identity()
    if host['instance']!='ugrp-sim-gcp2':p.error('CPU gcp2 only')
    a.out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(a.actor_source))
    from scripts.prepare_grasp_act_act14 import sample
    from scripts.run_grasp_act_recovery import dependency_modules
    ledger=[];counts=Counter();seen=set();groups={}
    with dependency_modules(a.teacher_source):
        from scripts import make_solo_teacher_plan as frozen
        candidates=frozen.candidates
        frozen.candidates=lambda kind:[r for r in candidates(kind) if r[0]=='s1_normal_mixed_v4' and r[3]['item_id']=='cyan_1']
        try:
            for split,seeds in (('train',range(919000,919040)),('eval',range(918000,918040))):
                rows=[]
                for seed in seeds:
                    plan=sample(0,'cyan',seed,frozen,ledger,counts)
                    key=fingerprint(plan)
                    if key in seen:raise ValueError('duplicate new reset state')
                    seen.add(key)
                    plan.update(episode_id=f'rl1b-{split}-{seed}',batch=f'rl1b-{split}',split=split,
                        setup_fingerprint=key,scene_profile='ACT15_frozen6f_floor_light_v1',map_id='zone_wide_door_geometry_v3')
                    cx,cy=plan['target_setup_xy'];x,y,_,yaw=plan['spawns']['r1']
                    station=frozen.cargo('cyan').station_m or .2002
                    plan['curriculum_setup_distance_m']=math.hypot(cx-station-x,cy-y)
                    plan['curriculum_setup_yaw_rad']=abs(math.atan2(math.sin(yaw),math.cos(yaw)))
                    rows.append(plan)
                groups[split]=rows
        finally:frozen.candidates=candidates
    spec=importlib.util.spec_from_file_location('rl1b_curriculum',ROOT/'scripts/rl_act_curriculum.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    curriculum=module.Curriculum([module.Start(r['seed'],r['curriculum_setup_distance_m'],r['curriculum_setup_yaw_rad'],r) for r in groups['train']],
        evaluation_seeds=[r['seed'] for r in groups['eval']],transition_limit=3,rng_seed=20261016,h4_curriculum_v1=True)
    # t=0 uses the same first quartile for ANY positive transition limit; limit3
    # here seals only the first RNG draw for exact-XML compiled asset export.
    startup=curriculum.sample(0,8)
    for name,rows in (('train-starts',groups['train']),('eval-starts',groups['eval']),
                      ('startup-train',startup),('startup-eval',groups['eval'][:8])):
        (a.out/(name+'.json')).write_text(json.dumps(dict(host=host,episodes=rows,
            scope='short same-model S1 cyan_1; no scene-v5/multikind generalization',
            rejection_table=str(a.out/'setup-funnel.json')),indent=2)+'\n')
    report=dict(counts=dict(counts),accepted=80,rejections=ledger,
        rejection_distribution=dict(Counter(r['category'] for r in ledger)),
        caps={'proposals_per_seed':400,'parking_checks_per_robot':2000},
        train_seeds=list(range(919000,919040)),eval_pool=list(range(918000,918040)),
        evaluation_seeds=list(range(918000,918008)),startup_train_seeds=[r['seed'] for r in startup],
        runtime_model_renders=0,physics_steps=0,optimizer_steps=0,
        source_sha=__import__('subprocess').check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip())
    (a.out/'setup-funnel.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rejections'}),flush=True)


if __name__=='__main__':main()
