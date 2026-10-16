#!/usr/bin/env python3
"""Delete each fourth-review guard in memory; no raw/source edits or physics.

Baseline witnesses must pass. Only an AssertionError from an expected verdict
or adapter contract kills a mutant; import/runtime errors are never successes.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SPEC = importlib.util.spec_from_file_location("mutation_299d_contract", ROOT / "tests/test_v6h_recorder_contract.py")
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def adjudicate(cp, damage):
    data, context = contract.public_record()
    damage(data)
    out = cp.adjudicate_attempt(data["row"], data["result"], data["trace"], recorder_context=context)
    assert out["state"] == "INVALID" and out["class"] is None, "contradiction must be INVALID"


def distance(cp, boundary):
    def damage(data):
        for r in cp.ROBOTS:
            data["result"]["chain_raw"][r][boundary]["1"]["gt"]["beam_xyz"][0] += 1.
    adjudicate(cp, damage)


def chronology(cp, kind):
    def damage(data):
        if kind == "timeline":
            timeline = data["result"]["chain_raw"]["r1"]["timeline"]
            timeline[7], timeline[8] = timeline[8], timeline[7]
        else:
            data["result"]["gt_at_stop"]["t"] = data["trace"][-1]["t"] + 100.
    adjudicate(cp, damage)


def required_start(adapter):
    data, context = contract.public_record()
    del data["result"]["chain_raw"]["r1"]["leg_start"]["0"]
    try:
        adapter.adapt(data["row"], data["result"], data["trace"], **context)
    except (KeyError, ValueError):
        return
    raise AssertionError("registered producer contract must require both starts")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    cp = contract.cp
    paths = {"classifier": HERE / "classify_placements.py", "adapter": HERE / "recorder_v4c6b.py"}
    before = {name: cp.sha256(path) for name, path in paths.items()}
    distance_call = '                validate_recorder_distances(row, result, recorder_context["case"])'
    chronology_call = '                validate_recorder_chronology(row, result, trace)'
    mutations = [
        ("R1_end_coordinates", "classifier", lambda m: distance(m, "leg_end"), distance_call, "                pass"),
        ("R1_start_coordinates", "classifier", lambda m: distance(m, "leg_start"), distance_call, "                pass"),
        ("R2_stream_order", "classifier", lambda m: chronology(m, "timeline"), chronology_call, "                pass"),
        ("R2_stop_window", "classifier", lambda m: chronology(m, "stop"), chronology_call, "                pass"),
        ("R2_adapter_start_contract", "adapter", required_start,
         'for boundary in ("leg_start", "leg_end"):', 'for boundary in ("leg_end",):'),
    ]
    results = []
    for name, target, witness, old, new in mutations:
        witness(cp if target == "classifier" else cp.rv)
        path = paths[target]
        source = path.read_text()
        assert source.count(old) == 1, name
        mutant = types.ModuleType(name)
        mutant.__file__ = str(path)
        exec(compile(source.replace(old, new), str(path) + ":" + name, "exec"), mutant.__dict__)
        try:
            witness(mutant)
        except AssertionError as error:
            results.append({"mutation": name, "target": target, "baseline_pass": True,
                            "mutant": "KILLED", "failure": str(error), "deleted": old, "replacement": new})
        else:
            raise AssertionError(name + ": mutant survived")
    assert before == {name: cp.sha256(path) for name, path in paths.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"source_sha256": before, "source_unchanged": True,
        "killed": len(results), "survived": 0, "results": results}, indent=2) + "\n")
    print(json.dumps({"killed": len(results), "survived": 0, "groups": ["299d-R1", "299d-R2"]}))


if __name__ == "__main__":
    main()
