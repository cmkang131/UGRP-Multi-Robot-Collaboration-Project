"""Admit immutable arms across C3-only actual-consumer wiring repairs."""
import ast,hashlib,json,subprocess
from pathlib import Path
from harness.python_source_closure import source_closure
SOURCE='105ffc704a48abb56f674b67e83dd815438fde10'
OWN_SOURCE='bfce6a0136dfb9a99f931ed8d979c851cfd28d5a'
MODULE='harness/pf_observation_consistency.py'

def retained_proof(root,retained):
    paths=set(source_closure(root,['harness/zone_s3_consistent_runtime.py']))
    paths.update('experiments/2026-10-09-s3-no-prior/s3fix6/'+n for n in ('replay_s3.py','replay_ownmap.py','evaluate.py'))
    identical={}
    for path in sorted(paths-{MODULE}):
        current=(root/path).read_bytes()
        for source in (SOURCE,OWN_SOURCE):
            assert current==subprocess.check_output(['git','show',source+':'+path],cwd=root),path
        identical[path]=hashlib.sha256(current).hexdigest()
    def normalized(source,consumers):
        text=(root/MODULE).read_text() if source is None else subprocess.check_output(['git','show',source+':'+MODULE],cwd=root,text=True)
        tree=ast.parse(text)
        tree.body=[n for n in tree.body if getattr(n,'name',None) not in {'_'+c+'_alpha' for c in consumers}]
        for node in tree.body:
            if getattr(node,'name',None) in {'attach_'+c for c in consumers}:
                for stmt in node.body:
                    if isinstance(stmt,ast.If) and ast.unparse(stmt.test)=="option == 'effective_sqrt_alpha_v1'":
                        stmt.body=[ast.Pass()]
        return ast.dump(tree,include_attributes=False)
    scopes=[(SOURCE,('ownmap','s3')),(OWN_SOURCE,('s3',))];equivalence={}
    for source,consumers in scopes:
        before,after=normalized(source,consumers),normalized(None,consumers)
        assert before==after,'retained behavior changed: '+source
        equivalence[source]=dict(excluded_c3_consumers=consumers,unchanged_ast_sha256=hashlib.sha256(before.encode()).hexdigest())
    receipts={}
    for option in ('off','effective_sqrt_v1','effective_mean_v1','effective_sqrt_alpha_v1'):
        for case in (('55001','55002') if option.endswith('alpha_v1') else ('55001','55002','v149','v150')):
            key=case+'-'+option;p=retained/key/'result.json';value=json.loads(p.read_text())
            assert value.get('failure') is None and value.get('error') is None
            if option.endswith('alpha_v1'):
                assert value['audit']['motion_noise_augmented']>0 and value['frames']==value['expected_frames']
            receipts[key]=dict(source_sha=OWN_SOURCE if option.endswith('alpha_v1') else SOURCE,
                path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    return dict(identical_dependency_sha256=identical,equivalence=equivalence,
        only_changed_runtime=MODULE,receipts=receipts,
        excluded_old_c3=['replays-v2:55001 alpha Q not delivered;55002 interrupted',
            'replays-v3:v149 obsolete S3 pulse table;v150 interrupted'],originals_preserved=True)
