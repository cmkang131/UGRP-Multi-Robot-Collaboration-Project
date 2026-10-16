"""PR #352 reviewer counterexamples ported from f5eb5636 as required regressions.

All nine former strict xfails must pass (including R3 from 3a6070b3). V88 expectations retain all fields;
v90 exercises its dedicated entry points. No native physics/render/model calls.
"""
import contextlib
import hashlib
import io
import importlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest

from harness import zone_final_pair_heldout as heldout
from harness import zone_final_pair_contract as c
from harness import zone_final_pair_heldout_clearance as clearance
from harness import zone_final_pair_excitation as excitation
from scripts import run_final_pair_v3 as run
from scripts import run_final_pair_heldout as managed
from tests.test_zone_final_pair_v3 import FakePhysics, offline_only

HEAD = "d92efd8d7381a270ff266c01d7534dc8ab1c89f8"
MAPS = ("zone_wide_corridor_final_v3", "zone_wide_door_geometry_v3")
ROLE = {"collection_role": "HELD_OUT_VALIDATION", "training_eligible": False,
        "teacher_only": True}
# Actual writer bytes generated independently at main 2523269857596ffdd1a8cda9814a6e92f399f1da.
# No source-dependent fields are removed from these expectations.
BASE_BYTES = {
    "calibration-unloaded": {
        "bundle": "1f4685fe5240ab91bb1982b6db8e3ec63b5689959e9afc787b2c38f55aaf3d94",
        "plan": "7f6d665104d953ce3ea8751b652963c31ab902ac33574d7acdcd86e54e8d8d36"},
    "calibration-loaded": {
        "bundle": "10605b2b433f8acb923e6802b490cb32c19d9c7222324b9ebe74f470ca7721d3",
        "plan": "ac640e5b194da11d1b58df676630aee058b0b8c9f0a89eff8e42984fd7b8c5dd"},
    "calibration-fine": {
        "bundle": "ab0bb9a4ba91a88ba316906ffc59e01b42ed882b676101ccda5019f71fae6bd5",
        "plan": "fea4037700fa0a67305968fdef1f653e24321358fb13babf2fe8280848a8c176"},
}


def args(tmp_path, map_id, check="calibration-unloaded"):
    return ["--check", check, "--map-id", map_id, "--seed", "911",
            "--expected-source-sha", "a" * 40, "--output", str(tmp_path / "out")]


def plan(argv, entry=run.main):
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        assert entry(argv) == 0
    return json.loads(captured.getvalue())


def baseline_writer(tmp_path, check, artifact):
    from tests.pinned_source_bundle import bundle_at, json_at
    revision = '2523269857596ffdd1a8cda9814a6e92f399f1da'
    paths = tuple(c.bundle(excitation.MAP_ID, check)['source_sha256'])
    if artifact == 'bundle':
        value = bundle_at(revision, c.__name__, excitation.MAP_ID, check, paths)
    else:
        code = ('import json,io,contextlib; from scripts import run_final_pair_v3 as run; '
                'output=io.StringIO();\nwith contextlib.redirect_stdout(output):\n '
                'assert run.main(' + repr(args(tmp_path, excitation.MAP_ID, check)) + ')==0\n'
                'print(output.getvalue())')
        value = json_at(revision, code, paths)
    return value


@pytest.mark.parametrize("check", tuple(BASE_BYTES))
@pytest.mark.parametrize("artifact", ("bundle", "plan"))
def test_v88_full_bytes_are_preserved(tmp_path, check, artifact):
    value = baseline_writer(tmp_path, check, artifact)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    assert hashlib.sha256(raw).hexdigest() == BASE_BYTES[check][artifact]


def test_existing_plan_regression_detects_training_label_drift(tmp_path, capsys, monkeypatch):
    from tests.test_zone_final_pair_heldout import (
        test_check_only_plans_admit_only_new_heldout_without_backend as existing_test)
    old_read = c.base.read
    monkeypatch.setattr(heldout, "ROLE", {**heldout.ROLE, "collection_role": "TRAINING"})

    def changed_registry(path):
        value = old_read(path)
        return ({**value, "collection_role": "TRAINING"}
                if Path(path) == c.ROOT / heldout.REGISTRY else value)

    monkeypatch.setattr(c.base, "read", changed_registry)
    detected = False
    try:
        existing_test(tmp_path, capsys, monkeypatch, MAPS[0], managed.main)
    except AssertionError:
        detected = True
    assert detected, "Existing plan regression accepted collection_role=TRAINING"


@pytest.mark.parametrize("map_id", MAPS)
def test_literal_heldout_role_in_plan_bundle_and_fake_result(tmp_path, map_id):
    value = plan(args(tmp_path, map_id), managed.main)
    bundle = {**heldout.bundle(map_id, "calibration-unloaded"),
              "case": heldout.cases("calibration-unloaded", map_id)[0]}
    result = managed.run_case(bundle, tmp_path / "fake", seed=911, backend_factory=FakePhysics)
    for record in (value, bundle, result):
        assert {key: record[key] for key in ROLE} == ROLE
    assert result["status"] == "COLLECTED_UNQUALIFIED"
    assert result["physical_success"] is None and not result["student_control"]


@pytest.mark.parametrize("map_id", MAPS)
@pytest.mark.parametrize("pose", ([999.0, -0.85, 0.0], [float("nan"), -0.85, 0.0]))
def test_heldout_start_and_nan_refuse_even_a_forged_saved_pass(tmp_path, monkeypatch, map_id, pose):
    bundle = {**heldout.bundle(map_id, "calibration-unloaded"),
              "case": heldout.cases("calibration-unloaded", map_id)[0]}
    monkeypatch.setattr(excitation, "UNLOADED_POSE", pose)
    assert not clearance.path_preflight("calibration-unloaded", map_id)["admitted"]
    bundle["clearance_preflight"]["admitted"] = True
    with pytest.raises(ValueError, match="COLLECTION_PREFLIGHT_REJECTED"):
        managed.run_case(bundle, tmp_path / "refused", seed=911,
                     backend_factory=lambda *a, **kw: pytest.fail("backend reached"))
    assert not (tmp_path / "refused").exists()


@pytest.mark.parametrize("extra", (
    ["--weld", "on"], ["--disable-interlock"], ["--render-profile", "default"],
    ["--teacher-only", "false"], ["--map-id", "unregistered_map"],
    ["--check", "calibration-fine", "--calibration", "unused.json"],
    ["--check", "calibration-loaded", "--calibration", "unused.json"],
    ["--seed", "912"],
))
def test_flags_cannot_widen_heldout_admission(tmp_path, extra):
    with pytest.raises((ValueError, SystemExit)):
        managed.main(args(tmp_path, MAPS[0]) + extra)
    assert not (tmp_path / "out").exists()


def test_handoff_shell_syntax_lock_flags_and_both_workflow_commands(tmp_path, monkeypatch):
    from scripts import agent_lock
    from sim import workflow_manager as wm
    text = (c.ROOT / "PHYSICS_HANDOFF.md").read_text()
    block = re.search(r"```bash\n(.*?)\n```", text, re.S).group(1)
    subprocess.run(["bash", "-n"], input=block, text=True, check=True)
    locks, commands = [], []
    # Only the CLI parsers run. No shared lock or output path is accessed.
    monkeypatch.setattr(agent_lock, "acquire", lambda *a, **kw: locks.append(kw) or {})
    replacements = {"$FINAL_BRANCH": "codex/calib-heldout-maps", "$$": "12345",
                    "$FINAL_SHA": HEAD}
    for line in block.replace("\\\n", " ").splitlines():
        if not line.startswith('"$PY"'):
            continue
        argv = [replacements.get(token, token) for token in shlex.split(line)]
        if argv[1:3] == ["scripts/agent_lock.py", "acquire"]:
            assert agent_lock.main(argv[2:]) == 0
        elif "scripts.sim_cli" in argv:
            command = argv[argv.index("scripts.sim_cli") + 1:]
            assert command[:4] == ["workflow", "run", "zone-final-pair-heldout-v90", "--"]
            runner_args = command[4:]
            parsed = managed.parser().parse_args(runner_args)
            assert parsed.execute and parsed.lock_owner == "codex"
            assert parsed.expected_source_sha == HEAD and parsed.seed == 911
            assert parsed.check == "calibration-unloaded"
            assert str(parsed.output) == "$RUN_ROOT/" + parsed.map_id
            runner_args[runner_args.index("--output") + 1] = str(tmp_path / parsed.map_id)
            preview = wm.plan(c.ROOT, command[2], runner_args)
            assert preview["command"][1:3] == ["-m", "scripts.run_final_pair_heldout"]
            assert not preview["execution_started"]
            runner_args.remove("--execute")
            assert plan(runner_args, managed.main)["runnable"]
            commands.append(parsed.map_id)
    assert commands == list(MAPS) and len(locks) == 2
    assert all(row["owner"] == "codex" and row["branch"] == "codex/calib-heldout-maps"
               and row["pid"] == 12345 and row["expected_minutes"] == 10 for row in locks)


# Documentation regressions ported from review 3a6070b3; no xfail remains.
def fake_host(tmp_path, monkeypatch, backend=FakePhysics):
    from scripts import agent_lock
    original = managed.subprocess.check_output
    def git(command, **kw):
        if '--git-common-dir' in command:
            return str(tmp_path / '.git') + '\n'
        if '--show-current' in command:
            return 'codex/review-352-fake\n'
        return original(command, **kw)
    monkeypatch.setattr(managed.subprocess, 'check_output', git)
    monkeypatch.setattr(managed, 'check_source', lambda _: None)
    monkeypatch.setattr(managed.shutil, 'disk_usage', lambda _: SimpleNamespace(free=20 * 1024**3))
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
def test_documented_direct_preview_actually_accepts_both_maps(tmp_path, capsys, map_id):
    text = (c.ROOT / 'PHYSICS_HANDOFF.md').read_text()
    module = re.search(r'`(run_final_pair_\w+) --check calibration-unloaded --map-id <위 두 지도>`', text).group(1)
    entry = importlib.import_module('scripts.' + module).main
    assert entry(args(tmp_path / 'unused', map_id)) == 0
    assert json.loads(capsys.readouterr().out)['execution_bundle_id'] == 'zone-final-pair-v90'
    # Also exercise the complete copyable preview, preserving the reviewer's
    # shorthand counterexample above. Never execute either shell block.
    block = re.findall(r'```bash\n(.*?)\n```', text, re.S)[1]
    subprocess.run(['bash', '-n'], input=block, text=True, check=True)
    assert 'FINAL_SHA=$(git rev-parse HEAD)' in block
    commands = [shlex.split(line) for line in block.replace('\\\n', ' ').splitlines()
                if line.startswith('"$PY" -m ')]
    assert len(commands) == 2
    selected = [words for words in commands if map_id in words]
    assert len(selected) == 1
    words = selected[0]
    assert words[1:3] == ['-m', 'scripts.' + module]
    flags = [HEAD if word == '$FINAL_SHA' else word for word in words[3:]]
    parsed = managed.parser().parse_args(flags)
    assert not parsed.execute and parsed.lock_owner is None
    assert parsed.check == 'calibration-unloaded' and parsed.seed == 911
    assert parsed.expected_source_sha == HEAD
    assert str(parsed.output) == '$RUN_ROOT/' + map_id
    output = tmp_path / 'preview-unused'
    flags[flags.index('--output') + 1] = str(output)
    assert entry(flags) == 0
    assert json.loads(capsys.readouterr().out)['execution_bundle_id'] == 'zone-final-pair-v90'
    assert not output.exists()


def test_exact_handoff_workflow_arguments_reach_fake_backend_for_both_maps(tmp_path, monkeypatch):
    from sim import workflow_manager as wm
    fake_host(tmp_path, monkeypatch)
    text = (c.ROOT / 'PHYSICS_HANDOFF.md').read_text()
    block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
    assert 'FINAL_SHA=$(git rev-parse HEAD)' in block
    commands = []
    for line in block.replace('\\\n', ' ').splitlines():
        if ' -m scripts.sim_cli workflow run ' not in line:
            continue
        words = shlex.split(line)
        selected = words.index('scripts.sim_cli')
        assert words[selected + 1:selected + 4] == ['workflow', 'run', 'zone-final-pair-heldout-v90']
        flags = words[selected + 5:]
        flags = [HEAD if word == '$FINAL_SHA' else word for word in flags]
        parsed = managed.parser().parse_args(flags)
        assert parsed.execute and parsed.lock_owner == 'codex' and parsed.seed == 911
        assert parsed.expected_source_sha == HEAD
        assert str(parsed.output) == '$RUN_ROOT/' + parsed.map_id
        out = tmp_path / 'outputs' / parsed.map_id
        flags[flags.index('--output') + 1] = str(out)
        planned = wm.plan(c.ROOT, 'zone-final-pair-heldout-v90', flags)
        assert planned['workflow_version'] == '3.2.0'
        assert planned['command'][1:3] == ['-m', 'scripts.run_final_pair_heldout']
        assert managed.main(planned['command'][3:]) == 0
        assert_saved(out, parsed.map_id)
        commands.append(parsed.map_id)
    assert commands == list(MAPS)
