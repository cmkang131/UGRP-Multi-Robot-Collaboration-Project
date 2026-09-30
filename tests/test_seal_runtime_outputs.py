"""Reproducibility checks for explicit output roles and audited mapping copies."""
import json
import os

import pytest

from harness import runtime_provenance as runtime
from test_seal_v2_review_301d import root, static, write, run, reject_before_child


def trace_outputs(root, outputs):
    declaration = static(root)
    return runtime.trace_contract(
        declaration, expected_static_sha256=declaration['sha256'], root=root,
        cases=[{'entry': 'entry.py', 'args': []}], output_artifacts=outputs,
    )


@pytest.mark.parametrize('query', [
    'os.listdir(".")',
    '[os.fsdecode(n) for n in os.listdir(b".")]',
    '[e.name for e in os.scandir(".")]',
    '[os.fsdecode(e.name) for e in os.scandir(b".")]',
    '[p.name for p in Path(".").iterdir()]',
    '[p.name for p in Path(".").glob("*")]',
])
def test_reserved_output_directory_view_stays_equal(root, query):
    write(root, 'entry.py', 'import os, sys\nfrom pathlib import Path\n'
          f'names = {query}\n'
          'assert "arbitrary.receipt" not in names\n'
          'assert "arbitrary.receipt.failed.json" not in names\n'
          'assert "runtime-seal.json" in names\n'
          'sys.audit("output.names." + str(len(names)))\n')
    write(root, 'runtime-seal.json', 'ordinary input, not a reserved output')
    outputs = [root / 'arbitrary.receipt', root / 'arbitrary.receipt.failed.json']
    value = trace_outputs(root, outputs)
    # Both exact output roles are invisible; similarly named input remains sealed.
    for output in outputs:
        output.write_text('tool-owned data')
    result = run(root, value)
    assert result['status'] == 'OK', result
    assert {k: v for k, v in result['events'].items() if k.startswith('output.names.')} == {
        k: v for k, v in value['traces'][0]['events'].items() if k.startswith('output.names.')}
    assert all(str(output) not in value['files'] for output in outputs)


@pytest.mark.parametrize('change', ['similar-name', 'other-directory', 'directory', 'symlink'])
def test_output_reservation_does_not_exempt_other_dependencies(root, monkeypatch, change):
    (root / 'other').mkdir()
    write(root, 'entry.py', 'import os\nos.listdir(".")\nos.listdir("other")\n')
    output = root / 'arbitrary.receipt'
    value = trace_outputs(root, [output])
    if change == 'similar-name':
        write(root, 'arbitrary.receipt.extra', 'new input')
    elif change == 'other-directory':
        write(root, 'other/arbitrary.receipt', 'new input')
    elif change == 'directory':
        output.mkdir()
    else:
        output.symlink_to('entry.py')
    reject_before_child(root, value, monkeypatch)


@pytest.mark.parametrize('alias', [False, True])
def test_reserved_output_cannot_be_consumed_as_input(root, alias):
    output = root / 'arbitrary.receipt'
    output.write_text('STOP')
    if alias:
        (root / 'alias').symlink_to(output.name)
    target = 'alias' if alias else output.name
    write(root, 'entry.py', f'open({target!r}).read()\n')
    with pytest.raises(runtime.TraceFailure, match='tool output cannot be read as input'):
        trace_outputs(root, [output])


def test_output_binding_through_parent_alias_is_pinned(root, monkeypatch):
    (root / 'real').mkdir()
    (root / 'other').mkdir()
    (root / 'view').symlink_to('real', target_is_directory=True)
    write(root, 'entry.py', 'import os\nassert os.listdir("real") == []\n')
    output = root / 'view/receipt'
    value = trace_outputs(root, [output])
    output.write_text(json.dumps(value))
    assert run(root, value)['status'] == 'OK'
    (root / 'view').unlink()
    (root / 'view').symlink_to('other', target_is_directory=True)
    reject_before_child(root, value, monkeypatch)


@pytest.mark.parametrize('binary', [False, True])
def test_environment_copy_is_independent_and_reads_every_item(binary):
    class Guard:
        def __init__(self):
            self.reads = []

        def env_read(self, key):
            self.reads.append(key)

    guard = Guard()
    values = {'MODE': 'STOP', 'UNUSED': 'retained', 'UNICODE': '한글'}
    adapter = runtime._Environment(guard, values, binary=binary)
    copied = adapter.copy()
    expected = {os.fsencode(k): os.fsencode(v) for k, v in values.items()} if binary else values
    assert type(copied) is dict and copied == expected
    assert set(guard.reads) == set(values)
    copied.clear()
    assert len(values) == 3
    assert adapter.copy() == expected
