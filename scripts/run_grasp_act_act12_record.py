"""Record with the exact ACT11 teacher; optional own-only review output.

The pinned runner predates an own-only review switch. Remove exactly its two
top-review output statements, checking their AST, without changing any other
statement. The original and effective runner hashes are saved explicitly.
This changes evaluation output only, never teacher/camera/control inputs.
"""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys

ACT11 = '1fce11554754d4609470e4fe4b172f9a583bc026'


def own_review_source(source):
    tree = ast.parse(source)
    removed = []
    class RemoveTop(ast.NodeTransformer):
        def visit_Expr(self, node):
            text = ast.unparse(node)
            expected = (
                "(out / 'review-top').mkdir()",
                "(out / 'review-top' / f'{tick:06d}.jpg').write_bytes(world.render_team_jpeg(camera=static['top_cameras'][0]['name']))",
            )
            if text in expected:
                removed.append(text)
                return None
            return self.generic_visit(node)
    tree = RemoveTop().visit(tree)
    if len(removed) != 2 or len(set(removed)) != 2:
        raise ValueError('pinned top-review statements changed')
    # Fail closed if any other use of the overview renderer remains.
    effective = ast.unparse(tree) + '\n'
    if 'render_team_jpeg' in effective or 'review-top' in effective:
        raise ValueError('unexpected top-review use')
    return effective, removed


@contextmanager
def own_review_only(adapter, policy_path):
    original_scope = adapter.dependency_modules
    @contextmanager
    def scope(root):
        with original_scope(root):
            import scripts.run_solo_grasp_act_teacher as runner
            original = runner.run
            source = inspect.getsource(original)
            effective, removed = own_review_source(source)
            # Keep live module globals: protected_runner installs its SIGINT
            # exception binding after entering this scope.
            namespace = vars(runner)
            exec(compile(effective, inspect.getsourcefile(original), 'exec'), namespace)
            policy_path.write_text(json.dumps({
                'mode': 'own_review_only_v1', 'teacher_source_sha': ACT11,
                'original_runner_function_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'effective_runner_function_sha256': hashlib.sha256(effective.encode()).hexdigest(),
                'removed_evaluation_only_statements': removed,
                'control_ast_change_count': 0,
            }, indent=2) + '\n')
            runner.run = namespace['run']
            try:
                yield
            finally:
                runner.run = original
    adapter.dependency_modules = scope
    try:
        yield
    finally:
        adapter.dependency_modules = original_scope


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--teacher-source', type=Path, required=True)
    p.add_argument('--own-review-only-v1', action='store_true')
    p.add_argument('arguments', nargs=argparse.REMAINDER)
    a = p.parse_args()
    root = a.teacher_source.resolve()
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != ACT11:
        raise ValueError('exact ACT11 source required')
    if subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain']):
        raise ValueError('clean ACT11 source required')
    sys.path.insert(0, str(root))
    import scripts.run_grasp_act_recovery as adapter
    arguments = a.arguments[1:] if a.arguments[:1] == ['--'] else a.arguments
    if '--out' not in arguments:
        p.error('--out required')
    out = Path(arguments[arguments.index('--out') + 1])
    out.parent.mkdir(parents=True, exist_ok=True)
    sys.argv = [str(root / 'scripts/run_grasp_act_recovery.py'), *arguments]
    if a.own_review_only_v1:
        with own_review_only(adapter, out.parent / 'review-policy.json'):
            adapter.main()
    else:
        adapter.main()


if __name__ == '__main__':
    main()
