"""P1 matched-writer format, reader, repair and provenance coverage (fake only)."""
import json
from dataclasses import replace

import matched_protocol as matched
from episode import run_episode
from limits import Invocation
from plan_parse import PlanParser
from prompt_env1 import OWN_DIALOGUE
from test_chen2d import calls
from test_chen2d_v11 import A, B, C, D, ONE, PATH, TO_B, BAD, HorizonFixtures


class MatchedWriterTests(HorizonFixtures):
    def writer_spec(self, framework="OWN", horizon=5, **options):
        return self.spec(ONE, framework, horizon, protocol="matched", history_method="authors",
                         history_window=1000, **options)

    def test_role_specific_shapes_and_shared_peer_slot_at_h1_and_h5(self):
        states = [ONE]
        for horizon in (1, 5):
            central = matched.build_prompt(2, 2, ONE, [], states, horizon=horizon, history_method="authors",
                                           history_window=1000, state_position="after")
            own = matched.build_prompt(2, 2, ONE, [], states, horizon=horizon, history_method="authors",
                                       history_window=1000, state_position="after", robot=(0, 0))
            group = matched.build_prompt(2, 2, ONE, [], states, horizon=horizon, history_method="authors",
                                         history_window=1000, state_position="after", block=(A, B))
            for prompt in (central, own, group):
                self.assertIn(OWN_DIALOGUE + "{}", prompt)
                self.assertIn(matched.FORMAT, prompt)
            self.assertIn(matched.JOINT_FORMAT, central)
            self.assertIn(matched.JOINT_FORMAT, group)
            self.assertNotIn(matched.OWN_FORMAT, central)
            self.assertIn(matched.OWN_FORMAT, own)
            self.assertNotIn(matched.JOINT_FORMAT, own)
            differences = [lines for lines in zip(central.splitlines(), own.splitlines(), group.splitlines(), strict=True)
                           if len(set(lines)) != 1]
            self.assertEqual(differences, [
                (matched.JOINT_WRITER, matched.OWN_WRITER.format(speaker=A), matched.GROUP_WRITER.format(robots=json.dumps([A, B]))),
                (matched.JOINT_FORMAT, matched.OWN_FORMAT, matched.JOINT_FORMAT)])

    def test_lenient_own_pilot_forms_waits_and_foreign_refusals(self):
        parser = PlanParser()
        pilot = ('[{"Agent[0.5, 0.5]":"move(box_green, target_green)"},'
                 '{"Agent[0.5, 0.5]":null},{"Agent[0.5, 0.5]":null},'
                 '{"Agent[0.5, 0.5]":null},{"Agent[0.5, 0.5]":null}]')
        green = "move(box_green, target_green)"
        self.assertEqual(parser.sequence(pilot, 5, own=True, speaker=A, matched_shape=True),
                         [green, None, None, None, None])
        self.assertEqual(parser.last_shape.form, "self_object_list")
        self.assertEqual(parser.sequence('[{}, {}, {}, {}, {}]', 5, own=True, speaker=A, matched_shape=True),
                         [None] * 5)
        self.assertEqual(parser.last_shape.form, "empty_object_list")
        self.assertEqual(parser.sequence(json.dumps([{A: {}}]), 1, own=True, speaker=A, matched_shape=True), [None])
        self.assertEqual(parser.sequence(json.dumps([TO_B, {A: None}, None, "idle", "{}"]), 5,
                                         own=True, speaker=A, matched_shape=True),
                         [TO_B, None, None, None, None])
        self.assertEqual(parser.last_shape.form, "mixed_list")
        self.assertEqual(parser.sequence("{}", 1, own=True, speaker=A, matched_shape=True), [None])
        self.assertEqual(parser.sequence(json.dumps({A: None}), 1, own=True, speaker=A, matched_shape=True), [None])
        self.assertIsNone(parser.sequence(json.dumps([{B: None}, {A: TO_B}]), 2,
                                          own=True, speaker=A, matched_shape=True))
        self.assertEqual((parser.last_shape.reason, parser.last_shape.detail), ("foreign_agent", B))
        # A foreign key cannot hide after a malformed or too-long own entry.
        self.assertIsNone(parser.sequence(json.dumps([TO_B, "nonsense", {B: None}]), 2,
                                          own=True, speaker=A, matched_shape=True))
        self.assertEqual(parser.last_shape.reason, "foreign_agent")
        self.assertIsNone(parser.sequence(json.dumps([None, {A: None, B: None}]), 2,
                                          own=True, speaker=A, matched_shape=True))
        self.assertEqual((parser.last_shape.reason, parser.last_shape.detail), ("foreign_agent", B))
        self.assertIsNone(parser.sequence(json.dumps([{A: None, B: None}]), 1,
                                          own=True, speaker=A, matched_shape=True))
        self.assertEqual(parser.last_shape.reason, "foreign_agent")
        self.assertEqual(parser.sequence('[{}, {}, {}]', 2, own=True, speaker=A, matched_shape=True), [None, None])
        self.assertIsNone(parser.sequence('42', 1, own=True, speaker=A, matched_shape=True))
        self.assertEqual(parser.last_shape.reason, "not_list")

    def test_strict_requested_shapes_and_group_scope(self):
        own = PlanParser("strict")
        self.assertEqual(own.sequence(json.dumps([TO_B]), 1, own=True, speaker=A, matched_shape=True), [TO_B])
        self.assertIsNone(own.sequence(json.dumps({A: TO_B}), 1, own=True, speaker=A, matched_shape=True))
        self.assertIsNone(own.sequence(json.dumps([TO_B]), 2, own=True, speaker=A, matched_shape=True))
        self.assertEqual(own.last_shape.reason, "wrong_length")
        self.assertIsNone(own.sequence(json.dumps([{B: TO_B}]), 1, own=True, speaker=A, matched_shape=True))
        self.assertEqual(own.last_shape.reason, "foreign_agent")
        self.assertIsNone(own.sequence(json.dumps([{A: TO_B, B: TO_B}]), 1, own=True, speaker=A, matched_shape=True))
        self.assertEqual(own.last_shape.reason, "foreign_agent")
        self.assertIsNone(own.sequence('[{}]', 1, own=True, speaker=A, matched_shape=True))
        self.assertEqual(own.last_shape.reason, "entry_type")

        group = PlanParser("strict")
        self.assertEqual(group.sequence(json.dumps([{}]), 1, agent_positions={(0.5, 0.5)}, matched_shape=True), [{}])
        self.assertIsNone(group.sequence(json.dumps({}), 1, agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertIsNone(group.sequence(json.dumps([{A: TO_B}, {B: TO_B}]), 2,
                                         agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertIsNone(group.sequence(json.dumps([{A: "not an action"}]), 1,
                                         agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertIsNone(group.sequence(json.dumps([{A: TO_B}]), 2,
                                         agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertEqual(group.last_shape.reason, "wrong_length")
        lenient_group = PlanParser()
        self.assertIsNone(lenient_group.sequence('[{}, {}, {}]', 2, agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertEqual(lenient_group.last_shape.reason, "wrong_length")
        self.assertIsNone(lenient_group.sequence('42', 1, agent_positions={(0.5, 0.5)}, matched_shape=True))
        self.assertEqual(lenient_group.last_shape.reason, "not_list")
        self.assertIsNone(PlanParser().sequence(json.dumps({B: [{A: TO_B}]}), 1,
                                                 agent_positions={(0.5, 0.5)}, matched_shape=True))
        lenient = PlanParser()
        self.assertEqual(lenient.sequence("{}", 1, agent_positions={(0.5, 0.5)}, matched_shape=True), [{}])
        self.assertEqual(lenient.last_shape.form, "joint_object_h1")
        self.assertEqual(lenient.sequence('{"plans":[{}]}', 1, agent_positions={(0.5, 0.5)}, matched_shape=True), [{}])
        self.assertEqual(lenient.last_shape.form, "joint_wrapper")
        self.assertEqual(lenient.sequence('{"step 1":{}}', 1, agent_positions={(0.5, 0.5)}, matched_shape=True), [{}])
        self.assertEqual(lenient.last_shape.form, "joint_numbered")

    def test_fake_episode_logs_shape_and_repairs_with_concrete_diagnostics(self):
        own = self.writer_spec(max_env_steps=1)
        pilot = json.dumps([{A: TO_B}, {}, {}, {}, {}])
        row, trace, _ = self.play(own, [pilot, json.dumps([None] * 5), json.dumps([None] * 5), json.dumps([None] * 5)],
                                  "pilot-shape")
        self.assertEqual(row["list_parser_version"], 17)
        self.assertEqual((trace[0]["reply_shape"], trace[0]["reply_shape_accepted"], trace[0]["own_reply_form"]),
                         ("self_object_list", True, "self_object_list"))

        leader = self.writer_spec("CMAS", 1, max_env_steps=1)
        _, trace, _ = self.play(leader, [json.dumps([{A: BAD}]), json.dumps([PATH[0]])], "repair")
        repair = trace[1]["messages"][-1]["content"]
        self.assertIn("not doable now", repair)
        self.assertIn("Doable actions now:", repair)
        self.assertIn("Expected shape:", repair)

    def test_fake_matched_cmas_repair_honors_explicit_horizon_length(self):
        spec = self.writer_spec("CMAS", 5)
        out = self.work / "fake-repair-h5"
        out.mkdir()
        budget = Invocation(out, out / "script.json")
        budget.create(None, 5, "fake")
        run_episode(spec, out, budget.path, "fake", "repair", 300)
        trace = calls(out / "episodes" / spec.name)
        self.assertEqual(len(json.loads(trace[1]["response"])), 5)

    def test_each_refused_own_writer_gets_its_own_reason_and_example(self):
        spec = self.writer_spec(horizon=1, parse_mode="strict", max_planning_rounds=1)
        replies = ["[]", "42", json.dumps([{A: None}]), json.dumps([{}])]
        row, trace, _ = self.play(spec, replies + [json.dumps([TO_B]), "[null]", "[null]", "[null]"], "four-repairs")
        self.assertEqual((row["repair_calls"], row["robots_dropped"]), (4, 0))
        for call, reason, example in zip(trace[4:],
                ("Wrong list length (expected 1, got 0)", "not a JSON list", f'Unknown agent named "{A}"', "entry 1"),
                (["move(box_red, square[1.5, 0.5])"], [None], [None], [None]), strict=True):
            repair = call["messages"][-1]["content"]
            self.assertIn(reason, repair)
            self.assertIn("Expected shape: " + json.dumps(example), repair)

    def test_joint_wrapper_diagnostics_keep_role_scope_and_actual_length(self):
        parser = PlanParser()
        allowed = {(0.5, 0.5), (0.5, 1.5)}
        for reply, reason, detail in (
                (json.dumps({C: [{A: TO_B}]}), "foreign_agent", C),
                ('{"plans":[{},{},{}]}', "wrong_length", "expected 1 to 2, got 3"),
                ('{"1":{}, "step 1":{}}', "duplicate_step", "A step number appears more than once."),
                ('[{}, null]', "entry_type", "Entry 2 must be a joint object.")):
            with self.subTest(reply=reply):
                self.assertIsNone(parser.sequence(reply, 2, agent_positions=allowed, matched_shape=True))
                self.assertEqual((parser.last_shape.reason, parser.last_shape.detail), (reason, detail))
