"""Static ACT6 gate/record/student plans, reusing the pinned scene planner."""
import argparse
from collections import Counter
from pathlib import Path
from harness.grasp_act_data import write_json
from scripts.run_grasp_act_recovery import dependency_modules

GATE_SEEDS=list(range(8316600,8316640))
RECORD_SEEDS=list(range(86600,86650))
STUDENT_SEED=91660


def prepare(dependency_root,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with dependency_modules(dependency_root):
        from scripts import make_solo_teacher_plan as planner
        for name,seeds,split in [('gate',GATE_SEEDS,'act6_gate'),('record',RECORD_SEEDS,'train')]:
            counts=Counter();episodes=[]
            for index,seed in enumerate(seeds):
                kind=('cyan','red','green','yellow')[index%4]
                e=planner.episode(counts[kind],kind,seed,split);counts[kind]+=1
                e.update(pr=504,negative_probe=False,gate_eligible=name=='gate',training_eligible=name=='record')
                episodes.append(e)
            write_json(output/f'act6-{name}-plan.json',{'episodes':episodes,'kinds':dict(counts),
                'seed_inventory_verified':False,'approved':False,'ready':False,
                'scope':'static setup only; live remote unused inventory required before execution'})
        old_range=planner.START_RANGE_M
        try:
            planner.START_RANGE_M=(.4,.8)
            e=planner.episode(0,'cyan',STUDENT_SEED,'heldout_start')
        finally:planner.START_RANGE_M=old_range
        write_json(output/'act6-student-plan.json',{
            'seed':e['seed'],'scenario_id':e['scenario_id'],'scenario_source_sha256':e['scenario_source_sha256'],
            'map_id':e['map_id'],'object_kind':e['kind'],'item_id':e['item_id'],'robot_id':e['robot_id'],
            'role':e['role'],'skill':'grasp_release','spawns':e['spawns'],
            'target_setup_xy':e['cargo_pose_m'][:2], 'setup_source':'same static-only solo planner',
            'seed_inventory_verified':False})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dependency-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.dependency_root,a.output)


if __name__=='__main__':main()
