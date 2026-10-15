"""Review-only SHA-bound crate18 queue; never submits."""
import hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT/'experiments/2026-10-15-crate18'
QUEUE=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(sha,summary):
 spec=importlib.util.spec_from_file_location('queue17',HERE.parent/'2026-10-15-crate17/queue.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 q=m.build(sha,{})
 q.update(owner='codex-crate18',status='BLOCKED' if summary['successes']!=6 else 'awaiting_diagnostic_admission',
  max_parallel=16,max_parallel_per_stage=16,stage_max_parallel={'reproduction':16,'diagnostic':16},
  crate18='crate18_v1',self_check=summary,candidates={c:{'crate_profile':p,'crate18':'crate18_v1'} for c,p in [('full','crate17_v1'),('no_clearance','crate17_no_clearance_v1')]},
  candidate_record={'record':str(HERE/'README.md'),'summary':str(HERE/'summary.json')},
  source_worktree=str(ROOT),runner_cwd=str(ROOT),
  runner_note='review-only; exact clean queue SHA checkout required before invoking remote_run; no approval inherited from DEV self-check',
  partial_admission={'scope':'all30 rows unapproved; no automatic first-row admission'},
  speed_limit={'concurrency':40,'crate_concurrency':16,'warn_above':3.5,'median_wall_per_sim_max':6.0},
  preconditions=['Self-check must be6/6; otherwise BLOCKED. No submission authorized by this queue.',
   'GCP project ugrp-act-train-1014, existing gcp1/n4-highcpu-64 only. budget-stop/idle20/8hSTOP required.',
   'Global admission<=40; candidate paired reproduction5 then diagnostic10, known failures first. max_parallel16.',
   'No pooling with crate16/17, other source/profile/host, or earlier crate18 tuning rounds.',
   'No top camera, no training RGB, no VM model key; inputs audit0/0.'],
  plan_sha256={f:digest(HERE/f) for f in ['reproduction-plan.json','diagnostic-plan.json']})
 q['excluded_starts']['path']=str(HERE/'diagnostic-plan.json')
 q['plan_sha256']['diagnostic-plan-rejected-starts.json.zst']=digest(HERE/'diagnostic-plan-rejected-starts.json.zst')
 q['coordinator_approval']['required_before']='separate admission of these30 queued rows; DEV approval not inherited'
 q['admission']['available_slots']='max(0, min(16 - crate_running, 40 - total_running))'
 q['criteria']['top_camera_capture']=False;q['criteria']['denominators']='candidate reproduction5 and fresh10 separate; prior profiles/rounds never pooled'
 for r in q['runs']:
  r['name']=r['name'].replace('crate17-','crate18-');r['max_parallel']=16;r['maximum_sim_s_per_episode']=90;r['crate18']='crate18_v1';r['status']=q['status']
  payload=r['payload'];payload[payload.index('--plan')+1]=payload[payload.index('--plan')+1].replace('2026-10-15-crate17','2026-10-15-crate18')
  payload[payload.index('--grasp-cap-s')+1]='60';payload[payload.index('--cap-s')+1]='27.5';payload[payload.index('--out')+1]=f"/home/ugrp/ugrp-sim/runs/{r['name']}/raw"
  payload.extend(['--crate18','crate18_v1'])
  r['command']=['python3','scripts/remote_run.py','--host','gcp1','--detach','--class','dev','--pr','500','--per-run-mb','128',str(ROOT),r['name'],'--',*payload]
 return q
def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--sha',required=True);a=p.parse_args();summary=json.loads((HERE/'summary.json').read_text())
 tested=summary['execution_source_sha']
 head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
 if head!=a.sha or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('clean exact current SHA required')
 runtime_paths=['sim','harness','scripts','configs','maps','experiments/2026-10-15-crate18/reproduction-plan.json','experiments/2026-10-15-crate18/diagnostic-plan.json']
 subprocess.run(['git','diff','--exit-code',tested,a.sha,'--',*runtime_paths],cwd=ROOT,check=True,stdout=subprocess.PIPE)
 before={str(p):digest(p) for p in QUEUE.glob('*.json')};q=build(a.sha,summary['self_check']);q['previous_queues_sha256']=before
 q['tested_execution_sha']=tested;q['runtime_files_identical_to_tested_sha']={'verified':True,'paths':runtime_paths,'method':'git diff --exit-code tested queue-sha -- paths; only records/offline drivers differ'}
 out=QUEUE/f'20261015-crate18-diag-{a.sha[:8]}.json'
 with out.open('x') as f:json.dump(q,f,ensure_ascii=False,separators=(',',':'));f.write('\n')
 assert all(digest(Path(p))==h for p,h in before.items());assert json.loads(out.read_text())==q
 print(json.dumps(dict(queue=str(out),sha256=digest(out),runs=len(q['runs']),status=q['status'],previous_queues_unchanged=len(before))))
if __name__=='__main__':main()
