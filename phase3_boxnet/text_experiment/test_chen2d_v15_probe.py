"""P1/P1b/P2 offline checks for ``probe_reading`` (no provider calls)."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from regression_inputs import REGRESSION

from env1_create import state_update_func, state_update_func_local_agent
from probe_reading import (CALLERS, HISTORY_SLOT, SavedState, build_prompt, evenly_spread_steps,
                           judge_reply, select_saved_states)
from probe_wording import LEADER_EXAMPLE, strip_nonstructural_style, style_spans
from prompt_env1 import input_prompt_1_func_total, input_prompt_local_agent_DMAS_dialogue_func


HERE = Path(__file__).resolve().parent
SOURCE = REGRESSION / "chen2d-10/fake-static/episodes/2x2_CMAS_static_env0"


class ReadingProbeTests(unittest.TestCase):
    def saved(self, count=3):
        return select_saved_states([SOURCE], count)

    def test_selection_is_even_deterministic_and_caller_independent(self):
        self.assertEqual(evenly_spread_steps(2, 9, 3), [2, 6, 9])
        first, second = self.saved(), self.saved()
        self.assertEqual([(s.state_id, s.step) for s in first], [(s.state_id, s.step) for s in second])
        self.assertEqual(len(first), 3)
        self.assertEqual(first[0].step, 2)
        self.assertEqual(first[-1].step, first[-1].record["steps"])

    def test_history_content_is_shared_and_only_reading_layout_changes(self):
        saved = self.saved()[1]
        pairs = [f"State{n}: {saved.states[n-1]}\nAction{n}: {saved.responses[n-1]}\n\n"
                 for n in range(1, saved.step)]
        for protocol in ("authors", "matched"):
            for caller in CALLERS:
                for strip in (False, True):
                    with self.subTest(protocol=protocol, caller=caller, strip=strip):
                        def render(arm):
                            return build_prompt(saved, caller, arm, 5, protocol=protocol, strip_style=strip)[0]
                        base, last, after = render("none"), render("last1"), render("all_after")
                        self.assertEqual(last.replace(pairs[-1], ""), base)
                        self.assertEqual(after.replace("".join(pairs), ""), base)
                        self.assertIn("".join(pairs), render("all_before"))

    def test_native_templates_and_exact_leader_block_transposition(self):
        saved = self.saved()[1]
        method = "_w_only_state_action_history"
        states, responses = list(saved.states), list(saved.responses)
        past = [""] * len(responses)
        for h in (1, 5):
            leader, _ = build_prompt(saved, "leader", "all_after", h)
            expected = input_prompt_1_func_total(state_update_func(saved.rows, saved.cols, saved.state),
                responses, states, past, method, "CMAS", history_window=10**9, cmas_history=True, horizon=h)
            self.assertEqual(leader.encode(), expected.encode())
            a, b, c = leader.index(HISTORY_SLOT), leader.index("Hence, the current state"), leader.index(LEADER_EXAMPLE)
            before, _ = build_prompt(saved, "leader", "all_before", h)
            self.assertEqual(before, leader[:a] + leader[b:c] + leader[a:b] + leader[c:])
            for arm, position in (("all_after", "after"), ("all_before", "before")):
                own, meta = build_prompt(saved, "own_last", arm, h)
                row, col = map(float, meta["robot"][6:-1].split(", "))
                local, other = state_update_func_local_agent(saved.rows, saved.cols, int(row), int(col), saved.state)
                expected = input_prompt_local_agent_DMAS_dialogue_func(local, other, json.dumps(meta["peer_lists"]),
                    responses, states, past, method, history_window=10**9, own_horizon=h, horizon=h, state_position=position)
                self.assertEqual(own.encode(), expected.encode())

    def test_own_first_and_last_differ_only_in_peer_lists(self):
        saved = self.saved()[1]
        first, first_meta = build_prompt(saved, "own_first", "last1")
        last, last_meta = build_prompt(saved, "own_last", "last1")
        self.assertEqual(first_meta["robot"], last_meta["robot"])
        self.assertEqual(first_meta["peer_lists"], {})
        self.assertTrue(last_meta["peer_lists"])
        marker = "Earlier robots' lists in this planning round: "
        prefix_a, value_a = first.rsplit(marker, 1)
        prefix_b, value_b = last.rsplit(marker, 1)
        self.assertEqual(prefix_a, prefix_b)
        tail_a = value_a[value_a.index("\n"):]
        tail_b = value_b[value_b.index("\n"):]
        self.assertEqual(tail_a, tail_b)

    def test_style_strip_removes_only_inventory_and_keeps_board(self):
        saved = self.saved()[0]
        for caller in CALLERS:
            prompt, _ = build_prompt(saved, caller, "last1")
            stripped = strip_nonstructural_style(prompt, caller)
            self.assertNotIn("Think step-by-step", prompt)
            self.assertNotIn("Respond very concisely", prompt)
            self.assertEqual(len(prompt) - len(stripped), sum(len(s) for spans in style_spans(caller, 1) for s in spans))
            self.assertIn("I can observe", stripped)
        own, _ = build_prompt(saved, "own_last", "last1")
        self.assertNotIn("Output only a JSON list", strip_nonstructural_style(own, "own_last"))
        self.assertIn("Output a JSON list of 1 entries", strip_nonstructural_style(own, "own_last"))

    def test_judge_flags_stale_action_and_peer_box_conflict(self):
        # The selected caller is the right square: it can move blue now, but
        # red was at that square in the previous state and an earlier peer has
        # just claimed red.  Its proposed red action is both stale and invalid.
        previous = {"0.5_0.5": ["target_red"], "0.5_1.5": ["box_red", "box_blue"]}
        current = {"0.5_0.5": ["target_red", "box_red"], "0.5_1.5": ["box_blue"]}
        move = "move(box_red, square[0.5, 0.5])"
        saved = SavedState(SOURCE, "synthetic", "synthetic", 2, 1, 2,
                           (previous, current),
                           (json.dumps({"Agent[0.5, 1.5]": move}),),
                           {"Agent[0.5, 0.5]": "move(box_red, target_red)"}, {})
        prompt, metadata = build_prompt(saved, "own_last", "last1")
        self.assertIn("Agent[0.5, 0.5]", prompt)
        verdict = judge_reply(saved, "own_last", json.dumps([move]), 1, metadata)
        self.assertEqual(verdict["not_doable_actions"], 1)
        self.assertEqual(verdict["stale_exact_repeat"], 1)
        self.assertEqual(verdict["stale_box_left_square"], 1)
        self.assertEqual(verdict["conflict_earlier_box"], 1)
        occupied = {**current, "0.5_1.5": ["box_blue", "box_red"]}
        other = replace(saved, states=(previous, occupied))
        verdict = judge_reply(other, "own_last", json.dumps([move]), 1, metadata)
        self.assertEqual((verdict["not_doable_actions"], verdict["conflict_earlier_box"], verdict["peer_box_name_overlap"]),
                         (0, 0, 1))

    def test_leader_checks_every_entry_including_off_board_and_malformed_actions(self):
        saved = self.saved()[1]
        _, meta = build_prompt(saved, "leader", "none")
        reply = {"Agent[0.5, 0.5]": None, "Agent[999.5, 0.5]": "move(box_red, target_red)"}
        result = judge_reply(saved, "leader", json.dumps(reply), 1, meta)
        self.assertEqual((result["plan_produced"], result["proposed_actions"], result["not_doable_actions"]), (True, 2, 2))

    def test_peer_lists_follow_applied_moves_and_selection_skips_unfinished_episodes(self):
        with tempfile.TemporaryDirectory(dir=HERE) as scratch:
            p = Path(scratch)
            for folder in ("pg_state", "response"):
                (p / folder).mkdir()
            state = {"0.5_0.5": ["box_red"], "0.5_1.5": ["box_blue"]}
            for n in range(1, 4):
                (p / "pg_state" / f"pg_state{n}.json").write_text(json.dumps(state))
            for n in range(1, 3):
                (p / "response" / f"response{n}.json").write_text('{"Agent[0.5, 0.5]":"unapplied proposal"}')
            record = dict(size="1x2", steps=2, finished=False, iterations=[
                dict(step=n, executed=True, applied_actions=[]) for n in (1, 2)])
            path = p / "episode.json"
            path.write_text(json.dumps(record))
            self.assertEqual(select_saved_states([p], 6), [])
            record["finished"] = True
            path.write_text(json.dumps(record))
            states = select_saved_states([p], 6)
            self.assertEqual([s.step for s in states], [2, 3])
            for saved in states:
                _, metadata = build_prompt(saved, "own_last", "none", 3)
                self.assertEqual(metadata["peer_lists"], {"Agent[0.5, 0.5]": [None, None, None]})

if __name__ == "__main__":
    unittest.main()
