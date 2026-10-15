"""Verified DEV4 -> disabled paired gate40 manifest. No remote submission."""
import base64,copy,hashlib,json,zlib,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.prepare_release_gate40_queue import build as old_build,compact,FLAGS,GUARD,ENTRY
ROOT=Path(__file__).resolve().parents[1]
RECORD='experiments/2026-10-14-e2e18-grasp-rootcause'
def build(sha):
 q=old_build()
 proof=json.loads((ROOT/RECORD/'release20-summary.json').read_text())
 assert proof['source_sha']==sha and proof['counts']==dict(completed=4,success=4,N=4)
 assert all(r['visual_review']['directly_viewed'] for r in proof['runs'])
 profile={**q['candidates'][0]['execution_profile'],'release20_settle':'release20_settle_v1'}
 q['candidates']=[dict(id=c,source_sha=sha,execution_profile=dict(profile,release_profile='release18_v1' if c=='A' else 'release19_v1')) for c in ('A','B')]
 q.update(owner='codex-release20',sha=sha,source_worktree=str(ROOT),created_utc=datetime.now(timezone.utc).isoformat(),status='PREPARED_NOT_APPROVED',pooling='Gate A and B independently n/40; never pool preflight, DEV4, earlier releases or hosts.',gate_run_count=80,preflight_run_count=3,priority_seeds=[110613,74976,78526],max_gcp1_total_concurrency=40,diagnostic_evidence=dict(path=RECORD+'/release20-summary.json',sha256=hashlib.sha256((ROOT/RECORD/'release20-summary.json').read_bytes()).hexdigest(),source_sha=sha),admission_policy='Coordinator must reserve on gcp1 shared admission.lock, counting live jobs and full multi-worker reservation slots; total <=40; do not alter other jobs.')
 q['runs']=[]
 devraw=(ROOT/RECORD/'release20-dev4-round2-plan.json').read_bytes()
 dev=json.loads(devraw)
 for i,seed in enumerate([110613,74976,78526]):
  c=dev['candidate_by_seed'][str(seed)]
  q['runs'].append(dict(stage='preflight',candidate=c,source_sha=sha,episode=i,seed=seed,name=f'r20pre-{i:02d}-{sha[:8]}',plan_zlib_base64=base64.b64encode(zlib.compress(devraw,9)).decode(),plan_sha256=hashlib.sha256(devraw).hexdigest(),**{f:False for f in FLAGS}))
 plan=json.loads(zlib.decompress(base64.b64decode(q['plan_zlib_base64'])))
 order=sorted(range(40),key=lambda i:plan['episodes'][i]['seed']!=110613)
 for c in ('A','B'):
  for i in order:
   q['runs'].append(dict(stage='gate',candidate=c,source_sha=sha,episode=i,seed=plan['episodes'][i]['seed'],name=f'r20{c.lower()}g-{i:02d}-{sha[:8]}',**{f:False for f in FLAGS}))
 q.update(run_count=len(q['runs']),storage_budget_mib=dict(per_run=96,total=96*len(q['runs'])),preflight_policy='Separate diagnostics first; not in n/40. The original gate40 seed set 110600–110639 remains byte-for-byte identical; 74976/78526 are not gate seeds.',remote_host_contacted=False)
 return q

def commands(q,source,candidate,stage='gate'):
 c=next(c for c in q['candidates'] if c['id']==candidate)
 for r in q['runs']:
  if r['candidate']!=candidate or r['stage']!=stage:continue
  values=dict(source=str(source),sha=c['source_sha'],name=r['name'],plan=r.get('plan_zlib_base64',q['plan_zlib_base64']),plan_sha=r.get('plan_sha256',q['plan_sha256']),episode=str(r['episode']),profile=compact(c['execution_profile']).decode())
  yield [v.format(**values) if v not in (GUARD,ENTRY) else v for v in q['command_template']]

def verify(q):
 assert len(q['sha'])==40 and all(c in '0123456789abcdef' for c in q['sha'])
 evidence=q['diagnostic_evidence'];payload=(ROOT/evidence['path']).read_bytes()
 assert hashlib.sha256(payload).hexdigest()==evidence['sha256']
 proof=json.loads(payload);assert proof['source_sha']==q['sha'] and proof['counts']==dict(completed=4,success=4,N=4)
 assert {c['id']:c['execution_profile']['release_profile'] for c in q['candidates']}=={'A':'release18_v1','B':'release19_v1'}
 assert q['run_count']==len(q['runs'])==83 and q['gate_run_count']==80
 assert [r['seed'] for r in q['runs'][:3]]==[110613,74976,78526]
 raw=zlib.decompress(base64.b64decode(q['plan_zlib_base64']))
 assert hashlib.sha256(raw).hexdigest()==q['plan_sha256']
 assert raw==(ROOT/q['plan_path']).read_bytes()
 for c in q['candidates']:
  assert c['source_sha']==q['sha'] and c['execution_profile']['release20_settle']=='release20_settle_v1'
  gate=[r for r in q['runs'] if r['stage']=='gate' and r['candidate']==c['id']]
  assert len(gate)==40 and {r['seed'] for r in gate}==set(range(110600,110640))
  assert gate[0]['seed']==110613 and len(list(commands(q,'/pinned-source',c['id'])))==40
 for r in [q,*q['runs']]: assert all(r[f] is False for f in FLAGS)
 assert not q['stage_ready']['gate'] and not q['coordinator_approval']['approved'] and q['authorized_run_count']==0
 for r in q['runs']:
  plan=json.loads(zlib.decompress(base64.b64decode(r.get('plan_zlib_base64',q['plan_zlib_base64']))))
  assert plan['episodes'][r['episode']]['seed']==r['seed']

def main():
 import argparse
 p=argparse.ArgumentParser(description='Prepare or verify a disabled release20 A/B gate queue; never contact a host')
 p.add_argument('--sha')
 p.add_argument('--verify',type=Path)
 p.add_argument('--commands',type=Path)
 p.add_argument('--source-worktree',type=Path)
 p.add_argument('--candidate',choices=('A','B'),default='A')
 p.add_argument('--stage',choices=('preflight','gate'),default='gate')
 p.add_argument('--queue-root',type=Path,default=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue'))
 a=p.parse_args()
 if a.verify or a.commands:
  q=json.loads((a.verify or a.commands).read_text());verify(q)
  if a.commands:
   if not a.source_worktree:p.error('--commands requires --source-worktree')
   for cmd in commands(q,a.source_worktree,a.candidate,a.stage):print(json.dumps(cmd))
  else:print('verified: A40/B40 original seeds +3 separate preflights; all approval/execution flags false')
  return
 if not a.sha:p.error('--sha required')
 q=build(a.sha);verify(q)
 path=a.queue_root/f"20261015-release-gate40-{a.sha[:8]}.json"
 with path.open('x') as f:f.write(json.dumps(q,ensure_ascii=False,separators=(',',':'))+'\n')
 assert path.stat().st_size<65536
 print(path)

if __name__=='__main__':main()
