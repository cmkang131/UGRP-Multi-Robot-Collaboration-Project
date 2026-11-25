from regression_inputs import REGRESSION
"""Check the offline replay's historical denominator and first-step legality on saved boards."""
import json
import runpy
from collections import Counter
from dataclasses import replace

from output_demand import measure_episode
from plan_parse import parse_own_reply
from storage import ROOT, write_json
from test_chen2d_v11 import A, B, ONE, TO_B, HorizonFixtures


replay_episode = runpy.run_path(str(ROOT / "fixtures/replay_own.py"))["replay_episode"]


class ReplayTests(HorizonFixtures):
    def test_native_own_reader_still_matches_archived_entries_and_rescue_metadata(self):
        old = runpy.run_path(str(REGRESSION / "chen2d-16/g4/source/plan_parse.py"))["parse_own_reply"]
        for horizon in (1, 5):
            for mode in ("strict", "lenient"):
                for value in ([{}], [TO_B, {}], [{A: TO_B}], ["idle"], ["{}"], [{"action": TO_B}],
                              {A: [None, TO_B]}, [TO_B, "invalid"], [[None, TO_B]], "wait"):
                    with self.subTest(horizon=horizon, mode=mode, value=value):
                        text = json.dumps(value)
                        previous = old(text, horizon, A, mode)
                        current = parse_own_reply(text, horizon, A, mode)
                        self.assertEqual(vars(previous) if previous else None, vars(current) if current else None)

    def test_refusals_actions_and_absent_response_have_separate_denominators(self):
        directory = self.work / "episode"
        (directory / "pg_state").mkdir(parents=True)
        (directory / "calls").mkdir()
        write_json(directory / "pg_state/pg_state1.json", ONE)
        cases = ([{A: TO_B}, {}, {}, {}, {}], [None] * 5, [{B: None}] * 5,
                 [{A: "move(box_missing, target_missing)"}] + [{}] * 4)
        checks = []
        for number, value in enumerate((*cases, None), 1):
            response = None if value is None else json.dumps(value)
            form = "list" if number == 2 else None
            if response is not None:
                checks.append(dict(call=number, speaker=A, status="valid" if form else "parse failure"))
            kinds = ["ok"] if response is not None else ["rate_limit"]
            write_json(directory / "calls" / f"{number:05d}.json",
                       dict(number=number, speaker=A, role="own", step=1, response=response, api_calls=1,
                            attempts=[dict(raw_output=response)], attempt_kinds=kinds, own_reply_form=form,
                            status="ok" if response else "error", failure=None if response else "failure model service"))
        write_json(directory / "episode.json", dict(framework="OWN", protocol="matched", horizon=5, parse="lenient",
                                                     condition="static", size="2x2", api_calls=5, round_log=[dict(checks=checks)]))
        result = replay_episode(directory)
        self.assertEqual([result[k] for k in ("logical_calls", "returned_replies", "previously_refused", "newly_read",
                                               "still_refused", "read_now", "first_step_doable", "no_reply")],
                         [5, 4, 3, 2, 1, 3, 2, 1])
        refusal, = result["refused_replies"]
        self.assertEqual(refusal["call"], 3)
        self.assertIn(B, refusal["detail"])
        self.assertEqual(result["calls_without_replies"][0]["call"], 5)

    def test_output_demand_reads_the_same_self_keyed_actions_as_the_episode(self):
        spec = replace(self.spec(ONE, "OWN", 1), protocol="matched", reasoning_setting="default", max_planning_rounds=1)
        row, _, folder = self.play(spec, [json.dumps([{A: TO_B}])] + ["[{}]"] * 3)
        self.assertEqual(row["steps"], 1)
        measured, _ = measure_episode(folder.parents[1], row, Counter())
        self.assertEqual(len(measured), 4)
        self.assertEqual([c["plan_agents"] for c in measured], [1, 0, 0, 0])
        self.assertTrue(all(c["plan_extracted"] for c in measured))
