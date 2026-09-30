"""Declared execution dependencies for NEW registrations (v2), stdlib only.

Legacy receipts/builders are deliberately untouched. Use the v2 conservative AST
closure: never execute a policy to discover its inputs, and never subtract a
reachable Python file. Dynamic imports, subprocesses and non-Python inputs need
reviewed declarations; one observed trace is not proof that other paths are dead.
This receipt verifies dependencies, not scientific approval or run admission.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from harness.python_source_closure_v2 import dynamic_calls, source_closure
from sim.workflow_manager import catalog as workflow_catalog

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'ugrp.execution_dependency_contract.v2'
SPEC_SCHEMA = 'ugrp.execution_dependency_spec.v2'
VERIFIER_SOURCES = ('harness/execution_dependency_contract.py', 'harness/python_source_closure.py',
                    'harness/python_source_closure_v2.py', 'sim/workflow_manager.py')
WORKFLOW_SOURCES = ('sim/workflow_manager.py', 'scripts/sim_cli.py',
                    'scripts/ugrp_session.py', 'scripts/open_simulation.command')


def digest(value, *, sort_keys=True):
    return hashlib.sha256(json.dumps(value, sort_keys=sort_keys, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def local_file(root, name):
    if not isinstance(name, str) or not name:
        raise ValueError('expected a repository-relative file path')
    path = PurePosixPath(name)
    target = root / name
    if (path.is_absolute() or '..' in path.parts or str(path) != name
            or not target.resolve().is_relative_to(root) or not target.is_file()):
        raise ValueError(f'missing or nonlocal dependency: {name}')
    return target


def read_json(path):
    """Reject ambiguous keys and nonfinite values, including in registry files."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def invalid(value):
        raise ValueError(f'nonfinite JSON value: {value}')

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            invalid(value)
        return result

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs,
                      parse_constant=invalid, parse_float=finite_float)


def selected_entry(root, selector):
    """Select dict keys or a unique list row by a stable string key, never index."""
    if not isinstance(selector, dict) or set(selector) != {'path', 'keys'}:
        raise ValueError('registry selector must contain path and keys')
    if (not isinstance(selector['path'], str) or not selector['path'].endswith('.json')
            or not isinstance(selector['keys'], list) or not selector['keys']):
        raise ValueError('registry selector requires a JSON path and nonempty keys')
    document = read_json(local_file(root, selector['path']))
    if selector['path'] == 'configs/simulation_workflows.json':
        # Use the SAME trusted validator as the actual standard runner, including
        # unselected rows. Do not import or execute code from the candidate root.
        try:
            workflow_catalog(root)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f'invalid workflow catalog: {exc}') from exc
    value = document
    for key in selector['keys']:
        if isinstance(key, str) and isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(key, dict) and len(key) == 1 and isinstance(value, list):
            field, expected = next(iter(key.items()))
            if not isinstance(field, str) or not isinstance(expected, str):
                raise ValueError('registry row selectors require string keys/values')
            rows = [row for row in value if isinstance(row, dict) and row.get(field) == expected]
            if len(rows) != 1:
                raise ValueError(f'registry entry missing or ambiguous: {selector}')
            value = rows[0]
        else:
            raise ValueError(f'registry entry missing or invalid: {selector}')
    # Catalog schema changes affect interpretation even if the selected row stays.
    schema = document.get('schema') if isinstance(document, dict) else None
    if schema is not None and not isinstance(schema, str):
        raise ValueError('catalog schema must be a string or null')
    return {'selector': copy.deepcopy(selector), 'catalog_schema': schema,
            'value': copy.deepcopy(value), 'sha256': digest(value, sort_keys=False)}


def _spec(value):
    required = {'schema', 'entry_points', 'modules', 'inputs', 'registries', 'dynamic_imports'}
    if not isinstance(value, dict) or set(value) != required or value['schema'] != SPEC_SCHEMA:
        raise ValueError('new registrations require an explicit v2 dependency spec; no legacy migration')
    spec = copy.deepcopy(value)
    for key in ('entry_points', 'modules', 'inputs'):
        items = spec[key]
        if not isinstance(items, list) or any(not isinstance(p, str) or not p for p in items):
            raise ValueError(f'{key} must be a list of strings')
        spec[key] = sorted(set(items))
    if not spec['entry_points'] or any(not p.endswith('.py') for p in spec['entry_points']):
        raise ValueError('entry_points must name runtime Python files (including subprocess workers)')
    if not isinstance(spec['registries'], list) or not isinstance(spec['dynamic_imports'], dict):
        raise ValueError('invalid registries or dynamic_imports declaration')
    for path, modules in spec['dynamic_imports'].items():
        if not isinstance(path, str) or not isinstance(modules, list) or not modules or any(
                not isinstance(m, str) or not m for m in modules):
            raise ValueError('dynamic imports require an explicit nonempty module list per source file')
        spec['dynamic_imports'][path] = sorted(set(modules))
    spec['registries'].sort(key=digest)
    if len({digest(s) for s in spec['registries']}) != len(spec['registries']):
        raise ValueError('duplicate registry selector')
    return spec


def build_contract(spec, *, root=ROOT):
    """Default builder for new registrations. No Git SHA or whole catalog digest.

    Python roots cover the runner, policy, host/scene, evaluator and subprocess
    entry points. inputs covers maps/models/calibration/native code/environment
    files; modules covers configuration-selected Python factories. Registry
    defaults outside a selected row must be selected separately. These declarations
    are part of the seal and require the same review as the registration.
    """
    root = Path(root).resolve()
    spec = _spec(spec)
    paths = (*spec['entry_points'], *spec['inputs'], *VERIFIER_SOURCES)
    for path in paths:
        local_file(root, path)
    modules = set(spec['modules'])
    for declared in spec['dynamic_imports'].values():
        modules.update(declared)
    # Entry paths support both python -m and python path.py: include every
    # possible repository-local resolution under root and entry directories.
    script_dirs = {str(Path(p).parent) for p in spec['entry_points']}
    inspected = set()
    while True:
        closure = source_closure(root, paths, modules=sorted(modules), script_dirs=script_dirs)
        pending = set(closure) - inspected
        if not pending:
            break
        for name in sorted(pending):
            inspected.add(name)
            if not name.endswith('.py'):
                continue
            for module in dynamic_calls(local_file(root, name)):
                if module is None or module.startswith('.'):
                    if name not in spec['dynamic_imports']:
                        raise ValueError(f'undeclared dynamic import: {name}')
                elif any((root / prefix / p).is_file() for prefix in {'', *script_dirs} for p in
                         (module.replace('.', '/') + '.py', module.replace('.', '/') + '/__init__.py')):
                    modules.add(module)
    if set(spec['dynamic_imports']) - set(closure):
        raise ValueError('dynamic import declaration is outside the runtime closure')
    entries = [selected_entry(root, s) for s in spec['registries']]
    registry_paths = {s['path'] for s in spec['registries']}
    if registry_paths.intersection(closure):
        raise ValueError('registry cannot be both a whole-file input and an entry pin')
    value = {'schema': SCHEMA, 'declaration': spec,
             'source_sha256': {p: hashlib.sha256(local_file(root, p).read_bytes()).hexdigest() for p in closure},
             'registry_entries': entries}
    return {**value, 'sha256': digest(value)}


def verify_contract(value, *, expected_sha256, root=ROOT):
    """Recompute closure and entry hashes against an independently sealed digest.

    Call before worker/physics startup, using the outer registration's approved
    digest (not a digest copied from an untrusted candidate). Run SHA, clean-tree,
    study/approval/budget/environment checks remain the runner's responsibility.
    """
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError('unsupported dependency contract; use the legacy verifier for old seals')
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected independently sealed dependency digest')
    body = {k: v for k, v in value.items() if k != 'sha256'}
    if value.get('sha256') != expected_sha256 or digest(body) != expected_sha256:
        raise ValueError('dependency contract seal mismatch')
    for entry in value.get('registry_entries', []):
        if entry.get('sha256') != digest(entry.get('value'), sort_keys=False):
            raise ValueError('registry value order/hash mismatch')
    actual = build_contract(value['declaration'], root=root)
    if actual != value:
        changed = sorted(p for p in set(actual['source_sha256']) | set(value['source_sha256'])
                         if actual['source_sha256'].get(p) != value['source_sha256'].get(p))
        raise ValueError(f'execution dependency drift: sources={changed}; '
                         f'registry_entries_changed={actual["registry_entries"] != value["registry_entries"]}')
    return {'schema': SCHEMA, 'sha256': expected_sha256,
            'sources': len(actual['source_sha256']), 'registry_entries': len(actual['registry_entries'])}


def workflow_spec(workflow_id, *, root=ROOT, entry_points=(), modules=(), inputs=(),
                  registries=(), dynamic_imports=None):
    """Declare the standard launcher, CLI, runner and selected row.

    This is an offline registration builder, not an alternate workflow executor.
    The complete row is pinned (including arguments/version). All catalog rows
    must remain valid under the standard runner; valid sibling edits stay free.
    """
    root = Path(root).resolve()
    selector = {'path': 'configs/simulation_workflows.json', 'keys': ['workflows', {'id': workflow_id}]}
    row = selected_entry(root, selector)['value']
    if not isinstance(row.get('entry'), str) or not isinstance(row.get('runner'), str):
        raise ValueError('workflow requires explicit Python entry and runner')
    return _spec({'schema': SPEC_SCHEMA,
                  'entry_points': [row['entry'], *entry_points,
                                   *(p for p in WORKFLOW_SOURCES if p.endswith('.py'))],
                  'modules': [row['runner'], *modules],
                  'inputs': [*inputs, *(p for p in WORKFLOW_SOURCES if not p.endswith('.py'))],
                  'registries': [selector, *registries], 'dynamic_imports': dynamic_imports or {}})
