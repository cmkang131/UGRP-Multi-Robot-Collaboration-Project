"""Offline integration coverage for the opt-in matched CMAS/OWN protocol."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

import matched_protocol as matched
from LLM import MODEL
from episode import run_episode
from limits import Invocation
from planning_metrics import (MATCHED_CALL_CAP, MATCHED_ENV_CAP, MATCHED_ROUND_CAP,
                              matched_cell_metrics)
from storage import read_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import BOARD, DELIVER, scripted_transport
from test_chen2d_v5 import local_references
from test_chen2d_v11 import A, B, C, D, BAD, ONE, PATH, TO_B, HorizonFixtures


ROBOTS = (A, B, C, D)


def own_round(plan, horizon=1):
    return [json.dumps([plan.get(robot)] + [None] * (horizon - 1)) for robot in ROBOTS]


class MatchedTests(HorizonFixtures):
    def matched(self, board=ONE, framework="CMAS", horizon=1, **options):
        return self.spec(board, framework, horizon, protocol="matched", history_method="authors",
                         history_window=1000, **options)

    def test_scaled_normal_entrypoint_cmas_and_own_h1_h5_both_state_orders(self):
        """The actual episode path accepts P0 metadata and both shared layouts."""
        for framework in ("CMAS", "OWN"):
            for horizon in (1, 5):
                for position in ("before", "after"):
                    with self.subTest(framework=framework, horizon=horizon, position=position):
                        spec = replace(self.matched(framework=framework, horizon=horizon, state_position=position),
                                       map_set="scaled:1", boxes_per_robot=1.0, box_count=1)
                        if framework == "CMAS":
                            replies = [json.dumps(step) for step in PATH] if horizon == 1 else [json.dumps(PATH)]
                        elif horizon == 1:
                            replies = sum((own_round(step) for step in PATH), [])
                        else:
                            replies = [json.dumps([step.get(robot) for step in PATH] + [None] * (horizon - len(PATH)))
                                       for robot in ROBOTS]
                        row, trace, _ = self.play(spec, replies, f"{framework}-{horizon}-{position}")
                        self.assertTrue(row["strict_success"])
                        self.assertEqual((row["map_set"], row["boxes_per_robot"], row["box_count"]),
                                         ("scaled:1", 1.0, 1))
                        self.assertEqual(row["state_position_effective"], position)
                        self.assertTrue(all(matched.GOAL in call["messages"][1]["content"] and
                                            matched.FORMAT in call["messages"][1]["content"] for call in trace))

    def test_last_authorized_repair_is_checked_for_leader_and_own_writer(self):
        leader = self.matched(max_env_steps=1)
        row, trace, _ = self.play(leader, [json.dumps([{A: BAD}]), json.dumps([{A: BAD}]), json.dumps([{A: TO_B}])], "leader-repair")
        batch, = row["round_log"]
        self.assertEqual((batch["repair_calls"], batch["checks"][-1]["status"], row["robots_dropped"]), (2, "valid", 0))
        self.assertTrue(trace[-1]["messages"][-1]["content"].endswith(matched.REPAIR_INSTRUCTION))

        own = self.matched(framework="OWN", max_env_steps=1)
        replies = [json.dumps([BAD]), json.dumps([None]), json.dumps([None]), json.dumps([None]),
                   json.dumps([BAD]), json.dumps([TO_B])]
        row, trace, _ = self.play(own, replies, "own-repair")
        batch, = row["round_log"]
        self.assertEqual((batch["repair_calls"], batch["checks"][-1]["status"], batch["dropped_robots"]),
                         (2, "valid", []))
        self.assertTrue(trace[-1]["messages"][-1]["content"].endswith(matched.REPAIR_INSTRUCTION))

    def test_invalid_own_writer_is_dropped_after_equal_repair_budget(self):
        spec = self.matched(framework="OWN", max_planning_rounds=1)
        replies = [json.dumps([BAD]), json.dumps([None]), json.dumps([None]), json.dumps([None]),
                   json.dumps([BAD]), json.dumps([BAD])]
        row, _, _ = self.play(spec, replies, "own-drop")
        batch, = row["round_log"]
        self.assertEqual((batch["repair_calls"], batch["dropped_robots"], row["robots_dropped"]), (2, [A], 1))
        self.assertEqual(row["first_blocked_cause"], "not-doable actions")

    def real_episode(self, kinds, tag):
        spec = self.matched(BOARD, max_env_steps=1, max_planning_rounds=2)
        out = self.work / tag
        out.mkdir()
        budget = Invocation(out, out / "meter.json")
        budget.create(None, 5, MODEL)
        with local_references(), scripted_transport(kinds):
            run_episode(spec, out, budget.path, MODEL, "correct", 300, 128, 0., .7)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder)

    def test_per_attempt_raw_finish_recovery_all_cut_and_unknown_class(self):
        good, trace = self.real_episode(["ok"], "real-good")
        self.assertEqual((good["rounds_no_cutoff"], trace[0]["attempts"][0]["finish_reason"],
                          trace[0]["attempts"][0]["raw_output"]), (1, "stop", DELIVER))
        recovered, trace = self.real_episode(["truncated", "ok"], "real-recovered")
        self.assertEqual((recovered["rounds_cutoff_recovered"], [a["cut_off"] for a in trace[0]["attempts"]]),
                         (1, [True, False]))
        exhausted, trace = self.real_episode(["truncated"] * 3, "real-exhausted")
        self.assertEqual((exhausted["rounds_all_attempts_cutoff"], exhausted["success_failure"],
                          [a["finish_reason"] for a in trace[0]["attempts"]]), (1, "failure output limit", ["length"] * 3))
        # Missing raw cut-off evidence is deliberately classified unknown, never as a recovered success.
        trace[0]["attempts"][0].pop("cut_off")
        from planning_metrics import round_cutoff
        self.assertEqual(round_cutoff(trace), "unknown")

    def test_environment_round_and_call_ceilings_and_exact_completion_caps(self):
        cases = (("environment", self.matched(max_env_steps=0), [], 300, MATCHED_ENV_CAP),
                 ("round", self.matched(max_planning_rounds=0), [], 300, MATCHED_ROUND_CAP),
                 ("call", self.matched(), [], 0, MATCHED_CALL_CAP))
        for name, spec, replies, ceiling, label in cases:
            with self.subTest(name=name):
                row, _, _ = self.play(spec, replies, name, ceiling=ceiling)
                self.assertEqual(row["success_failure"], label)
        exact = self.matched(max_env_steps=3, max_planning_rounds=3)
        row, _, _ = self.play(exact, [json.dumps(step) for step in PATH], "exact", ceiling=3)
        self.assertTrue(row["strict_success"])
        self.assertEqual((row["steps"], row["planning_rounds"], row["api_calls"]), (3, 3, 3))

    def test_32_robot_own_h1_gets_one_complete_round_at_exact_call_cap(self):
        board = {f"{i + .5}_{j + .5}": [] for i in range(4) for j in range(8)}
        board["0.5_0.5"] = ["box_red", "target_red"]
        base = fixture_spec(self.work / "big-board.json", board, "static", rows=4, cols=8)
        spec = replace(base, framework="OWN", protocol="matched", horizon=1, max_env_steps=1,
                       max_planning_rounds=1, history_method="authors", history_window=1000)
        replies = [json.dumps(["move(box_red, target_red)"])] + [json.dumps([None])] * 31
        row, trace, _ = self.play(spec, replies, "own32", ceiling=32)
        self.assertTrue(row["strict_success"])
        self.assertEqual((row["api_calls"], len(trace), row["planning_rounds"]), (32, 32, 1))

    def test_first_blocked_is_retained_before_later_completion_and_zero_completion_ratios(self):
        spec = self.matched(max_env_steps=3, max_planning_rounds=4)
        row, _, _ = self.play(spec, ["[{}]"] + [json.dumps(step) for step in PATH], "blocked-then-complete")
        self.assertTrue(row["strict_success"])
        self.assertEqual((row["first_blocked_round"], row["first_blocked_cause"]), (1, "no actions proposed"))
        no_completion = dict(row, strict_success=False, finished=True, api_calls=4, prompt_tokens=20, completion_tokens=8)
        metrics = matched_cell_metrics([no_completion])
        self.assertEqual((metrics["calls_per_strict_completion"], metrics["prompt_tokens_per_strict_completion"],
                          metrics["generated_tokens_per_strict_completion"]), ("no completion",) * 3)


if __name__ == "__main__":
    unittest.main()
