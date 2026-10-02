"""PR #352 reviewer counterexamples ported from f5eb5636 as required regressions.

All seven former strict xfails must pass. V88 expectations retain all fields;
v90 exercises its dedicated entry points. No native physics/render/model calls.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess

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


@pytest.mark.parametrize("check", tuple(BASE_BYTES))
@pytest.mark.parametrize("artifact", ("bundle", "plan"))
def test_v88_full_bytes_are_preserved(tmp_path, check, artifact):
    value = (c.bundle(excitation.MAP_ID, check) if artifact == "bundle"
             else plan(args(tmp_path, excitation.MAP_ID, check)))
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
            parsed = run.parser().parse_args(runner_args)
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
