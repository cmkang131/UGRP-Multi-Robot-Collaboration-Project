"""Create one review-only queue at the clean pushed SHA. No VM connection."""
import argparse,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()
def build(sha,prior):
 old=json.loads((HERE/'crate13-queue-contract.json').read_text())
 keep=('branch','pr','host','machine_type','azure_allowed','submission_owner','source_worktree','runner_cwd','runner_note','stop_rule','admission','max_combined_concurrency','max_parallel_per_stage')
 q={k:old[k] for k in keep}
 q.update(owner='codex-crate14',sha=sha,created_utc=datetime.now(timezone.utc).isoformat(),
  status='awaiting_diagnostic_admission',approved=False,enabled=False,ready=False,runs_enabled=False,
  stage_ready={'reproduction':False,'diagnostic':False,'gate':False},run_count=13,
  stage_counts={'reproduction':3,'diagnostic':10,'gate':0},stage_order=['reproduction','diagnostic'],
  stage_max_parallel={'reproduction':10,'diagnostic':10},crate_profile='crate14_v1',cargo_scene_version='crate_mass_025_v1',
  coordinator_approval={'approved':False,'sha':sha,'required_before':'any run','prior_approval_inherited':False},
  gate_approved=False,gate_promotion_authorized_if_all_conditions_pass=False,
  speed_limit={'concurrency':40,'crate_concurrency':10,'warn_above':3.5,'median_wall_per_sim_max':6.0,
    'basis':'record first30 on same machine at actual admitted load',
    'block_only':['median_wall_per_sim > 6.0','incomplete','HOST_ERROR'],
    'median_3_5_to_6_action':'record warning only; no speed block'},
  criteria={'weld':'off','top_camera_control':False,'training_rgb':False,'held_object':'hidden_v1',
   'input_audit':{'held_world_reads':0,'invisible_measurements':0},
   'denominators':'original crate13 setup reproduction 3 development only (77990,79314,79317); fresh crate14 conditional-start diagnostic 10 only; never pool',
   'minimum_future_gate':'at least 40 accepted non-near-wall episodes, >=95%, drawn/excluded denominator reported; separately approved'},
  storage_budget_mib={'reproduction':384,'diagnostic':1280,'total_new_raw_upper_estimate':1664},
  start_distribution=json.loads((HERE/'diag_plan_crate14_79450.json').read_text())['start_distribution'],
  seed_reservation=json.loads((HERE/'crate14-seed-reservation.json').read_text()),
  near_wall_filter=json.loads((HERE/'diag_plan_crate14_79450.json').read_text())['near_wall_filter'],
  preconditions=['No VM access or launch performed by author. All ready flags remain false.',
   'Operations rechecks live seed inventory/reservations before admission; saved snapshots alone are not live proof.',
   'GCP project ugrp-act-train-1014 only; credit stop, 8h max, idle20, disk and shared slot reservation required.',
   'Do not pool profile, scene or machine results. Review first30 raw and preserve every result including stops/HOST_ERROR.',
   'Input boundary: existing visible-relative demonstration sensor adapter retained; RGB-only interpretation remains unconfirmed.',
   'No gate/training/automatic promotion; crate14 alignment/peer-clock and conditional starts have no physical validation.'],
  candidate_record={'record':str(HERE/'crate14.md'),'summary':str(HERE/'crate14-summary.json')},
  plan_sha256={},runs=[],previous_queues_sha256=prior)
 for stage,filename in [('reproduction','repro_plan_crate14.json'),('diagnostic','diag_plan_crate14_79450.json')]:
  f=HERE/filename;p=json.loads(f.read_text());q['plan_sha256'][filename]=digest(f)
  artifact=p.get('start_distribution',{}).get('rejected_starts_artifact')
  if artifact:
   asset=HERE/artifact['path'];assert digest(asset)==artifact['sha256']
   q['plan_sha256'][asset.name]=digest(asset)
  for i,e in enumerate(p['episodes']):
   name=f"crate-{'reproduction' if stage=='reproduction' else 'diag'}-{e['seed']}-{sha[:8]}"
   payload=['.venv-sim/bin/python','-m','scripts.run_crate_teacher','--plan',str(f.relative_to(ROOT)),'--episode',str(i),
    '--grasp-cap-s','80','--cap-s','90','--observe-mode','backoff_v3','--zone-slots','zone','--reach-mode','pad_window_v2',
    '--own-pose-source','commands','--held-object','hidden_v1','--setdown-lookaround','setdown_lookaround_own_v2',
    '--crate-scene','crate_mass_025_v1','--crate-lift-pose','crate_antipodal_grasp_v1','--rgb-lift','crate_rgb_lift_v3',
    '--teacher-stability','align_relook_v1','--teacher-search','search_reacquire_v1','--approach-goal-set','approach_goal_set_v1',
    '--crate-approach-recovery','crate_approach_recovery_v1','--crate-profile','crate14_v1',
    '--recording-mode','success_measurement','--execution-host','gcp1','--pr','500','--out',f'/home/ugrp/ugrp-sim/runs/{name}/raw']
   q['runs'].append({'stage':stage,'seed':e['seed'],'scenario_id':e['scenario_id'],'near_wall':e['near_wall'],'name':name,
    'approved':False,'enabled':False,'ready':False,'stage_ready':False,'runs_enabled':False,'status':'awaiting_diagnostic_admission','maximum_sim_s_per_episode':170,
    'max_parallel':10,'max_combined_concurrency':40,'payload':payload,
    'command':['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','500','--per-run-mb','128',str(ROOT),name,'--',*payload]})
 assert len(q['runs'])==13 and not any(r['near_wall'] for r in q['runs'] if r['stage']=='diagnostic')
 return q

def main():
 p=argparse.ArgumentParser();p.add_argument('--sha',required=True);a=p.parse_args()
 sha=git('rev-parse','HEAD')
 if a.sha!=sha or git('branch','--show-current')!='claude/act-crate-teacher' or git('status','--porcelain'):raise ValueError('clean current crate SHA required')
 remote=git('ls-remote','origin','refs/heads/claude/act-crate-teacher').split()[0]
 if remote!=sha:raise ValueError('pushed SHA required')
 prior={str(p):digest(p) for p in QUEUE.glob('*.json')};q=build(sha,prior);q['remote_verified_sha']=remote
 out=QUEUE/f'20261015-crate14-diag-{sha[:8]}.json'
 with out.open('x') as f:json.dump(q,f,ensure_ascii=False,separators=(',',':'));f.write('\n')
 assert all(digest(Path(p))==h for p,h in prior.items()),'prior queue changed'
 assert json.loads(out.read_text())==q
 print(json.dumps({'queue':str(out),'sha256':digest(out),'previous_queues_unchanged':len(prior),'runs':13,'approved':False}))
if __name__=='__main__':main()
