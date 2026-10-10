"""Small counterexamples for the deletion auditor, no repository imports."""
from audit import Graph


def make(source, extra=None):
    files = {'scripts/entry.py': source, 'harness/__init__.py': '',
             'harness/live.py': '', 'harness/unrelated.py': '',
             'scripts/helper.py': '', 'harness/__main__.py': ''}
    files.update(extra or {})
    return Graph(files, files.__getitem__)


def test_imports_relative_and_alias():
    graph = make('from harness import live as active\nfrom . import helper\n')
    assert {'harness/live.py', 'scripts/helper.py'} <= graph.parse('scripts/entry.py')
    assert 'harness/unrelated.py' not in graph.parse('scripts/entry.py')


def test_dynamic_constant_table_and_alias():
    graph = make('from importlib import import_module as load\n'
                 'PLUGINS = {"a": "harness.live"}\nload(PLUGINS[key])\n')
    assert 'harness/live.py' in graph.parse('scripts/entry.py')


def test_subprocess_module_and_path_composition():
    graph = make('import subprocess\nsubprocess.run([python, "-m", "harness"])\n'
                 'path = ROOT / "harness" / "live.py"\n')
    assert {'harness/__main__.py', 'harness/live.py'} <= graph.parse('scripts/entry.py')


def test_no_basename_substring_matching():
    graph = make('description = "unrelated and live are words in this paragraph"\n')
    assert not graph.parse('scripts/entry.py')


def test_unknown_loader_is_reported():
    graph = make('import importlib\nimportlib.import_module(request.module)\n')
    graph.parse('scripts/entry.py')
    assert len(graph.unresolved) == 1


def test_ci_pattern_is_not_a_runtime_root():
    graph = make('', {'scripts/run_ci_tests.py': 'TEST_PATTERNS = ("tests/test_old.py",)\n',
                      'tests/test_old.py': 'import harness.unrelated\n'})
    assert 'tests/test_old.py' not in graph.closure(['scripts/run_ci_tests.py'])
