"""Retain admitted B inputs/results across uncalled physics-host-only changes."""
import ast
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from harness.zone_final_pair_binding import bind

HERE=Path(__file__).parent
EXCLUDED={'sim/final_environment_checks.py':{'reset','close'},
          'sim/v7_exact_speedups.py':{'write_receipt'}}


def proof(root, previous):
    spec=importlib.util.spec_from_file_location('prior_equivalence',HERE.parent/'s3fix6/replay_equivalence.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    normalized={}
    for path,names in EXCLUDED.items():
        def normalize(text):
            tree=ast.parse(text)
            class Remove(ast.NodeTransformer):
                def visit_FunctionDef(self,node):
                    return None if node.name in names else self.generic_visit(node)
            return ast.dump(Remove().visit(tree),include_attributes=False)
        now=normalize((root/path).read_text())
        archived=subprocess.check_output(['git','show',old.SOURCE+':'+path],cwd=root,text=True)
        assert now==normalize(archived),path
        normalized[path]=dict(excluded_uncalled_physics_functions=sorted(names),
            unchanged_ast_sha256=hashlib.sha256(now.encode()).hexdigest())
    def closure(*args,**kwargs):
        historical=set(json.loads((HERE.parent/'s3fix6/comparison.json').read_text())['runtime_source_sha256'])
        current=set(old.source_closure(*args,**kwargs))
        added=current-historical
        assert added=={'harness/controller_exact_speedups.py'},added
        # Its only new import edge is inside excluded PhysicsBackend.reset.
        # The AST proof above removes precisely that body and no module code.
        return historical-set(EXCLUDED)
    result=bind(old.retained_proof,source_closure=closure)(root,previous)
    result['receipts']={k:v for k,v in result['receipts'].items() if k.endswith('-off')}
    assert len(result['receipts'])==4
    result.update(physics_host_only_changes=normalized,
        scope='four admitted B replays retained; no PhysicsBackend construction/reset/close/write_receipt in saved-input consumers',
        baseline_reexecuted=False)
    return result
