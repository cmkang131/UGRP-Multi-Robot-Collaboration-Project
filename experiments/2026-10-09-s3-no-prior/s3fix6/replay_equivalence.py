"""Admit immutable B/C1/C2 receipts across a C3-only consumer wiring repair."""
import ast,hashlib,json,subprocess
from pathlib import Path
from harness.python_source_closure import source_closure
SOURCE='105ffc704a48abb56f674b67e83dd815438fde10'
MODULE='harness/pf_observation_consistency.py'

def retained_proof(root,retained):
    paths=set(source_closure(root,['harness/zone_s3_consistent_runtime.py']))
    paths.update('experiments/2026-10-09-s3-no-prior/s3fix6/'+n for n in ('replay_s3.py','replay_ownmap.py','evaluate.py'))
    identical={}
    for path in sorted(paths-{MODULE}):
        current=(root/path).read_bytes();old=subprocess.check_output(['git','show',SOURCE+':'+path],cwd=root)
        assert current==old,path
        identical[path]=hashlib.sha256(current).hexdigest()
    old=ast.parse(subprocess.check_output(['git','show',SOURCE+':'+MODULE],cwd=root,text=True))
    new=ast.parse((root/MODULE).read_text())
    def retained_tree(tree):
        tree.body=[n for n in tree.body if getattr(n,'name',None)!='_ownmap_alpha']
        for node in tree.body:
            if getattr(node,'name',None)=='attach_ownmap':
                for stmt in node.body:
                    if isinstance(stmt,ast.If) and ast.unparse(stmt.test)=="option == 'effective_sqrt_alpha_v1'":
                        stmt.body=[ast.Pass()]
        return ast.dump(tree,include_attributes=False)
    before,after=retained_tree(old),retained_tree(new)
    assert before==after,'non-C3 behavior changed'
    receipts={}
    for option in ('off','effective_sqrt_v1','effective_mean_v1'):
        for case in ('55001','55002','v149','v150'):
            key=case+'-'+option;p=retained/key/'result.json';value=json.loads(p.read_text())
            assert value.get('failure') is None and value.get('error') is None
            receipts[key]=dict(source_sha=SOURCE,path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return dict(retained_source_sha=SOURCE,retained_options=['off','effective_sqrt_v1','effective_mean_v1'],
        identical_dependency_sha256=identical,unchanged_non_c3_ast_sha256=hashlib.sha256(before.encode()).hexdigest(),
        only_changed_runtime=MODULE,receipts=receipts,
        excluded_old_c3='replays-v2:55001 alpha Q not delivered;55002 interrupted; preserved')
