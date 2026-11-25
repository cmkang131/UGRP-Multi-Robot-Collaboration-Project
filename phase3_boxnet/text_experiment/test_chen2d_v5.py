"""Offline speech, map design, plan attribution, accounting and paired-analysis regressions."""
import contextlib
import json
import random
import importlib.util
import socket
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import LLM
import fake_model
import test_chen2d
from env1_create import action_from_response, env_create, state_update_func_local_agent
from episode import run_episode
from limits import CALL_LIMIT, Invocation
from map_events import MAIN_SLOTS, agent_at, cell_key, event_path, map_assignment, reference_trajectory
from paired import sign_test
from relay import AUDIENCE, CHOICE, FREE, HEADER, free_checks, parse_reply
from run_chen2d import FRAMEWORKS
from storage import ROOT, code_version, digest, read_json, write_json
from test_chen2d import calls, fixture_spec
from test_chen2d_v2 import enrolled_spec, fixed_dialogue
from test_chen2d_v3 import BOARD, OUTPUT_TOKENS, scripted_transport
from test_chen2d_v4 import archived_bytes, cli


PINNED_BRAIN = ROOT / "fixtures/planner-v1"
PINNED_CLIENT_SHA256 = "2b9c5dda01817ad4d3889efcf4f845505bd8c1b21333081c9ce566e323a7dcad"


@contextlib.contextmanager
def local_references():
    # Historical scripted-HTTP regressions use their original, hash-pinned client.
    source = PINNED_BRAIN / "llm.py"
    if digest(source.read_bytes()) != PINNED_CLIENT_SHA256:
        raise ValueError("Historical planner client differs from the pinned input")
    spec = importlib.util.spec_from_file_location("llm", source)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    with (patch.object(LLM, "BRAIN", PINNED_BRAIN), patch.dict(sys.modules, llm=client),
          patch.object(socket.socket, "connect", side_effect=AssertionError("Unexpected network connection"))):
        yield


def author_trace(records):
    return [(c["step"], c["round"], c["speaker"], c["role"], c["told"], c["messages"], c["response"])
            for c in records if c["role"] != "relay"]


class SpeechTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen5-test-")
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)

    def play(self, spec, tag, script="correct", replies=None, max_calls=None, invocation="first"):
        out = self.work / tag
        out.mkdir(exist_ok=True)
        budget = Invocation(out, out / (invocation + ".json"))
        budget.create(max_calls, 10, "fake")
        hook = patch.object(fake_model, "reply", side_effect=replies) if replies else contextlib.nullcontext()
        with hook:
            run_episode(spec, out, budget.path, "fake", script, 300)
        folder = out / "episodes" / spec.name
        return read_json(folder / "episode.json"), calls(folder)

    def run_cli(self, out, *args):
        result = cli("run_chen2d.py", "--out", out, "--model", "fake", "--frameworks", "CMAS",
                     "--conditions", "e1", "--tell", "member", "--envs", "0", *args)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_saved_v4_bytes_for_all_four_frameworks(self):
        for fw in FRAMEWORKS:
            with self.subTest(fw=fw):
                spec = enrolled_spec(fw, "e2", tell="all", dropoff="always", speech="authors", dropoff_rule="off")
                old = REGRESSION / "chen2d-4/e2/episodes" / spec.name
                saved, trace = read_json(old / "episode.json"), calls(old)
                call_clock = [t for c in trace for t in (0., c["elapsed_seconds"])]
                step_clock = [t for it in saved["iterations"] for t in (0., it["planning_seconds"])]
                with (patch("LLM.monotonic", side_effect=call_clock),
                      patch("episode.time", SimpleNamespace(monotonic=iter(step_clock).__next__))):
                    row, _ = self.play(spec, fw, invocation=trace[0]["invocation"])
                self.assertEqual((row["code_version"], row["speech"]), (code_version(), "authors"))
                new = self.work / fw / "episodes" / spec.name
                files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
                self.assertEqual(files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
                for f in files:
                    self.assertEqual(archived_bytes(new / f, 4, saved["code_version"]), (old / f).read_bytes(), str(f))

    def test_verbatim_send_prompt_order_private_persistent_delivery_and_plan_source(self):
        for fw in FRAMEWORKS:
            with self.subTest(fw=fw):
                spec = enrolled_spec(fw, tell="member", event_step_override=1, dropoff="always")
                def replies(messages, script):
                    if "Reply SEND or PASS." in messages[1]["content"] or "Reply PASS or SEND." in messages[1]["content"]:
                        return " I choose sEnD! "
                    return fixed_dialogue(messages, script)
                automatic, a = self.play(replace(spec, speech="auto"), fw + "-auto", replies=replies)
                choice, b = self.play(replace(spec, speech="choice"), fw + "-choice", replies=replies)
                self.assertEqual(author_trace(a), author_trace(b))
                robot, leader, event = choice["M"], choice["L"], choice["event"]
                robots = [agent_at((i + .5, j + .5)) for i in range(2) for j in range(2)]
                targets = [leader] if fw in ("CMAS", "HMAS-2") else [r for r in robots if r != robot]
                for row in (automatic, choice):
                    delivery, = row["relay_records"]
                    self.assertEqual((delivery["after_step"], delivery["recipients"], delivery["delivered_text"]),
                                     (1, targets, event["announcement"]))
                    self.assertEqual(delivery["call_made"], row["speech"] == "choice")
                relay, = [c for c in b if c["role"] == "relay"]
                self.assertEqual((relay["step"], relay["speaker"], relay["told"]), (1, robot, True))
                local, _ = state_update_func_local_agent(2, 2, *map(int, event["D"]), event["state_after"])
                self.assertEqual(relay["messages"][1]["content"],
                    local + event["announcement"] + "\n" + CHOICE[choice["wording"]].format(recipient=AUDIENCE[fw]))
                self.assertTrue(all(c["step"] == 1 for c in b[:relay["number"] - 1]))
                self.assertTrue(all(c["step"] > 1 for c in b[relay["number"]:]))
                actual = [c for c in b if c["role"] != "relay"]
                block = HEADER + f"[{robot}, after step 1]: " + event["announcement"] + "\n"
                after = [c for c in actual if c["step"] > 1]
                self.assertGreater(len({c["step"] for c in after}), 1)
                for c in actual:
                    prompt = c["messages"][1]["content"]
                    receives = c["step"] > 1 and c["speaker"] in targets
                    marker = "Hence, the current state" if c["role"] == "central" else "The current state and possible actions of yourself"
                    self.assertEqual(HEADER in prompt, receives)
                    self.assertEqual(block + marker in prompt, receives)
                    self.assertEqual(sum(m["content"].count(HEADER) for m in c["messages"]), int(receives))
                self.assertTrue(any(len(c["messages"]) > 2 for c in after))
                if fw == "DMAS":
                    self.assertEqual({c["speaker"] for c in after}, set(robots))
                if fw == "HMAS-2":
                    self.assertTrue(any(c["role"] == "review" for c in after))
                    self.assertTrue(any(len(c["messages"]) >= 4 and c["role"] == "central" for c in after))
                for it in choice["iterations"][1:]:
                    if it["executed"]:
                        c = b[it["plan_maker_call"] - 1]
                        expected_roles = {"DMAS": ("dialogue",), "HMAS-1": ("central", "dialogue")}
                        self.assertIn(c["role"], expected_roles.get(fw, ("central",)))
                        self.assertEqual(json.loads(c["response"].removeprefix("EXECUTE\n")), it["issued_plan"])
                        self.assertEqual(it["plan_maker_told"], c["told"])
                        self.assertEqual(it["plan_maker_message_block"], block in c["messages"][1]["content"])
                        self.assertEqual(it["plan_maker_had_news"], c["told"] or it["plan_maker_message_block"])
                self.assertEqual(choice["first_plan_respected_change"], choice["iterations"][1]["executed_plan_respected_change"])
                self.assertEqual((automatic["relay_calls"], choice["relay_calls"], choice["relay_prompt_tokens"],
                                  choice["relay_completion_tokens"], choice["relay_reasoning_tokens"],
                                  choice["relay_cost_usd"], choice["relay_seconds"]), (0, 1, 11, 7, 2, .001, relay["elapsed_seconds"]))
                self.assertEqual(choice["api_calls"], automatic["api_calls"] + 1)
                self.assertEqual((automatic["relay_tokens"], choice["relay_tokens"]), (0, 18))

    def test_pass_and_format_errors_are_invisible_to_other_prompts(self):
        for fw in FRAMEWORKS:
            spec = enrolled_spec(fw, tell="member", dropoff="always")
            authors, original = self.play(spec, fw + "-authors")
            for script, decision in (("relay-pass", "PASS"), ("relay-invalid", "relay_format_error")):
                with self.subTest(fw=fw, decision=decision):
                    row, trace = self.play(replace(spec, speech="choice"), fw + script, script)
                    self.assertEqual(author_trace(original), author_trace(trace))
                    delivery, = row["relay_records"]
                    self.assertEqual((delivery["reply_class"], delivery["delivered_text"], delivery["recipients"]),
                                     (decision, None, []))
                    self.assertEqual(authors["first_plan_maker_had_news"], row["first_plan_maker_had_news"])
        for reply, expected in (("bypass", "relay_format_error"), ("SEND/PASS", "relay_format_error"),
                                (" PASS... \n", "PASS"), ("I will send.", "SEND"), ("", "relay_format_error")):
            self.assertEqual(parse_reply("choice", reply, "notice")[0], expected)

    def test_self_skip_all_calls_and_ordered_inboxes(self):
        for fw in FRAMEWORKS:
            spec = enrolled_spec(fw, tell="all", dropoff="always", speech="choice")
            row, trace = self.play(spec, fw)
            private = fw in ("CMAS", "HMAS-2")
            self.assertEqual(row["relay_calls"], 3 if private else 4)
            self.assertEqual(len(row["relay_records"]), 4)
            for record in row["relay_records"]:
                also_central = fw == "HMAS-1" and record["sender"] == row["L"]
                self.assertEqual(record["sender"] in record["recipients"], also_central)
                if record["sender"] == row["L"] and private:
                    self.assertEqual((record["status"], record["call_made"]), ("relay_skipped_self", False))
            for c in trace:
                if c["step"] <= row["event_step"] or c["role"] == "relay":
                    continue
                received = [r for r in row["relay_records"] if c["speaker"] in r["recipients"]]
                expected = "".join(f"[{r['sender']}, after step {row['event_step']}]: {r['delivered_text']}\n" for r in received)
                self.assertEqual(HEADER in c["messages"][1]["content"], bool(received))
                if received:
                    self.assertIn(HEADER + expected, c["messages"][1]["content"])
            if private:
                leader, _ = self.play(replace(spec, tell="leader"), fw + "-leader")
                self.assertEqual((leader["relay_calls"], leader["relay_records"][0]["status"]), (0, "relay_skipped_self"))

    def test_free_text_cut_and_destination_scoring(self):
        spec = enrolled_spec("DMAS", tell="member", dropoff="always", speech="free")
        event = read_json(event_path(spec.env_path))
        free = f"Send BOX_{event['A'].upper()} to {event['D']}. " + "x" * 420 + " drop-off"
        normal = fake_model.reply
        def long_message(messages, script):
            if "Reply with the message text alone" in messages[1]["content"]:
                return free
            return normal(messages, script)
        row, trace = self.play(spec, "free", replies=long_message)
        record, = row["relay_records"]
        self.assertEqual((record["delivered_text"], record["reply_class"], record["cut"]), (free[:400], "message", True))
        self.assertEqual((record["names_colour"], record["names_dropoff"], record["names_coordinates"],
                          record["names_destination"]), (True, False, True, True))
        relay = next(c for c in trace if c["role"] == "relay")
        self.assertTrue(relay["messages"][1]["content"].endswith(FREE.format(recipient=AUDIENCE["DMAS"])))
        for c in trace:
            if c["step"] > row["event_step"]:
                self.assertEqual(free[:400] in c["messages"][1]["content"], c["speaker"] in record["recipients"])
        self.assertTrue(free_checks("at the DROP-OFF", event)["names_dropoff"])
        self.assertFalse(free_checks(f"infra{event['A']} at [10.5, 0.5]", event)["names_colour"])
        self.assertFalse(free_checks("at [10.5, 0.5]", event)["names_coordinates"])
        self.assertEqual(parse_reply("free", " PaSs! ", ""), ("PASS", None, False))
        self.assertEqual(parse_reply("free", "pass it along!", ""), ("message", "pass it along!", False))
        self.assertEqual(parse_reply("free", "  red here.\n", ""), ("message", "  red here.\n", False))

    def test_returned_member_and_initial_state_trigger(self):
        spec = enrolled_spec("DMAS", "e2", tell="member", dropoff="always", speech="choice")
        row, trace = self.play(spec, "returned")
        relay, = [c for c in trace if c["role"] == "relay"]
        self.assertEqual((relay["speaker"], relay["step"]), (agent_at(row["event"]["X"]), row["trigger_step"]))
        self.assertEqual(row["M"], relay["speaker"])
        zero = fixture_spec(self.work / "board.json", BOARD, "e1", tell="member", dropoff="always", speech="choice")
        row, trace = self.play(zero, "zero")
        self.assertEqual([(c["role"], c["step"]) for c in trace[:2]], [("relay", 0), ("central", 1)])
        self.assertTrue(row["iterations"][0]["plan_maker_message_block"])

    def test_resume_in_middle_of_forwarding_preserves_paid_prefix_and_inboxes(self):
        spec = enrolled_spec("DMAS", tell="all", dropoff="always", speech="choice")
        full, reference = self.play(spec, "full")
        relays = [c for c in reference if c["role"] == "relay"]
        cap = relays[1]["number"]
        paused, prefix = self.play(spec, "resume", max_calls=cap)
        self.assertEqual((paused["finished"], paused["event_fired"], paused["relay_calls"]), (False, True, 2))
        self.assertEqual(sum(bool(r["recipients"]) for r in paused["relay_records"]), 2)
        row, resumed = self.play(spec, "resume", invocation="second")
        self.assertEqual(prefix, resumed[:cap])
        self.assertEqual(author_trace(reference), author_trace(resumed))
        for key in ("relay_records", "api_calls", "relay_calls", "relay_cost_usd", "wrong_deliveries", "strict_success"):
            self.assertEqual(full[key], row[key], key)
        used = sum(read_json(self.work / "resume" / name)["calls"] for name in ("first.json", "second.json"))
        self.assertEqual(used, len(reference))

    def test_stratified_events_and_legacy_bytes(self):
        envs = ROOT / "envs"
        for name, sha in read_json(REGRESSION / "chen2d-5/legacy-hashes.json").items():
            self.assertEqual(digest((envs / name).read_bytes()), sha, name)
        for rows, cols in ((2, 4), (4, 4)):
            design, seeds = Counter(), set()
            for slot in MAIN_SLOTS:
                path = envs / f"{rows}x{cols}" / f"env{slot}.json"
                state, event = read_json(path), read_json(event_path(path))
                self.assertEqual(event["env_sha256"], digest(path.read_bytes()))
                self.assertEqual(state, env_create(rows, cols, 1, 3, rng=random.Random(event["seed"])))
                self.assertNotIn(event["seed"], seeds)
                seeds.add(event["seed"])
                self.assertEqual(event["slot_seed"], slot)
                row, col = map(int, event["D"])
                self.assertEqual(event["stratum"], "first_column" if col == 0 else "other_columns")
                self.assertEqual(event["member_position"], row * cols + col + 1)
                self.assertEqual(event["M"], agent_at(event["D"]))
                design[event["stratum"], event["wording"]] += 1
                def admissible(board, assignment):
                    at_step = ([board] + [s for s, _ in reference_trajectory(board, action_from_response)])[assignment["event_step"]]
                    return [key for key, items in board.items() if
                            (key.split("_")[1] == "0.5") == (event["stratum"] == "first_column")
                            and "target_" + assignment["A"] not in items and "box_" + assignment["A"] not in at_step[key]]
                self.assertIn(cell_key(event["D"]), admissible(state, event))
                self.assertGreater(event["reference_box_A_left"], 0)
                for skipped in event["skipped_seeds"]:
                    rejected = env_create(rows, cols, 1, 3, rng=random.Random(skipped))
                    baseline = map_assignment(rejected, skipped, "", rows, cols, action_from_response)
                    self.assertEqual(admissible(rejected, baseline), [])
            self.assertEqual(design, Counter({(s, w): 6 for s in ("first_column", "other_columns") for w in (1, 2)}))
        self.assertEqual(Counter(read_json(envs / "2x2" / f"env{s}.speech.event.json")["wording"] for s in range(4)), {1: 2, 2: 2})

    def test_both_wordings_on_actual_calls_across_frameworks_and_event_kinds(self):
        for seed, expected in ((0, 1), (1, 2)):
            for fw in FRAMEWORKS:
                for kind in ("e1", "e2"):
                    spec = enrolled_spec(fw, kind, seed=seed, tell="all", dropoff="always", speech="choice")
                    row, trace = self.play(spec, f"wording-{seed}-{fw}-{kind}")
                    self.assertEqual(row["wording"], expected)
                    questions = [c["messages"][1]["content"].splitlines()[-1] for c in trace if c["role"] == "relay"]
                    self.assertEqual(set(questions), {CHOICE[expected].format(recipient=AUDIENCE[fw])})

    def test_temperature_on_wire_reset_and_resumed_cutoff(self):
        spec = fixture_spec(self.work / "one.json", BOARD, "static")
        out = self.work / "wire"
        out.mkdir()
        first, second = [Invocation(out, out / (n + ".json")) for n in ("first", "second")]
        first.create(1, 1, LLM.MODEL)
        second.create(None, 1, LLM.MODEL)
        def respond(body, number):
            return "truncated" if body["temperature"] == 0 else ("idle" if number == 2 else "ok")
        with local_references(), scripted_transport(respond) as (sent, waits):
            run_episode(spec, out, first.path, LLM.MODEL, "correct", 300, OUTPUT_TOKENS, 0., .7)
            directory = out / "episodes" / spec.name
            self.assertEqual(read_json(directory / "episode.json")["success_failure"], CALL_LIMIT)
            run_episode(spec, out, second.path, LLM.MODEL, "correct", 300, OUTPUT_TOKENS, 0., .7)
        row, log = read_json(directory / "episode.json"), calls(directory)
        self.assertEqual([body["temperature"] for body, _ in sent], [0., .7, 0., .7])
        self.assertEqual([[a["temperature"] for a in c["attempts"]] for c in log], [[0., .7], [0., .7]])
        self.assertEqual((row["steps"], row["success_failure"], row["api_calls"], row["truncated_attempts"]),
                         (2, "success", 4, 2))
        self.assertEqual((row["temperature"], row["retry_temperature"]), (0., .7))
        self.assertEqual([read_json(b.path)["calls"] for b in (first, second)], [1, 3])
        ledger = [json.loads(s) for s in (directory / "campaign-calls.jsonl").read_text().splitlines()]
        self.assertEqual([r["event"] for r in ledger], ["reserve", "settle"] * 4)

    def test_third_attempt_temperature_tracks_previous_failure(self):
        spec = fixture_spec(self.work / "one.json", BOARD, "static")
        with local_references():
            for idx, (kinds, temperatures) in enumerate((
                    (["truncated", "truncated", "ok"], [.2, .7, .7]),
                    (["truncated", "rate_limit", "ok"], [.2, .7, .2]),
                    (["rate_limit", "truncated", "ok"], [.2, .2, .7]))):
                out = self.work / str(idx)
                out.mkdir()
                budget = Invocation(out, out / "budget.json")
                budget.create(None, 1, LLM.MODEL)
                with scripted_transport(kinds) as (sent, _):
                    run_episode(spec, out, budget.path, LLM.MODEL, "correct", 300, OUTPUT_TOKENS, .2, .7)
                self.assertEqual([body["temperature"] for body, _ in sent], temperatures)
                log = calls(out / "episodes" / spec.name)
                self.assertEqual([a["temperature"] for a in log[0]["attempts"]], temperatures)

    def test_plan_attribution_retained_proposals_reviews_and_synthetic_empty_plan(self):
        # The authors retain the last central plan on a later reply with no braces.
        cmas = enrolled_spec("CMAS", tell="member", dropoff="always", speech="auto", event_step_override=1)
        row, _ = self.play(cmas, "retained", replies=iter(["{}"] + ["no plan"] * 29))
        second = row["iterations"][1]
        self.assertEqual((second["plan_maker_call"], second["plan_maker_message_block"]), (1, False))
        dmas = replace(cmas, framework="DMAS")
        row, _ = self.play(dmas, "fallback", script="endless")
        self.assertIsNone(row["iterations"][1]["plan_maker_call"])
        hmas = replace(cmas, framework="HMAS-2")
        row, trace = self.play(hmas, "review")
        self.assertTrue(any(c["role"] == "review" and c["step"] > 1 for c in trace))
        for it in row["iterations"][1:]:
            maker = trace[it["plan_maker_call"] - 1]
            self.assertEqual((maker["role"], maker["speaker"]), ("central", row["L"]))
            self.assertTrue(it["plan_maker_message_block"])

    def test_frames_survive_history_trimming_without_changing_history_budget(self):
        spec = enrolled_spec("HMAS-2", tell="member", event_step_override=1, speech="auto", dropoff="always")
        def fixed(messages, _):
            return "I Agree" if "Please evaluate the given plan." in messages[1]["content"] else "{}"
        for limit in (1, 900):
            with patch("prompt_env1.input_prompt_token_limit", limit):
                row, seen = self.play(spec, f"inbox-{limit}", replies=fixed)
                _, original = self.play(replace(spec, speech="authors"), f"authors-{limit}", replies=fixed)
            text = HEADER + f"[{row['M']}, after step 1]: {row['event']['announcement']}\n"
            self.assertEqual(len(seen), 30)
            for call, old in zip(seen, original, strict=True):
                prompt = call["messages"][1]["content"]
                self.assertEqual(text in prompt, call["step"] > 1)
                self.assertEqual(prompt.replace(text, ""), old["messages"][1]["content"])

    def test_shuffle_observed_order_same_map_wording_and_source_snapshots(self):
        def admissions(tag, seed):
            out = self.work / tag
            self.run_cli(out, "--sizes", "4x4", "--envs", "100-101", "--frameworks", "CMAS,DMAS,HMAS-2,HMAS-1",
                         "--conditions", "e1,e2", "--speech", "choice", "--jobs", "3",
                         "--episode-call-ceiling", "1", "--shuffle", str(seed))
            path, = out.glob("invocations/*.json")
            ledger = read_json(path)
            starts = [json.loads(line) for line in path.with_suffix(".starts.jsonl").read_text().splitlines()]
            order = [r["episode_id"] for r in starts]
            self.assertTrue(all(r["admission"] == "started" for r in starts))
            self.assertEqual((ledger["shuffle"], ledger["requested"]), (seed, order))
            self.assertEqual(set(order), set(read_json(out / "assignments.json")))
            for f, sha in read_json(out / "run.json")["source_sha256"].items():
                self.assertEqual(digest((out / "source" / f).read_bytes()), sha)
            for p in out.glob("episodes/*/episode.json"):
                row = read_json(p)
                frozen = out / "maps" / "4x4" / f"env{row['env_seed']}.json"
                self.assertEqual(row["env_sha256"], digest(frozen.read_bytes()))
                self.assertEqual(row["wording"], read_json(event_path(frozen))["wording"])
            return order
        order = admissions("first", 429)
        self.assertEqual(admissions("second", 429), order)
        self.assertNotEqual(admissions("third", 430), order)

    def test_unfinished_and_unrecorded_are_zero_and_temperatures_cannot_mix(self):
        out = self.work / "guard"
        self.run_cli(out, "--max-calls", "1", "--envs", "0-3", "--jobs", "1", "--speech", "choice")
        result = cli("summarize.py", out, "--by", "stratum")
        self.assertEqual(result.returncode, 0, result.stderr)
        _, headers, *lines = result.stdout.splitlines()
        groups = [dict(zip(headers.split(" | "), line.split(" | "), strict=True)) for line in lines]
        self.assertEqual(sum(int(g["assigned"]) for g in groups), 4)
        self.assertEqual(sum(int(g["recorded"]) for g in groups), 1)
        for group in groups:
            n = int(group["assigned"])
            self.assertEqual(group["strict success"], f"0.0% (0/{n})")
            self.assertIn(f"{CALL_LIMIT} ({n})", group["technical failures by label"])
        self.run_cli(out, "--envs", "0-3", "--speech", "choice")
        compared = cli("summarize.py", out)
        self.assertIn("choice | e1 | member | 4 | 4", compared.stdout)
        for field in ("temperature", "retry_temperature"):
            other = self.work / field
            self.run_cli(other, "--" + field.replace("_", "-"), ".7", "--max-calls", "0")
            result = cli("summarize.py", out, other)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different " + field, result.stderr)
        path = next(out.glob("episodes/*/episode.json"))
        row = read_json(path)
        write_json(path, dict(row, temperature=1))
        self.assertIn("Mixed temperature", cli("summarize.py", out).stderr)
        write_json(path, dict(row, code_version="different"))
        self.assertIn("code version", cli("summarize.py", out).stderr)

    def test_paired_cli_constructed_differences_missing_arms_and_exact_tails(self):
        out = self.work / "pair"
        self.run_cli(out, "--envs", "0-7", "--frameworks", "CMAS,DMAS", "--speech", "authors,choice", "--max-calls", "0")
        manifest = read_json(out / "assignments.json")
        config = read_json(out / "run.json")
        for name, item in manifest.items():
            seed = item["env_seed"]
            # CMAS differences +1 five times, -1 once, +1 and 0.
            # DMAS differences 0 six times, +1 and 0. The last two map contrasts tie.
            if item["framework"] == "CMAS":
                yes = seed == 5 if item["speech"] == "authors" else seed in (0, 1, 2, 3, 4, 6)
            else:
                yes = seed == 6 and item["speech"] == "choice"
            if seed == 7 and item["speech"] == "choice":
                continue  # assigned without a recorded episode
            path = out / "episodes" / name / "episode.json"
            path.parent.mkdir(parents=True)
            row = dict(item, code_version=config["code_version"], temperature=0., retry_temperature=0.,
                       dropoff="always", event_file_version=3, max_output_tokens=config["max_output_tokens"],
                       map_assignment={"event_file_version": 3}, finished=seed != 7, strict_success=yes or seed == 7,
                       change_respected=None, dropoff_misuse=0, dropoff_misuse_before=0, dropoff_misuse_after=0)
            write_json(path, row)
        result = cli("paired.py", out, "--a", "authors", "--b", "choice")
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in ("CMAS | 5 | 1 | 0 | -1", "CMAS   b better=6   a better=1   tie=1",
                         "DMAS   b better=1   a better=0   tie=7", "DMAS | 7 | 0 | 0 | 0",
                         "positive=5   negative=1   ties dropped=2   n used=6   exact two-sided sign p=7/32"):
            self.assertIn(expected, result.stdout)
        self.assertEqual(sign_test(1, 1), Fraction(1))
        self.assertIsNone(sign_test(0, 0))
        unpaired = cli("paired.py", out, "--a", "authors", "--b", "free")
        self.assertIn("unassigned | NA", unpaired.stdout)
        self.assertIn("unpaired=8", unpaired.stdout)


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", "test_chen2d_v2", "test_chen2d_v3", "test_chen2d_v4", "test_chen2d_v5"]
    with local_references():
        print("Folder-local reference hashes verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
