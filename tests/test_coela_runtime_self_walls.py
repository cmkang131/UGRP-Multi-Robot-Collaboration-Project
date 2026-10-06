"""Option ``self_wall_memory`` of the CoELA runtime: off is the pinned runtime, on_v1 is the same code with SelfWallMemory.

Contract fixtures only (no model, no physics). Refs #216.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness import coela_runtime
from harness import coela_runtime_self_walls as walls
from harness.coela_modules import Memory as CoelaMemory
from harness.self_wall_memory import SelfWallMemory
from tests.test_coela_runtime import FixtureEnvironment

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "rgb_communication_audit" / "source_manifest.json"
BUNDLE_ID = "coela-self-wall-memory-on-v1"
ROBOTS = ("r1", "r2", "r3")
# The bundle that was in source_manifest.json before the option existed. It must stay exactly as it was.
ORIGINAL_BUNDLE = {
    "audited_git_sha": "120cc821b6a1d5c104aab8c8ef2260cf7f8c9a7b",
    "files_sha256": {
        "harness/camera_policy.py": "b2192e72c9cbf95a41f7c9b665607734e842d0e61c34454f50772809a579edfa",
        "harness/camera_runtime.py": "61f1e75dbb97045cb336441b4e2ac7fb366878501dea664b8610e51065fa1b96",
        "sim/camera_robot_port.py": "182628c96a6e2e6f3d17703173dd96384113c3006a1f91ebc4a2c8b92b0cca35",
        "harness/coela_modules.py": "af8275de470d75ed4037f1be236f6572cde49abc0c597f1c2760795f7ba2706e",
        "harness/coela_runtime.py": "a6fc5afa7d873281c4f008958f946bd9696d30b376a79a611e84b1a7fd8c75e3",
        "sim/mixed_warehouse.py": "66b4f48fd06f24bdf58dd6a1906b9b721b95f02686fefed902e36b1c494239f2",
        "harness/dispatch_plan.py": "eb23b29567a751379e0ea08b6612fa9b1cb6f790ec0d109322916b7b2c0f6407",
        "harness/dispatch_execution.py": "680c594b438613ad30e4f36023ebc4bc10b0927137c250723ceb275302db735b",
        "harness/three_robot_plan.py": "e48c4550425e0479b8ed878c458c6574a496750f41e357b8b1af2e3b3c2bdadd",
        "harness/mixed_warehouse_protocol.py": "21dcce5eb992ddccdb6f68f92cda3df0330ec635c6a1719594ebba96232842f0",
        "harness/mixed_warehouse_runtime.py": "a1e890c0a05621619f414421df859158d9d8afcf3074ff0341d90ab51b5ab93d",
    },
}


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


class WaitingPlanner:
    model_name = "waiting_fixture"
    evidence_kind = "fixture"

    def __init__(self):
        self.seen = []

    def decide(self, context):
        self.seen.append(copy.deepcopy(context))
        return {"decision": {"action": {"kind": "wait"}, "message": None}, "usage": None}


def record(t, view_index=1, r=2.0):
    return {"t_sim": t, "seg": [[r, 0.3, r + 0.2, 0.1, None]], "posture": "other", "load": False, "view_index": view_index}


def episode(runner, **kwargs):
    """One short episode of three waiting planners (one call each). Returns (result, {robot: first planner context}, journal)."""
    planners = {r: WaitingPlanner() for r in ROBOTS}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "episode.jsonl"
        result = runner(FixtureEnvironment(), planners, mode="none", timeout_s=.35, decision_period_s=10.,
                        max_calls_per_robot=3, journal_path=path, **kwargs)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
    return result, {r: planners[r].seen[0] for r in ROBOTS}, rows


def comparable(rows):
    """Journal rows without wall-clock fields, the actor inputs ordered by robot."""
    out = []
    for row in rows:
        if row["event"] == "actor_input":
            out.append({k: v for k, v in row.items() if k != "wall_s"})
    return sorted(out, key=lambda row: row["robot_id"])


class OffIsThePinnedRuntime(unittest.TestCase):
    def test_off_calls_the_pinned_function_with_the_callers_arguments_and_returns_its_result(self):
        calls = []

        def fake(environment, planners, **kwargs):
            calls.append((environment, planners, kwargs))
            return {"sentinel": True}

        env, planners = object(), {"r1": 1}
        with patch.object(coela_runtime, "run_coela_episode", fake):
            for kwargs in ({}, {"self_wall_memory": "off"}):
                result = walls.run_coela_episode(env, planners, mode="natural", timeout_s=3., **kwargs)
                self.assertEqual(result, {"sentinel": True})
        self.assertEqual(len(calls), 2)
        for environment, given, kwargs in calls:
            self.assertIs(environment, env)
            self.assertIs(given, planners)
            self.assertEqual(kwargs, {"mode": "natural", "timeout_s": 3.})      # no extra keyword reaches the pinned runtime

    def test_default_is_off(self):
        self.assertEqual(walls.SELF_WALL_MEMORY_DEFAULT, "off")
        self.assertIsNone(walls.memory_factory())
        self.assertIsNone(walls.memory_factory("off"))

    def test_off_episode_is_the_same_as_the_pinned_episode(self):
        pinned_result, pinned_context, pinned_rows = episode(coela_runtime.run_coela_episode)
        off_result, off_context, off_rows = episode(walls.run_coela_episode)
        off2_result, off2_context, off2_rows = episode(walls.run_coela_episode, self_wall_memory="off")
        self.assertEqual(pinned_result["calls"], {"r1": 1, "r2": 1, "r3": 1})
        for result, context, rows in ((off_result, off_context, off_rows), (off2_result, off2_context, off2_rows)):
            self.assertEqual(result["calls"], pinned_result["calls"])
            self.assertEqual(json.dumps(context, sort_keys=True), json.dumps(pinned_context, sort_keys=True))
            self.assertEqual(json.dumps(comparable(rows), sort_keys=True), json.dumps(comparable(pinned_rows), sort_keys=True))
        text = json.dumps(pinned_context)
        self.assertNotIn("self_walls", text)

    def test_off_keeps_the_pinned_memory_class_and_nothing_global_is_patched(self):
        seen = []

        class Probe(WaitingPlanner):
            def decide(self, context):
                seen.append(coela_runtime.Memory)
                return super().decide(context)

        for option in ("off", "on_v1"):
            planners = {r: Probe() for r in ROBOTS}
            walls.run_coela_episode(FixtureEnvironment(), planners, self_wall_memory=option, mode="none",
                                    timeout_s=.35, decision_period_s=10., max_calls_per_robot=3)
        self.assertTrue(seen)
        self.assertTrue(all(cls is CoelaMemory for cls in seen))           # also while an on_v1 episode was running
        self.assertIs(coela_runtime.Memory, CoelaMemory)

    def test_unknown_option_and_a_source_without_on_v1_are_refused(self):
        with self.assertRaises(ValueError):
            walls.run_coela_episode(FixtureEnvironment(), {}, self_wall_memory="on")
        with self.assertRaises(ValueError):
            walls.run_coela_episode(FixtureEnvironment(), {}, self_walls_source=lambda rid: [])
        with self.assertRaises(ValueError):
            walls.memory_factory("on_v2")


class OnV1UsesSelfWallMemory(unittest.TestCase):
    def test_context_gains_only_the_two_self_wall_keys(self):
        _, pinned_context, _ = episode(coela_runtime.run_coela_episode)
        _, context, _ = episode(walls.run_coela_episode, self_wall_memory="on_v1")
        for rid in ROBOTS:
            memory = dict(context[rid]["memory"])
            self.assertEqual(memory.pop("self_walls"), [])
            self.assertEqual(memory.pop("self_walls_text"), "self_walls: no wall observed yet")
            rest = {**context[rid], "memory": memory}
            self.assertEqual(json.dumps(rest, sort_keys=True), json.dumps(pinned_context[rid], sort_keys=True))

    def test_records_of_each_robots_own_source_reach_its_planner_only(self):
        sources = {"r1": [record(0.0, 1, 2.0)], "r2": [record(0.0, 1, 3.0), record(5.0, 2, 3.5)], "r3": []}
        asked = []

        def source(robot_id):
            asked.append(robot_id)
            return sources[robot_id]

        _, context, rows = episode(walls.run_coela_episode, self_wall_memory="on_v1", self_walls_source=source)
        self.assertEqual({rid: len(context[rid]["memory"]["self_walls"]) for rid in ROBOTS}, {"r1": 1, "r2": 2, "r3": 0})
        self.assertEqual(context["r1"]["memory"]["self_walls"][0]["seg"][0][0], 2.0)
        self.assertIn("3.5m", context["r2"]["memory"]["self_walls_text"])
        self.assertNotIn("3.5m", context["r1"]["memory"]["self_walls_text"])
        self.assertEqual(set(asked), set(ROBOTS))
        # the journaled observation is what the environment returned: the walls travel through the memory only
        for row in rows:
            if row["event"] == "observation":
                self.assertNotIn("self_walls", row["observation"])

    def test_source_from_maps_hands_out_a_copy_of_each_robots_records(self):
        class Map:
            records = [record(0.0)]

        maps = {"r1": Map()}
        source = walls.source_from_maps(maps)
        got = source("r1")
        got.append("x")
        self.assertEqual(len(Map.records), 1)
        self.assertEqual(source("r2"), [])

    def test_on_v1_refuses_to_run_when_a_pinned_source_changed(self):
        env = FixtureEnvironment()
        with patch.dict(walls.PINNED_SOURCES_SHA256, {"harness/coela_runtime.py": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "PINNED_SOURCE_CHANGED"):
                walls.run_coela_episode(env, {r: WaitingPlanner() for r in ROBOTS}, self_wall_memory="on_v1")
            self.assertEqual(env.requests, [])                                  # refused before any request
            episode(walls.run_coela_episode)                                    # off does not care


class RegisteredAsANewBundle(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def test_the_original_bundle_is_untouched(self):
        self.assertEqual(self.manifest["audited_git_sha"], ORIGINAL_BUNDLE["audited_git_sha"])
        self.assertEqual(self.manifest["files_sha256"], ORIGINAL_BUNDLE["files_sha256"])
        for name in ("harness/coela_runtime.py", "harness/coela_modules.py"):       # the files this option leaves alone
            self.assertEqual(sha(name), ORIGINAL_BUNDLE["files_sha256"][name], name)

    def test_the_new_bundle_lists_the_option_files_and_the_unchanged_pinned_files(self):
        bundle = self.manifest["additional_bundles"][BUNDLE_ID]
        self.assertEqual(bundle["option"], {"name": "self_wall_memory", "values": ["off", "on_v1"], "default": "off"})
        self.assertEqual(set(bundle["files_sha256"]), {"harness/coela_runtime_self_walls.py", "harness/self_wall_memory.py"})
        for name, expected in bundle["files_sha256"].items():
            self.assertEqual(sha(name), expected, f"{name}: update the bundle in source_manifest.json")
        self.assertEqual(bundle["pinned_files_used_unchanged_sha256"], walls.PINNED_SOURCES_SHA256)
        self.assertEqual(bundle["pinned_files_used_unchanged_sha256"],
                         {k: ORIGINAL_BUNDLE["files_sha256"][k] for k in walls.PINNED_SOURCES_SHA256})

    def test_the_manifest_has_nothing_else_new(self):
        self.assertEqual(set(self.manifest) - {"audited_git_sha", "files_sha256", "visually_inspected_existing_samples",
                                               "recorded_request_sample"}, {"additional_bundles"})
        self.assertEqual(set(self.manifest["additional_bundles"]), {BUNDLE_ID})


class SourceHookOfSelfWallMemory(unittest.TestCase):
    def obs(self, sim_time=1.0):
        return {"observation_id": "o", "sim_time": sim_time, "cargo": []}

    def test_a_source_needs_the_option(self):
        with self.assertRaises(ValueError):
            SelfWallMemory("r1", self_walls_source=lambda rid: [])

    def test_off_never_calls_the_source_and_on_polls_it_on_every_observe(self):
        calls = []
        memory = SelfWallMemory("r1", self_walls_enabled=True, self_walls_source=lambda rid: calls.append(rid) or [record(1.0)])
        memory.observe(self.obs(), 1.0)
        memory.observe(self.obs(2.0), 2.0)
        self.assertEqual(calls, ["r1", "r1"])
        self.assertEqual(len(memory.self_walls), 1)                              # the same (t_sim, view_index) is one record
        quiet = SelfWallMemory("r1")
        quiet.observe(self.obs(), 1.0)
        self.assertEqual(quiet.self_walls, [])

    def test_a_bad_record_from_the_source_is_loud(self):
        memory = SelfWallMemory("r1", self_walls_enabled=True, self_walls_source=lambda rid: [{"garbage": 1}])
        with self.assertRaisesRegex(ValueError, "INVALID_SELF_WALL_RECORD"):
            memory.observe(self.obs(), 1.0)


if __name__ == "__main__":
    unittest.main()
