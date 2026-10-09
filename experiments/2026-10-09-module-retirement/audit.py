"""Read-only retirement inventory. Never imports inspected code or touches outputs.

Use exact AST import/module/path identities, not basename substring searches.
Branch snapshots are read from Git objects; no checkout, merge or simulation.
"""
from __future__ import annotations

import ast
from collections import defaultdict
import fnmatch
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = '888447674318bc311e1ef65f71c654692b2b76bb'
CORE = ('harness/', 'sim/', 'scripts/')
EXTRA_REFS = ('origin/codex/s3-door-yield', 'origin/codex/s3-three-robot-host',
              'origin/codex/s4-llm-host', 'origin/codex/sim-speed-egomap53')
ACTIVE = ('scripts/run_s3_host.py', 'scripts/run_s3_door_yield.py',
          'harness/s4_llm_host.py', 'harness/s4_llm_inputs.py', 'harness/s4_llm_routing.py',
          'scripts/agent_lock.py', 'scripts/agent_worktree.py', 'scripts/ugrp_session.py',
          'scripts/run_ci_tests.py', 'scripts/sim_cli.py', 'sim/workflow_manager.py')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode()


def snapshot(ref):
    entries = {}
    for line in git('ls-tree', '-r', ref).splitlines():
        meta, name = line.split('\t', 1)
        if meta.split()[1] == 'blob':
            entries[name] = meta.split()[2]
    return entries


class Blobs:
    def __init__(self):
        self.cache = {}
        self.proc = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, oid):
        if oid not in self.cache:
            self.proc.stdin.write((oid + '\n').encode())
            self.proc.stdin.flush()
            header = self.proc.stdout.readline().split()
            self.cache[oid] = self.proc.stdout.read(int(header[2])).decode('utf-8', 'replace')
            self.proc.stdout.read(1)
        return self.cache[oid]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


class Graph:
    def __init__(self, files, read):
        self.files = files
        self.read = read
        self.py = {p for p in files if p.endswith('.py')}
        self.edges = {}
        self.unresolved = []
        self.errors = []

    @lru_cache(maxsize=65536)
    def module(self, name, source='', wildcard=False):
        """Resolve imports plus package initializers, including script sys.path."""
        if not name or any(not x.replace('-', '_').isidentifier() for x in name.split('.')):
            return set()
        stem = name.replace('.', '/')
        # Root, current script directory, and known script import roots.
        prefixes = {'', str(PurePosixPath(source).parent), 'scripts', 'scripts/red_block'}
        result = set()
        for prefix in prefixes:
            path = f'{prefix}/{stem}' if prefix not in ('', '.') else stem
            result.update(p for p in (path + '.py', path + '/__init__.py') if p in self.py)
            parts = path.split('/')
            result.update('/'.join(parts[:i]) + '/__init__.py' for i in range(1, len(parts))
                          if '/'.join(parts[:i]) + '/__init__.py' in self.py)
            if wildcard:
                result.update(p for p in self.py if p.startswith(path + '/'))
        return result

    def paths(self, node, source):
        """Fold pathlib / and joinpath fragments without executing expressions."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.Add)):
            left = self.paths(node.left, source) or ['']
            right = self.paths(node.right, source)
            join = '/' if isinstance(node.op, ast.Div) else ''
            return [((a + join) if a else '') + b for a in left for b in right]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'with_name' and node.args:
                return [str(PurePosixPath(source).parent / p) for p in self.paths(node.args[0], source)]
            if node.func.attr in ('joinpath', 'join'):
                values = ['']
                for arg in node.args:
                    values = [str(PurePosixPath(a) / b) for a in values
                              for b in self.paths(arg, source)]
                return values
        return []

    def literal(self, value, source=''):
        """Only complete module/path tokens; accept module:attribute plugin syntax."""
        value = value.strip()
        result = set()
        if value in self.py:
            result.add(value)
        normalized = value.removeprefix('./')
        if normalized in self.py:
            result.add(normalized)
        if value.endswith('.py'):
            sibling = str(PurePosixPath(source).parent / value)
            if sibling in self.py:
                result.add(sibling)
        if '.' in value and '/' not in value and not any(c.isspace() for c in value):
            mod = value.split(':', 1)[0]
            # patch("package.module.function") still loads package.module.
            while mod:
                found = self.module(mod, source)
                if found:
                    result.update(found)
                    break
                mod = mod.rpartition('.')[0]
        return result

    def text_refs(self, text):
        """Exact fully qualified tokens in docs/shell/config, never basename matches."""
        result = set()
        for token in re.findall(r'(?<![\w/])(?:harness|sim|scripts|tests)(?:[/\.][\w.-]+)+', text):
            result.update(self.literal(token.rstrip('.')))
        for module in re.findall(r'(?<!\S)-m\s+([\w.]+)', text):
            result.update(self.module(module))
            result.update(self.module(module + '.__main__'))
        return result

    def parse(self, source):
        if source in self.edges:
            return self.edges[source]
        found = set()
        try:
            tree = ast.parse(self.read(source), filename=source)
        except SyntaxError as e:
            self.errors.append({'file': source, 'error': str(e)})
            self.edges[source] = found
            return found
        nodes = list(ast.walk(tree))
        constants = {}
        aliases = {}
        for n in nodes:
            if isinstance(n, ast.Import):
                for a in n.names:
                    aliases[a.asname or a.name] = a.name
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    aliases[a.asname or a.name] = (n.module or '') + '.' + a.name
            elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                try:
                    v = ast.literal_eval(n.value)
                except (ValueError, TypeError, SyntaxError):
                    continue
                for target in n.targets if isinstance(n, ast.Assign) else [n.target]:
                    if isinstance(target, ast.Name):
                        constants[target.id] = v

        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, (tuple, list, set)):
                for item in value:
                    yield from strings(item)
            elif isinstance(value, dict):
                for item in (*value.keys(), *value.values()):
                    yield from strings(item)

        def values(node):
            if isinstance(node, ast.Name):
                return list(strings(constants.get(node.id)))
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
                return list(strings(constants.get(node.value.id)))
            try:
                return list(strings(ast.literal_eval(node)))
            except (ValueError, TypeError, SyntaxError):
                return []

        for n in nodes:
            if isinstance(n, ast.Import):
                for a in n.names:
                    found.update(self.module(a.name, source))
            elif isinstance(n, ast.ImportFrom):
                package = source.removesuffix('/__init__.py').removesuffix('.py').split('/')
                if not source.endswith('/__init__.py'):
                    package.pop()
                if n.level:
                    package = package[:len(package) - n.level + 1]
                    mod = '.'.join(package + ([n.module] if n.module else []))
                else:
                    mod = n.module or ''
                found.update(self.module(mod, source, any(a.name == '*' for a in n.names)))
                for a in n.names:
                    if a.name != '*':
                        found.update(self.module(mod + '.' + a.name, source))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                found.update(self.literal(n.value, source))
                # Shell commands and Python -c strings are parsed as complete paths/modules.
                if any(s in n.value for s in ('python', 'import ', ' -m ')):
                    found.update(self.text_refs(n.value))
            elif isinstance(n, (ast.List, ast.Tuple)):
                for i, item in enumerate(n.elts[:-1]):
                    if isinstance(item, ast.Constant) and item.value == '-m':
                        for module in values(n.elts[i + 1]):
                            found.update(self.module(module, source))
                            found.update(self.module(module + '.__main__', source))
            elif isinstance(n, ast.Call):
                call = ast.unparse(n.func)
                first, _, tail = call.partition('.')
                call = aliases.get(first, first) + ('.' + tail if tail else '')
                if call.endswith(('import_module', '__import__', 'run_module', 'spec_from_file_location')):
                    index = 1 if call.endswith('spec_from_file_location') else 0
                    arg = n.args[index] if len(n.args) > index else None
                    resolved = values(arg) if arg else []
                    for value in resolved:
                        found.update(self.module(value, source))
                        found.update(self.literal(value, source))
                    if not resolved:
                        self.unresolved.append({'file': source, 'line': n.lineno,
                                                'call': ast.unparse(n)})
            if isinstance(n, (ast.BinOp, ast.Call)):
                for path in self.paths(n, source):
                    found.update(self.literal(path, source))
        found.discard(source)
        # CI's selection list describes which tests to run after retirement; it
        # does not make every historical test an application entrypoint.
        if source == 'scripts/run_ci_tests.py':
            found = {p for p in found if not p.startswith('tests/')}
        self.edges[source] = found
        return found

    def closure(self, roots):
        seen, todo = set(), list(roots)
        while todo:
            source = todo.pop()
            if source in seen or source not in self.py:
                continue
            seen.add(source)
            todo.extend(self.parse(source) - seen)
        return seen


def main():
    blobs = Blobs()
    base = snapshot(BASE)
    graph = Graph(base, lambda p: blobs.read(base[p]))
    core = {p for p in graph.py if p.startswith(CORE)}
    tests = {p for p in graph.py if p.startswith('tests/')}
    reasons = defaultdict(set)

    def add(paths, reason):
        for p in paths:
            if p in graph.py:
                reasons[p].add(reason)

    add(ACTIVE, 'explicit active/operational root')
    # Real robot code is a protected boundary, including out-of-scope package roots.
    add((p for p in graph.py if not p.startswith((*CORE, 'tests/', 'experiments/'))),
        'outside retirement scope / real robot entry')
    add((p for p in core if p.startswith(('scripts/red_block/', 'scripts/tensorboard_tools/'))),
        'hardware or TensorBoard user tools')
    add(('scripts/approach_red_block.py', 'scripts/fetch_red_block.py', 'scripts/pick_red_block.py',
         'scripts/track_red_block.py', 'scripts/masterpi_control.py', 'scripts/robot_actions.py',
         'scripts/migrate_cursor_history.py', 'scripts/verify_terrain_maps.py'), 'hardware/operational tool')
    # All current documentation commands plus exact path mentions, conservatively.
    for p in base:
        if (p.startswith('docs/') and not p.startswith('docs/archive/') and p.endswith('.md')) or (
                '/' not in p and p.endswith('.md')) or p.startswith(('.github/', '.githooks/')) or (
                p.endswith(('.sh', '.command', '.zsh', '.ps1', '.bat')) and not p.startswith('experiments/')):
            add(graph.text_refs(blobs.read(base[p])), 'documented/CI/tool path: ' + p)
    # Dynamic plugin module values in current configuration. Source hash ledgers are
    # records, not entrypoints; do not promote arbitrary historical .py paths.
    for p in base:
        if p.startswith(('config/', 'configs/')) and p.endswith(('.json', '.yaml', '.yml', '.toml')):
            for token in re.findall(r'["\']((?:harness|sim|scripts)\.[\w.:]+)["\']', blobs.read(base[p])):
                if 'simulation_workflows' not in p:
                    add(graph.literal(token), 'configured plugin: ' + p)
    prs = json.loads((HERE / 'prs.json').read_text())
    refs = {p['headRefName']: p['headRefOid'] for p in prs}
    for ref in EXTRA_REFS:
        refs.setdefault(ref.removeprefix('origin/'), git('rev-parse', ref).strip())
    branch_records = []
    for name, sha in refs.items():
        print('branch', name, sha[:12], flush=True)
        branch = snapshot(sha)
        branch_graph = Graph(branch, lambda p, b=branch: blobs.read(b[p]))
        ancestor = git('merge-base', BASE, sha).strip()
        changed = git('diff', '--name-only', '--diff-filter=ACMRT', ancestor, sha).splitlines()
        roots = {p for p in changed if p.endswith('.py') and p in branch}
        # A modified launch shell, manifest or bundle can depend on unchanged main.
        for p in changed:
            if p in branch and p.endswith(('.json', '.yaml', '.yml', '.sh', '.zsh', '.command', '.md')):
                roots.update(branch_graph.text_refs(blobs.read(branch[p])))
        reached = branch_graph.closure(roots)
        add(reached, 'branch: ' + name)
        branch_records.append({'branch': name, 'sha': sha, 'merge_base': ancestor,
                               'changed': changed, 'main_dependencies': sorted(reached & graph.py),
                               'unresolved': branch_graph.unresolved, 'errors': branch_graph.errors})
    # Packages are cheap and their import side effects/namespace must survive.
    add((p for p in core if p.endswith(('/__init__.py', '/__main__.py'))), 'package/CLI entrypoint')
    live = graph.closure(reasons)
    runtime_live = live & core
    # Keep any test touching a live module, then its complete dependency closure.
    # Unclassified tests are retained, never deleted just because AST found no edge.
    test_targets = {p: {q for q in graph.parse(p) & core if not q.endswith('/__init__.py')}
                    for p in tests}
    while True:
        keep_tests = {p for p, targets in test_targets.items() if not targets or targets & live or p in live}
        grown = graph.closure(live | keep_tests)
        if grown == live:
            break
        live = grown
    dead_core = core - live
    holds = {p: 'real robot calibration/geometry boundary; current owner use unconfirmed'
             for p in dead_core if p.startswith('scripts/benchmarks/') or
             p in ('scripts/stress_real_geometry_parity.py', 'scripts/eval_masterpi_v2_expert.py')}
    if 'harness/real_obstacles.py' in dead_core:
        holds['harness/real_obstacles.py'] = 'physical MasterPi depth-provider contract; protected real robot boundary'
    # Historical executable records are not removed. Preserve their actual AST
    # dependencies as well; README reproduction notes alone cannot fix an import.
    historical_roots = {p for p in graph.py if p.startswith('experiments/')}
    historical_dependencies = graph.closure(historical_roots) & dead_core
    for p in historical_dependencies:
        holds[p] = 'retained executable experiment record imports/launches this file'
    held_closure = graph.closure(holds) & dead_core
    for p in held_closure:
        holds.setdefault(p, 'dependency of a deferred file')
    dead_core -= held_closure
    dead_tests = {p for p in tests - live if test_targets[p] and test_targets[p] <= dead_core}
    for p in graph.py:
        if p.startswith((*CORE, 'tests/')):
            graph.parse(p)
    catalogs = []
    for p in base:
        if p == 'configs/simulation_workflows.json' or p.startswith('configs/simulation_workflows.d/'):
            value = json.loads(blobs.read(base[p]))
            for w in value['workflows']:
                targets = graph.literal(w.get('entry', '')) | graph.literal(w.get('runner', ''))
                catalogs.append({'file': p, 'id': w['id'], 'entry': w.get('entry'),
                                 'retire': bool(targets) and targets <= dead_core})
    report = {'base': BASE, 'branches': branch_records,
              'roots': {p: sorted(v) for p, v in sorted(reasons.items())},
              'runtime_live': sorted(runtime_live), 'live_core': sorted(live & core),
              'test_only_retained': sorted((live & core) - runtime_live),
              'held_core': holds,
              'dead_core': sorted(dead_core), 'dead_tests': sorted(dead_tests),
              'catalogs': catalogs, 'unresolved': graph.unresolved, 'errors': graph.errors,
              'counts': {'core': len(core), 'live_core': len(live & core), 'held_core': len(holds), 'dead_core': len(dead_core),
                         'tests': len(tests), 'dead_tests': len(dead_tests)},
              'out_of_scope': sorted(p for p in base if p.startswith(('maps/', 'sim/assets/')))}
    # Keep the review artifact small; frozen refs + this program reproduce the
    # complete branch walk, so do not duplicate thousands of paths per branch.
    report['branches'] = [
        {k: b[k] for k in ('branch', 'sha', 'merge_base')} |
        {'changed_file_count': len(b['changed']), 'main_dependency_count': len(b['main_dependencies']),
         'unresolved_count': len(b['unresolved']), 'errors': b['errors']}
        for b in branch_records]
    report['roots'] = {p: [r[0], f'plus {len(r)-1} other root reasons'] if len(r) > 1 else r
                       for p, r in report['roots'].items()}
    (HERE / 'inventory.json').write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')) + '\n')
    (HERE / 'edges.json').write_text(json.dumps({p: sorted(v) for p, v in sorted(graph.edges.items())}, separators=(',', ':')) + '\n')
    print(json.dumps(report['counts'], indent=2))
    print('retired catalogs:', [w['id'] for w in catalogs if w['retire']])
    print('unresolved dynamic calls:', len(graph.unresolved), 'parse errors:', graph.errors)
    print('candidates:', '\n'.join(sorted(dead_core)))
    blobs.close()


if __name__ == '__main__':
    main()
