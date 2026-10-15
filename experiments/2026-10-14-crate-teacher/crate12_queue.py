"""Write ONE disabled diagnostic queue for the clean, pushed crate12 SHA.

No VM creation, submission, monitoring or changes to any earlier queue.
Operations must verify remote seed reservations and admit the diagnostics.
"""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
TEMPLATE=QUEUE/'20261015-crate-49d11b8e.json'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def main():
    p=argparse.ArgumentParser();p.add_argument('--sha',required=True);a=p.parse_args()
    sha=git('rev-parse','HEAD')
    if a.sha!=sha or git('branch','--show-current')!='claude/act-crate-teacher':
        raise ValueError('queue must name the current crate branch SHA')
    if git('status','--porcelain'):raise ValueError('clean source required')
    remote=git('ls-remote','origin','refs/heads/claude/act-crate-teacher').split()[0]
    if remote!=sha:raise ValueError('push verification required')
    prior={str(f):digest(f) for f in QUEUE.glob('*.json')}
    old=json.loads(TEMPLATE.read_text())
    inherit=('branch','pr','host','machine_type','azure_allowed','submission_owner','source_worktree',
             'runner_cwd','runner_note','stop_rule','admission','speed_limit',
             'max_combined_concurrency','max_parallel_per_stage')
    q={k:old[k] for k in inherit}
    q.update(owner='codex-crate12',sha=sha,remote_verified_sha=remote,
             created_utc=datetime.now(timezone.utc).isoformat(),status='awaiting_diagnostic_admission',
             ready=False,runs_enabled=False,run_count=13,stage_counts={'reproduction':3,'diagnostic':10,'gate':0},
             stage_order=['reproduction + diagnostic, separate denominators','coordinator review; no gate in this queue'],
             stage_max_parallel={'reproduction':10,'diagnostic':10},
             cargo_scene_version='crate_mass_025_v1',crate_profile='crate12_v1',
             gate_promotion_authorized_if_all_conditions_pass=False,
             coordinator_approval={'approved':False,'sha':sha,'required_before':'gate',
                                   'prior_approval_inherited':False},
             purpose='Three exact-geometry reproductions and ten new diagnostic seeds, no gate or training.',
             criteria={'weld':'off','training_rgb':False,'top_camera_control':False,
                       'denominators':'fresh N=10 (near_wall 2/10), reproduction N=3 (near_wall 1/3); never pool',
                       'success':'physical prefix hold AND own-input release authorization AND release success AND distinct lugs; audit violations=0',
                       'count_failures':['handoff','timeout','HOST_ERROR','unknown RGB','input violation'],
                       'start_los':'fresh: off/unverified; reproductions: original saved plan unchanged',
                       'minimum_future_gate':'same profile >=38/40, separately approved; gate absent here'},
             storage_budget_mib={'diagnostic':1280,'reproduction':384,'total_new_raw_upper_estimate':1664,
                                 'copies_budgeted_separately':True},
             candidate_record={'record':str(HERE/'crate12.md'),'summary':str(HERE/'crate12-summary.json'),
                               'new_remote_runs':0},
             seed_reservation={'fresh_diagnostic':list(range(77990,78000)),
                               'reproductions':[77978,77981,77982],'never_train':True,
                               'local_unused_verified':True,'remote_unused_verified':False,
                               'remote_check':'SSH gcp1 ProxyCommand failed at gcloud instances describe; no VM started'},
             remaining_unverified=['GCP physical effects and fresh RGB colour assignment accuracy',
                                   'near_wall still 0/11 saved wall-feasible paired stances; physical impossibility not established',
                                   'actual RGB landmark identification/map localization and pose correction',
                                   'remote seeds, credit stop, disk, concurrency, first30 speed and coordinator approval'],
             preconditions=[
                 'Operations only: verify remote unused seeds/reservations before admission. Never replace seeds after results.',
                 'Project ugrp-act-train-1014 only; verify credit stop, 8h stop, 20min idle and disk budget.',
                 'Freeze clean pushed SHA and plan hashes. Do not inherit legacy approval or pool profiles/machines.',
                 'Reserve slots under shared admission lock, combined <=40 and crate <=10; measure first30 at actual load.',
                 'Review own RGB, fixed signals, source tags and first30 command/decision ledgers; unknowns stay failures.',
                 'Confirmed common physical/control defect: stop owned affected running/pending jobs, preserve raw and fix first.',
                 'Keep near_wall in denominators. Retrieve and hash all 13 results including HOST_ERROR.',
                 'No gate jobs, no training, no automatic promotion or host fallback. Coordinator approval remains false.'
             ],plan_sha256={},runs=[],previous_queues_sha256=prior)
    for stage,name in [('reproduction','repro_plan_crate12.json'),('diagnostic','diag_plan_crate12_77990.json')]:
        f=HERE/name;plan=json.loads(f.read_text());q['plan_sha256'][name]=digest(f)
        for i,e in enumerate(plan['episodes']):
            run=f"crate-{'reproduction' if stage=='reproduction' else 'diag'}-{e['seed']}-{sha[:8]}"
            payload=['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan',str(f.relative_to(ROOT)),
                     '--episode',str(i),'--grasp-cap-s','80','--cap-s','90','--observe-mode','backoff_v3',
                     '--zone-slots','zone','--reach-mode','pad_window_v2','--own-pose-source','commands',
                     '--held-object','hidden_v1','--setdown-lookaround','setdown_lookaround_own_v2',
                     '--crate-scene','crate_mass_025_v1','--crate-lift-pose','crate_antipodal_grasp_v1',
                     '--rgb-lift','crate_rgb_lift_v3','--teacher-stability','align_relook_v1',
                     '--teacher-search','search_reacquire_v1','--approach-goal-set','approach_goal_set_v1',
                     '--crate-approach-recovery','crate_approach_recovery_v1','--crate-profile','crate12_v1',
                     '--recording-mode','success_measurement','--execution-host','gcp1','--pr','500',
                     '--out',f'/home/ugrp/ugrp-sim/runs/{run}/raw']
            q['runs'].append({'stage':stage,'seed':e['seed'],'scenario_id':e['scenario_id'],'near_wall':e['near_wall'],
                             'name':run,'ready':False,'runs_enabled':False,'status':'awaiting_diagnostic_admission',
                             'maximum_sim_s_per_episode':170,'max_parallel':10,'max_combined_concurrency':40,
                             'payload':payload,'command':['python3','scripts/remote_run.py','--host','gcp1','--detach',
                             '--class','dev','--pr','500','--per-run-mb','128',str(ROOT),run,'--',*payload]})
    assert len(q['runs'])==13
    assert sum(r['near_wall'] for r in q['runs'] if r['stage']=='diagnostic')==2
    out=QUEUE/f'20261015-crate-diag-{sha[:8]}.json'
    with out.open('x') as f:json.dump(q,f,ensure_ascii=False,indent=2);f.write('\n')
    assert all(digest(Path(f))==h for f,h in prior.items()),'an earlier queue changed concurrently'
    check=json.loads(out.read_text());assert check==q
    print(json.dumps({'queue':str(out),'sha256':digest(out),'runs':13,'previous_queues_unchanged':len(prior),
                      'coordinator_approval':False,'runs_enabled':False}))


if __name__=='__main__':main()
