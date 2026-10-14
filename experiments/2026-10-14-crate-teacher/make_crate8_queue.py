"""Write the local diagnostic queue after clean commit/push; never submit jobs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
EXP=Path(__file__).resolve().parent
ADMIN=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
OLD='20261014-crate-c5a76175.json'
PLAN='diag_plan_crate8_77960.json'


def available_slots(total_running, crate_running):
    if not 0 <= crate_running <= total_running:
        raise ValueError('inconsistent live counts')
    return max(0,min(10-crate_running,40-total_running))


def build(sha, summary):
    plan=json.loads((EXP/PLAN).read_text())
    old=json.loads((ADMIN/'vm3-queue'/OLD).read_text())
    q={k:old[k] for k in ('branch','pr','host','machine_type','azure_allowed','submission_owner',
                         'source_worktree','runner_cwd','runner_note','criteria','stop_rule')}
    q.update(owner='codex-crate8',sha=sha,remote_verified_sha=sha,created_utc=datetime.now(timezone.utc).isoformat(),
             status='ready',ready=True,runs_enabled=True,supersedes=[OLD],run_count=10,
             cargo_scene_version='crate_mass_025_v1',crate_lift_pose='crate_cartesian_lift_v1',
             max_combined_concurrency=40,max_parallel_per_stage=10,stage_max_parallel={'diagnostic':10},
             stage_counts={'diagnostic':10},
             admission={'count_scope':'all running/reserved jobs on gcp1, including other queues',
                        'available_slots':'max(0, min(10 - crate_running, 40 - total_running))',
                        'reservation':'operations must count and reserve slots under its shared admission lock before each launch; no independent check-then-launch',
                        'enforcement_verified':False},
             purpose='Fresh 10-run diagnostic only; no gate or training',
             profile=old['profile'].replace('crate_lift_pose_margin_v1','crate_cartesian_lift_v1'),
             seed_reservation={'seeds':list(range(77960,77970)),'split':'crate_diagnostic','never_train':True,
                               'local_unused_verified':True,'remote_unused_verified':False},
             baseline_diagnostic={'sha':old['sha'],'success_n':0,'N':10,'pool_with_new_candidate':False},
             speed_limit={'concurrency':40,'crate_concurrency':10,'median_wall_per_sim_max':3.5,
                          'basis':'Measure first30 at actual load on this machine; 40 is admission cap, not a measured speed qualification',
                          'on_incomplete_or_exceeded':'SPEED_GATE_FAIL; stop promotion and notify'},
             storage_budget_mib={'diagnostic':1280,'total_new_raw_upper_estimate':1280,
                                 'scope':'128 MiB/run including additional evaluation telemetry; budget copies separately'},
             plan_sha256={PLAN:hashlib.sha256((EXP/PLAN).read_bytes()).hexdigest()},
             candidate_record={'record':str(EXP/'crate8.md'),'summary':str(EXP/'crate8-summary.json'),
                               'local_tests':summary['local_tests'],'new_remote_runs':0},
             remaining_unverified=summary['remaining_unverified'],
             preconditions=[
                 'Verify GCP credit stop, 8h cap, 20min idle guard, disk budget and unused remote seeds before execution.',
                 'Freeze clean worktree and remote SHA; retain mass 0.25 kg, servo limits, physics, weld OFF, input boundary and all success thresholds.',
                 'Enforce combined active+reserved <=40 and crate active+reserved <=10 under a shared reservation lock; never launch all queues independently.',
                 'Inspect first30 and failure frames; compare measured joints and full contact loads to issued static assumptions. Stop same-defect jobs immediately.',
                 'Both input-audit counts must remain zero. load_detail is evaluator-only and must not enter teacher/LLM/ACT inputs.',
                 'No gate or automatic promotion. Retrieve failures and HOST_ERROR as part of N=10.'])
    q['runs']=[]
    for index,ep in enumerate(plan['episodes']):
        name=f"crate-diag-{ep['seed']}-{sha[:8]}"
        payload=['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan',f'experiments/2026-10-14-crate-teacher/{PLAN}',
                 '--episode',str(index),'--grasp-cap-s','80','--cap-s','90','--observe-mode','backoff_v3',
                 '--zone-slots','zone','--reach-mode','pad_window_v2','--own-pose-source','commands',
                 '--held-object','hidden_v1','--setdown-lookaround','off','--crate-scene','crate_mass_025_v1',
                 '--crate-lift-pose','crate_cartesian_lift_v1','--rgb-lift','crate_rgb_lift_v3',
                 '--teacher-stability','align_relook_v1','--teacher-search','search_reacquire_v1',
                 '--approach-goal-set','approach_goal_set_v1','--execution-host','gcp1','--pr','500',
                 '--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
        q['runs'].append({'stage':'diagnostic','seed':ep['seed'],'scenario_id':ep['scenario_id'],'name':name,
                          'ready':True,'status':'ready','runs_enabled':True,'max_parallel':10,'max_other_running':30,
                          'max_combined_concurrency':40,'maximum_sim_s_per_episode':170,'payload':payload,
                          'command':['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','500',
                                     '--per-run-mb','128',str(ROOT),name,'--',*payload]})
    assert len(q['runs'])==10 and {r['stage'] for r in q['runs']}=={'diagnostic'}
    return q


def main():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    assert git('branch','--show-current')=='claude/act-crate-teacher'
    assert not git('status','--porcelain')
    assert git('remote','get-url','origin')=='https://github.com/kcm0127-dotcom/ugrp.git'
    sha=git('rev-parse','HEAD')
    assert git('ls-remote','origin','refs/heads/claude/act-crate-teacher').split()[0]==sha
    summary=json.loads((EXP/'crate8-summary.json').read_text())
    assert summary['local_tests']['passed']>0 and summary['local_tests']['failed']==0
    for ref in summary['artifacts'].values():
        assert hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()==ref['sha256']
    q=build(sha,summary)
    dest=ADMIN/'vm3-queue'/f'20261015-crate-{sha[:8]}.json'
    assert not dest.exists()
    dest.write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    oldpath=dest.with_name(OLD);old=json.loads(oldpath.read_text())
    assert old['sha']=='c5a76175086473115eacd7bef6fe662e06fd908f'
    old.update(status='superseded',ready=False,runs_enabled=False,superseded_by=dest.name,
               superseded_reason='crate8 replaces failed legacy-prefix diagnostic; see crate8.md')
    for r in old['runs']:r.update(status='superseded',ready=False,runs_enabled=False)
    oldpath.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    assert json.loads(dest.read_text())==q
    delivery={'sha':sha,'queue':str(dest),'queue_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
              'superseded':str(oldpath),'new_remote_runs':0}
    (ADMIN/'crate8-delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    print(json.dumps(delivery))


if __name__=='__main__':main()
