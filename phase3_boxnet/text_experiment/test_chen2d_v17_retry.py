"""Matched logical calls through the archived client with scripted HTTP responses."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from LLM import MAX_REPLY_ATTEMPTS, MAX_TRANSPORT_ATTEMPTS, MODEL, TRANSPORT_RETRY_TOTAL_S, load_real_api
from episode import run_episode
from limits import CALL_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, UNUSABLE_REPLY, Invocation
from planning_metrics import round_cutoff
from storage import read_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v3 import BOARD, OUTPUT_TOKENS, scripted_transport
from test_chen2d_v5 import local_references
from test_chen2d_v11 import HorizonFixtures


def http_response(status, body=b"{}", headers=()):
    return SimpleNamespace(status=status, read=lambda _: body, getheaders=lambda: headers)


class MatchedRetryTests(HorizonFixtures):
    def setUp(self):
        super().setUp()
        self.episode = replace(fixture_spec(self.work / "board.json", BOARD, "static"),
                               protocol="matched", horizon=1, max_env_steps=1, max_planning_rounds=1)

    def play(self, tag, kinds=(), *, max_calls=None, ceiling=30, response=None, invocation="first"):
        out = self.work / tag
        out.mkdir(exist_ok=True)
        budget = Invocation(out, out / f"{invocation}.json")
        budget.create(max_calls, 5, MODEL)
        with local_references(), scripted_transport(kinds) as (sent, waits):
            connection = load_real_api().http.client.HTTPSConnection
            override = patch.object(connection, "getresponse", return_value=response) if response else nullcontext()
            with override:
                run_episode(self.episode, out, budget.path, MODEL, "correct", ceiling, OUTPUT_TOKENS, 0., .7)
        directory = out / "episodes" / self.episode.name
        call, = calls(directory)
        self.assertEqual(read_json(budget.path)["calls"], len(sent))
        return read_json(directory / "episode.json"), call, sent, waits

    def test_mixed_pilot_pattern_preserves_three_cutoff_reply_budget(self):
        kinds = ["truncated", "rate_limit", "truncated", "http_5xx", "truncated"]
        row, call, sent, waits = self.play("mixed", kinds)
        self.assertEqual((MAX_REPLY_ATTEMPTS, MAX_TRANSPORT_ATTEMPTS, TRANSPORT_RETRY_TOTAL_S), (3, 3, 60.0))
        self.assertEqual((row["success_failure"], row["api_calls"], len(sent), len(waits)), (OUTPUT_LIMIT, 5, 5, 4))
        self.assertEqual(call["attempt_kinds"], kinds)
        self.assertEqual((call["reply_attempt_count"], call["transport_attempt_count"],
                          call["reply_attempt_limit"], call["transport_attempt_limit"]), (3, 2, 3, 3))
        self.assertEqual([a["temperature"] for a in call["attempts"]], [0., .7, .7, .7, .7])
        self.assertEqual(round_cutoff([call]), "all attempts cut off")

    def test_both_actual_pilot_prefixes_leave_a_reply_attempt(self):
        prefixes = (["truncated", "truncated", "rate_limit"], ["rate_limit", "truncated", "truncated"])
        for i, prefix in enumerate(prefixes):
            for final, label in (("truncated", OUTPUT_LIMIT), ("ok", "success")):
                with self.subTest(prefix=prefix, final=final):
                    row, call, sent, _ = self.play(f"pilot-{i}-{final}", [*prefix, final])
                    self.assertEqual((row["success_failure"], len(sent), call["reply_attempt_count"],
                                      call["transport_attempt_count"]), (label, 4, 3, 1))
                    self.assertEqual(row["rounds_all_attempts_cutoff" if final == "truncated"
                                         else "rounds_cutoff_recovered"], 1)

    def test_mixed_transport_then_cutoff_recovers_on_a_reply(self):
        row, call, sent, waits = self.play("recovered", ["rate_limit", "truncated", "http_5xx", "ok"])
        self.assertEqual((row["success_failure"], row["api_calls"], len(sent), len(waits)), ("success", 4, 4, 3))
        self.assertEqual((call["reply_attempt_count"], call["transport_attempt_count"]), (2, 2))
        self.assertEqual([a["temperature"] for a in call["attempts"]], [0., 0., .7, .7])
        self.assertEqual(round_cutoff([call]), "first attempt cut off and recovered")

    def test_no_reply_transport_exhaustion_is_model_service(self):
        row, call, sent, waits = self.play("service", ["rate_limit", "network", "http_5xx"])
        self.assertEqual((row["success_failure"], row["finished"], row["api_calls"], len(sent), len(waits)),
                         (MODEL_SERVICE, True, 3, 3, 2))
        self.assertEqual((call["reply_attempt_count"], call["transport_attempt_count"]), (0, 3))

    def test_last_transport_error_preserves_a_received_cutoff(self):
        row, call, _, _ = self.play("last-503", ["truncated", "rate_limit", "network", "http_5xx"])
        self.assertEqual((row["success_failure"], call["reply_attempt_count"], call["transport_attempt_count"]),
                         (OUTPUT_LIMIT, 1, 3))
        self.assertEqual(round_cutoff([call]), "all attempts cut off")

    def test_unusable_reply_and_generic_response_error_have_their_own_label(self):
        for i, (body, kind) in enumerate(((b"{", "bad_body"), (b'{"choices": []}', "ResponseError"))):
            with self.subTest(body=body):
                row, call, sent, waits = self.play(f"unusable-{i}", response=http_response(200, body))
                self.assertEqual((row["success_failure"], row["api_calls"], len(sent), len(waits)),
                                 (UNUSABLE_REPLY, 3, 3, 2))
                self.assertEqual(call["attempt_kinds"], [kind] * 3)
                self.assertEqual((call["reply_attempt_count"], call["transport_attempt_count"]), (3, 0))
                self.assertEqual(round_cutoff([call]), "unknown")

    def test_permanent_transport_refusal_is_service_and_not_retried(self):
        row, call, sent, waits = self.play("permanent", response=http_response(401))
        self.assertEqual((row["success_failure"], len(sent), waits,
                          call["reply_attempt_count"], call["transport_attempt_count"]), (MODEL_SERVICE, 1, [], 0, 1))

    def test_retry_after_beyond_window_is_not_shortened(self):
        row, call, sent, waits = self.play("long-wait", response=http_response(429, headers=[("Retry-After", "61")]))
        self.assertEqual((row["success_failure"], call["detail"], len(sent), waits), (MODEL_SERVICE, "rate_limit", 1, []))

    def test_resume_preserves_both_attempt_budgets_and_the_logical_call(self):
        before, first, sent, _ = self.play("resume", ["truncated", "rate_limit"], max_calls=2)
        self.assertEqual((before["success_failure"], before["finished"], len(sent), first["status"]),
                         (CALL_LIMIT, False, 2, "interrupted"))
        self.assertEqual((first["reply_attempt_count"], first["transport_attempt_count"]), (1, 1))
        row, call, sent, _ = self.play("resume", ["http_5xx", "truncated", "truncated"], invocation="second")
        self.assertEqual((row["success_failure"], row["api_calls"], len(sent)), (OUTPUT_LIMIT, 5, 3))
        self.assertEqual(call["attempts"][:2], first["attempts"])
        self.assertEqual(len({a["logical_call_id"] for a in call["attempts"]}), 1)
        self.assertEqual(len({a["attempt_id"] for a in call["attempts"]}), 5)
        self.assertEqual((call["reply_attempt_count"], call["transport_attempt_count"]), (3, 2))
