from regression_inputs import REGRESSION
"""Task 14 regression tests at the fake-model call and episode boundaries."""
import json
import sys
import unittest
from collections import Counter
from dataclasses import replace
from unittest.mock import patch

import fake_model
from episode import Spec, run_episode
from limits import CALL_LIMIT, Invocation
from map_events import agent_at, cell_key
from output_demand import measure_episode, selected_sequence
from plan_parse import PlanParser
from planning_metrics import DMAS_RETENTIONS, comparison_metrics, repair_feedback
from prompt_env1 import OWN_DIALOGUE
from relay import HEADER, STATE_HEADERS
from storage import ROOT, read_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v2 import enrolled_spec
from test_chen2d_v4 import cli
from test_chen2d_v5 import local_references
from test_chen2d_v11 import A, B, C, D, BAD, GREEN_TO_D, ONE, PATH, RED, TO_B, TWO, HorizonFixtures
from test_chen2d_v13 import PURPLE_AGENT, PURPLE_MOVE


def peer_block(message):
    text = message["content"].rsplit(OWN_DIALOGUE, 1)[1]
    return json.JSONDecoder().raw_decode(text)[0]


def execute(plans):
    return "EXECUTE\n" + json.dumps(plans)


class JointReplyTests(HorizonFixtures):
    def test_step_number_objects_in_numeric_order_for_both_frameworks(self):
        plans = [*PATH[:2], *([{}] * 7), PATH[2]]
        for fw in ("CMAS", "DMAS"):
            for prefix in ("", "step "):
                with self.subTest(fw=fw, prefix=prefix):
                    # The review quotes the numbered-object shape. Put step 10 before step 2 on the wire.
                    raw = json.dumps({f"{prefix}{i}": plans[i-1] for i in range(10, 0, -1)})
                    replies = [raw] if fw == "CMAS" else ["PROCEED"] * 3 + ["EXECUTE\n" + raw]
                    row, _, _ = self.play(self.spec(ONE, fw, 10), replies, fw + prefix)
                    self.assertEqual(row["round_log"][0]["proposed_plans"], plans)
                    self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
                    self.assertEqual((row["strict_success"], row["lenient_rescues"], row["empty_steps_skipped"]),
                                     (True, 1, 7))
        row, trace, _ = self.play(self.spec(ONE, parse_mode="strict"),
                                  [json.dumps({"1": PATH[0]}), json.dumps(PATH)], "strict")
        self.assertEqual((row["round_log"][0]["checks"][0]["status"], len(trace)), ("parse failure", 2))

    def test_unknown_joint_keys_are_format_errors_including_later_steps(self):
        cases = [{"Robot7": TO_B}, [PATH[0], {"note": "pass"}], {"step 1": {"Agent[9.5, 0.5]": TO_B}}]
        for fw in ("CMAS", "DMAS"):
            for i, (value, key) in enumerate(zip(cases, ("Robot7", "note", "Agent[9.5, 0.5]"))):
                raw = json.dumps(value)
                initial = [raw] if fw == "CMAS" else ["PROCEED"] * 3 + ["EXECUTE\n" + raw]
                row, trace, _ = self.play(self.spec(ONE, fw), initial + [json.dumps(PATH)], fw + str(i))
                first, repaired = row["round_log"][0]["checks"]
                self.assertEqual((first["status"], first["rejected_actions"], repaired["status"]),
                                 ("parse failure", {}, "valid"))
                feedback = repair_feedback(trace[-1])
                self.assertIn(f'"{key}" is not an agent name', feedback)
                self.assertNotIn("doable action list", feedback)
                self.assertEqual((row["strict_success"], row["planning_rounds"]), (True, 1))

    def test_archived_demand_uses_the_plan_extracted_by_that_protocol(self):
        parser = PlanParser()
        joint = dict(role="central", response=json.dumps({"1": PATH[0], "2": PATH[1]}))
        self.assertEqual(selected_sequence(joint, parser, 2, prior_shapes=True)[0], 0)
        self.assertEqual(selected_sequence(joint, parser, 2)[0], 2)
        own = dict(role="own", speaker=A, own_reply_form="fenced",
                   response='Draft ["wait", null], then ' + json.dumps([RED, None]))
        self.assertEqual(selected_sequence(own, parser, 2, prior_shapes=True)[0], 1)
        self.assertEqual(selected_sequence(own, parser, 2)[0], 0)

    def test_dmas_keeps_earlier_writer_after_execute_without_a_plan(self):
        for mode in ("lenient", "strict"):
            row, trace, _ = self.play(self.spec(ONE, "DMAS", parse_mode=mode),
                                      [execute(PATH), "We agree. EXECUTE"], mode)
            batch, = row["round_log"]
            self.assertEqual((batch["final_speaker"], batch["final_call"], batch["final_submission_call"]), (A, 1, 1))
            self.assertEqual([it["issued_plan"] for it in row["iterations"]], PATH)
            self.assertEqual([c["status"] for c in batch["checks"]], ["valid", "parse failure"])
            self.assertEqual([c["speaker"] for c in trace], [A, C])
            for record in (batch, row, comparison_metrics([row])):
                self.assertEqual([record[k] for k in DMAS_RETENTIONS], [1, 0])

    def test_dmas_keeps_nonempty_plan_after_reviewed_empty_replies(self):
        for i, raw in enumerate(("EXECUTE\n[{}]", "EXECUTE\n[{}, {}, {}, {}, {}]", "EXECUTE\n[]")):
            row, _, _ = self.play(self.spec(ONE, "DMAS", 5), [execute([{}, *PATH]), raw], str(i))
            batch, = row["round_log"]
            self.assertEqual((batch["final_speaker"], batch["proposed_plans"], row["strict_success"]), (A, [{}, *PATH], True))
            for record in (batch, row, comparison_metrics([row])):
                self.assertEqual([record[k] for k in DMAS_RETENTIONS], [0, 1])
        # With no nonempty plan this round, an empty list of plans remains eligible.
        with patch("episode.step_limit", return_value=2):
            row, _, _ = self.play(self.spec(ONE, "DMAS"), [execute(PATH[:1]), execute([{}]),
                                  execute([{}]), execute([{}, {}])], "reset")
        self.assertEqual([r["final_speaker"] for r in row["round_log"]], [A, C])
        self.assertEqual([r["dmas_empty_overwrites_prevented"] for r in row["round_log"]], [1, 0])
        self.assertEqual(row["round_log"][1]["stop_reason"], "all empty")

    def test_dmas_repairs_the_retained_parsable_writer(self):
        row, trace, _ = self.play(self.spec(ONE, "DMAS"), [execute([{A: BAD}]), "EXECUTE", json.dumps(PATH)])
        self.assertEqual([c["speaker"] for c in trace], [A, C, A])
        self.assertEqual(trace[-1]["messages"][1], trace[0]["messages"][1])
        batch, = row["round_log"]
        self.assertEqual((batch["final_submission_call"], batch["final_call"], row["strict_success"]), (1, 3, True))

    def test_dmas_retained_proposal_and_counts_survive_an_interrupted_sweep(self):
        spec = self.spec(ONE, "DMAS")
        path = self.work / "episodes" / spec.name / "episode.json"
        for tag, cap, reply in (("first", 1, execute(PATH)), ("resume", None, "EXECUTE")):
            budget = Invocation(self.work, self.work / (tag + ".json"))
            budget.create(cap, 5, "fake")
            with patch("fake_model.reply", side_effect=[reply]):
                run_episode(spec, self.work, budget.path, "fake", "correct", 300)
            self.assertEqual(read_json(budget.path)["calls"], 1)
            row = read_json(path)
            batch, = row["round_log"]
            self.assertEqual((batch["final_call"], batch["proposed_plans"]), (1, PATH))
            if cap:
                self.assertEqual((row["success_failure"], row["steps"], row[DMAS_RETENTIONS[0]]), (CALL_LIMIT, 0, 0))
            else:
                self.assertEqual((row["strict_success"], row["steps"], row[DMAS_RETENTIONS[0]]), (True, 3, 1))


class OwnRulesTests(HorizonFixtures):
    def own_case(self, raw, horizon, tag, *, strict=False):
        h = horizon
        idle = json.dumps([None] * h)
        replies = [raw, json.dumps([GREEN_TO_D] + [None] * (h - 1))]
        if h > 1:
            replies.extend([idle, idle])
        if strict:
            replies.append(idle)
        spec = self.spec(TWO, "OWN", h, max_env_steps=1, parse_mode="strict" if strict else "lenient")
        return self.play(spec, replies, tag)

    def test_wait_spellings_bare_null_and_empty_list(self):
        forms = ('["null", "null", "null", "null", "null"]', '["None", "none", "", "wait", null]',
                 "null", "[]", '"wait"')
        for index, raw in enumerate(forms):
            for strict in (False, True):
                with self.subTest(raw=raw, strict=strict):
                    row, trace, folder = self.own_case(raw, 5, f"{index}-{strict}", strict=strict)
                    self.assertEqual(row["round_log"][0]["checks"][0]["status"], "parse failure" if strict else "valid")
                    self.assertEqual(len(trace), 4 + int(strict))
                    self.assertEqual(read_json(folder / "dialogue_history/dialogue_history0.txt")[A], [None] * 5)

    def test_action_objects_whitespace_single_quotes_and_trailing_commas(self):
        cases = [('[{"action": "move(box_red, target_red)"}, null]', RED),
                 ('[" move(  box_red ,   target_red  ) ", null]', RED),
                 ('["move(box_red,target_red)", null]', RED),
                 ("['move(box_red, target_red)', null]", RED),
                 ('["move(box_red, target_red)", null,]', RED),
                 ("\u0060\u0060\u0060python\n[{'action':'move( box_red , square[ 0.5,1.5 ] )',}, 'None',]\n\u0060\u0060\u0060", TO_B)]
        for i, (raw, expected) in enumerate(cases):
            with self.subTest(raw=raw):
                for strict in (False, True):
                    row, trace, folder = self.own_case(raw, 2, f"{i}-{strict}", strict=strict)
                    self.assertEqual(trace[0]["lenient_rescue"], not strict)
                    self.assertEqual(row["round_log"][0]["checks"][0]["status"], "parse failure" if strict else "valid")
                    self.assertEqual(read_json(folder / "dialogue_history/dialogue_history0.txt")[A],
                                     [None if strict else expected, None])

    def test_keep_only_the_prefix_before_a_malformed_later_entry(self):
        cases = [(json.dumps([RED, "unusable", RED, None, RED]), 2),
                 (json.dumps([RED, None, {B: TO_B}, None, RED]), 3),
                 (json.dumps([RED, None, None, None, 17]), 5),
                 (json.dumps([[RED], None]), 2),
                 ('["move(box_red, target_red)", ???, "move(box_red, target_red)"]', 2)]
        for i, (raw, position) in enumerate(cases):
            row, trace, folder = self.own_case(raw, 5, str(i))
            self.assertEqual((trace[0]["response"], trace[0]["own_reply_invalid_position"]), (raw, position))
            measured, _ = measure_episode(folder.parents[1], dict(row, reasoning_setting="default"), Counter())
            self.assertEqual(measured[0]["own_reply_invalid_position"], position)
            self.assertEqual((row["own_prefixes_kept"], row["own_robots_dropped"], row["api_calls"]), (1, 0, 4))
            self.assertEqual(read_json(folder / "dialogue_history/dialogue_history0.txt")[A], [RED, None, None, None, None])
            self.assertEqual(row["iterations"][0]["action_calls"][A], 1)
        raw = json.dumps(["unusable", RED, None, None, None])
        row, trace, _ = self.play(self.spec(TWO, "OWN", 5, max_env_steps=1),
                                  [raw, "null", "null", "null", json.dumps([RED])], "bad-first")
        self.assertEqual((trace[0]["own_reply_form"], row["own_prefixes_kept"], len(trace)), (None, 0, 5))

    def test_reviewed_purple_nested_and_self_keyed_moves_already_worked_in_task13(self):
        folder = REGRESSION / "chen2d-13/registered-map"
        saved = read_json(folder / "episodes/4x4_OWN_static_env0/episode.json")
        config = read_json(folder / "run.json")
        spec = Spec(4, 4, "OWN", "static", 0, folder / "maps/4x4/env0.json", saved["env_sha256"],
                    saved["event_sha256"], dropoff=config["dropoff"], max_env_steps=1)
        for label, raw in (("nested", '[["move(box_purple, square[0.5, 2.5])"]]'),
                           ("self_dict", '{"Agent[0.5, 3.5]": ["move(box_purple, square[0.5, 2.5])"]}')):
            row, trace, _ = self.play(spec, [raw] + ["[null]"] * 7, label)
            self.assertEqual((trace[0]["speaker"], trace[0]["own_reply_form"]), (PURPLE_AGENT, label))
            self.assertEqual((row["iterations"][0]["issued_plan"], row["api_calls"]), ({PURPLE_AGENT: PURPLE_MOVE}, 8))
            self.assertIn("box_purple", row["final_state"]["0.5_2.5"])

    def test_seven_robots_each_receive_two_repairs_and_two_remain_dropped(self):
        squares = [(i+.5, j+.5) for i in range(4) for j in range(4)]
        robots = list(map(agent_at, squares))
        board = {cell_key(p): ["box_red", "target_red"] if i < 8 else [] for i, p in enumerate(squares)}
        spec = replace(fixture_spec(self.work / "many.json", board, "static", 4, 4),
                       framework="OWN", horizon=5, max_env_steps=1)
        replies = ["unreadable"] * 7 + [json.dumps([RED])] + ["[]"] * 8
        replies += ["unreadable"] * 7 + [json.dumps([RED])] * 5 + ["unreadable"] * 2
        row, trace, _ = self.play(spec, replies)
        checks = row["round_log"][0]["checks"]
        self.assertEqual(Counter(c["speaker"] for c in checks if c["repair"]), {r: 2 for r in robots[:7]})
        self.assertEqual((row["api_calls"], row["own_robots_dropped"], row["round_log"][0]["own_robots_dropped"]),
                         (30, 2, 2))
        self.assertEqual(row["iterations"][0]["issued_plan"], {r: RED for r in [*robots[:5], robots[7]]})
        self.assertEqual(len(trace), 30)

    def test_unreachable_idle_robots_skip_repair_but_distance_h_is_eligible(self):
        squares = [(i+.5, j+.5) for i in range(4) for j in range(4)]
        board = {cell_key(p): [] for p in squares}
        board["0.5_0.5"] = ["box_red", "target_red"]
        spec = replace(fixture_spec(self.work / "reach.json", board, "static", 4, 4), framework="OWN", horizon=2)
        replies = ["[]"] * 16
        replies[0], replies[2] = json.dumps([RED]), "unclear"   # distance 2
        replies[3], replies[15] = "unclear", json.dumps([BAD])  # distances 3 and 6
        row, trace, folder = self.play(spec, replies + ["[null, null]"])
        self.assertEqual([c["speaker"] for c in trace[16:]], [agent_at(squares[2])])
        self.assertEqual((row["strict_success"], row["own_unreachable_skipped"], row["own_robots_dropped"]),
                         (True, 2, 0))
        peers = read_json(folder / "dialogue_history/dialogue_history0.txt")
        self.assertEqual(peers[agent_at(squares[2])], [None, None])
        self.assertTrue(all(peers[agent_at(squares[i])] is None for i in (3, 15)))

    def test_one_concrete_own_example_of_the_requested_length(self):
        for h in (1, 2, 5):
            row, trace, _ = self.own_case(json.dumps([RED] * h), h, str(h))
            prompt = trace[0]["messages"][1]["content"]
            examples = [line.removeprefix("Example#1: ") for line in prompt.splitlines() if line.startswith("Example")]
            self.assertEqual(len(examples), 1)
            self.assertEqual(json.loads(examples[0]), ["move(box_blue, square[0.5, 1.5])"] + [None] * (h-1))
            self.assertIn("unquoted JSON literal", prompt)
            self.assertEqual(row["api_calls"], len(trace))

    def test_refused_and_dropped_lists_display_as_null_and_repairs_reuse_the_first_view(self):
        idle = "[null, null]"
        replies = [json.dumps([BAD, TO_B]), "I have nothing to move.", idle, idle,
                   json.dumps([RED, None]), "unreadable", "unreadable"]
        row, trace, folder = self.play(self.spec(TWO, "OWN", 2, max_env_steps=1), replies)
        views = [{}, {A: None}, {A: None, B: None}, {A: None, B: None, C: [None, None]}]
        self.assertEqual([peer_block(c["messages"][1]) for c in trace[:4]], views)
        for c in trace[4:]:
            index = 0 if c["speaker"] == A else 1
            self.assertEqual(c["messages"][1], trace[index]["messages"][1])
            self.assertEqual(peer_block(c["messages"][-1]), views[index])
        self.assertEqual(read_json(folder / "dialogue_history/dialogue_history0.txt"),
                         {A: [RED, None], B: None, C: [None, None], D: [None, None]})
        self.assertEqual((row["own_robots_dropped"], row["iterations"][0]["action_calls"]), (1, {A: 5}))


class PromptReplayTests(HorizonFixtures):
    def test_relay_skips_a_state_heading_quoted_in_earlier_dialogue(self):
        original = fake_model.reply
        marker = STATE_HEADERS["local"]
        def quote_heading(messages, script):
            reply = original(messages, script)
            if reply.startswith("EXECUTE") and "State1:" not in messages[1]["content"]:
                return "Quoted for discussion: " + marker + "\n" + reply
            return reply

        spec = enrolled_spec("DMAS", "e1", speech="auto", dropoff="always", tell="all",
                             relay_display="once", event_step_override=1, history_method="dialogue",
                             history_window=100000, state_position="after")
        row, trace, _ = self.play(spec, quote_heading)
        call = next(c for c in trace if c["told"])
        prompt = call["messages"][1]["content"]
        history, notice, current = prompt.partition("Change of orders (announced")
        self.assertTrue(notice)
        self.assertIn("Quoted for discussion: " + marker, history)
        self.assertNotIn(HEADER, history)
        relay = current.split("\n" + HEADER)[1]
        delivery = relay.split(marker + " {" + call["speaker"] + ": in square")[0]
        self.assertEqual(len(delivery.splitlines()), 3)
        self.assertTrue(row["iterations"][1]["plan_maker_message_block"])

    def test_event_announcement_and_relay_follow_history_in_e1_and_e2(self):
        for fw in ("DMAS", "OWN"):
            for h in (1, 5):
                for condition in ("e1", "e2"):
                    with self.subTest(fw=fw, h=h, condition=condition):
                        spec = enrolled_spec(fw, condition, dropoff="always", speech="auto", tell="all",
                                             horizon=h, history_window=100000, state_position="after")
                        row, trace, _ = self.play(spec, fake_model.reply, f"{fw}-{h}-{condition}")
                        self.assertTrue(row["event_fired"])
                        addressed = [c for c in trace if c["told"] and c["role"] in ("own", "dialogue")]
                        self.assertTrue(addressed)
                        for c in addressed:
                            prompt = c["messages"][1]["content"]
                            before, heading, _ = prompt.partition(STATE_HEADERS["local"])
                            self.assertTrue(heading)
                            history, notice, delivery = before.partition("Change of orders (announced")
                            self.assertIn("The previous state and action pairs at each step are:", history)
                            self.assertIn("Action1:", history)
                            self.assertTrue(notice)
                            _, relay, lines = delivery.partition("\n" + HEADER)
                            self.assertTrue(relay)
                            self.assertEqual(len(lines.splitlines()), 3)
                            self.assertTrue(all(line.startswith("[Agent[") for line in lines.splitlines()))
                            self.assertTrue(lines.endswith("\n"))

    def test_all_static_after_prompts_match_the_task12_archive_byte_for_byte(self):
        archive = REGRESSION / "chen2d-12/fake-order-after"
        out = self.work / "after"
        process = cli("run_chen2d.py", "--model", "fake", "--frameworks", "DMAS", "--sizes", "4x4,4x8",
                      "--conditions", "static", "--dropoff", "event", "--envs", "0,1,2,3", "--state-position", "after",
                      "--history-window", 100000, "--max-output-tokens", 8192, "--out", out)
        self.assertEqual(process.returncode, 0, process.stderr)
        originals = sorted((archive / "episodes").iterdir())
        self.assertEqual([p.name for p in originals], sorted(p.name for p in (out / "episodes").iterdir()))
        total_calls = total_saved = 0
        for old in originals:
            new = out / "episodes" / old.name
            previous, current = calls(old), calls(new)
            self.assertEqual(len(previous), len(current))
            for a, b in zip(previous, current):
                self.assertEqual(a["messages"][1]["content"].encode(), b["messages"][1]["content"].encode())
            total_calls += len(previous)
            names = sorted(p.name for p in (old / "prompt").iterdir())
            self.assertEqual(names, sorted(p.name for p in (new / "prompt").iterdir()))
            for name in names:
                self.assertEqual((old / "prompt" / name).read_bytes(), (new / "prompt" / name).read_bytes())
            total_saved += len(names)
        self.assertEqual((len(originals), total_calls, total_saved), (8, 328, 82))


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 15))]
    with local_references():
        print("Folder-local references, fake replies and scripted transports. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
