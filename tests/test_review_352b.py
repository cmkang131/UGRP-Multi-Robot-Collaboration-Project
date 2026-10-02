"""Independent fa2119ca re-review: serialized roles and admission boundaries.

Run from the candidate archive; main-based review branches skip this module.
Only fake acquisition is used. No native physics, rendering, or model calls.
"""
import copy
import importlib
import json
from pathlib import Path
import re
import shlex
import sys
from types import SimpleNamespace

import pytest

heldout = pytest.importorskip('harness.zone_final_pair_heldout')
from harness import zone_final_pair_contract as c
from scripts import run_final_pair_heldout as run
from tests.test_zone_final_pair_v3 import FakePhysics, offline_only

MAPS = ('zone_wide_corridor_final_v3', 'zone_wide_door_geometry_v3')
ROLE = {'collection_role': 'HELD_OUT_VALIDATION', 'training_eligible': False,
        'teacher_only': True}
HEAD = 'fa2119ca6926a66a317a455701cbc389d7d3fb58'


def argv(out, map_id):
    return ['--check', 'calibration-unloaded', '--map-id', map_id, '--seed', '911',
            '--expected-source-sha', HEAD, '--output', str(out)]


def fake_host(tmp_path, monkeypatch, backend=FakePhysics):
    from scripts import agent_lock
    original = run.subprocess.check_output
    def git(command, **kw):
        if '--git-common-dir' in command:
            return str(tmp_path / '.git') + '\n'
        if '--show-current' in command:
            return 'codex/review-352-fake\n'
        return original(command, **kw)
    monkeypatch.setattr(run.subprocess, 'check_output', git)
    monkeypatch.setattr(run, 'check_source', lambda _: None)
    monkeypatch.setattr(run.shutil, 'disk_usage', lambda _: SimpleNamespace(free=20 * 1024**3))
    monkeypatch.setattr(agent_lock, 'status', lambda _: {
        'pid_alive': True, 'owner': 'codex', 'branch': 'codex/review-352-fake'})
    monkeypatch.setitem(sys.modules, 'sim.final_pair_heldout', SimpleNamespace(PhysicsBackend=backend))


def assert_roles(record):
    for key, expected in ROLE.items():
        assert record[key] == expected, key
        assert type(record[key]) is type(expected), key


def assert_saved(out, map_id, failed=False):
    records = {name: json.loads((out / name).read_text()) for name in (
        'plan.json', 'result.json', f'{map_id}/bundle.json', f'{map_id}/result.json')}
    for record in records.values():
        assert_roles(record)
    total = records['result.json']
    case = records[f'{map_id}/result.json']
    assert len(total['cases']) == 1 and total['cases'][0] == case
    assert_roles(total['cases'][0])
    for result in (total, case):
        assert result['status'] == ('HOST_ERROR' if failed else 'COLLECTED_UNQUALIFIED')
        assert result['physical_success'] is None
    assert case['collection_data_status'] == ('PARTIAL_INVALID_HOST_ERROR' if failed else 'UNQUALIFIED')
    assert case['partial_data_retained'] is failed
    hashes = json.loads((out / map_id / 'artifacts.sha256.json').read_text())
    for name in ('bundle.json', 'result.json'):
        assert hashes[name] == c.base.sha(out / map_id / name)


@pytest.mark.parametrize('map_id', MAPS)
@pytest.mark.parametrize('failed', (False, True))
def test_all_saved_roles_in_both_maps_and_host_error(tmp_path, monkeypatch, map_id, failed):
    class Backend(FakePhysics):
        failure = RuntimeError('synthetic acquisition fault') if failed else None
    fake_host(tmp_path, monkeypatch, Backend)
    out = tmp_path / 'outputs' / map_id
    assert run.main(argv(out, map_id) + ['--execute', '--lock-owner', 'codex']) == int(failed)
    assert_saved(out, map_id, failed)


@pytest.mark.parametrize('map_id', MAPS)
@pytest.mark.parametrize('seed', (-1, 0, 910, 912, 2147483647))
def test_seed_widening_refused_at_cli_case_and_backend(tmp_path, map_id, seed):
    from sim.final_pair_heldout import PhysicsBackend
    out = tmp_path / 'refused'
    with pytest.raises(ValueError, match='seed 911'):
        run.main(argv(out, map_id) + ['--seed', str(seed)])
    bundle = {**heldout.bundle(map_id, 'calibration-unloaded'),
              'case': heldout.cases('calibration-unloaded', map_id)[0]}
    for execute in (
        lambda: run.run_case(bundle, out, seed=seed,
            backend_factory=lambda *a, **kw: pytest.fail('backend reached')),
        lambda: PhysicsBackend(bundle, out, seed=seed),
    ):
        with pytest.raises(ValueError, match='seed 911'):
            execute()
    assert not out.exists()


@pytest.mark.parametrize('map_id', MAPS)
@pytest.mark.parametrize('check', ('calibration-fine', 'calibration-loaded'))
def test_fine_loaded_refused_even_with_forged_case_and_measurement(tmp_path, map_id, check):
    from sim.final_pair_heldout import PhysicsBackend
    from harness.zone_final_pair_excitation import MAP_ID
    bundle = {**heldout.bundle(map_id, 'calibration-unloaded'),
              'case': heldout.cases('calibration-unloaded', map_id)[0]}
    training = c.bundle(MAP_ID, check)
    bundle.update(check=check, timing=training['timing'], measurement=training['measurement'])
    bundle['measurement']['map_id'] = map_id
    out = tmp_path / 'refused'
    with pytest.raises(ValueError):
        run.run_case(bundle, out, seed=911,
            backend_factory=lambda *a, **kw: pytest.fail('backend reached'))
    with pytest.raises(ValueError):
        PhysicsBackend(bundle, out, seed=911)
    assert not out.exists()


@pytest.mark.parametrize('map_id', MAPS)
@pytest.mark.parametrize('key,bad', [('collection_role', 'TRAINING'),
                                   ('training_eligible', True), ('teacher_only', False)])
def test_code_registry_label_mutation_rejected_by_independent_saved_expectations(
        tmp_path, monkeypatch, map_id, key, bad):
    fake_host(tmp_path, monkeypatch)
    read = c.base.read
    monkeypatch.setattr(heldout, 'ROLE', {**heldout.ROLE, key: bad})
    def changed(path):
        value = read(path)
        return {**value, key: bad} if Path(path) == c.ROOT / heldout.REGISTRY else value
    monkeypatch.setattr(c.base, 'read', changed)
    out = tmp_path / 'outputs' / map_id
    assert run.main(argv(out, map_id) + ['--execute', '--lock-owner', 'codex']) == 0
    with pytest.raises(AssertionError, match=key):
        assert_saved(out, map_id)


@pytest.mark.parametrize('target', ('plan.json', 'result.json', 'case-result', 'nested-case'))
@pytest.mark.parametrize('key,bad', [('collection_role', 'TRAINING'),
                                   ('training_eligible', True), ('teacher_only', False)])
def test_isolated_serialized_label_mutation_is_detected(tmp_path, monkeypatch, target, key, bad):
    fake_host(tmp_path, monkeypatch)
    map_id = MAPS[0]
    out = tmp_path / 'outputs' / map_id
    write = run.write
    def corrupt(path, value):
        relative = str(path.relative_to(out))
        wanted = f'{map_id}/result.json' if target == 'case-result' else target
        if relative == wanted or target == 'nested-case' and relative == 'result.json':
            value = copy.deepcopy(value)
            record = value['cases'][0] if target == 'nested-case' else value
            record[key] = bad
        write(path, value)
    monkeypatch.setattr(run, 'write', corrupt)
    assert run.main(argv(out, map_id) + ['--execute', '--lock-owner', 'codex']) == 0
    with pytest.raises(AssertionError):
        assert_saved(out, map_id)


@pytest.mark.xfail(strict=True, raises=ValueError,
    reason='R3: PHYSICS_HANDOFF.md:67 still advertises the rejected v88 direct preview')
@pytest.mark.parametrize('map_id', MAPS)
def test_documented_direct_preview_actually_accepts_both_maps(tmp_path, capsys, map_id):
    text = (c.ROOT / 'PHYSICS_HANDOFF.md').read_text()
    module = re.search(r'`(run_final_pair_\w+) --check calibration-unloaded --map-id <위 두 지도>`', text).group(1)
    entry = importlib.import_module('scripts.' + module).main
    assert entry(argv(tmp_path / 'unused', map_id)) == 0
    assert json.loads(capsys.readouterr().out)['execution_bundle_id'] == 'zone-final-pair-v90'


def test_exact_handoff_workflow_arguments_reach_fake_backend_for_both_maps(tmp_path, monkeypatch):
    from sim import workflow_manager as wm
    fake_host(tmp_path, monkeypatch)
    text = (c.ROOT / 'PHYSICS_HANDOFF.md').read_text()
    block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
    commands = []
    for line in block.replace('\\\n', ' ').splitlines():
        if ' -m scripts.sim_cli workflow run ' not in line:
            continue
        words = shlex.split(line)
        selected = words.index('scripts.sim_cli')
        assert words[selected + 1:selected + 4] == ['workflow', 'run', 'zone-final-pair-heldout-v90']
        flags = words[selected + 5:]
        flags = [HEAD if word == '$FINAL_SHA' else word for word in flags]
        parsed = run.parser().parse_args(flags)
        assert parsed.execute and parsed.lock_owner == 'codex' and parsed.seed == 911
        assert parsed.expected_source_sha == HEAD
        assert str(parsed.output) == '$RUN_ROOT/' + parsed.map_id
        out = tmp_path / 'outputs' / parsed.map_id
        flags[flags.index('--output') + 1] = str(out)
        planned = wm.plan(c.ROOT, 'zone-final-pair-heldout-v90', flags)
        assert planned['workflow_version'] == '3.2.0'
        assert planned['command'][1:3] == ['-m', 'scripts.run_final_pair_heldout']
        assert run.main(planned['command'][3:]) == 0
        assert_saved(out, parsed.map_id)
        commands.append(parsed.map_id)
    assert commands == list(MAPS)
