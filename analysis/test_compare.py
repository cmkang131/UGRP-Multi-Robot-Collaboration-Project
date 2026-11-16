import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from compare import aggregate, analyze_run, write_outputs
import causes


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scenes = {
            "C": {"boxes": [{"id": "a", "colour": "blue"}, {"id": "b", "colour": "blue"}],
                  "orders": [{"id": "o1", "colour": "blue", "sign": 11, "count": 1},
                             {"id": "o2", "colour": "blue", "sign": 12, "count": 1}],
                  "oracle_plan": {"r1": [["a", "o1"]], "r2": [["b", "o2"]]}},
            "D": {"boxes": [{"id": "a", "colour": "red"}],
                  "orders": [{"id": "o1", "colour": "red", "sign": 12, "count": 1}],
                  "oracle_plan": {"r1": [], "r2": [["a", "o1"]]}}}
        self.c = {"status": "complete", "scene": "C", "robots": ["r1", "r2"],
                  "correct_boxes": 1, "required_boxes": 2, "wrong_place_boxes": 0, "end_s": 200,
                  "choices": {"r1": {"picked": "blue", "dest": "zone_sign12"},
                              "r2": {"picked": "blue", "dest": "zone_sign11"}},
                  "brain": json.dumps({"calls": 4, "cost_usd": 0.02,
                                       "messages": [{"from": "r1", "to": ["r2"], "text": "go"}]}),
                  "decisions": []}
        self.d = {"status": "complete", "scene": "D", "robots": ["r1", "r2"],
                  "correct_boxes": 1, "required_boxes": 1, "wrong_place_boxes": 0, "end_s": 100,
                  "choices": {"r1": {"picked": None, "dest": "zone_sign11"},
                              "r2": {"picked": "red", "dest": "zone_sign12"}},
                  "brain": {"kind": "fixed_plan"},
                  "decisions": [
                      {"rid": "r1", "t": 0, "point": "pick", "option": "none", "sent": [], "calls": 0},
                      {"rid": "r2", "t": 0, "point": "pick", "option": "box:1", "sent": [], "calls": 0,
                       "options": [{"key": "box:1", "text": "grasp <red box>"}]},
                      {"rid": "r2", "t": 1, "point": "destination", "option": "zone:sign12", "sent": [], "calls": 0}]}
        self.retry = copy.deepcopy(self.d)
        self.retry["choices"]["r2"]["picked"] = "blue"
        self.retry["decisions"] += [
            {"rid": "r2", "t": 2, "point": "pick", "option": "box:0", "sent": [], "calls": 0,
             "options": [{"key": "box:0", "text": "grasp <blue box>"}]},
            {"rid": "r2", "t": 3, "point": "destination", "option": "zone:sign11", "sent": [], "calls": 0}]
        self.running = {"status": "running", "scene": "C"}

    def run_fixture(self, name, data, summary=None):
        path = self.root / name
        path.mkdir(exist_ok=True)
        (path / "team.json").write_text(json.dumps(data), encoding="utf-8")
        if summary:
            (path / "out-r2").mkdir(exist_ok=True)
            (path / "out-r2" / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        return analyze_run(path, self.scenes)

    def test_c_multiset_and_robot_assignment_are_separate(self):
        row = self.run_fixture("t0-C-h", self.c, {
            "carry_to": {"nav": {"outcome": "box_not_held"}}, "regrasps": [{}, {}]})
        self.assertTrue(row["plan_cover"])
        self.assertFalse(row["oracle_match"])
        self.assertFalse(row["physical_success"])
        self.assertEqual(row["quadrant"], "P1_S0")
        self.assertEqual(row["messages_r1"], 1)
        self.assertEqual(row["messages_r2"], 0)
        self.assertEqual(row["llm_calls"], 4)
        self.assertEqual(row["cost_usd"], 0.02)
        self.assertIn("T0_NONZERO_MESSAGES", row["warnings"])
        self.assertIn({"robot": "r2", "nav.outcome": "box_not_held", "regrasps": 2}, row["failure_diagnostics"])
        duplicate = copy.deepcopy(self.c)
        duplicate["choices"]["r1"]["dest"] = "zone_sign11"
        bad = self.run_fixture("t1-C-h", duplicate)
        self.assertFalse(bad["plan_cover"])
        self.assertEqual(bad["quadrant"], "P0_S0")

    def test_d_empty_assignment_and_strict_physical_rule(self):
        row = self.run_fixture("oracle-D", self.d)
        self.assertEqual(row["last_assignments"]["r1"], [])
        for key in ("physical_success", "plan_cover", "oracle_match", "first_plan_cover", "first_oracle_match"):
            self.assertTrue(row[key], key)
        self.assertEqual(row["quadrant"], "P1_S1")
        self.assertEqual(row["cost_usd"], 0)
        wrong = copy.deepcopy(self.d)
        wrong["wrong_place_boxes"] = 1
        self.assertFalse(self.run_fixture("wrong", wrong)["physical_success"])

    def test_regrasp_preserves_first_attempt_not_last_choices(self):
        row = self.run_fixture("retry", self.retry)
        self.assertTrue(row["first_plan_cover"])
        self.assertTrue(row["first_oracle_match"])
        self.assertFalse(row["plan_cover"])
        self.assertFalse(row["oracle_match"])
        self.assertEqual(row["quadrant"], "P0_S1")
        self.assertEqual(row["first_assignments"]["r2"], [("red", "sign12")])
        incomplete = copy.deepcopy(self.retry)
        incomplete["decisions"].pop(2)
        row = self.run_fixture("incomplete", incomplete)
        self.assertEqual(row["first_assignments"]["r2"], [("red", None)])
        self.assertFalse(row["first_plan_cover"])

    def test_exclusions_missing_records_and_output_denominators(self):
        rows = [self.run_fixture("oracle-D", self.d),
                self.run_fixture("t1-C-h", self.c),
                self.run_fixture("t2-C-h", self.running)]
        (self.root / "missing").mkdir()
        rows.append(analyze_run(self.root / "missing", self.scenes))
        self.run_fixture("t1-C-check", self.c)
        rows.append(analyze_run(self.root / "t1-C-check", self.scenes, suffix="h"))
        self.assertEqual(aggregate(rows)[:5], [2, 3, "1/2", "2/2", "1/2"])
        self.assertEqual(aggregate(rows)[-2:], ["100 (n=1)", "150 (n=2)"])
        write_outputs(rows, self.root / "out")
        with (self.root / "out/runs.csv").open() as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 5)
        self.assertIn("running", (self.root / "out/summary.md").read_text())
        self.assertIn("outside comparison", (self.root / "out/table.md").read_text())

    def test_unresolved_local_index_is_not_guessed(self):
        unknown = copy.deepcopy(self.d)
        unknown["decisions"][1].pop("options")
        row = self.run_fixture("unknown", unknown)
        self.assertIsNone(row["first_plan_cover"])
        self.assertIsNone(row["first_assignments"]["r2"])
        unknown["scene"] = None
        row = self.run_fixture("legacy", unknown)
        self.assertTrue(row["physical_success"])
        self.assertIsNone(row["plan_cover"])

    def test_external_brain_enrichment_without_double_count(self):
        team = copy.deepcopy(self.d)
        team["decisions"][1].pop("options")
        self.run_fixture("t1-D-h", team)
        brain_path = self.root / "brain/t1-D-h"
        brain_path.mkdir(parents=True)
        (brain_path / "brain-record.json").write_text(json.dumps({
            "calls": 3, "cost_usd": 0.1, "messages": [{"from": "r2", "to": ["r1"]}],
            "decisions": {"r2": [dict(self.d["decisions"][1], time=0.001)]}}))
        row = analyze_run(self.root / "t1-D-h", self.scenes, self.root / "brain")
        self.assertTrue(row["first_plan_cover"])
        self.assertEqual(row["messages"], 1)
        self.assertEqual(row["llm_calls"], 3)
        self.assertEqual(row["cost_usd"], 0.1)


LCOLOURS = {"red", "blue"}
L_SCENE = {"id": "L", "type": "orders_concentrated",
           "boxes": [{"id": "a", "colour": "red"}, {"id": "b", "colour": "blue"}],
           "orders": [{"id": "o1", "colour": "red", "sign": 11, "count": 1},
                      {"id": "o2", "colour": "blue", "sign": 12, "count": 1}],
           "oracle_plan": {"r1": [["a", "o1"]], "r2": [["b", "o2"]]}}
C_SCENE = {"id": "C", "type": "same_colour_competition",
           "boxes": [{"id": "a", "colour": "blue"}, {"id": "b", "colour": "blue"}],
           "orders": [{"id": "o1", "colour": "blue", "sign": 11, "count": 1},
                      {"id": "o2", "colour": "blue", "sign": 12, "count": 1}],
           "oracle_plan": {"r1": [["a", "o2"]], "r2": [["b", "o1"]]}}
D_SCENE = {"id": "D", "type": "decoy_boxes",
           "boxes": [{"id": "a", "colour": "blue"}, {"id": "c", "colour": "red"}],
           "orders": [{"id": "o1", "colour": "red", "sign": 12, "count": 1}],
           "oracle_plan": {"r1": [], "r2": [["c", "o1"]]}}
DEST_T = 44.700000000133386   # r2 decides here, exactly as in the real L01 record


def envelope(sender, to, send, facts=None, text="hello", deliver=None):
    body = json.dumps({"facts": facts or [], "message": text})
    return {"time": send, "deliver_at": send + 2.0 if deliver is None else deliver,
            "from": sender, "to": [to], "text": body}


def order_fact(colour, zone, kind="orders", **value):
    return {"id": colour, "seen": 0, "table": kind, "value": dict({"box": colour, "zone": zone}, **value)}


class CauseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scenes = {"L": L_SCENE, "C": C_SCENE, "D": D_SCENE}

    def make_run(self, name, scene, choices, picks, knows, messages=None, calls=True,
                 own_dialogue=None, show=True):
        """picks: rid -> (colour, destination option or None, destination time)."""
        run = self.root / "runs" / name
        brain = self.root / "brain" / name
        run.mkdir(parents=True)
        brain.mkdir(parents=True)
        table = {o["id"]: o for o in scene["orders"]}
        team_rows, brain_rows, prompts = [], {}, []
        for rid, (colour, dest, when) in picks.items():
            sent = {"sent": []} if messages is not None else {}   # no record at all when None
            team_rows.append(dict({"t": 12.0, "rid": rid, "point": "pick", "options": ["box:0", "wait"],
                                   "option": "box:0", "calls": 3}, **sent))
            brain_rows.setdefault(rid, []).append({
                "time": 11.999999999989331, "point": "pick", "option": "box:0", "sent": [],
                "options": [{"key": "box:0", "text": "go grasp target object <%s box> (entry 0)" % colour}]})
            if dest:
                team_rows.append(dict({"t": round(when, 1), "rid": rid, "point": "destination",
                                       "options": [dest, "wait"], "option": dest, "calls": 3}, **sent))
                brain_rows[rid].append({"time": when, "point": "destination", "option": dest,
                                        "sent": [], "options": [{"key": dest, "text": "go"}]})
                prompts.append((rid, "destination", when, colour))
        team = {"status": "complete", "scene": scene["id"], "robots": ["r1", "r2"], "end_s": 100.0,
                "correct_boxes": 2, "required_boxes": 2, "wrong_place_boxes": 0,
                "knows": knows, "orders": [{"id": k, "colour": v["colour"],
                                            "dest": "sign" + str(v["sign"])} for k, v in table.items()],
                "choices": choices, "decisions": team_rows}
        (run / "team.json").write_text(json.dumps(team), encoding="utf-8")
        record = {"decisions": brain_rows, "calls": 6, "cost_usd": 0.0}
        if messages is not None:
            record["messages"] = messages
        (brain / "brain-record.json").write_text(json.dumps(record), encoding="utf-8")
        if calls:
            lines = []
            for index, (rid, point, when, colour) in enumerate(prompts):
                orders = [{"box": table[i]["colour"], "count": 1, "zone": "sign" + str(table[i]["sign"])}
                          for i in knows[rid]]
                shown = [m for m in (messages or []) if show and m["deliver_at"] <= when + 1e-6
                         and m["to"] == [rid]] + (own_dialogue or [] if rid == "r2" else [])
                progress = {"own_facts": [{"orders": orders, "progress": "x"},
                                          {"holding": colour, "progress": "y"}],
                            "point": point, "robot": rid, "roster": ["r1", "r2"], "time": when}
                prompt = ("My friends ... choose the best available action ...\nGoal: x\nProgress: "
                          + json.dumps(progress) + "\nDialogue history:\nAgent 1: \"Hi\"\n"
                          + json.dumps([{"from": m["from"], "text": m["text"], "time": m["time"]}
                                        for m in shown]) + "\nPrevious actions: []\nAvailable actions:\nA. x\n")
                base = {"raw_prompt": prompt, "call_index": 2 * index + 1}
                lines += [dict(base, event="start"), dict(base, event="finish"),   # start + 2 action calls
                          dict(base, event="finish", call_index=2 * index + 2)]
            (brain / "llm-calls.jsonl").write_text("\n".join(map(json.dumps, lines)), encoding="utf-8")
        return causes.analyze_causes(run, self.scenes, self.root / "brain")

    def l_run(self, name, r2_zone="zone:sign11", messages=None, calls=True, own_dialogue=None):
        sign_ = r2_zone.split(":")[1]
        return self.make_run(
            name, L_SCENE,
            {"r1": {"picked": "red", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "zone_" + sign_}},
            {"r1": ("red", "zone:sign11", 38.7), "r2": ("blue", r2_zone, DEST_T)},
            {"r1": ["o1", "o2"], "r2": []}, messages, calls, own_dialogue)

    def test_message_pair_parsing_sources_and_roles(self):
        text = json.dumps({"facts": [
            order_fact("blue", "sign12"),
            {"id": "blue2", "table": "assignments", "value": {"box": "blue", "robot": "r2", "zone": "sign12"}},
            {"id": "red", "table": "boxes", "value": {"colour": "red", "delivered": "sign11"}},
            {"id": "red", "table": "boxes", "value": {"colour": "red"}}],
            "message": "I'm taking red to sign11, not sign12. Please take the blue box to sign12."})
        pairs, ok = causes.message_pairs(text, LCOLOURS)
        self.assertTrue(ok)
        got = {(p["pair"], p["kind"], p["src"]) for p in pairs}
        self.assertIn((("blue", "sign12"), "order", "fact"), got)
        self.assertIn((("blue", "sign12"), "assignment", "fact"), got)
        self.assertIn((("red", "sign11"), "delivered", "fact"), got)
        self.assertIn((("red", "sign11"), "text_self", "text"), got)
        self.assertIn((("blue", "sign12"), "text_directive", "text"), got)
        self.assertNotIn((("red", "sign12"), "text_self", "text"), got)   # negated sign dropped
        plain, ok = causes.message_pairs("go to the door", LCOLOURS)
        self.assertEqual((plain, ok), ([], False))

    def test_grounding_classes_and_independent_flags(self):
        msg = lambda facts, sender="r1": {"from": sender, "to": {"r2"}, "send": 1.0, "deliver": 3.0,
                                         "pairs": causes.message_pairs(json.dumps({"facts": facts}), LCOLOURS)[0]}
        own = {("blue", "sign12")}
        kinds = lambda received, zone, own_=own: causes.classify(
            "destination", "blue", zone, own_, received, "r2", True)
        self.assertEqual(kinds([], "sign12")["label"], "own_order")
        self.assertEqual(kinds([], "sign11", set())["label"], "guess")
        said = [msg([order_fact("blue", "sign12")])]
        self.assertEqual(kinds(said, "sign12", set())["label"], "message")
        weak = kinds(said, "sign11", set())
        self.assertEqual((weak["label"], weak["weak"], weak["strong"]), ("conflicts_message", True, False))
        directive = [msg([order_fact("blue", "sign12", "assignments", robot="r2")])]
        strong = kinds(directive, "sign11", {("blue", "sign11")})
        self.assertEqual((strong["label"], strong["in_own"], strong["strong"]),
                         ("conflicts_message", True, True))      # own order AND contradicts a directive
        third = [msg([order_fact("blue", "sign12", "assignments", robot="r1")])]
        self.assertEqual(kinds(third, "sign11", set())["label"], "guess")   # sender's own intent
        intent = [msg([{"id": "blue", "table": "assignments", "value": {"colour": "blue", "zone": "sign11"}}])]
        # 2026-11-15 rule fix: a sender-intent pair is still a team-goal pair, so the same pair supports me
        self.assertEqual(kinds(intent, "sign11", set())["label"], "message")
        self.assertEqual(kinds(intent, "sign12", set())["label"], "guess")  # other sign: no support, no conflict
        self.assertEqual(causes.classify("destination", "blue", "sign11", None, [], "r2", True)["label"], "unknown")
        self.assertEqual(causes.classify("pick", "blue", None, {("blue", "sign12")}, [], "r2", True)["label"], "own_order")
        self.assertEqual(causes.classify("pick", "blue", None, set(), said, "r2", True)["label"], "message")
        self.assertEqual(causes.classify("pick", "blue", None, set(), [], "r2", True)["label"], "guess")

    REPORT = ("I've passed the door with the red box and I'm delivering it to the sign11 zone. "
              "I'll handle the blue box to sign12 next — you take the remaining red box in the box room.")

    def test_first_person_report_pair_grounds_destination(self):
        # real t1-L01-c1: r1 reported (73.9 s) "I'll handle the blue box to sign12 next"; r2 then chose sign12
        pairs, _ = causes.message_pairs(json.dumps({"facts": [], "message": self.REPORT}), LCOLOURS)
        self.assertIn((("blue", "sign12"), "text_self"), {(p["pair"], p["kind"]) for p in pairs})
        row = self.l_run("t1-L-r", r2_zone="zone:sign12",
                         messages=[envelope("r1", "r2", 40.0, [], self.REPORT, deliver=42.0)])
        labels = [e["label"] for e in row["events"] if e["kind"] == "destination" and e["rid"] == "r2"]
        self.assertEqual(labels, ["message"])
        self.assertEqual(row["success_class"], "message_grounded")
        late = self.l_run("t1-L-s", r2_zone="zone:sign12",       # delivered after the decision: no support
                          messages=[envelope("r1", "r2", 44.0, [], self.REPORT, deliver=DEST_T + 0.5)])
        self.assertEqual(late["success_class"], "guess_correct")

    def test_first_person_pair_needs_same_colour_and_sign_and_never_conflicts(self):
        msg = lambda text: {"from": "r1", "to": {"r2"}, "send": 1.0, "deliver": 3.0,
                            "pairs": causes.message_pairs(json.dumps({"facts": [], "message": text}), LCOLOURS)[0]}
        label = lambda text, zone, kind="destination": causes.classify(
            kind, "blue", zone if kind == "destination" else None, set(), [msg(text)], "r2", True)
        self.assertEqual(label("I'll handle the blue box to sign12 next", "sign12")["label"], "message")
        other_colour = label("I'll handle the red box to sign12 next", "sign12")
        self.assertEqual((other_colour["label"], other_colour["support"]), ("guess", False))
        other_sign = label("I'll handle the blue box to sign11 next", "sign12")
        self.assertEqual((other_sign["label"], other_sign["support"], other_sign["weak"]), ("guess", False, False))
        for negated in ("I'll handle the blue box, not sign12", "Blue goes to sign11 instead of sign12"):
            self.assertFalse(label(negated, "sign12")["support"], negated)    # negated sign still dropped
        self.assertEqual(label("I'll handle the blue box to sign12 next", None, "pick")["label"], "guess")
        third = {"from": "r1", "to": {"r2"}, "send": 1.0, "deliver": 3.0, "pairs": causes.message_pairs(
            json.dumps({"facts": [order_fact("blue", "sign12", "assignments", robot="r3")]}), LCOLOURS)[0]}
        self.assertEqual(causes.classify("destination", "blue", "sign12", set(), [third], "r2", True)["label"],
                         "guess")                                            # about a third robot: ignored

    def test_first_person_pair_counts_as_needed_fact_in_info_status(self):
        row = self.l_run("t1-L-t", messages=[envelope("r1", "r2", 40.0, [], self.REPORT, deliver=42.0)])
        self.assertIn("ignored", row["tags"])          # r2 kept blue->sign11 after being told blue->sign12
        late = self.l_run("t1-L-u", messages=[envelope("r1", "r2", 44.0, [], self.REPORT, deliver=DEST_T + 0.5)])
        self.assertIn("late", late["tags"])

    def test_not_sent_and_guess_wrong(self):
        row = self.l_run("t1-L-a", messages=[])
        self.assertFalse(row["plan_cover"])
        self.assertEqual(set(row["tags"]), {"not_sent", "guess_wrong"})
        self.assertEqual(row["primary"], "not_sent")
        self.assertEqual(row["evidence"][0]["robot"], "r2")
        self.assertEqual(row["evidence"][0]["call_index"], 3)   # first action call, start/duplicate rows skipped

    def test_late_vs_ignored_boundary_and_own_dialogue(self):
        fact = [order_fact("blue", "sign12")]
        just_after = envelope("r1", "r2", DEST_T - 2.0 + 0.1, fact)   # delivered 0.1 s after the decision
        row = self.l_run("t1-L-b", messages=[just_after])
        self.assertIn("late", row["tags"])
        self.assertNotIn("ignored", row["tags"])
        self.assertEqual(row["primary"], "late")
        before = envelope("r1", "r2", 42.7, fact, deliver=DEST_T - 1e-11)   # real-data margin
        own = {"from": "r2", "time": 12.0, "text": "my own earlier message"}
        row = self.l_run("t1-L-c", messages=[before], own_dialogue=[own])
        self.assertIn("ignored", row["tags"])
        self.assertNotIn("guess_wrong", row["tags"])     # contradicted a message, so not a guess
        self.assertEqual(row["primary"], "ignored")
        labels = [e["label"] for e in row["events"] if e["kind"] == "destination" and e["rid"] == "r2"]
        self.assertEqual(labels, ["conflicts_message"])
        self.assertFalse(any(e["prompt_mismatch"] for e in row["events"]))   # own message ignored in check
        self.assertEqual(row["evidence"][0]["messages"][0]["from"], "r1")

    def test_prompt_timing_disagreement_is_flagged(self):
        message = envelope("r1", "r2", 42.7, [order_fact("blue", "sign12")], deliver=DEST_T - 1e-11)
        row = self.make_run(
            "t1-L-d", L_SCENE,
            {"r1": {"picked": "red", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "zone_sign11"}},
            {"r1": ("red", "zone:sign11", 38.7), "r2": ("blue", "zone:sign11", DEST_T)},
            {"r1": ["o1", "o2"], "r2": []}, [message], show=False)   # delivered, but absent from prompt
        self.assertTrue(any(e["prompt_mismatch"] for e in row["events"]))
        self.assertIn("other", row["tags"])
        self.assertIn("ignored", row["tags"])    # flagged, not silently reclassified
        self.assertEqual(row["primary"], "other")

    def test_peer_intent_message_is_not_the_needed_fact(self):
        intent = envelope("r1", "r2", 30.0, [order_fact("red", "sign11", "assignments")],
                          "I'm holding red, heading to sign11.", deliver=DEST_T - 1.0)
        row = self.l_run("t1-L-m", messages=[intent])
        self.assertEqual(set(row["tags"]), {"not_sent", "guess_wrong"})   # blue->sign12 never sent
        self.assertNotIn("ignored", row["tags"])

    def test_late_evidence_records_send_time_relation(self):
        row = self.l_run("t1-L-n", messages=[envelope("r1", "r2", 110.0, [order_fact("blue", "sign12")])])
        hit = row["evidence"][0]["messages"][0]
        self.assertFalse(hit["sent_before_decision"])
        self.assertEqual(row["primary"], "late")

    def test_surplus_only_decoy_run(self):
        choices = {"r1": {"picked": "red", "dest": "zone_sign12"}, "r2": {"picked": "blue", "dest": "zone_sign11"}}
        picks = {"r1": ("red", "zone:sign12", 40.0), "r2": ("blue", "zone:sign11", DEST_T)}
        knows = {"r1": ["o1"], "r2": []}
        bare = self.make_run("t1-D-a", D_SCENE, choices, picks, knows, [])
        self.assertFalse(bare["plan_cover"])
        self.assertEqual(set(bare["tags"]), {"not_sent", "guess_wrong"})   # nothing missing, a decoy carried
        claim = envelope("r1", "r2", 30.0, [order_fact("red", "sign12", "assignments")],
                         "I'm taking red to sign12.", deliver=32.0)
        told = self.make_run("t1-D-b", D_SCENE, choices, picks, knows, [claim])
        self.assertEqual(set(told["tags"]), {"ignored", "guess_wrong"})
        self.assertEqual(told["primary"], "ignored")
        t0 = self.make_run("t0-D-a", D_SCENE, choices, picks, knows)
        self.assertEqual(set(t0["tags"]), {"no_info_T0", "guess_wrong"})

    def test_no_info_t0(self):
        row = self.l_run("t0-L-a")
        self.assertEqual(set(row["tags"]), {"no_info_T0", "guess_wrong"})
        self.assertEqual(row["primary"], "no_info_T0")

    def test_other_and_unknown(self):
        idle = self.make_run("t1-L-f", L_SCENE, {"r1": {"picked": None}, "r2": {"picked": None}},
                             {"r1": ("red", None, 0), "r2": ("blue", None, 0)},
                             {"r1": ["o1", "o2"], "r2": []}, [])
        self.assertIn("other", idle["tags"])
        self.assertTrue(any(e["reason"].startswith("owner of a missing order") for e in idle["evidence"]))
        unknown = self.l_run("t1-L-g", messages=None)
        self.assertIn("other", unknown["tags"])
        self.assertTrue(any(e["label"] == "unknown" for e in unknown["events"]
                            if e["kind"] == "destination"))
        self.assertNotIn("guess_wrong", unknown["tags"])

    def test_c_scene_duplicate_ignored_directive_overrides_own_order(self):
        directive = envelope("r1", "r2", 40.6,
                             [order_fact("blue", "sign12", "assignments", robot="r2")], deliver=42.6)
        row = self.make_run(
            "t1-C-a", C_SCENE,
            {"r1": {"picked": "blue", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "zone_sign11"}},
            {"r1": ("blue", "zone:sign11", 42.6), "r2": ("blue", "zone:sign11", DEST_T)},
            {"r1": ["o1", "o2"], "r2": ["o1"]}, [directive])
        self.assertFalse(row["plan_cover"])
        self.assertEqual(row["primary"], "ignored")
        r2 = next(e for e in row["events"] if e["rid"] == "r2" and e["kind"] == "destination")
        self.assertEqual((r2["label"], r2["in_own"], r2["strong"]), ("conflicts_message", True, True))
        self.assertIn("not_sent", row["tags"])    # r2 never told r1 anything before r1 decided
        t0 = self.make_run(
            "t0-C-a", C_SCENE,
            {"r1": {"picked": "blue", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "zone_sign11"}},
            {"r1": ("blue", "zone:sign11", 42.6), "r2": ("blue", "zone:sign11", DEST_T)},
            {"r1": ["o1", "o2"], "r2": ["o1"]})
        self.assertEqual(t0["tags"], ["no_info_T0"])

    def test_success_classes_keep_guess_correct_apart(self):
        guess = self.l_run("t1-L-h", r2_zone="zone:sign12", messages=[])
        self.assertTrue(guess["plan_cover"])
        self.assertEqual(guess["success_class"], "guess_correct")
        followed = self.l_run("t1-L-i", r2_zone="zone:sign12", messages=[
            envelope("r1", "r2", 10.0, [order_fact("blue", "sign12")])])
        self.assertEqual(followed["success_class"], "message_grounded")
        own = self.make_run(
            "t1-C-b", C_SCENE,
            {"r1": {"picked": "blue", "dest": "zone_sign12"}, "r2": {"picked": "blue", "dest": "zone_sign11"}},
            {"r1": ("blue", "zone:sign12", 42.6), "r2": ("blue", "zone:sign11", DEST_T)},
            {"r1": ["o1", "o2"], "r2": ["o1"]}, [])
        self.assertEqual(own["success_class"], "own_only")

    def test_outputs_count_exclusions_and_separate_guess_successes(self):
        rows = [self.l_run("t1-L-j", r2_zone="zone:sign12", messages=[]),
                self.l_run("t0-L-b"), self.l_run("t1-L-k", messages=[])]
        skipped = causes.analyze_causes(self.root / "runs/missing", self.scenes, self.root / "brain")
        (self.root / "runs/t2-L-z").mkdir()
        (self.root / "runs/t2-L-z/team.json").write_text(json.dumps({"status": "running", "scene": "L"}))
        rows += [skipped, causes.analyze_causes(self.root / "runs/t2-L-z", self.scenes, self.root / "brain")]
        causes.write_outputs(rows, self.root / "out")
        text = (self.root / "out/causes.md").read_text()
        self.assertIn("analysed 3", text)
        self.assertIn("running", text)
        with (self.root / "out/causes.csv").open() as stream:
            table = {r["run"]: r for r in csv.DictReader(stream)}
        self.assertEqual(table["t1-L-j"]["success_class"], "guess_correct")
        self.assertEqual(table["t0-L-b"]["primary_cause"], "no_info_T0")
        self.assertEqual(table["t1-L-k"]["tags"], "not_sent|guess_wrong")
        with (self.root / "out/choices.csv").open() as stream:
            self.assertTrue(any(r["label"] == "guess" for r in csv.DictReader(stream)))

    # ---- put_down (choices.dest == 'put_down'): an empty assignment for C, counted apart, 'dropped_needed' when it was needed
    def put_run(self, name, scene, r1, r2_colour, knows, messages, r2_when=DEST_T, r1_dest=None):
        picks = {"r1": (r1[0], r1[1], 38.7), "r2": (r2_colour, "put_down", r2_when)}
        choices = {"r1": {"picked": r1[0], "dest": "zone_" + r1[1].split(":")[1]},
                   "r2": {"picked": r2_colour, "dest": "put_down"}}
        return self.make_run(name, scene, choices, picks, knows, messages)

    def test_put_down_of_a_decoy_is_an_empty_assignment_and_counted_as_decoy(self):
        row = self.put_run("t1-D-p", D_SCENE, ("red", "zone:sign12"), "blue", {"r1": ["o1"], "r2": []}, [])
        self.assertTrue(row["plan_cover"])                                  # r2 put the decoy down: not a wrong carry
        self.assertEqual(row["tags"], [])
        self.assertEqual(row["success_class"], "own_only")                  # r1's own order; r2's put-down is no destination
        self.assertEqual([(p["rid"], p["colour"], p["kind"]) for p in row["put_downs"]], [("r2", "blue", "decoy")])
        self.assertEqual([e["kind"] for e in row["events"] if e["rid"] == "r2"], ["pick", "put_down"])
        self.assertEqual(next(e for e in row["events"] if e["kind"] == "put_down")["label"], "put_down")
        carried = self.make_run("t1-D-c", D_SCENE, {"r1": {"picked": "red", "dest": "zone_sign12"},
                                                    "r2": {"picked": "blue", "dest": "zone_sign11"}},
                                {"r1": ("red", "zone:sign12", 40.0), "r2": ("blue", "zone:sign11", DEST_T)},
                                {"r1": ["o1"], "r2": []}, [])
        self.assertFalse(carried["plan_cover"])                             # carrying the decoy to a zone is still wrong
        self.assertEqual(carried["put_downs"], [])

    def test_lost_put_down_team_only_keeps_the_information_cause_and_adds_dropped_needed(self):
        knows = {"r1": ["o1", "o2"], "r2": []}                              # r1 knows both orders, r2 knows none
        t1 = self.put_run("t1-L-p", L_SCENE, ("red", "zone:sign11"), "blue", knows, [])
        self.assertFalse(t1["plan_cover"])
        self.assertEqual([(p["kind"], p["knew"], p["pair"]) for p in t1["put_downs"]],
                         [("lost", "team_only", ["blue", "sign12"])])
        self.assertEqual(set(t1["tags"]), {"dropped_needed", "not_sent"})
        self.assertEqual(t1["primary"], "not_sent")                         # precedence: the information gap explains it
        t0 = self.put_run("t0-L-p", L_SCENE, ("red", "zone:sign11"), "blue", knows, None)
        self.assertEqual(set(t0["tags"]), {"dropped_needed", "no_info_T0"})
        self.assertEqual(t0["primary"], "no_info_T0")
        told = envelope("r1", "r2", 30.0, [order_fact("blue", "sign12")], "blue goes to sign12", deliver=32.0)
        heard = self.put_run("t1-L-q", L_SCENE, ("red", "zone:sign11"), "blue", knows, [told])
        self.assertEqual(set(heard["tags"]), {"dropped_needed", "ignored"})  # told in time, put it down anyway

    def test_lost_put_down_of_an_own_order_is_dropped_needed_alone(self):
        row = self.put_run("t1-L-r", L_SCENE, ("red", "zone:sign11"), "blue", {"r1": ["o1"], "r2": ["o2"]}, [])
        self.assertEqual([(p["kind"], p["knew"]) for p in row["put_downs"]], [("lost", "own_order")])
        self.assertEqual(row["tags"], ["dropped_needed"])
        self.assertEqual(row["primary"], "dropped_needed")
        t0 = self.put_run("t0-L-r", L_SCENE, ("red", "zone:sign11"), "blue", {"r1": ["o1"], "r2": ["o2"]}, None)
        self.assertEqual((t0["tags"], t0["primary"]), (["dropped_needed"], "dropped_needed"))


class PutDownRules(unittest.TestCase):
    """Hand-built records: (colour, 'put_down') is an empty assignment; decoy / duplicate / lost with three robots."""
    def team(self, choices, knows=None):
        return {"robots": sorted(choices), "choices": choices, "knows": knows,
                "orders": [{"id": "o1", "colour": "blue", "dest": "sign11"}, {"id": "o2", "colour": "blue", "dest": "sign12"},
                           {"id": "o3", "colour": "red", "dest": "sign13"}]}

    scene = {"id": "S", "boxes": [{"id": "a", "colour": "blue"}, {"id": "b", "colour": "blue"}, {"id": "c", "colour": "red"},
                                  {"id": "d", "colour": "green"}],
             "orders": [{"id": "o1", "colour": "blue", "sign": 11, "count": 1}, {"id": "o2", "colour": "blue", "sign": 12, "count": 1},
                        {"id": "o3", "colour": "red", "sign": 13, "count": 1}],
             "oracle_plan": {"r1": [["a", "o1"]], "r2": [["b", "o2"]], "r3": [["c", "o3"]]}}

    def test_assignments_and_judge_treat_put_down_as_empty(self):
        import compare
        choices = {"r1": {"picked": "blue", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "put_down"},
                   "r3": {"picked": "green", "dest": "put_down"}}
        plan = compare.assignments(choices, ["r1", "r2", "r3"])
        self.assertEqual(plan, {"r1": [("blue", "sign11")], "r2": [], "r3": []})
        self.assertEqual(compare.assignments({"r1": {}}, ["r1"]), {"r1": None})   # no pick record: still unknown
        full = {"r1": [("blue", "sign11")], "r2": [("blue", "sign12")], "r3": [("red", "sign13")]}
        self.assertEqual(compare.judge(full, self.scene)[0], True)
        self.assertEqual(compare.judge(plan, self.scene)[0], False)        # missing orders: not covered either way
        extra = dict(full, r3=[("red", "sign13")])
        extra["r2"] = []
        self.assertEqual(compare.judge(extra, self.scene)[0], False)

    def test_first_assignment_put_down_at_first_destination_decision_is_empty(self):
        import compare
        def row(option, when):
            return [{"rid": "r1", "t": 1.0, "point": "pick", "option": "box:0", "colour": "blue", "sent": []},
                    {"rid": "r1", "t": when, "point": "destination", "option": option, "sent": []}]
        team = {"decisions": row("put_down", 2.0)}
        first, evidence = compare.first_assignments(team, {}, ["r1"])
        self.assertEqual(first["r1"], [])
        zone = {"decisions": row("zone:sign11", 2.0) + [{"rid": "r1", "t": 3.0, "point": "door", "option": "put_down", "sent": []}]}
        first, _ = compare.first_assignments(zone, {}, ["r1"])
        self.assertEqual(first["r1"], [("blue", "sign11")])               # put down later at the door: first plan stays

    def test_classify_decoy_duplicate_lost_with_allocation(self):
        last = {"r1": [("blue", "sign12")], "r2": [], "r3": []}
        team = self.team({"r1": {"picked": "blue", "dest": "zone_sign12"}, "r2": {"picked": "green", "dest": "put_down"},
                          "r3": {"picked": "red", "dest": "put_down"}}, knows={"r1": ["o2"], "r2": [], "r3": ["o3"]})
        kinds = {p["rid"]: p for p in causes.classify_put_downs(team, self.scene, ["r1", "r2", "r3"], last)}
        self.assertEqual(kinds["r2"]["kind"], "decoy")                     # no green order
        self.assertEqual((kinds["r3"]["kind"], kinds["r3"]["knew"], kinds["r3"]["pair"]), ("lost", "own_order", ["red", "sign13"]))
        self.assertNotIn("r1", kinds)
        # duplicate: the colour is ordered and nothing of it is missing; two put-downs, one missing pair -> first one is lost
        last = {"r1": [("blue", "sign12")], "r2": [("red", "sign13")], "r3": []}
        team = self.team({"r1": {"picked": "blue", "dest": "zone_sign12"}, "r2": {"picked": "red", "dest": "zone_sign13"},
                          "r3": {"picked": "red", "dest": "put_down"}})
        self.assertEqual([p["kind"] for p in causes.classify_put_downs(team, self.scene, ["r1", "r2", "r3"], last)], ["duplicate"])
        last = {"r1": [("blue", "sign12")], "r2": [], "r3": [("red", "sign13")]}
        team = self.team({"r1": {"picked": "blue", "dest": "zone_sign12"}, "r2": {"picked": "blue", "dest": "put_down"},
                          "r3": {"picked": "red", "dest": "zone_sign13"}}, knows={"r1": ["o2"], "r2": ["o2"], "r3": ["o3"]})
        found = causes.classify_put_downs(team, self.scene, ["r1", "r2", "r3"], last)
        self.assertEqual([(p["kind"], p["knew"], p["pair"]) for p in found], [("lost", "team_only", ["blue", "sign11"])])   # r2 knows only o2
        team["knows"] = None
        self.assertEqual(causes.classify_put_downs(team, self.scene, ["r1", "r2", "r3"], last)[0]["knew"], "unknown")
        both = {"r1": [("blue", "sign12")], "r2": [], "r3": []}            # blue sign11 missing once, two blue put-downs
        team = self.team({"r1": {"picked": "blue", "dest": "zone_sign12"}, "r2": {"picked": "blue", "dest": "put_down"},
                          "r3": {"picked": "blue", "dest": "put_down"}})
        both_rows = causes.classify_put_downs(team, dict(self.scene, orders=self.scene["orders"][:2]), ["r1", "r2", "r3"], both)
        self.assertEqual([(p["rid"], p["kind"]) for p in both_rows], [("r2", "lost"), ("r3", "duplicate")])


if __name__ == "__main__":
    unittest.main()
