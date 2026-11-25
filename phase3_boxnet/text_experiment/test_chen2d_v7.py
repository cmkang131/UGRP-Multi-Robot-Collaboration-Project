"""Offline confirmation-design, transport, statistics and prompt-attribution checks."""
import contextlib
import csv
import io
import json
import random
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from regression_inputs import REGRESSION
from types import SimpleNamespace
from unittest.mock import patch

import audit_news
import cost
import free_messages
import rescues
import run_chen2d
from analysis_runs import episode_usage, paired_maps, read_run
from env1_create import action_from_response, env_create, saved_env
from episode import Spec, run_episode
from limits import CALL_LIMIT, Invocation
from LLM import QWEN, load_real_api
from map_events import (CONFIRM_SLOTS, E2_EVENT_FILE_VERSION, MAIN_SLOTS, NoAdmissibleDestination,
                        agent_at, boxes, cell_key, coordinates, disjoint_e2, event_path,
                        map_assignment, reference_trajectory)
from paired import binomial_lower, discordance, holm, noninferiority, paired_interval
from storage import ROOT, digest, read_json, write_json
from test_chen2d import calls
from test_chen2d_v3 import scripted_transport
from test_chen2d_v4 import cli
from test_chen2d_v5 import PINNED_BRAIN, PINNED_CLIENT_SHA256, local_references

V6 = REGRESSION / "chen2d-6/smoke"


def printed(func, *args):
    with contextlib.redirect_stdout(io.StringIO()) as output:
        func(*args)
    return output.getvalue()


def pipe_table(text, heading):
    lines = iter(text.splitlines())
    columns = next(line.split(" | ") for line in lines if line.startswith(heading))
    records = []
    for line in lines:
        values = line.split(" | ")
        if len(values) != len(columns):
            break
        records.append(dict(zip(columns, values, strict=True)))
    return records


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen7-test-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def test_fresh_maps_reference_strata_replacements_and_input_hashes(self):
        envs = ROOT / "envs"
        manifest = read_json(envs / "manifest.json")
        events = read_json(envs / "events-manifest.json")
        for (rows, cols), slots in CONFIRM_SLOTS.items():
            design, used, rejected = Counter(), set(), set()
            size = f"{rows}x{cols}"
            for slot in slots:
                path = envs / size / f"env{slot}.json"
                state, base = read_json(path), read_json(event_path(path))
                revised_path = event_path(path, E2_EVENT_FILE_VERSION)
                for file, registry in ((path, manifest), (event_path(path), events), (revised_path, events)):
                    self.assertEqual(digest(file.read_bytes()), registry[str(file.relative_to(envs))])
                revised = read_json(revised_path)
                self.assertEqual(revised["source_event_sha256"], digest(event_path(path).read_bytes()))
                for key in base.keys() - {"A2", "D2", "L2", "event_file_version"}:
                    self.assertEqual(revised[key], base[key])
                self.assertEqual((base["map_set"], base["slot_seed"], base["M"]), ("confirm", slot, agent_at(base["D"])))
                self.assertEqual(base["env_sha256"], digest(path.read_bytes()))
                seed = base["seed"]
                self.assertNotIn(seed, used)
                used.add(seed)
                self.assertEqual(state, env_create(rows, cols, 1, 3, rng=random.Random(seed)))
                trajectory = [state] + [s for s, _ in reference_trajectory(state, action_from_response)]
                at_event = trajectory[base["event_step"]]
                self.assertGreater(base["reference_box_A_left"], 0)
                self.assertEqual(base["reference_box_A_left"], max(boxes(at_event).values()))
                self.assertEqual(boxes(at_event)[base["A"]], base["reference_box_A_left"])
                self.assertNotIn("box_" + base["A"], at_event[cell_key(base["D"])])
                self.assertNotIn("target_" + base["A"], state[cell_key(base["D"])])
                row, col = map(int, base["D"])
                stratum = "first_column" if col == 0 else "other_columns"
                self.assertEqual((base["stratum"], base["member_position"]), (stratum, row * cols + col + 1))
                design[stratum, base["wording"]] += 1
                for skipped in base["skipped_seeds"]:
                    self.assertNotIn(skipped, rejected)
                    rejected.add(skipped)
                    board = env_create(rows, cols, 1, 3, rng=random.Random(skipped))
                    with self.assertRaises(NoAdmissibleDestination):
                        map_assignment(board, skipped, "", rows, cols, action_from_response, stratum=stratum)
            self.assertFalse(used & rejected)
            self.assertEqual(design, {(s, w): len(slots) // 4 for s in ("first_column", "other_columns") for w in (1, 2)})
            self.assertTrue(rejected)
        old = (REGRESSION / "chen2d-7/pre-enrolment.sha256").read_text().splitlines()
        for line in old:
            sha, name = line.split("  ", 1)
            self.assertEqual(digest((ROOT / name).read_bytes()), sha, name)

    def test_every_main_and_confirm_map_fires_disjoint_e2_in_scripted_episode(self):
        budget = Invocation(self.work, self.work / "budget.json")
        budget.create(None, 50, "fake")
        cases = [(2, 4, MAIN_SLOTS), (4, 4, MAIN_SLOTS),
                 *((r, c, slots) for (r, c), slots in CONFIRM_SLOTS.items())]
        fired = 0
        for rows, cols, slots in cases:
            for slot in slots:
                path, sha = saved_env(rows, cols, slot)
                metadata = event_path(path, E2_EVENT_FILE_VERSION)
                spec = Spec(rows, cols, "CMAS", "e2", slot, path, sha, digest(metadata.read_bytes()),
                            tell="member", speech="choice")
                run_episode(spec, self.work, budget.path, "fake", "correct", 300)
                row = read_json(self.work / "episodes" / spec.name / "episode.json")
                self.assertTrue(row["event_fired"], spec.name)
                self.assertIs(row["leader_is_member"], False, spec.name)
                self.assertIs(row["event"]["leader_is_member"], False)
                self.assertEqual(row["M"], agent_at(row["event"]["X"]))
                state = read_json(path)
                leaders = [agent_at(coordinates(k)) for k, items in state.items() if "target_" + row["A2"] not in items]
                self.assertIn(row["L"], leaders)
                self.assertEqual(row["event_sha256"], digest(metadata.read_bytes()))
                self.assertEqual(row["event_file_version"], 4)
                fired += 1
        self.assertEqual(fired, 208)

    def test_redraw_colour_prefers_late_delivery_then_other_eligible_colours(self):
        state = {"0.5_0.5": ["target_red", "target_blue"], "0.5_1.5": ["target_red", "target_green"]}
        base = dict(env_sha256="fixture", A2="red", D2=[0.5, 0.5], A="red", L="unchanged",
                    reference_first_delivery_steps={"blue": 1, "green": 2, "red": 2})
        a = disjoint_e2(state, base, "sha")
        self.assertEqual((a["A2"], a["L2"], a["D2"]), ("green", "Agent[0.5, 0.5]", [0.5, 0.5]))
        self.assertEqual((a["A2_redraw"]["previous_A2"], a["A2_redraw"]["pool"]), ("red", "first_delivery_step_2_or_later"))
        base["reference_first_delivery_steps"]["green"] = 1
        b = disjoint_e2(state, base, "sha")
        self.assertEqual(b["A2_redraw"]["pool"], "all_eligible_colours")
        self.assertIn(b["A2"], ("blue", "green"))
        self.assertEqual((b["A"], b["L"]), ("red", "unchanged"))
        self.assertEqual(b, disjoint_e2(state, base, "sha"))
        with self.assertRaisesRegex(ValueError, "No colour admits"):
            disjoint_e2({"0.5_0.5": ["target_red", "target_blue", "target_green"]}, base, "sha")

    def test_mixed_event_versions_freeze_and_resume(self):
        out = self.work / "mixed"
        args = ("run_chen2d.py", "--model", "fake", "--out", out, "--sizes", "2x4", "--envs", "0,100,200",
                "--frameworks", "CMAS", "--tell", "member")
        for conditions in ("e1", "e1,e2"):
            result = cli(*args, "--conditions", conditions)
            self.assertEqual(result.returncode, 0, result.stderr)
        _, assigned, rows = read_run(out)
        self.assertEqual(len(rows), 6)
        for name, r in rows.items():
            version = 4 if r["condition"] == "e2" and r["env_seed"] else 3
            self.assertEqual(r["event_file_version"], version)
            path = event_path(out / "maps/2x4" / f"env{r['env_seed']}.json", version)
            self.assertEqual(assigned[name]["event_sha256"], digest(path.read_bytes()))
        self.assertEqual(cli("summarize.py", out).returncode, 0)

    def test_v6_e1_replays_archived_bytes(self):
        config = read_json(V6 / "run.json")
        for old in sorted((V6 / "episodes").iterdir()):
            row, trace = read_json(old / "episode.json"), calls(old)
            spec = Spec(2, 4, row["framework"], "e1", row["env_seed"], V6 / "maps/2x4" / f"env{row['env_seed']}.json",
                        row["env_sha256"], row["event_sha256"], tell="member", speech=row["speech"])
            budget = Invocation(self.work, self.work / (trace[0]["invocation"] + ".json"))
            if not budget.path.exists():
                budget.create(None, 2, "fake")
            call_clock = [t for c in trace for t in (0., c["elapsed_seconds"])]
            step_clock = [t for it in row["iterations"] for t in (0., it["planning_seconds"])]
            with (patch("LLM.monotonic", side_effect=call_clock),
                  patch("episode.time", SimpleNamespace(monotonic=iter(step_clock).__next__))):
                run_episode(spec, self.work, budget.path, "fake", "correct", 300,
                            temperature=config["temperature"], retry_temperature=config["retry_temperature"])
            new = self.work / "episodes" / old.name
            old_files = {p.relative_to(old) for p in old.rglob("*") if p.is_file()}
            self.assertEqual(old_files, {p.relative_to(new) for p in new.rglob("*") if p.is_file()})
            for f in old_files:
                if f.name == "episode.json":
                    current = read_json(new / f)
                    current["code_version"] = row["code_version"]
                    actual = (json.dumps(current, ensure_ascii=False, indent=2) + "\n").encode()
                else:
                    actual = (new / f).read_bytes()
                self.assertEqual(actual, (old / f).read_bytes(), str(old / f))

    def test_qwen_scripted_wire_price_reservation_settlement_and_model_guard(self):
        # Materialise the same hash-verified archive used by local_references for run.json provenance.
        source = (PINNED_BRAIN / "llm.py").read_bytes()
        self.assertEqual(digest(source), PINNED_CLIENT_SHA256)
        (self.work / "llm.py").write_bytes(source)
        out = self.work / "qwen"
        args = ["run_chen2d.py", "--model", QWEN, "--out", str(out), "--sizes", "2x2", "--envs", "0",
                "--frameworks", "CMAS", "--conditions", "static", "--max-output-tokens", "24000",
                "--episode-call-ceiling", "2", "--max-cost-usd", "0.09"]
        route = lambda model: ("offline.invalid", 443, "/script", model, "test-fixture-credential")
        with (scripted_transport(["http_5xx", "ok"]) as (sent, _), patch.object(load_real_api(), "_load_route", side_effect=route),
              patch.object(run_chen2d, "BRAIN", self.work), patch.object(run_chen2d, "ProcessPoolExecutor", ThreadPoolExecutor),
              patch.object(sys, "argv", args)):
            printed(run_chen2d.main)
        self.assertEqual(len(sent), 2)
        for body, _ in sent:
            self.assertEqual((body["model"], body["max_tokens"]), (QWEN, 24000))
            self.assertNotIn("reasoning", body)
            self.assertEqual(body["provider"], {"max_price": {"prompt": .25, "completion": .9},
                                               "require_parameters": True, "allow_fallbacks": False})
        tokens_bound = len(sent[0][0]["messages"][0]["content"].encode()) + 1024
        held = (Decimal(tokens_bound) * Decimal(".25") + Decimal(24000) * Decimal(".9")) / 1_000_000
        ledger = read_json(next(out.glob("invocations/*.json")))
        rowfile = next(out.glob("episodes/*/episode.json"))
        row = read_json(rowfile)
        self.assertEqual((row["model"], read_json(out / "run.json")["model"], ledger["model"]), (QWEN,) * 3)
        self.assertEqual(ledger["reservations"], {})
        self.assertEqual((ledger["calls"], Decimal(ledger["reported_cost_usd"])), (2, Decimal(".00002")))
        self.assertAlmostEqual(float(ledger["guard_cost_usd"]), float(held + Decimal(".00002")))
        self.assertIsNone(row["cost_usd"])
        self.assertAlmostEqual(row["guard_cost_usd"], float(held + Decimal(".00002")))
        attempt = calls(rowfile.parent)[0]["attempts"]
        self.assertEqual(attempt[0]["guard_cost_usd"], float(held))
        self.assertEqual(attempt[1]["cost_usd"], .00002)
        write_json(rowfile, dict(row, model="other"))
        self.assertIn("model", cli("summarize.py", out).stderr)
        other = self.work / "glm"
        other.mkdir()
        write_json(other / "run.json", dict(read_json(out / "run.json"), model="z-ai/glm-5.3-flash"))
        self.assertIn("different model", cli("summarize.py", out, other).stderr)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT, prefix=".chen7-analysis-")
        self.addCleanup(temp.cleanup)
        self.work = Path(temp.name)

    def test_exact_interval_holm_and_noninferiority_boundary(self):
        from math import comb
        p = binomial_lower(4, 10, .0125)
        self.assertAlmostEqual(sum(comb(10, k) * p**k * (1 - p)**(10 - k) for k in range(4, 11)), .0125)
        delta, lo, hi = paired_interval(3, 1, 8, .95)
        r_delta, r_lo, r_hi = paired_interval(1, 3, 8, .95)
        self.assertEqual(delta, .25)
        self.assertEqual((delta, lo, hi), (-r_delta, -r_hi, -r_lo))
        self.assertEqual(paired_interval(0, 0, 0, .95), (None,) * 3)
        self.assertEqual(holm({"CMAS": Fraction(1,32), "DMAS": Fraction(1,16)}),
                         {"CMAS": Fraction(1,16), "DMAS": Fraction(1,16)})
        assigned = {f"{fw}{s}": dict(size="2x4", condition="e1", tell="member", framework=fw,
                     speech="choice", env_seed=s, env_sha256=str(s)) for s in range(128) for fw in ("CMAS", "DMAS")}
        won = dict(finished=True, strict_success=True)
        rows = dict.fromkeys(assigned, won)
        args = (assigned, rows, ("CMAS", "DMAS"), "choice")
        _, lower, _ = paired_interval(0, 0, 128, .90)
        self.assertAlmostEqual(lower, .025 ** (1 / 128) - 1)
        self.assertTrue(printed(noninferiority, *args, .10).rstrip().endswith("| non-inferior"))
        self.assertTrue(printed(noninferiority, *args, -lower).rstrip().endswith("| non-inferiority not established"))
        assigned["CMAS0"]["env_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "Map inputs differ"):
            paired_maps(assigned, rows, "framework", ("CMAS", "DMAS"))

    def test_partial_mcnemar_discordances_and_technical_zero(self):
        out = self.work / "partial"
        result = cli("run_chen2d.py", "--out", out, "--model", "fake", "--sizes", "2x2", "--conditions", "e1",
                     "--tell", "member", "--frameworks", "CMAS,DMAS", "--speech", "authors,choice",
                     "--envs", "0-7", "--max-calls", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = read_json(out / "run.json")
        for name, item in read_json(out / "assignments.json").items():
            seed, fw, choice = item["env_seed"], item["framework"], item["speech"] == "choice"
            if (fw, choice, seed) == ("CMAS", True, 7):
                continue
            yes = choice and seed < (6 if fw == "CMAS" else 4)
            row = dict(item, model="fake", code_version=config["code_version"], dropoff="always",
                       event_file_version=3, map_assignment={"event_file_version": 3},
                       max_output_tokens=config["max_output_tokens"], temperature=0., retry_temperature=0.,
                       strict_success=yes, finished=True, success_failure="success",
                       change_respected=None if seed == 1 and not choice else int(yes))
            if (fw, choice, seed) == ("CMAS", True, 6):
                row.update(strict_success=True, success_failure=CALL_LIMIT)
            folder = out / "episodes" / name
            folder.mkdir(parents=True)
            write_json(folder / "episode.json", row)
        args = ("paired.py", out, "--test", "mcnemar", "--a", "authors", "--b", "choice")
        self.assertIn("1 unrecorded episodes", cli(*args).stderr)
        other = cli("paired.py", out, "--noninferiority", "--speech", "choice", "--margin", ".10")
        self.assertIn("1 unrecorded episodes", other.stderr)
        strict = cli(*args, "--allow-partial")
        self.assertEqual(strict.returncode, 0, strict.stderr)
        self.assertTrue(strict.stdout.startswith("WARNING: 1 unrecorded"))
        cmas, dmas = pipe_table(strict.stdout, "size |")
        self.assertEqual((cmas["paired n"], cmas["choice only"], cmas["authors only"], cmas["NA pairs"]),
                         ("8", "6", "0", "0"))
        self.assertEqual((cmas["exact p"], cmas["Holm p"]), ("1/32 (0.03125)", "1/16 (0.0625)"))
        self.assertEqual((dmas["choice only"], dmas["exact p"], dmas["Holm p"]), ("4", "1/8 (0.125)", "1/8 (0.125)"))
        other = cli(*args, "--allow-partial", "--outcome", "change_respected")
        cmas, dmas = pipe_table(other.stdout, "size |")
        self.assertEqual((cmas["paired n"], cmas["NA pairs"], cmas["choice only"]), ("6", "2", "5"))
        self.assertEqual((dmas["paired n"], dmas["NA pairs"], dmas["choice only"]), ("7", "1", "3"))
        self.assertEqual(discordance({1: {"a": None, "b": None}}, "b", "a", "change_respected"), (0, 0, 0, 1))
        with self.assertRaisesRegex(ValueError, "Unassigned arm"):
            discordance({1: {"a": None}}, "b", "a", "strict")

    def test_all_episode_costs_rescue_denominators_and_seeded_paired_bootstrap(self):
        assigned, rows = {}, {}
        for fw, factor in (("CMAS", 2), ("DMAS", 1)):
            for slot in (1, 2):
                name = fw + str(slot)
                assigned[name] = dict(size="2x4", env_seed=slot, framework=fw, condition="e1", tell="member", speech="choice")
                units = slot * factor
                rows[name] = dict(finished=True, strict_success=slot == 1, api_calls=10 * units, prompt_tokens=6 * units,
                                  completion_tokens=2 * units, reasoning_tokens=units, relay_calls=2,
                                  cost_usd=.1 * units if slot == 1 else None, guard_cost_usd=.1 * units,
                                  lenient_rescues=slot)
        txt = printed(cost.report, self.work, assigned, rows, 19, 500)
        cmas, _ = pipe_table(txt, "framework |")
        self.assertEqual([float(cmas[k]) for k in ("episodes", "strict successes", "calls mean", "calls median",
                                                  "prompt tokens", "completion tokens", "reasoning tokens",
                                                  "USD sum", "USD mean", "missing reported cost", "guard used",
                                                  "relay calls", "calls per strict success", "tokens per strict success",
                                                  "USD per strict success")],
                         [2, 1, 30, 30, 36, 12, 6, .6, .3, 1, 1, 4, 60, 48, .6])
        for r in pipe_table(txt, "size |"):
            self.assertEqual((r["ratio"], r["lower95"], r["upper95"]), ("2.000000",) * 3)
        pairs = [(1, 10), (100, 20), (4, 5)]
        self.assertEqual(cost.bootstrap_ratio(pairs, 14, 1000), cost.bootstrap_ratio(pairs, 14, 1000))
        estimate, low, high = cost.bootstrap_ratio(pairs, 14, 1000)
        self.assertEqual(estimate, 3)
        self.assertLess(low, estimate)
        self.assertGreater(high, estimate)
        self.assertEqual(cost.bootstrap_ratio([(0, 0)], 7, 200), (None,) * 3)
        rows["CMAS1"].update(strict_success=False)
        cmas = pipe_table(printed(cost.report, self.work, assigned, rows, 19, 50), "framework |")[0]
        self.assertEqual(cmas["USD per strict success"], "NA")
        cmas, dmas = pipe_table(printed(rescues.report, self.work, assigned, rows), "framework |")
        self.assertEqual((cmas["episodes with rescue"], cmas["rescues per 100 calls"], cmas["strict successes with rescue"]),
                         ("2", "5.000000", "0"))
        self.assertEqual(dmas["strict successes with rescue"], "1")
        rows["CMAS2"].pop("cost_usd")
        self.assertIsNone(episode_usage(self.work, "CMAS2", rows["CMAS2"])["cost_usd"])
        cmas = pipe_table(printed(cost.report, self.work, assigned, rows, 19, 50), "framework |")[0]
        self.assertEqual((cmas["missing reported cost"], cmas["guard used"], cmas["USD sum"]), ("1", "1", "0.60000000"))

    def test_news_from_actual_speaker_prompt_and_step_specific_dialogue_or_feedback(self):
        folder = V6 / "episodes/2x4_DMAS_e1_member_env100"
        row = read_json(folder / "episode.json")
        it = next(i for i in row["iterations"] if i["step"] > row["event_step"])
        call = read_json(folder / "calls" / f"{it['plan_maker_call']:05d}.json")
        self.assertEqual(audit_news.news_source(call, row["event"]), "none")
        notice = row["event"]["announcement"]
        colour, destination = row["event"]["A"], row["event"]["D"]
        users = call["messages"]
        original = users[1]["content"]
        marker = "The current state and possible actions of yourself are:"
        sender = f"Agent{destination}"
        for message, expected in ((f"[{sender}: {colour} should use the dropoff]", "dialogue"),
                                  (f"[{sender}: Reroute box_{colour} to square{destination}]", "dialogue"),
                                  (f"[{sender}: keep moving {colour}]", "none"),
                                  (f"[{sender}: {colour}]\n\n[Agent[0.5, 0.5]: use the dropoff]", "none"),
                                  (f"[{sender}: greenhouse dropoff]", "none")):
            users[1]["content"] = audit_news.DIALOGUE.sub(lambda m: m[0].replace(m[1], message, 1)
                if m[1] else m[0].replace("{}", "{" + message + "}", 1), original)
            self.assertEqual(audit_news.news_source(call, row["event"]), expected, message)
        users[1]["content"] = original.replace(marker, notice + "\n" + marker)
        self.assertEqual(audit_news.news_source(call, row["event"]), "direct")
        inbox = f"Messages received from robots:\n[{sender}, after step {row['event_step']}]: {notice}\n"
        users[1]["content"] = original.replace(marker, inbox + marker)
        self.assertEqual(audit_news.news_source(call, row["event"]), "relay")
        users[1]["content"] = original
        users.extend([dict(role="assistant", content=f"{colour} dropoff"),
                      dict(role="user", content=f"{sender}: okay\nThis is the feedback from local agents. {colour} {destination}")])
        self.assertEqual(audit_news.news_source(call, row["event"]), "none")
        users[-1]["content"] = f"{sender}: {colour} now goes to the drop-off.\nThis is the feedback from local agents."
        self.assertEqual(audit_news.news_source(call, row["event"]), "dialogue")
        self.assertEqual(audit_news.news_source(dict(call, step=row["event_step"]), row["event"]), "none")
        step = {"step": row["event_step"] + 1, "executed": True}
        row["iterations"] = [step, dict(step, step=step["step"] + 1, plan_maker_call=None),
                             dict(step, step=step["step"] + 2, executed=False)]
        inspected = audit_news.inspect_episode(folder, row)
        self.assertEqual([s.detail for s in inspected], ["attribution-unavailable", "no-maker", "unexecuted"])

    def test_free_export_raw_cut_pass_and_multiple_senders_share_one_row(self):
        folder = V6 / "episodes/2x4_DMAS_e1_member_env100_free"
        row = read_json(folder / "episode.json")
        name, record = row["episode_id"], row["relay_records"][0]
        colours = row["event"]["A"]
        actual = f'Agent says "{colours} target is no longer wanted".\nUse square{row["event"]["D"]}. ' + "x"*400
        dest = self.work / "episodes" / name / "calls"
        dest.mkdir(parents=True)
        write_json(dest / "00001.json", {"response": actual})
        write_json(dest / "00002.json", {"response": "PASS"})
        row["relay_records"] = [dict(record, call_number=1, delivered_text=actual[:400], cut=True),
                                dict(record, sender="Agent[0.5, 0.5]", call_number=2, reply_class="PASS", delivered_text=None)]
        assigned = {name: {**row, "tell": "all"}}
        text = printed(free_messages.report, self.work, assigned, {name: row})
        exported, = csv.DictReader(io.StringIO(text))
        self.assertEqual(json.loads(exported["text"]), [actual, "PASS"])
        self.assertEqual(json.loads(exported["delivered_text"]), [actual[:400], None])
        self.assertEqual(json.loads(exported["reply_class"]), ["message", "PASS"])
        for field in ("names_colour", "names_dropoff_or_D", "old_target_wrong"):
            self.assertEqual(json.loads(exported[field]), [True, None])
        for phrase in ("target_red is wrong", "do not use that target", "targets no longer receive blue"):
            self.assertTrue(free_messages.old_target_wrong(phrase))
        self.assertFalse(free_messages.old_target_wrong("retarget to the wrong location"))
        self.assertFalse(free_messages.old_target_wrong("target is beside the dropoff"))

    def test_analysis_clis_leave_run_byte_and_timestamp_identical_without_csv(self):
        out = self.work / "archive"
        shutil.copytree(V6, out)
        (out / "episodes.csv").unlink()
        (out / ".summary.lock").unlink(missing_ok=True)

        def snapshot():
            return {str(p.relative_to(out)): (p.stat().st_mtime_ns, digest(p.read_bytes()))
                    for p in out.rglob("*") if p.is_file()}

        before = snapshot()
        for options in (("paired.py", "--a", "authors", "--b", "choice"),
                        ("paired.py", "--test", "mcnemar", "--a", "authors", "--b", "choice"),
                        ("paired.py", "--noninferiority"), ("cost.py", "--bootstrap", "100"),
                        ("audit_news.py",), ("rescues.py",), ("free_messages.py",)):
            result = cli(options[0], out, *options[1:])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    suites = sys.argv[1:] or ["test_chen2d", *(f"test_chen2d_v{n}" for n in range(2, 8))]
    with local_references():
        print("Folder-local reference hashes verified. Network connections disabled.", flush=True)
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(suites))
    sys.exit(not result.wasSuccessful())
