"""Bind an inert comparison queue to an actually tested commit; never submit."""
import argparse,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
from scripts.prepare_grasp_act_search20_queue import FLAGS,EXP,ROOT,OUT,digest


def queue(sha,evidence,*,not_ready=False):
    report=json.loads(evidence.read_text())
    if report['source_sha']!=sha:raise ValueError('evidence SHA mismatch')
    passed=report['n']==6 and report['N']==6 and report['host_errors']==0 and report['interrupted']==0
    if not passed and not not_ready:raise ValueError('six-run acceptance has not passed; use --not-ready for a BLOCKED record only')
    if not report['remote_full_manifest_verified'] or not report['all_audits_enabled'] or report['audits_missing_N'] or report['input_invisible_total'] or report['input_held_total']:
        raise ValueError('missing integrity/input-audit acceptance')
    old=OUT/'20261015-grasp-search20-fd9995df-diag.json';prior=json.loads(old.read_text())
    profiles={**prior['profiles'],'search21':'search21_v1'};runs=[];candidates=[]
    for candidate,legacy in [('base','base'),('cargo_v6','v6')]:
        seeds=[];plans={}
        for stage in ('repro4','novel12'):
            plan=EXP/f'teacher-search20-{legacy}-{stage}-plan.json'
            stored=subprocess.check_output(['git','show',sha+':'+str(plan)],cwd=ROOT)
            if hashlib.sha256(stored).hexdigest()!=digest(plan):raise ValueError('plan not frozen in tested SHA')
            rows=json.loads(stored)['episodes'];indices=list(range(len(rows)))
            if stage=='repro4':indices=[next(i for i,r in enumerate(rows) if r['seed']==s) for s in (8311709,8311723,8311711,315709)]
            current=[rows[i]['seed'] for i in indices];seeds+=current;plans[stage]=str(plan)
            name=f'grasp-search21-{candidate}-{stage}-gcp-{sha[:8]}'
            command=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','484',
                '--per-run-mb','1536',str(ROOT),name,'--','.venv-sim/bin/python','-m','scripts.run_grasp_act_batch',
                '--root','../../runs/'+name,'--plan',str(plan),'--concurrency',str(min(6,len(rows))),
                '--cap-s','60','--execution-host','gcp1','--speed-gate-limit','6.0','--diagnostic-only',
                '--episode-indices',*map(str,indices)]
            for k,v in profiles.items():
                if k!='self_pose_source':command+=['--'+k.replace('_','-'),v]
            runs.append({**dict.fromkeys((*FLAGS,'review_passed'),False),'candidate':candidate,'stage':stage,
                'name':name,'source_sha':sha,'plan':str(plan),'plan_sha256':digest(plan),'seeds':current,
                'episode_indices':indices,'planned_N':len(rows),'qualification_denominator':0,
                'max_parallel':min(6,len(rows)),'maximum_sim_s_per_episode':60,'command':command,
                'depends_on':['current_gcp1_capacity_and_seed_reservation','existing_budget_duration_idle_guards',
                    'exact_tested_sha_and_committed_plans','operator_activation_of_this_inert_queue']})
        candidates.append({'name':candidate,'cargo_scene':'off' if candidate=='base' else 'cargo_v6','seeds':seeds,'plans':plans})
    assert candidates[0]['seeds']==candidates[1]['seeds']
    source=['sim/grasp_act_search21.py','sim/grasp_act_search20.py','sim/grasp_act_search19.py','sim/grasp_act_teacher_v3.py',
        'sim/grasp_act_pregrasp.py','sim/grasp_act_search15_modes.py','harness/grasp_act_admission.py',
        'scripts/run_grasp_act_batch.py','scripts/run_grasp_act_teacher.py']
    hashes={p:hashlib.sha256(subprocess.check_output(['git','show',sha+':'+p],cwd=ROOT)).hexdigest() for p in source}
    record={**dict.fromkeys((*FLAGS,'review_passed'),False),'schema':'ugrp.grasp_act.search21.comparison_queue.v1',
        'status':'REVIEW_ONLY_NOT_SUBMITTED' if passed else 'BLOCKED_FAILED_SHORT6','owner':'e2e18-rootcause','branch':'claude/e2e18-grasp-rootcause',
        'pr':484,'sha':sha,'base_sha':'fd9995df458e366f0fd52ad3b973314bf7e74fe6',
        'created_utc':datetime.now(timezone.utc).isoformat(),'source_worktree':str(ROOT),
        'host':'gcp1','project_id':'ugrp-act-train-1014','machine_type':'n4-highcpu-64',
        'profiles':profiles,'candidates':candidates,'candidate_count':2,'runs':runs,'planned_N':32,
        'planned_max_parallel':6,'host_total_concurrency_limit':40,'qualification_denominator':0,
        'short6_passed':passed,'source_hashes':hashes,'acceptance_evidence':str(evidence),'acceptance_evidence_sha256':digest(evidence),
        'previous_queue':str(old),'previous_queue_sha256':digest(old),
        'record':'experiments/2026-10-14-e2e18-grasp-rootcause/search21.md',
        'scene_decision':'base v4 reproduction control only; cargo_v6 separate; no pooling',
        'remaining':([] if passed else ['NOT_READY: 8311709 base tile_1 and v6 red_2, 315709 v6 yellow_1 stale-hazard envelope deadlock; no passed SHA'])+['32-run comparison not submitted','no gate40, camera training data, ACT training or promotion',
            'fresh 5mm geometry padding is not a physical or probabilistic safety guarantee']}
    path=OUT/f'20261015-grasp-search21-{sha[:8]}-diag.json'
    with path.open('x') as f:f.write(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--not-ready',action='store_true')
    a=p.parse_args();queue(a.sha,a.evidence,not_ready=a.not_ready)
