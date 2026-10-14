"""Local, disabled diagnostic queue. Never submits or contacts a VM."""
import hashlib,importlib.util,json,subprocess
from pathlib import Path

EXP=Path(__file__).resolve().parent
ROOT=EXP.parents[1]
ADMIN=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
OLD='20261015-crate-5644e3dd.json'
PLAN='diag_plan_crate9_77970.json'
MODE='crate_antipodal_grasp_v1'


def build(sha,summary):
    spec=importlib.util.spec_from_file_location('crate8_queue',EXP/'make_crate8_queue.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.OLD=OLD;module.PLAN=PLAN
    q=module.build(sha,summary)
    q.update(owner='codex-crate9',status='blocked',ready=False,runs_enabled=False,
             blocked_reason='77969 search rotation stalls at wheel/lug and near-wall contact; no safe simple recovery implemented. Do not execute the known-defect search bundle.',
             crate_lift_pose=MODE,profile=q['profile'].replace('crate_cartesian_lift_v1',MODE),
             purpose='Fresh diagnostic N=10 prepared, NOT executable; no gate/training/automatic promotion.',
             baseline_diagnostic={'sha':'5644e3dd114c34c2ee0e5e09b4bdaba10754621e','success_n':5,'N':10,'pool_with_new_candidate':False},
             candidate_record={'record':str(EXP/'crate9.md'),'summary':str(EXP/'crate9-summary.json'),
                               'local_tests':summary['local_tests'],'new_remote_runs':0})
    q['seed_reservation']['seeds']=list(range(77970,77980))
    q['preconditions'].insert(0,'Fix the documented search collision/no-motion defect and revalidate before changing any ready/runs_enabled flag; user AGENTS stop-on-known-defect rule.')
    for run in q['runs']:
        for field in ('payload','command'):
            run[field]=[MODE if word=='crate_cartesian_lift_v1' else word for word in run[field]]
        run.update(status='blocked',ready=False,runs_enabled=False)
    assert len(q['runs'])==10 and {r['stage'] for r in q['runs']}=={'diagnostic'}
    assert [r['seed'] for r in q['runs']]==list(range(77970,77980))
    assert all('--crate-lift-pose' in r['payload'] and MODE in r['payload'] for r in q['runs'])
    return q


def main():
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
    assert git('branch','--show-current')=='claude/act-crate-teacher'
    assert not git('status','--porcelain')
    assert git('remote','get-url','origin')=='https://github.com/kcm0127-dotcom/ugrp.git'
    sha=git('rev-parse','HEAD')
    assert git('ls-remote','origin','refs/heads/claude/act-crate-teacher').split()[0]==sha
    summary=json.loads((EXP/'crate9-summary.json').read_text())
    assert summary['local_tests']['passed']>0 and summary['local_tests']['failed']==0
    for item in summary['artifacts'].values():
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256']
    q=build(sha,summary);dest=ADMIN/'vm3-queue'/f'20261015-crate-{sha[:8]}.json'
    assert not dest.exists()
    dest.write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n')
    oldpath=dest.with_name(OLD);old=json.loads(oldpath.read_text())
    assert old['sha']=='5644e3dd114c34c2ee0e5e09b4bdaba10754621e'
    old.update(status='superseded',ready=False,runs_enabled=False,superseded_by=dest.name,
               superseded_reason='crate9 visible antipodal grasp candidate; search issue remains blocked')
    for run in old['runs']:run.update(status='superseded',ready=False,runs_enabled=False)
    oldpath.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    assert json.loads(dest.read_text())==q
    delivery={'sha':sha,'queue':str(dest),'queue_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
              'ready':False,'superseded':str(oldpath),'new_remote_runs':0}
    (ADMIN/'crate9-delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    print(json.dumps(delivery))
if __name__=='__main__':main()
