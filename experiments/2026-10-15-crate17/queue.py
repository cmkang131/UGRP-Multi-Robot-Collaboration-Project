"""Write a new SHA-bound review queue. Never connect to or launch a VM."""
import argparse,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
REPO='https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def build(sha,prior):
 old=json.loads((HERE.parent/'2026-10-14-crate-teacher/crate13-queue-contract.json').read_text())
 keep=('branch','pr','host','machine_type','azure_allowed','submission_owner','source_worktree','runner_cwd','runner_note','stop_rule','admission','max_combined_concurrency','max_parallel_per_stage')
 q={k:old[k] for k in keep}
 p=json.loads((HERE/'diagnostic-plan.json').read_text())
 q.update(owner='codex-crate17',sha=sha,created_utc=datetime.now(timezone.utc).isoformat(),
  status='awaiting_diagnostic_admission',approved=False,enabled=False,ready=False,runs_enabled=False,
  stage_ready={'reproduction':False,'diagnostic':False,'gate':False},run_count=30,
  stage_counts={'reproduction':10,'diagnostic':20,'gate':0},stage_order=['reproduction','diagnostic'],
  stage_max_parallel={'reproduction':10,'diagnostic':10},crate_profile='crate17_v1',cargo_scene_version='crate_mass_025_v1',
  candidates={'full':'crate17_v1','no_clearance':'crate17_no_clearance_v1'},
  per_candidate_stage_counts={'reproduction':5,'diagnostic':10,'gate':0},
  partial_admission={'scope':'row.approved at this SHA; global flags are batch defaults, not inherited approval',
   'first_two_row_ids':[0,1],'first_two_approved':False,'remaining_approved':False,
   'rule':'operations may approve ONLY these two rows during Sonnet review; remaining rows require APPROVE and first-two raw review'},
  coordinator_approval={'approved':False,'sha':sha,'required_before':'each admitted row; explicit row-level approval allows first two only','prior_approval_inherited':False},
  gate_approved=False,gate_enabled=False,training_approved=False,training_enabled=False,
  gate_promotion_authorized_if_all_conditions_pass=False,
  speed_limit={'concurrency':40,'crate_concurrency':10,'warn_above':3.5,'median_wall_per_sim_max':6.0,
   'basis':'measure first30 on same machine at actual admitted load; bounded planning offline only; physical speed unbenchmarked',
   'block_only':['median_wall_per_sim > 6.0','incomplete','HOST_ERROR']},
  criteria={'weld':'off','top_camera_control':False,'training_rgb':False,'held_object':'hidden_v1',
   'input_audit':{'held_world_reads':0,'invisible_measurements':0},
   'denominators':'per candidate reproduction5 development only; also keep original setup3 vs conditional-start2 separate. Fresh10 per candidate separate; paired seeds do not make 30 independent starts. Never pool old SHA/profile/host.',
   'minimum_future_gate':'separately approved >=40 accepted non-near-wall episodes, >=95%; full drawn/excluded denominator'},
  storage_budget_mib={'reproduction':1280,'diagnostic':2560,'total_new_raw_upper_estimate':3840},
  start_distribution=p['start_distribution'],
  near_wall_filter={k:v for k,v in p['near_wall_filter'].items() if k!='excluded_episodes'},
  excluded_starts={'path':str(HERE/'diagnostic-plan.json'),
   'sha256':digest(HERE/'diagnostic-plan.json'),'json_pointer':'/near_wall_filter/excluded_episodes'},
  seed_reservation=json.loads((HERE/'seed-reservation.json').read_text()),
  preconditions=['All approval and execution flags false; no VM access/launch by author.',
   'Operations must recheck live seed inventory, cost guards, disk and shared slots before admission.',
   'GCP project ugrp-act-train-1014 only; budget-stop untouched; 8h maximum and idle20 required.',
   'Same n4-highcpu-64 only; first30 raw review required; no gate/training or automatic promotion.',
   'Visible-relative teacher adapter retained; RGB-only pose inference and physical success unverified.',
   '15mm preferred / 5mm fallback geometric padding is not measured localization uncertainty; no robustness or success claim.'],
  candidate_record={'record':str(HERE/'README.md'),'summary':str(HERE/'summary.json')},
  plan_sha256={},runs=[],previous_queues_sha256=prior)
 for stage,filename in [('reproduction','reproduction-plan.json'),('diagnostic','diagnostic-plan.json')]:
  f=HERE/filename;plan=json.loads(f.read_text());q['plan_sha256'][filename]=digest(f)
  artifact=plan.get('start_distribution',{}).get('rejected_starts_artifact')
  if artifact:
   asset=HERE/artifact['path'];assert digest(asset)==artifact['sha256'];q['plan_sha256'][asset.name]=digest(asset)
  for i,e in enumerate(plan['episodes']):
   for candidate,profile in q['candidates'].items():
    name=f"crate17-{candidate}-{'reproduction' if stage=='reproduction' else 'diag'}-{e['seed']}-{sha[:8]}"
    payload=['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan',str(f.relative_to(ROOT)),'--episode',str(i),
     '--grasp-cap-s','80','--cap-s','90','--observe-mode','backoff_v3','--zone-slots','zone','--reach-mode','pad_window_v2',
     '--own-pose-source','commands','--held-object','hidden_v1','--setdown-lookaround','setdown_lookaround_own_v2',
     '--crate-scene','crate_mass_025_v1','--crate-lift-pose','crate_antipodal_grasp_v1','--rgb-lift','crate_rgb_lift_v3',
     '--teacher-stability','align_relook_v1','--teacher-search','search_reacquire_v1','--approach-goal-set','approach_goal_set_v1',
     '--crate-approach-recovery','crate_approach_recovery_v1','--crate-profile',profile,
     '--recording-mode','success_measurement','--execution-host','gcp1','--pr','500','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
    q['runs'].append({'row_id':len(q['runs']),'candidate':candidate,'crate_profile':profile,'stage':stage,'seed':e['seed'],'scenario_id':e['scenario_id'],'near_wall':e['near_wall'],'name':name,
     'approved':False,'enabled':False,'ready':False,'stage_ready':False,'runs_enabled':False,'submitted':False,
     'status':'awaiting_diagnostic_admission','maximum_sim_s_per_episode':170,'max_parallel':10,'max_combined_concurrency':40,
     'payload':payload,'command':['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','500','--per-run-mb','128',str(ROOT),name,'--',*payload]})
 assert len(q['runs'])==30 and not any(r['near_wall'] for r in q['runs'])
 return q

def main():
 p=argparse.ArgumentParser();p.add_argument('--sha',required=True);a=p.parse_args();sha=git('rev-parse','HEAD')
 if a.sha!=sha or git('branch','--show-current')!='claude/act-crate-teacher' or git('status','--porcelain'):raise ValueError('clean current crate SHA required')
 remote=git('ls-remote',REPO,'refs/heads/claude/act-crate-teacher').split()[0]
 if remote!=sha:raise ValueError('canonical pushed SHA required')
 prior={str(p):digest(p) for p in QUEUE.glob('*.json')};q=build(sha,prior);q['remote_verified_sha']=remote
 out=QUEUE/f'20261015-crate17-diag-{sha[:8]}.json'
 with out.open('x') as f:json.dump(q,f,ensure_ascii=False,separators=(',',':'));f.write('\n')
 assert all(digest(Path(p))==h for p,h in prior.items()),'prior queue changed'
 assert json.loads(out.read_text())==q
 print(json.dumps({'queue':str(out),'sha256':digest(out),'previous_queues_unchanged':len(prior),'runs':30,'approved':False}))
if __name__=='__main__':main()
