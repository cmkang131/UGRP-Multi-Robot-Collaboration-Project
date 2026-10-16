"""v2 fail-closed edges beyond the independent #301 reproductions; no physics."""
import copy
import json

import pytest

from harness.execution_dependency_contract import (
    WORKFLOW_SOURCES, build_contract, verify_contract, workflow_spec,
)
from test_seal_v2_review_301 import sandbox, spec, write, seal, run, must_reject


@pytest.mark.parametrize('loader', [
    'import importlib as il\nother = il\nfirst = other.import_module\nload = first\nmod = load(name="plugin")',
    'import builtins as b\nload = b.__import__\nmod = load("plugin")',
    'import builtins as b\nload = getattr(b, "__import__")\nmod = load("plugin")',
    'import importlib.metadata\nmod = importlib.import_module("plugin")',
    'il = __import__("importlib")\nmod = il.import_module("plugin")',
    'import importlib\nmod = (load := importlib.import_module)("plugin")',
])
def test_loader_alias_chains_and_keyword_names(sandbox, loader):
    write(sandbox, 'entry.py', loader + '\nprint(mod.COMMAND)\n')
    write(sandbox, 'plugin.py', 'COMMAND = "STOP"\n')
    receipt, expected = seal(sandbox, spec())
    assert run(sandbox) == 'STOP'
    write(sandbox, 'plugin.py', 'COMMAND = "MOVE"\n')
    assert run(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('statement', [
    'holder.load = importlib.import_module',
    'load = [importlib.import_module][0]',
    'consume(importlib.import_module)',
    'getattr(importlib, key)("plugin")',
    'load = importlib.__dict__["import_module"]',
    'load = getattr(importlib, "__dict__")["import_module"]',
    'importlib.import_module(first)\nimportlib.import_module(second)',
])
def test_file_declaration_does_not_authorize_unresolved_loader_uses(sandbox, statement):
    write(sandbox, 'entry.py', 'import importlib\n' + statement + '\n')
    write(sandbox, 'plugin.py', 'VALUE = 1\n')
    # Even an explicit module list is not a blanket exception for escaped loaders
    # or multiple unresolved call sites. Refactor these into reviewed wrappers.
    with pytest.raises(ValueError, match='dynamic'):
        build_contract(spec(dynamic_imports={'entry.py': ['plugin']}), root=sandbox)


def test_builtin_alias_fromlist_still_requires_coverage(sandbox):
    write(sandbox, 'entry.py', 'from builtins import __import__ as load\n'
          'print(load("pkg", fromlist=["child"]).child.COMMAND)\n')
    write(sandbox, 'pkg/__init__.py', '')
    write(sandbox, 'pkg/child.py', 'COMMAND = "STOP"\n')
    with pytest.raises(ValueError, match='undeclared dynamic import'):
        build_contract(spec(), root=sandbox)
    receipt, expected = seal(sandbox, spec(dynamic_imports={'entry.py': ['pkg.child']}))
    assert run(sandbox) == 'STOP'
    write(sandbox, 'pkg/child.py', 'COMMAND = "MOVE"\n')
    assert run(sandbox) == 'MOVE'
    must_reject(sandbox, receipt, expected)


def test_computed_all_pins_unused_children_and_new_files(sandbox):
    write(sandbox, 'entry.py', 'from pkg import *\nprint(child.COMMAND)\n')
    write(sandbox, 'pkg/__init__.py', '__all__ = ["ch" + "ild"]\n')
    write(sandbox, 'pkg/child.py', 'COMMAND = "STOP"\n')
    write(sandbox, 'pkg/unselected.py', 'VALUE = 1\n')
    receipt, expected = seal(sandbox, spec())
    assert 'pkg/unselected.py' in receipt['source_sha256']
    assert run(sandbox) == 'STOP'
    write(sandbox, 'pkg/new_child.py', 'VALUE = 2\n')
    must_reject(sandbox, receipt, expected)


def test_relative_star_in_namespace_package_pins_children(sandbox):
    write(sandbox, 'entry.py', 'from pkg import parent\n')
    write(sandbox, 'pkg/parent.py', 'from .childpkg import *\n')
    write(sandbox, 'pkg/childpkg/__init__.py', '__all__ = ["child"]\n')
    write(sandbox, 'pkg/childpkg/child.py', 'VALUE = 1\n')
    receipt, expected = seal(sandbox, spec())
    write(sandbox, 'pkg/childpkg/child.py', 'VALUE = 2\n')
    must_reject(sandbox, receipt, expected)


@pytest.mark.parametrize('module', ['helper.py', 'jobs/helper.py', 'jobs/child.py'])
def test_script_resolution_pins_all_local_candidates_and_transitive_siblings(sandbox, module):
    write(sandbox, 'jobs/entry.py', 'import helper\nprint(helper.COMMAND)\n')
    write(sandbox, 'helper.py', 'COMMAND = "ROOT"\n')
    write(sandbox, 'jobs/helper.py', 'from child import COMMAND\n')
    write(sandbox, 'jobs/child.py', 'COMMAND = "SCRIPT"\n')
    receipt, expected = seal(sandbox, spec('jobs/entry.py'))
    assert {'helper.py', 'jobs/helper.py', 'jobs/child.py'} <= receipt['source_sha256'].keys()
    assert run(sandbox, 'jobs/entry.py') == 'SCRIPT'
    write(sandbox, module, 'COMMAND = "MOVE"\n')
    must_reject(sandbox, receipt, expected)


def test_receipt_key_reorder_cannot_hide_behind_dict_equality(sandbox):
    write(sandbox, 'entry.py', '')
    write(sandbox, 'registry.json', '{"policy":{"first":1,"second":2}}')
    receipt, expected = seal(sandbox, spec(registries=[{'path': 'registry.json', 'keys': ['policy']}]))
    changed = copy.deepcopy(receipt)
    changed['registry_entries'][0]['value'] = {'second': 2, 'first': 1}
    with pytest.raises(ValueError, match='order/hash mismatch'):
        verify_contract(changed, expected_sha256=expected, root=sandbox)


def workflow_fixture(root):
    rows = [dict(id=name, entry=f'{name}.py', runner=name, version='1', output_flag=None,
                 output_kind='directory', required_inputs=[], side_effect='offline_analysis')
            for name in ('used', 'unused')]
    for name in ('used', 'unused'):
        write(root, name + '.py', '')
    catalog = {'schema': 'ugrp.local_workflow_catalog.v1', 'workflows': rows}
    write(root, 'configs/simulation_workflows.json', json.dumps(catalog))
    return catalog


@pytest.mark.parametrize('path', WORKFLOW_SOURCES)
def test_each_standard_launcher_is_mandatory_and_pinned(sandbox, path):
    workflow_fixture(sandbox)
    declaration = workflow_spec('used', root=sandbox)
    receipt, expected = seal(sandbox, declaration)
    assert path in receipt['source_sha256']
    write(sandbox, path, (sandbox / path).read_text() + '\n# launcher change\n')
    must_reject(sandbox, receipt, expected)
    (sandbox / path).unlink()
    with pytest.raises(ValueError, match='missing or nonlocal'):
        build_contract(declaration, root=sandbox)


@pytest.mark.parametrize('fault', ['required-field', 'deleted-file', 'missing-id'])
def test_unused_catalog_admission_errors_fail_seal(sandbox, fault):
    catalog = workflow_fixture(sandbox)
    receipt, expected = seal(sandbox, workflow_spec('used', root=sandbox))
    if fault == 'required-field':
        del catalog['workflows'][1]['runner']
    elif fault == 'missing-id':
        del catalog['workflows'][1]['id']
    else:
        (sandbox / 'unused.py').unlink()
    write(sandbox, 'configs/simulation_workflows.json', json.dumps(catalog))
    must_reject(sandbox, receipt, expected)
