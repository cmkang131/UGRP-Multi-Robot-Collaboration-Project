"""Prepare local comparison plans/disabled queue only. Never submits a host job."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from scripts.make_grasp_act_plan import prepare

ROOT=Path(__file__).resolve().parents[1]
EXP=Path('experiments/2026-10-14-e2e18-grasp-rootcause')
OUT=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
OLD=OUT/'20261015-grasp-search19-06558d64-diag.json'
FLAGS=('approved','enabled','ready','stage_ready','runs_enabled','submitted',
       'operator_activation_authorized','execute','coordinator_approval','gate40_approved',
       'record_training','training_approved','automatic_promotion','pool_with_previous_profiles',
       'gate_promotion_authorized_if_all_conditions_pass','speed_promotion_authorized_if_all_conditions_pass')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def novel_inventory():
    paths=list(OUT.glob('*.json'))
    paths+=list(EXP.glob('*plan.json'))
    paths+=list(Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs').glob('*/diagnostic*/episode-*/raw/plan.json*'))
    seeds=set()
    def collect(o):
        if isinstance(o,dict):
            for k,v in o.items():
                if k=='seed' and isinstance(v,int):seeds.add(v)
                elif k in ('seeds','new_seeds') and isinstance(v,list):seeds.update(x for x in v if isinstance(x,int))
                else:collect(v)
        elif isinstance(o,list):
            for v in o:collect(v)
    for path in paths:
        if 'teacher-search20-' in path.name:continue
        if path.suffix=='.zst':
            data=subprocess.check_output(['zstd','-q','-dc',str(path)])
        else:data=path.read_bytes()
        collect(json.loads(data))
    return seeds,len(paths)


def prepare_plans():
    used,n=novel_inventory();seed=8312200
    while set(range(seed,seed+12))&used:seed+=12
    repro=json.loads((EXP/'teacher-search19-repro4-plan.json').read_text())
    repro['purpose']='search20 exact search19 setups; diagnostic reproduction N=4, not gate'
    novel=prepare(count=12,seed=seed,split='development',pair=True,visible_start=True,
                  start_nominal_goal_feasible='start_nominal_goal_feasible_v1')
    novel['purpose']='search20 unexecuted local-novel diagnostic seeds N=12; remote reservation unverified'
    inventory={'files_parsed':n,'new_seeds':list(range(seed,seed+12)),
               'local_conflicts':[],'remote_inventory_verified':False}
    for candidate in ('base','v6'):
        for stage,data in (('repro4',repro),('novel12',novel)):
            data=deepcopy(data)
            for ep in data['episodes']:
                ep['cargo_scene']='off' if candidate=='base' else 'cargo_v6'
                if candidate=='v6':
                    prior=ep['scenario_id'];ep['scenario_id']=prior[:-3]+'_v6'
                    path=ROOT/'configs/zone_study_scenarios_v6'/(ep['scenario_id']+'.json')
                    config=json.loads(path.read_text())
                    assert ep['map_id']==config['map_id']
                    assert not any(p['kind'] in ('tile','can') for p in config['eval']['setup']['placements'])
                    ep['scenario_source_sha256']=digest(path)
                    ep['comparison_parent_scenario']=prior
                    ep['initial_scene_context']='cargo_v6: same spawns/beam/pan; tile/can replaced with authored boxes'
            data['student_evaluation']=False;data['recording']=False
            (EXP/f'teacher-search20-{candidate}-{stage}-plan.json').write_text(json.dumps(data,indent=2)+'\n')
    (EXP/'search20-seed-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    print(json.dumps(inventory))


def queue(sha):
    if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('full commit SHA required')
    if subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()!=sha:raise ValueError('queue must bind current HEAD')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],text=True).strip():raise ValueError('committed clean source required')
    prior=json.loads(OLD.read_text());profiles={**prior['profiles'],'search20':'search20_v1'}
    runs=[];candidates=[]
    for candidate in ('base','v6'):
        seeds=[];plans={}
        for stage in ('repro4','novel12'):
            plan=EXP/f'teacher-search20-{candidate}-{stage}-plan.json';rows=json.loads(plan.read_text())['episodes']
            current=[x['seed'] for x in rows];seeds+=current;plans[stage]=str(plan)
            name=f'grasp-search20-{candidate}-{stage}-gcp-{sha[:8]}'
            command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','484',
                '--per-run-mb','640',str(ROOT),name,'--','.venv-sim/bin/python','-m','scripts.run_grasp_act_batch',
                '--root','../../runs/'+name,'--plan',str(plan),'--concurrency',str(min(16,len(rows))),
                '--cap-s','60','--execution-host','gcp1','--speed-gate-limit','6.0','--diagnostic-only']
            for k,v in profiles.items():
                if k!='self_pose_source':command+=['--'+k.replace('_','-'),v]
            runs.append({**dict.fromkeys(FLAGS,False),'candidate':candidate,'stage':stage,'name':name,
                'source_sha':sha,'plan':str(plan),'plan_sha256':digest(plan),'seeds':current,'planned_N':len(rows),
                'qualification_denominator':0,'max_parallel':len(rows),'maximum_sim_s_per_episode':60,
                'command':command,'depends_on':['independent_review','explicit_coordinator_approval',
                    'current_remote_seed_inventory_and_reservation','cost_disk_load_memory_admission',
                    'same_machine_type_first30_record','clean_source_at_exact_sha']})
        candidates.append({'name':'search20' if candidate=='base' else 'search20+cargo_v6',
            'cargo_scene':'off' if candidate=='base' else 'cargo_v6','seeds':seeds,'plans':plans})
    assert candidates[0]['seeds']==candidates[1]['seeds']
    paths=[EXP/'search20.md',EXP/'search20-replay-summary.json',EXP/'search20-error-distribution.json',
           *[Path(r['plan']) for r in runs]]
    record={**dict.fromkeys(FLAGS,False),'schema':'ugrp.grasp_act.search20.comparison_queue.v1',
        'status':'REVIEW_ONLY_NOT_SUBMITTED','owner':'e2e18-rootcause','branch':'claude/e2e18-grasp-rootcause',
        'pr':484,'created_utc':datetime.now(timezone.utc).isoformat(),'sha':sha,'base_sha':'06558d64a2fd1bd34e59cfea7e0b40045b6dab77',
        'source_worktree':str(ROOT),'host':'gcp1','project_id':'ugrp-act-train-1014','machine_type':'n4-highcpu-64',
        'profiles':profiles,'candidates':candidates,'candidate_count':2,'runs':runs,'planned_N':32,
        'qualification_denominator':0,'planned_disk_mib':20480,'planned_max_parallel':16,
        'seed_inventory':json.loads((EXP/'search20-seed-inventory.json').read_text()),
        'previous_queue':str(OLD),'previous_queue_sha256':digest(OLD),
        'source_hashes':{str(p):digest(p) for p in paths},
        'scene_decision':'keep v4 as matched control, compare explicit v6; no pooling or default switch',
        'remaining':['new physical trajectories unmeasured','budget/time guards are cooperative, not hard realtime',
            '140mm admission intentionally rejects old 15.5mm stance','no gate/recording/training/promotion authorization']}
    path=OUT/f'20261015-grasp-search20-{sha[:8]}-diag.json'
    with path.open('x') as f:f.write(json.dumps(record,indent=2)+'\n')
    print(path)


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha');a=p.parse_args()
    if a.sha:queue(a.sha)
    else:prepare_plans()


if __name__=='__main__':main()
