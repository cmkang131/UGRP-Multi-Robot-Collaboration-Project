import contextlib
import csv
import io
import json
import shutil
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import analyze_main as am
import compare

HERE = Path(__file__).resolve().parent


def scene(sid, type_code, control=False):
    return {"id": sid, "type": "x", "type_code": type_code, "control": control,
            "boxes": [{"id": "a", "colour": "red"}, {"id": "b", "colour": "blue"}],
            "orders": [{"id": "o1", "colour": "red", "sign": 11, "count": 1},
                       {"id": "o2", "colour": "blue", "sign": 12, "count": 1}],
            "oracle_plan": {"r1": [["a", "o1"]], "r2": [["b", "o2"]]}}


def team(scene_id, cover=True, status="complete", brain=None, knows=None, success=True):
    choices = {"r1": {"picked": "red", "dest": "zone_sign11"},
               "r2": {"picked": "blue", "dest": "zone_sign12" if cover else "zone_sign11"}}
    data = {"status": status, "scene": scene_id, "robots": ["r1", "r2"], "choices": choices, "decisions": [],
            "correct_boxes": 2 if success else 1, "required_boxes": 2, "wrong_place_boxes": 0, "end_s": 200.0,
            "knows": knows or {"r1": ["o1"], "r2": ["o2"]}, "orders": [], "brain": brain or {}}
    if status != "complete":
        for key in ("correct_boxes", "required_boxes", "wrong_place_boxes", "end_s", "choices"):
            data.pop(key)
    return data


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.scene_ids = ["L2-01", "C2-01", "X2-01"]
        self.scene_file = self.root / "scenes.json"
        self.scene_file.write_text(json.dumps({"scenes": [scene("L2-01", "L"), scene("C2-01", "C"),
                                                          scene("X2-01", "X", control=True)]}), encoding="utf-8")

    def make(self, name, data=None, brain=None, where=None):
        path = (where or self.runs) / name
        path.mkdir(parents=True, exist_ok=True)
        if data is not None:
            (path / "team.json").write_text(json.dumps(data), encoding="utf-8")
        if brain is not None:
            (path / "brain").mkdir(exist_ok=True)
            (path / "brain" / "brain-record.json").write_text(json.dumps(brain), encoding="utf-8")
        return path

    def analyze(self, *extra, runs=None):
        args = am.parse(["--runs", str(runs or self.runs), "--scenes", str(self.scene_file), "--name", "t",
                         "--boots", "200"] + list(extra))
        cells, text, tests, by_type, cond, inputs = am.analyze(args)
        return args, cells, text, tests

    def cell(self, cells, run_id):
        return next(c for c in cells if c["run_id"] == run_id)


class Statistics(unittest.TestCase):
    def test_sign_test_hand_values(self):
        self.assertAlmostEqual(am.sign_test_p(5, 5), 2 / 32)                 # 2 * (1/32)
        self.assertAlmostEqual(am.sign_test_p(0, 4), 2 / 16)
        self.assertAlmostEqual(am.sign_test_p(5, 6), 2 * 7 / 64)             # P(Bin(6,.5) <= 1) = 7/64
        self.assertAlmostEqual(am.sign_test_p(9, 10), 2 * 11 / 1024)         # P(Bin(10,.5) <= 1) = 11/1024
        self.assertEqual(am.sign_test_p(2, 4), 1.0)                          # centre, clipped to 1
        self.assertEqual(am.sign_test_p(1, 2), 1.0)
        self.assertEqual(am.sign_test_p(0, 0), 1.0)                          # all ties
        self.assertAlmostEqual(am.sign_test_p(16, 16), 2 / 2 ** 16)          # REVIEW-2: 3.05e-5
        self.assertAlmostEqual(am.sign_test_p(19, 20), 42 / 2 ** 20)         # REVIEW-2: 19 pos, 1 neg: 4.0e-5

    def test_holm_hand_values(self):
        none = am.holm([0.03, 0.04])      # .03 > .05/2 -> stop; .04 < .05 is NOT rejected
        self.assertEqual([d["reject"] for d in none], [False, False])
        both = am.holm([0.04, 0.01])      # input order is kept
        self.assertEqual([d["reject"] for d in both], [True, True])
        self.assertAlmostEqual(both[1]["adj_p"], 0.02)
        self.assertAlmostEqual(both[0]["adj_p"], 0.04)
        one = am.holm([0.02, 0.06])
        self.assertEqual([d["reject"] for d in one], [True, False])
        self.assertAlmostEqual(one[0]["threshold"], 0.025)
        self.assertEqual(am.holm([0.2])[0]["adj_p"], 0.2)

    def test_percentile_rule(self):
        values = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(am.percentile(values, 0.5), 3)
        self.assertAlmostEqual(am.percentile(values, 0.25), 2)
        self.assertAlmostEqual(am.percentile(values, 0.025), 1.1)            # position 0.1 between 1 and 2
        self.assertAlmostEqual(am.percentile(values, 0.975), 4.9)
        self.assertEqual(am.percentile([7], 0.9), 7)

    def test_bootstrap_reproducible_and_bounded(self):
        values = [1.0, 0.5, 0.0, 0.0, 0.5, 1.0, 0.0]
        first = am.bootstrap_ci(values, 500, 123)
        am._CI_CACHE.clear()
        self.assertEqual(first, am.bootstrap_ci(values, 500, 123))           # same seed, same interval (no cache)
        self.assertTrue(any(am.bootstrap_ci(values, 500, other) != first for other in (124, 125, 126, 127)))
        self.assertTrue(min(values) <= first[0] <= first[1] <= max(values))
        self.assertEqual(am.bootstrap_ci([1.0] * 4, 300, 7), (1.0, 1.0))      # constant effect: degenerate interval
        self.assertEqual(am.bootstrap_ci([0.0] * 4, 300, 7), (0.0, 0.0))
        self.assertIsNone(am.bootstrap_ci([], 10, 1))

    def test_paired_counts_and_exact_means(self):
        first = {"s1": Fraction(1, 2), "s2": Fraction(0), "s3": Fraction(1), "s4": Fraction(1, 3)}
        second = {"s1": Fraction(1), "s2": Fraction(0), "s3": Fraction(0), "s5": Fraction(1)}
        result = am.paired(first, second, boots=100)
        self.assertEqual((result["n_scenes"], result["pos"], result["neg"], result["tie"]), (3, 1, 1, 1))
        self.assertAlmostEqual(result["p"], 1.0)
        self.assertAlmostEqual(result["mean_D"], (0.5 - 1 + 0) / 3)
        self.assertEqual(result["ci95"] is not None, True)


class Penalty(Base):
    """Message-penalty score SP = max(0, C - lambda * max(0, M - 2R)). All expected values are hand arithmetic."""
    L05, L02, L10 = Fraction(1, 20), Fraction(1, 50), Fraction(1, 10)

    def test_formula_hand_values(self):
        pen = am.penalized
        self.assertEqual(am.PENALTY_LAMBDAS, {"SP05": self.L05, "SP02": self.L02, "SP10": self.L10})
        self.assertEqual(am.PENALTY_ALLOWANCE, 2)
        for lam in (self.L05, self.L02, self.L10):                       # M <= 2R = 4: no penalty
            self.assertEqual((pen(1, 0, 2, lam), pen(1, 4, 2, lam)), (1, 1))
        self.assertEqual(pen(1, 6, 2, self.L05), Fraction(9, 10))        # excess 2: 1 - 0.05*2
        self.assertEqual(pen(1, 6, 2, self.L02), Fraction(24, 25))       # 1 - 0.02*2 = 0.96
        self.assertEqual(pen(1, 6, 2, self.L10), Fraction(4, 5))         # 1 - 0.10*2 = 0.8
        self.assertEqual(pen(1, 16, 2, self.L05), Fraction(2, 5))        # both robots at the cap 8: excess 12, 1 - 0.6
        self.assertEqual(pen(1, 16, 2, self.L02), Fraction(19, 25))      # 1 - 0.24 = 0.76
        self.assertEqual(pen(1, 16, 2, self.L10), 0)                     # 1 - 1.2 < 0: floor 0
        self.assertEqual(pen(1, 30, 2, self.L05), 0)                     # 1 - 1.3 < 0: floor 0
        self.assertEqual(pen(0, 0, 2, self.L05), 0)                      # C = 0 stays 0 for any M
        self.assertEqual(pen(0, 16, 2, self.L10), 0)
        self.assertEqual(pen(1, 6, 3, self.L05), 1)                      # R = 3: allowance 6
        self.assertEqual(pen(1, 8, 3, self.L05), Fraction(9, 10))        # excess 2
        self.assertIsNone(pen(1, None, 2, self.L05))                     # unknown M is not read as 0
        self.assertIsNone(pen(None, 3, 2, self.L05))

    def test_cells_read_m_from_brain_record(self):
        def msgs(n):
            return [{"from": "r1" if i % 2 == 0 else "r2", "to": ["r2" if i % 2 == 0 else "r1"], "time": 10.0 + i,
                     "deliver_at": 12.0 + i, "text": "x"} for i in range(n)]
        self.make("t0-L2-01-c1", team("L2-01"), brain={"messages": []})
        self.make("t1-L2-01-c1", team("L2-01"), brain={"messages": msgs(6)})
        self.make("t1-C2-01-c1", team("C2-01"), brain={"messages": msgs(16)})
        self.make("t1-X2-01-c1", team("X2-01", cover=False), brain={"messages": msgs(10)})
        self.make("t2-L2-01-c1", team("L2-01"), brain={"messages": msgs(4)})
        self.make("t2-C2-01-c1", team("C2-01"))                                   # no message record at all
        _, cells, _, _ = self.analyze()
        t0, six, sixteen = self.cell(cells, "t0-L2-01-c1"), self.cell(cells, "t1-L2-01-c1"), self.cell(cells, "t1-C2-01-c1")
        self.assertEqual((t0["M"], t0["C"], t0["SP05"], t0["SP02"], t0["SP10"]), (0, 1, 1, 1, 1))   # T0: SP = C
        self.assertEqual((six["M"], six["n_robots"], six["M_max_robot"]), (6, 2, 3))
        self.assertEqual((six["SP05"], six["SP02"], six["SP10"]), (Fraction(9, 10), Fraction(24, 25), Fraction(4, 5)))
        self.assertEqual((sixteen["SP05"], sixteen["SP02"], sixteen["SP10"]), (Fraction(2, 5), Fraction(19, 25), 0))
        lost = self.cell(cells, "t1-X2-01-c1")
        self.assertEqual((lost["C"], lost["M"], lost["SP05"], lost["SP10"]), (0, 10, 0, 0))     # C = 0: SP = 0
        edge = self.cell(cells, "t2-L2-01-c1")
        self.assertEqual((edge["M"], edge["SP10"]), (4, 1))                                    # exactly the allowance
        unknown = self.cell(cells, "t2-C2-01-c1")
        self.assertEqual((unknown["state"], unknown["M"], unknown["SP05"]), ("ok", None, None))
        self.assertTrue(any("message count unknown" in w for w in unknown["warnings"]))
        book = am.Book(cells)
        self.assertEqual(book.scene_means("T2", "SP05", "zero"), {"L2-01": Fraction(1)})        # NA cell leaves the mean
        self.assertEqual(book.scene_means("T1", "SP05", "zero")["L2-01"], Fraction(9, 10))
        self.assertEqual(book.scene_means("T1", "SP05", "zero")["X2-01"], 0)

    def test_failed_cells_follow_the_mode_and_plan_na_is_not_the_physical_exception(self):
        self.make("t1-L2-01-c1", team("L2-01"), brain={"messages": [{"from": "r1"}] * 6})
        self.make("t1-L2-01-c2")                                                  # crash
        _, cells, _, _ = self.analyze()
        book = am.Book(cells)
        self.assertEqual(book.scene_means("T1", "SP05", "zero")["L2-01"], Fraction(9, 10) / 2)
        self.assertEqual(book.scene_means("T1", "SP05", "drop")["L2-01"], Fraction(9, 10))
        self.assertEqual(book.scene_means("T1", "SP05", "one")["L2-01"], Fraction(19, 20))
        na = dict(cells[0], state="plan_na", SP05=None, S=1)
        self.assertIsNone(am.Book([na]).value(na, "SP05", "zero"))                # plan NA: no score (S would be 1)
        self.assertEqual(am.Book([na]).value(na, "S", "zero"), 1)

    def test_all_ties_in_c_but_all_negative_in_sp(self):
        """6 scenes, T0 and T1 both cover everything (C ties, p = 1) but T1 sends 6 messages (SP05 = 0.9)."""
        scene_ids = ["s%d" % i for i in range(6)]
        cells = []
        for structure, m in (("T0", 0), ("T1", 6), ("T2", 0)):
            for sid in scene_ids:
                cell = dict(am.evaluate_stub(), state="ok", arm="mainA", group="mainA", scene=sid, structure=structure, rep=1,
                            C=1, G=1, S=1, M=m, n_robots=2)
                for key, lam in am.PENALTY_LAMBDAS.items():
                    cell[key] = am.penalized(1, m, 2, lam)
                cells.append(cell)
        args = am.parse(["--runs", str(self.runs), "--scenes", str(self.scene_file), "--name", "t", "--boots", "100"])
        tests, _ = am.run_tests(am.Book(cells), cells, {s: {} for s in scene_ids}, args)

        def pick(metric, contrast):
            return next(t for t in tests if t["metric"] == metric and t["mode"] == "zero" and t["variant"] == "all"
                        and t["contrast"] == contrast)
        c01, c02 = pick("C", "T0->T1"), pick("C", "T0->T2")
        self.assertEqual((c01["pos"], c01["neg"], c01["tie"], c01["p"]), (0, 0, 6, 1.0))
        sp01, sp02 = pick("SP05", "T0->T1"), pick("SP05", "T0->T2")
        self.assertEqual((sp01["pos"], sp01["neg"], sp01["tie"]), (0, 6, 0))
        self.assertAlmostEqual(sp01["p"], 2 / 64)                                  # 2 * P(Bin(6,.5) <= 0)
        self.assertAlmostEqual(sp01["mean_D"], -0.1)
        self.assertEqual((sp02["m"], sp02["p"]), (0, 1.0))                         # T2 sends nothing: ties
        # SP has its own Holm family of two: smallest p against .05/2, adjusted = 2 * 2/64
        self.assertEqual((sp01["family_size"], sp02["family_size"], c01["family_size"]), (2, 2, 2))
        self.assertAlmostEqual(sp01["holm_adj_p"], 2 * 2 / 64)
        self.assertAlmostEqual(sp01["holm_threshold"], 0.025)
        self.assertFalse(sp01["holm_reject"])                                      # 0.03125 > 0.025
        self.assertEqual(c01["holm_adj_p"], 1.0)                                   # C family is untouched by SP
        # lambda changes the mean D but not the sign pattern, so p stays the same
        self.assertAlmostEqual(pick("SP02", "T0->T1")["mean_D"], -0.04)
        self.assertAlmostEqual(pick("SP10", "T0->T1")["mean_D"], -0.2)
        self.assertEqual(pick("SP10", "T0->T1")["p"], sp01["p"])


class SpVerdictAndBreakEven(Base):
    """2026-11-16: SP verdict = mean D with the scene bootstrap interval (C keeps the sign test); break-even lambda*.
    Every expected value is hand arithmetic."""
    F = Fraction

    def test_ci_verdict_words(self):
        self.assertTrue(am.ci_verdict((0.1, 0.4)).startswith("높음"))
        self.assertTrue(am.ci_verdict((-0.4, -0.1)).startswith("낮음"))
        self.assertTrue(am.ci_verdict((-0.1, 0.4)).startswith("구분 안 됨"))
        self.assertTrue(am.ci_verdict((0.0, 0.0)).startswith("구분 안 됨"))      # all ties: no difference
        self.assertEqual(am.ci_verdict(None), "NA")

    def test_sp_verdict_in_tests_and_summary(self):
        """T0 covers all 6 scenes (SP 1), T1 covers all but sends 6 messages (SP05 0.9): C ties, the SP interval sits below 0."""
        scene_ids = ["s%d" % i for i in range(6)]
        cells = []
        for structure, m in (("T0", 0), ("T1", 6)):
            for sid in scene_ids:
                cell = dict(am.evaluate_stub(), state="ok", arm="mainA", group="mainA", scene=sid, structure=structure, rep=1,
                            C=1, G=1, S=1, M=m, n_robots=2, tags=[])
                for key, lam in am.PENALTY_LAMBDAS.items():
                    cell[key] = am.penalized(1, m, 2, lam)
                cells.append(cell)
        args = am.parse(["--runs", str(self.runs), "--scenes", str(self.scene_file), "--name", "t", "--boots", "100"])
        scenes = {s: {} for s in scene_ids}
        tests, by_type = am.run_tests(am.Book(cells), cells, scenes, args)
        sp = next(t for t in tests if t["metric"] == "SP05" and t["mode"] == "zero" and t["variant"] == "all" and t["contrast"] == "T0->T1")
        c = next(t for t in tests if t["metric"] == "C" and t["mode"] == "zero" and t["variant"] == "all" and t["contrast"] == "T0->T1")
        self.assertEqual((sp["verdict_basis"], c["verdict_basis"]), ("ci", "sign_holm"))
        self.assertAlmostEqual(sp["mean_D"], -0.1)
        self.assertAlmostEqual(sp["ci95"][0], -0.1)                     # every scene has D = -0.1: degenerate interval
        self.assertAlmostEqual(sp["ci95"][1], -0.1)
        self.assertTrue(sp["ci_verdict"].startswith("낮음"))
        self.assertTrue(c["ci_verdict"].startswith("구분 안 됨"))         # C: tie everywhere
        self.assertIn("pos", sp)                                          # the sign test is still computed and kept
        be = next(t for t in tests if t["metric"] == "SP_BE" and t["contrast"] == "T0->T1")
        self.assertEqual((be["status"], be["breakeven_lambda"], be["mean_D_at_zero"]), ("at_zero", 0.0, 0.0))   # C ties: f(0)=0
        text = am.main_tests(tests, args) + am.breakeven_table(tests) + am.cap_table(cells)
        self.assertIn("판정 (구간)", text)
        self.assertIn("낮음 (구간이 0 아래)", text)
        self.assertIn("## 2c. 손익분기", text)
        self.assertIn("## 2d. 메시지 상한", text)

    def test_breakeven_no_floor(self):
        """T0 scene mean (1 + 0)/2 = 0.5; T1 cells (C=1, excess 6) twice: SP = 1 - 6 lam. f = 0.5 - 6 lam -> lam* = 1/12 (SP = 0.5 > 0)."""
        first = {"s": [(self.F(1), 0), (self.F(0), 0)]}
        second = {"s": [(self.F(1), 6), (self.F(1), 6)]}
        status, lam, f0, n = am.breakeven_lambda(first, second)
        self.assertEqual((status, lam, f0, n), ("value", self.F(1, 12), self.F(1, 2), 1))

    def test_breakeven_with_floor_segment(self):
        """T0 mean 0.2 (cells 1,0,0,0,0). T1 cells (1, excess 2) and (1, excess 20), mean (max(0,1-2L)+max(0,1-20L))/2.
        The second cell hits its floor at L = 1/20; beyond that the mean is (1-2L)/2, so f = 0.3 - L -> lam* = 3/10.
        (Without the floor the mean would go negative and the answer would be 1/22 + wrong.)"""
        first = {"s": [(self.F(1), 0)] + [(self.F(0), 0)] * 4}
        second = {"s": [(self.F(1), 2), (self.F(1), 20)]}
        status, lam, f0, n = am.breakeven_lambda(first, second)
        self.assertEqual((status, lam, f0), ("value", self.F(3, 10), self.F(8, 10)))
        self.assertEqual(am.mean_difference_at(first, second, self.F(3, 10))[0], 0)
        # a second scene where both are 0 changes neither the zero crossing (f halves, the root stays)
        both = am.breakeven_lambda(dict(first, b=[(self.F(0), 0)]), dict(second, b=[(self.F(0), 0)]))
        self.assertEqual((both[0], both[1], both[2], both[3]), ("value", self.F(3, 10), self.F(4, 10), 2))

    def test_breakeven_none_and_at_zero(self):
        inside = {"s": [(self.F(1), 0), (self.F(1), 0)]}              # T1 stays inside the allowance, covers more than T0
        status, lam, f0, _ = am.breakeven_lambda({"s": [(self.F(1, 2), 0)]}, inside)
        self.assertEqual((status, lam, f0), ("none", None, self.F(1, 2)))
        status, lam, f0, _ = am.breakeven_lambda({"s": [(self.F(1), 0)]}, {"s": [(self.F(1, 2), 0)]})
        self.assertEqual((status, lam, f0), ("at_zero", self.F(0), self.F(-1, 2)))
        self.assertEqual(am.breakeven_lambda({"a": [(self.F(1), 0)]}, {"b": [(self.F(1), 0)]})[0], "NA")   # no common scene
        # T1 covers more only through cells that stay inside the allowance, one cell is penalised: the floor leaves f > 0 -> none
        status, lam, _, _ = am.breakeven_lambda({"s": [(self.F(1, 4), 0)]}, {"s": [(self.F(1), 0), (self.F(1), 40)]})
        self.assertEqual(status, "none")       # at the floor the mean is 1/2 > 1/4

    def test_penalty_terms_follow_failure_modes_and_unknown_m(self):
        ok = dict(am.evaluate_stub(), state="ok", arm="a", scene="s", structure="T1", rep=1, C=1, M=6, n_robots=2)
        crash = dict(am.evaluate_stub(), state="failed", arm="a", scene="s", structure="T1", rep=2)
        unknown = dict(am.evaluate_stub(), state="ok", arm="a", scene="s", structure="T1", rep=3, C=1, M=None, n_robots=2)
        book = am.Book([ok, crash, unknown])
        self.assertEqual(book.penalty_terms("T1", "zero")["s"], [(self.F(1), 2), (self.F(0), 0)])    # excess 6 - 4, crash = 0, M unknown left out
        self.assertEqual(book.penalty_terms("T1", "one")["s"], [(self.F(1), 2), (self.F(1), 0)])
        self.assertEqual(book.penalty_terms("T1", "drop")["s"], [(self.F(1), 2)])


class CapAndVia(Base):
    """2026-11-16 analysis-only labels: cap_reached, not_sent_cap, message origin (via). Times are hand-set.
    Scene: red -> sign11 (o1), blue -> sign12 (o2). r1 knows both orders and holds the missing pair (blue, sign12).
    r2 knows nothing and goes blue -> sign11 at t = decide_at (a wrong pair, never told by a message with a pair)."""
    def run_team(self, name, sent_times, decide_at, cap=8, via=None, chances=None, planner="brain-v3-msg4-20261116", messages_by_robot=None):
        data = team("L2-01", cover=False, knows={"r1": ["o1", "o2"], "r2": []})
        data["choices"] = {"r1": {"picked": "red", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "zone_sign11"}}
        data["decisions"] = [
            {"rid": "r1", "t": 1.0, "point": "pick", "option": "box:0", "colour": "red", "sent": [], "calls": 1},
            {"rid": "r1", "t": 3.0, "point": "destination", "option": "zone:sign11", "sent": [], "calls": 1},
            {"rid": "r2", "t": 1.0, "point": "pick", "option": "box:0", "colour": "blue", "sent": [], "calls": 1},
            {"rid": "r2", "t": decide_at, "point": "destination", "option": "zone:sign11", "sent": [], "calls": 1}]
        messages = [{"from": "r1", "to": ["r2"], "time": t, "deliver_at": t + 2.0, "text": "hello, still here"} for t in sent_times]
        for i, message in enumerate(messages):
            if via and via[i]:
                message["via"] = via[i]
        record = {"planner": planner, "messages": messages, "max_messages_per_robot": cap,
                  "messages_by_robot": messages_by_robot or {"r1": len(messages), "r2": 0}}
        if chances is not None:
            record["chances"] = chances
        data["brain"] = record
        self.make(name, data, brain=record)

    def one(self, name, **kw):
        self.run_team(name, **kw)
        _, cells, _, _ = self.analyze()
        return self.cell(cells, name)

    def test_cap_before_the_decision_tags_not_sent_cap(self):
        cell = self.one("t1-L2-01-c1", sent_times=[float(i) for i in range(1, 9)], decide_at=20.0)   # 8th message at t = 8.0 <= 20.0
        self.assertEqual((cell["C"], cell["M"], cell["cap"], cell["cap_reached"], cell["cap_n"]), (0, 8, 8, True, 1))
        self.assertIn("not_sent", cell["tags"])
        self.assertIn("not_sent_cap", cell["tags"])
        self.assertEqual(cell["primary"], "not_sent")                 # a side tag: the primary cause is unchanged
        self.assertEqual((cell["msg_decision"], cell["msg_chance"]), (8, 0))

    def test_cap_after_the_decision_is_not_the_cause(self):
        cell = self.one("t1-L2-01-c1", sent_times=[float(i) for i in range(1, 9)], decide_at=5.0)    # decided at 5.0 < cap time 8.0
        self.assertTrue(cell["cap_reached"])                          # the run reached the cap, but only later
        self.assertIn("not_sent", cell["tags"])
        self.assertNotIn("not_sent_cap", cell["tags"])

    def test_seven_messages_is_not_the_cap(self):
        cell = self.one("t1-L2-01-c1", sent_times=[float(i) for i in range(1, 8)], decide_at=20.0)
        self.assertEqual((cell["M"], cell["cap_reached"], cell["cap_n"]), (7, False, 0))
        self.assertNotIn("not_sent_cap", cell["tags"])
        self.assertIn("not_sent", cell["tags"])

    def test_cap_unknown_without_the_record_key(self):
        """No `max_messages_per_robot` (T0 / legacy record): cap_reached is NA (None), never False, and nothing is tagged."""
        self.run_team("t1-L2-01-c1", sent_times=[float(i) for i in range(1, 9)], decide_at=20.0)
        record = json.loads((self.runs / "t1-L2-01-c1" / "brain" / "brain-record.json").read_text(encoding="utf-8"))
        del record["max_messages_per_robot"]
        (self.runs / "t1-L2-01-c1" / "brain" / "brain-record.json").write_text(json.dumps(record), encoding="utf-8")
        _, cells, _, _ = self.analyze()
        cell = self.cell(cells, "t1-L2-01-c1")
        self.assertEqual((cell["cap"], cell["cap_reached"], cell["cap_n"]), (None, None, None))
        self.assertNotIn("not_sent_cap", cell["tags"])
        t0 = self.cell(self.analyze_t0(), "t0-L2-01-c1")
        self.assertEqual((t0["cap_reached"], t0["msg_decision"], t0["msg_chance"]), (None, 0, 0))

    def analyze_t0(self):
        self.make("t0-L2-01-c1", team("L2-01"), brain={"messages": []})
        return self.analyze()[1]

    def test_via_counts_and_the_mismatch_warning(self):
        sent = {"time": 3.0, "deliver_at": 5.0, "from": "r1", "to": ["r2"], "text": "ok", "via": "chance"}
        chances = {"r1": [{"time": 3.0, "sent": [sent], "calls": 1, "asked": True, "final": False}], "r2": []}
        cell = self.one("t1-L2-01-c1", sent_times=[1.0, 3.0, 6.0], decide_at=20.0, via=[None, "chance", None], chances=chances)
        self.assertEqual((cell["M"], cell["msg_decision"], cell["msg_chance"]), (3, 2, 1))
        self.assertEqual([w for w in cell["warnings"] if "via" in w or "chance" in w], [])           # the chance record agrees with via
        # an old planner wrote no `via`: the chance record holds 1 message, via marks 0 -> warning, and the old version is flagged
        old = self.one("t1-C2-01-c1", sent_times=[1.0, 3.0, 6.0], decide_at=20.0, via=None, chances=chances, planner="brain-v2-20261115")
        self.assertEqual((old["msg_decision"], old["msg_chance"]), (3, 0))
        self.assertTrue(any("via marks 0 chance messages but the chance record holds 1" in w for w in old["warnings"]))
        self.assertTrue(any("older than brain-v3" in w for w in old["warnings"]))

    def test_tally_mismatch_is_warned(self):
        cell = self.one("t1-L2-01-c1", sent_times=[1.0, 2.0], decide_at=20.0, messages_by_robot={"r1": 5, "r2": 0})
        self.assertTrue(any("messages_by_robot" in w for w in cell["warnings"]))


class PutDown(Base):
    """choices.dest == 'put_down': empty assignment for C, classified apart, 'dropped_needed' in the cause split, table 5c."""
    def setUp(self):
        super().setUp()
        decoy = scene("D2-01", "D")
        decoy["orders"] = decoy["orders"][:1]                      # only a red order; the blue box is a decoy
        decoy["oracle_plan"] = {"r1": [["a", "o1"]], "r2": []}
        self.scene_file.write_text(json.dumps({"scenes": [scene("L2-01", "L"), scene("C2-01", "C"), decoy]}), encoding="utf-8")

    def put_team(self, scene_id, knows):
        data = team(scene_id, knows=knows, brain={"messages": []})
        data["choices"] = {"r1": {"picked": "red", "dest": "zone_sign11"}, "r2": {"picked": "blue", "dest": "put_down", "go": False}}
        data["correct_boxes"], data["wrong_place_boxes"] = 1, 0
        return data

    def test_put_down_cells_and_tables(self):
        self.make("t1-D2-01-c1", self.put_team("D2-01", {"r1": ["o1"], "r2": []}))      # decoy put down: covered
        self.make("t1-L2-01-c1", self.put_team("L2-01", {"r1": ["o1", "o2"], "r2": []}))  # needed blue, only r1 knew it
        self.make("t1-C2-01-c1", self.put_team("C2-01", {"r1": ["o1"], "r2": ["o2"]}))     # needed blue, r2 knew it itself
        self.make("t0-L2-01-c1", self.put_team("L2-01", {"r1": ["o1", "o2"], "r2": []}), brain={"messages": []})
        _, cells, text, tests = self.analyze()
        decoy, lost_team, lost_own = (self.cell(cells, "t1-%s-c1" % s) for s in ("D2-01", "L2-01", "C2-01"))
        self.assertEqual((decoy["C"], decoy["put_decoy"], decoy["put_lost_team"]), (1, 1, 0))
        self.assertEqual((lost_team["C"], lost_team["put_lost_team"], lost_team["put_lost_own"], lost_team["primary"]), (0, 1, 0, "not_sent"))
        self.assertIn("dropped_needed", lost_team["tags"])
        self.assertEqual((lost_own["C"], lost_own["put_lost_own"], lost_own["primary"], lost_own["tags"]), (0, 1, "dropped_needed", ["dropped_needed"]))
        self.assertEqual(self.cell(cells, "t0-L2-01-c1")["primary"], "no_info_T0")
        self.assertIn("## 5c. 내려놓기(put_down) 분류", text)
        self.assertIn("필요한 상자 내려놓음", text)
        book = am.Book(cells)
        n, parts = book.cause_partition("T1", "legacy-c")
        means = book.scene_means("T1", "C", "zero", "legacy-c")
        self.assertEqual(n, 3)
        self.assertEqual(sum(parts.values()), 1 - sum(means.values()) / len(means))            # the split still sums to the shortfall
        self.assertEqual((parts["dropped_needed"], parts["not_sent"]), (Fraction(1, 3), Fraction(1, 3)))
        row = next(r for r in text.splitlines() if r.startswith("| legacy-c | T1 | 3 | 3 | 3 | 3 |"))
        self.assertEqual([c.strip() for c in row.strip("|").split("|")][6:], ["1", "0", "1", "1", "0", "0", "1/3"])


class Cells(Base):
    def build_two_rep_set(self):
        for structure in ("t0", "t1"):
            self.make("%s-L2-01-c1" % structure, team("L2-01"))
            self.make("%s-C2-01-c1" % structure, team("C2-01", cover=structure == "t1"))
        self.make("t0-L2-01-c2")                       # no team.json: crashed, scene only readable from the name
        self.make("t0-C2-01-c2", team("C2-01", status="running"))   # never finished
        self.make("t1-L2-01-c2", team("L2-01"))
        self.make("t1-C2-01-c2", team("C2-01"))

    def test_failure_modes_zero_drop_one(self):
        self.build_two_rep_set()
        args, cells, text, tests = self.analyze()
        self.assertEqual(self.cell(cells, "t0-L2-01-c2")["scene"], "L2-01")    # not "L2": hyphen-safe
        self.assertEqual(self.cell(cells, "t0-L2-01-c2")["state"], "failed")
        self.assertEqual(self.cell(cells, "t0-C2-01-c2")["state"], "in_progress")
        book = am.Book(cells)
        expected = {"zero": {"L2-01": Fraction(1, 2), "C2-01": Fraction(0)},
                    "drop": {"L2-01": Fraction(1), "C2-01": Fraction(0)},
                    "one": {"L2-01": Fraction(1), "C2-01": Fraction(1, 2)}}
        for mode, want in expected.items():
            self.assertEqual(book.scene_means("T0", "C", mode, "legacy-c"), want, mode)
        # D = T1 - T0 per scene; T1 is 1 everywhere
        pairs = {t["mode"]: t for t in tests if t["contrast"] == "T0->T1" and t["metric"] == "C" and t["variant"] == "all"}
        self.assertEqual((pairs["zero"]["pos"], pairs["zero"]["neg"], pairs["zero"]["tie"]), (2, 0, 0))
        self.assertAlmostEqual(pairs["zero"]["mean_D"], 0.75)
        self.assertEqual((pairs["drop"]["pos"], pairs["drop"]["tie"]), (1, 1))
        self.assertAlmostEqual(pairs["drop"]["mean_D"], 0.5)
        self.assertEqual((pairs["one"]["pos"], pairs["one"]["tie"]), (1, 1))
        self.assertAlmostEqual(pairs["one"]["mean_D"], 0.25)
        self.assertAlmostEqual(pairs["zero"]["p"], 0.5)

    def test_interim_leaves_in_progress_out_but_keeps_failures(self):
        self.build_two_rep_set()
        _, cells, _, _ = self.analyze()
        book = am.Book(cells, interim=True)
        # C2-01 T0: c1 not covered, c2 running -> only c1 counts under --interim; crash on L2-01 still counts as 0
        self.assertEqual(book.scene_means("T0", "C", "zero", "legacy-c"),
                         {"L2-01": Fraction(1, 2), "C2-01": Fraction(0)})
        self.assertEqual(book.scene_means("T0", "C", "one", "legacy-c")["C2-01"], Fraction(0))
        self.assertEqual(am.Book(cells).scene_means("T0", "C", "one", "legacy-c")["C2-01"], Fraction(1, 2))

    def test_control_scenes_variant_and_reps_padding(self):
        for structure in ("t0", "t1"):
            self.make("%s-L2-01-c1" % structure, team("L2-01", cover=structure == "t1"))
            self.make("%s-X2-01-c1" % structure, team("X2-01"))          # control scene: same in both structures
        args, cells, _, tests = self.analyze("--reps", "2")
        pad = self.cell(cells, "")
        self.assertEqual((pad["rep"], pad["state"]), (2, "in_progress"))
        self.assertIn("planned (--reps 2)", pad["reason"])
        self.assertEqual(len(cells), 8)                                   # 4 observed + 4 padded
        _, _, _, tests = self.analyze("--interim")
        by_variant = {t["variant"]: t for t in tests if t["contrast"] == "T0->T1" and t["metric"] == "C" and t["mode"] == "zero"}
        self.assertEqual(by_variant["all"]["n_scenes"], 2)
        self.assertEqual(by_variant["no_control"]["n_scenes"], 1)         # X2-01 (control) left out
        self.assertEqual((by_variant["all"]["pos"], by_variant["all"]["tie"]), (1, 1))

    def test_scene_from_name_hyphen_ids(self):
        known = ["L2-01", "L2-02", "C2-01", "K201", "RND2-01"]
        self.assertEqual(am.scene_from_name("t1-L2-01-c1", known), ("L2-01", False))
        self.assertEqual(am.scene_from_name("A-L2_02-T1-r1", known), ("L2-02", False))
        self.assertEqual(am.scene_from_name("t2-RND2-01-h", known), ("RND2-01", False))
        self.assertEqual(am.scene_from_name("t0-K201-x", known), ("K201", False))
        self.assertEqual(am.scene_from_name("t0-90721-a", known), (None, False))
        self.assertEqual(am.scene_type("K203", {}), "K2")
        self.assertEqual(am.scene_type("L301", {}), "L3")
        self.assertEqual(am.scene_type("X01", {}), "X")
        self.assertEqual(am.scene_type("L2-01", {"type_code": "L"}), "L")

    def test_legacy_name_parts(self):
        known = ["C01", "L2-01"]
        self.assertEqual(am.legacy_parts("t1-C01-h", known), ("T1", "h", "C01"))
        self.assertEqual(am.legacy_parts("t0-L2-01-c1", known), ("T0", "c", "L2-01"))
        self.assertEqual(am.legacy_parts("oracle-C01", known), (am.ORACLE, "x", "C01"))     # no bundle letter: not the scene's 'C'
        self.assertEqual(am.legacy_parts("fixed-90721", known), ("UNKNOWN", "x", None))

    def test_team_json_scene_overrides_wrong_name_parse(self):
        # compare.py reads "L2" from the name; the cell must use team.json's scene
        self.make("t1-L2-01-c1", team("L2-01"))
        _, cells, _, _ = self.analyze()
        self.assertEqual(compare.analyze_run(self.runs / "t1-L2-01-c1", {}) ["scene"], "L2-01")
        self.assertEqual(cells[0]["scene"], "L2-01")
        self.assertEqual(cells[0]["scene_src"], "team.json")

    def test_halts_cap_is_result_exceptions_are_faults(self):
        cases = {"t0-L2-01-c1": ({"r1": "Robot call cap reached", "r2": None}, "ok", "cap_end"),
                 "t0-L2-01-c2": ({"r1": None, "r2": "ResponseError"}, "failed", ""),
                 "t0-C2-01-c1": ({"r1": "Campaign dollar budget exhausted", "r2": None}, "failed", ""),
                 "t0-C2-01-c2": ({"r1": "Per-instance call cap reached", "r2": None}, "ok", "cap_end_instance"),
                 "t0-X2-01-c1": ({"r1": "Campaign attempt cap reached", "r2": None}, "failed", "")}
        for name, (halted, state, cap) in cases.items():
            self.make(name, team(name.split("-c")[0][3:]), brain={"halted_by_robot": halted, "calls": 3})
        _, cells, _, _ = self.analyze()
        for name, (halted, state, cap) in cases.items():
            c = self.cell(cells, name)
            self.assertEqual((c["state"], c["cap_end"]), (state, cap), name)
        self.assertIn("ResponseError", self.cell(cells, "t0-L2-01-c2")["reason"])

    def test_rerun_replaces_only_a_fault(self):
        self.make("t1-L2-01-c1", team("L2-01", status="failed"))        # fault
        self.make("t1-L2-01-c1-rr1", team("L2-01"))
        self.make("t1-C2-01-c1", team("C2-01", cover=False))             # a real (bad) result
        self.make("t1-C2-01-c1-rr1", team("C2-01"))
        _, cells, _, _ = self.analyze()
        self.assertEqual(len(cells), 2)
        fixed = self.cell(cells, "t1-L2-01-c1")
        self.assertEqual((fixed["state"], fixed["C"], fixed["attempts"]), ("ok", 1, 2))
        kept = self.cell(cells, "t1-C2-01-c1")
        self.assertEqual((kept["state"], kept["C"]), ("ok", 0))
        self.assertTrue(any("ignored" in w for w in kept["warnings"]))

    def test_plan_na_scene_missing_and_policy(self):
        self.make("t0-L2-01-c1", team("L2-01"))
        self.make("t0-ZZ-c1", team("ZZ9"))                               # complete run of a scene we have no file for
        _, cells, _, _ = self.analyze()
        c = self.cell(cells, "t0-ZZ-c1")
        self.assertEqual(c["state"], "plan_na")
        self.assertIn("not in scene files", c["reason"])
        self.assertEqual(am.Book(cells).value(c, "C", "zero"), None)
        self.assertEqual(am.Book(cells, plan_na="failure").value(c, "C", "zero"), 0)
        self.assertEqual(am.Book(cells).value(c, "S", "zero"), 1)

    def test_duplicate_cell_key_is_an_error(self):
        results = self.root / "results"
        results.mkdir()
        manifest = self.root / "m.csv"
        manifest.write_text("run_id,group,scene_id,team,rep\nA-1,mainA,L2-01,T1,1\nA-2,mainA,L2-01,T1,1\n", encoding="utf-8")
        with self.assertRaises(SystemExit):
            self.analyze("--manifest", str(manifest), runs=results)

    def test_grounded_cover_excludes_guess_hits(self):
        def decisions(rid, colour, zone):
            return [{"rid": rid, "t": 12.0, "point": "pick", "option": "box:0", "colour": colour, "sent": [], "calls": 1},
                    {"rid": rid, "t": 30.0, "point": "destination", "option": "zone:" + zone, "sent": [], "calls": 1}]
        own = team("L2-01")
        own["decisions"] = decisions("r1", "red", "sign11") + decisions("r2", "blue", "sign12")
        luck = team("C2-01", knows={"r1": ["o1", "o2"], "r2": []})       # r2 holds no order but still picks the right pair
        luck["decisions"] = decisions("r1", "red", "sign11") + decisions("r2", "blue", "sign12")
        self.make("t0-L2-01-c1", own)
        self.make("t0-C2-01-c1", luck)
        _, cells, _, _ = self.analyze()
        a, b = self.cell(cells, "t0-L2-01-c1"), self.cell(cells, "t0-C2-01-c1")
        self.assertEqual((a["C"], a["success_class"], a["G"]), (1, "own_only", 1))
        self.assertEqual((b["C"], b["success_class"], b["G"]), (1, "guess_correct", 0))

    def test_cause_partition_sums_to_shortfall(self):
        for rep in (1, 2):
            self.make("t0-L2-01-c%d" % rep, team("L2-01", cover=rep == 1))
            self.make("t0-C2-01-c%d" % rep, team("C2-01", cover=False))
        self.make("t0-X2-01-c1", team("X2-01"))
        self.make("t0-X2-01-c2")                                          # crash: no tag, goes to the fault row
        _, cells, _, _ = self.analyze()
        book = am.Book(cells)
        n, parts = book.cause_partition("T0", "legacy-c")
        means = book.scene_means("T0", "C", "zero", "legacy-c")
        self.assertEqual(n, 3)
        self.assertEqual(sum(parts.values()), 1 - sum(means.values()) / len(means))
        self.assertEqual(parts["fault"], Fraction(1, 6))                  # 1 of 2 reps in 1 of 3 scenes
        self.assertEqual(parts["no_info_T0"], Fraction(1, 6) + Fraction(1, 3))

    def test_regression_against_compare_py(self):
        runs, brain = HERE / "data" / "team-llm26", HERE / "data" / "brain"
        if not runs.is_dir():
            self.skipTest("batch1 data not present")
        args = am.parse(["--runs", str(runs), "--scenes", str(HERE / "data" / "scenes18b.json"), "--brain", str(brain),
                         "--name", "t", "--boots", "50"])
        cells = am.analyze(args)[0]
        scenes = {s["id"]: s for s in compare.read_json(HERE / "data" / "scenes18b.json")["scenes"]}
        checked = 0
        for cell in cells:
            if not cell["run_id"].endswith("-h"):
                continue
            row = compare.analyze_run(runs / cell["run_id"], scenes, brain, "h")
            self.assertEqual(cell["raw_C"], row["plan_cover"], cell["run_id"])
            self.assertEqual(cell["raw_S"], row["physical_success"], cell["run_id"])
            checked += 1
        self.assertEqual(checked, 15)


class Batch(Base):
    def write_results(self):
        results = self.root / "results"
        results.mkdir()
        manifest = self.root / "manifest.csv"
        rows = [("BASE-L2-01-T0-r1", "baseline", "L2-01", "T0", 1), ("A-L2-01-T0-r1", "mainA", "L2-01", "T0", 1),
                ("A-L2-01-T1-r1", "mainA", "L2-01", "T1", 1), ("A-L2-01-T1-r2", "mainA", "L2-01", "T1", 2),
                ("A-C2-01-T1-r1", "mainA", "C2-01", "T1", 1), ("ABL-L2-01-T1-r1", "ablation", "L2-01", "T1", 1), ("FULL-L2-01-T1-r1", "fullinfo", "L2-01", "T1", 1)]
        lines = ["run_id,group,scene_id,team,rep,vm_args,server_args"]
        for run_id, group, sid, structure, rep in rows:
            extra = "--pre-exchange" if group == "ablation" else ""
            lines.append("%s,%s,%s,%s,%d,%s,%s" % (run_id, group, sid, structure, rep, am.COMMON_ARGS, extra))
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        index = ["run_id,group,scene_id,team,rep,status,warnings",
                 "A-L2-01-T1-r2,mainA,L2-01,T1,2,failed,rsync", "A-C2-01-T1-r1,mainA,C2-01,T1,1,pending,"]
        for run_id, group, sid, structure, rep in rows:
            if run_id not in ("A-L2-01-T1-r2", "A-C2-01-T1-r1"):
                index.append("%s,%s,%s,%s,%d,done," % (run_id, group, sid, structure, rep))
        (results / "index.csv").write_text("\n".join(index) + "\n", encoding="utf-8")
        for run_id, group, sid, structure, rep in rows:
            if run_id in ("A-L2-01-T1-r2", "A-C2-01-T1-r1"):
                continue
            fixed = {"kind": "fixed_plan"} if group == "baseline" else {}
            self.make(run_id, team(sid, brain=fixed), where=results)
        return results, manifest

    def test_structure_scene_group_from_manifest_not_folder_name(self):
        results, manifest = self.write_results()
        _, cells, text, tests = self.analyze("--manifest", str(manifest), runs=results)
        by_id = {c["run_id"]: c for c in cells}
        self.assertEqual(by_id["BASE-L2-01-T0-r1"]["structure"], am.ORACLE)       # baseline never lands in a T0 cell
        self.assertEqual(by_id["A-L2-01-T1-r1"]["structure"], "T1")
        self.assertEqual(by_id["A-L2-01-T1-r1"]["scene"], "L2-01")
        self.assertEqual(by_id["A-L2-01-T1-r1"]["arm"], "mainA")
        self.assertEqual(by_id["ABL-L2-01-T1-r1"]["arm"], "ablation [--pre-exchange]")
        self.assertEqual(by_id["A-L2-01-T1-r2"]["state"], "failed")                  # dispatcher gave up
        self.assertEqual(by_id["A-C2-01-T1-r1"]["state"], "in_progress")             # still pending
        book = am.Book(cells)
        self.assertEqual(book.scene_means("T1", "C", "zero", "mainA"), {"L2-01": Fraction(1, 2), "C2-01": Fraction(0)})
        self.assertEqual(book.scene_means("T1", "C", "drop", "mainA"), {"L2-01": Fraction(1)})
        self.assertEqual(am.Book(cells, interim=True).scene_means("T1", "C", "zero", "mainA"), {"L2-01": Fraction(1, 2)})
        self.assertEqual(book.scene_means(am.ORACLE, "C", "zero"), {"L2-01": Fraction(1)})
        # condition comparison pairs the ablation / fullinfo arms with mainA on the same scene and structure
        args = am.parse(["--runs", str(results), "--scenes", str(self.scene_file), "--name", "t", "--boots", "50"])
        ref, rows = am.condition_rows(book, cells, args)
        self.assertEqual(ref, "mainA")
        found = {(r["arm"], r["structure"], r["ref_structure"], r["metric"]): r for r in rows}
        abl = found[("ablation [--pre-exchange]", "T1", "T1", "C")]
        self.assertEqual((abl["kind"], abl["n_scenes"], abl["pos"], abl["mean_D"]), ("condition", 1, 1, 0.5))   # 1 - 1/2
        self.assertEqual(found[("fullinfo", "T1", "T1", "C")]["kind"], "fullinfo")
        # full information is compared with every reference structure, ablation only with the same one
        self.assertEqual({k[2] for k in found if k[0] == "fullinfo"}, {"T0", "T1", "T2"} & {k[2] for k in found if k[0] == "fullinfo"})
        self.assertIn(("fullinfo", "T1", "T0", "C"), found)
        self.assertNotIn(("ablation [--pre-exchange]", "T1", "T0", "C"), found)
        self.assertIn("ablation [--pre-exchange]", text)

    def test_shortfall_against_oracle_baseline(self):
        results, manifest = self.write_results()
        args, cells, _, _ = self.analyze("--manifest", str(manifest), runs=results)
        scenes = am.load_scenes([self.scene_file])
        text = am.shortfall(cells, am.Book(cells), scenes, args)
        row = next(line for line in text.splitlines() if line.startswith("| mainA | T1 |"))
        columns = [c.strip() for c in row.strip("|").split("|")]
        # scenes L2-01 (1 of 2 reps ok, one failed -> 1/2) and C2-01 (pending -> 0): C mean 25.0; oracle covers L2-01 only
        self.assertEqual(columns[2:6], ["2", "25.0", "1", "50.0"])
        self.assertIn("기준선(정답 계획 고정 실행) 칸 1개", text)

    def test_index_without_manifest_stops_when_a_planned_row_lacks_args(self):
        # collect.py writes meta.json (with vm_args) only for collected runs; a pending mainA row sorts first (A-C2-01...)
        results, _ = self.write_results()
        for run_id in ("A-L2-01-T1-r1", "A-L2-01-T0-r1"):
            meta = {"run_id": run_id, "group": "mainA", "team": "T1" if "T1" in run_id else "T0", "scene_id": "L2-01",
                    "rep": 1, "vm_args": am.COMMON_ARGS}
            (results / run_id / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaises(SystemExit) as stop:
            self.analyze(runs=results)
        self.assertIn("vm_args", str(stop.exception))

    def test_index_with_meta_for_every_run_works_and_attempts_come_from_index(self):
        results = self.root / "results"
        results.mkdir()
        (results / "index.csv").write_text("run_id,group,scene_id,team,rep,status,attempts,warnings\n"
                                           "A-L2-01-T1-r1,mainA,L2-01,T1,1,done,3,\n", encoding="utf-8")
        self.make("A-L2-01-T1-r1", team("L2-01"), where=results)
        (results / "A-L2-01-T1-r1" / "meta.json").write_text(json.dumps({"vm_args": am.COMMON_ARGS}), encoding="utf-8")
        _, cells, _, _ = self.analyze(runs=results)
        self.assertEqual((cells[0]["arm"], cells[0]["attempts"], cells[0]["state"]), ("mainA", 3, "ok"))

    def test_main_group_with_two_arms_is_an_error(self):
        results, manifest = self.write_results()
        text = manifest.read_text(encoding="utf-8").replace("A-L2-01-T1-r2,mainA,L2-01,T1,2,--robot-tags",
                                                            "A-L2-01-T1-r2,mainA,L2-01,T1,2,--extra-flag --robot-tags")
        manifest.write_text(text, encoding="utf-8")
        with self.assertRaises(SystemExit) as stop:
            self.analyze("--manifest", str(manifest), runs=results)
        self.assertIn("several arms", str(stop.exception))

    def test_manifest_scene_mismatch_is_a_failed_cell(self):
        results, manifest = self.write_results()
        self.make("A-L2-01-T1-r1", team("C2-01"), where=results)       # team.json ran another scene
        _, cells, _, _ = self.analyze("--manifest", str(manifest), runs=results)
        cell = next(c for c in cells if c["run_id"] == "A-L2-01-T1-r1")
        self.assertEqual(cell["state"], "failed")
        self.assertIn("scene mismatch", cell["reason"])

    def test_exit_file_inside_run_folder_is_read(self):
        # collect.py layout: results/<run_id>/exit-<name>.json (name = run_id, or <run_id>-retryN after a retry via meta.json source_name)
        results, manifest = self.write_results()
        (results / "A-L2-01-T1-r1" / "exit-A-L2-01-T1-r1.json").write_text(json.dumps({"exit_code": 3}), encoding="utf-8")
        (results / "A-L2-01-T0-r1" / "exit-A-L2-01-T0-r1-retry1.json").write_text(json.dumps({"exit_code": 124}), encoding="utf-8")
        (results / "A-L2-01-T0-r1" / "meta.json").write_text(json.dumps({"source_name": "A-L2-01-T0-r1-retry1"}), encoding="utf-8")
        (results / "ABL-L2-01-T1-r1" / "exit-ABL-L2-01-T1-r1.json").write_text(json.dumps({"exit_code": 0}), encoding="utf-8")
        _, cells, _, _ = self.analyze("--manifest", str(manifest), runs=results)
        by_id = {c["run_id"]: c for c in cells}
        self.assertIn("VM exit_code 3", by_id["A-L2-01-T1-r1"]["warnings"])
        self.assertIn("VM exit_code 124", by_id["A-L2-01-T0-r1"]["warnings"])
        self.assertNotIn("VM exit_code", "; ".join(by_id["ABL-L2-01-T1-r1"]["warnings"]))

    def test_exit_file_next_to_run_folder_still_read_for_legacy_layout(self):
        results, manifest = self.write_results()
        (results / "exit-A-L2-01-T1-r1.json").write_text(json.dumps({"exit_code": 7}), encoding="utf-8")
        _, cells, _, _ = self.analyze("--manifest", str(manifest), runs=results)
        self.assertIn("VM exit_code 7", next(c for c in cells if c["run_id"] == "A-L2-01-T1-r1")["warnings"])

    def test_manifest_may_be_given_twice_and_rows_merge(self):
        results, manifest = self.write_results()
        lines = manifest.read_text(encoding="utf-8").splitlines()
        first, second = self.root / "m1.csv", self.root / "m2.csv"
        first.write_text("\n".join(lines[:4]) + "\n", encoding="utf-8")                  # header + 3 rows
        second.write_text("\n".join([lines[0]] + lines[4:]) + "\n", encoding="utf-8")
        _, cells, _, _ = self.analyze("--manifest", str(first), "--manifest", str(second), runs=results)
        self.assertEqual({c["arm"] for c in cells}, {"baseline", "mainA", "ablation [--pre-exchange]", "fullinfo"})

    def test_split_warnings_keeps_compound_phrases_whole(self):
        text = "x summary missing; first assignment unresolved; not scored; scene unavailable; planning not scored; unknown cost calls"
        self.assertEqual(am.split_warnings(text), ["x summary missing", "first assignment unresolved; not scored",
                                                   "scene unavailable; planning not scored", "unknown cost calls"])
        self.assertEqual(am.split_warnings(""), [])

    def test_first_assignment_warning_is_counted_not_listed(self):
        # a T1 run whose first pick is an explicit `finish` (colour unresolvable), and a fixed-plan baseline run (no first pick at all)
        results, manifest = self.write_results()
        data = team("L2-01", brain={})
        data["decisions"] = [{"rid": "r1", "t": 1.0, "point": "pick", "option": "box:0", "colour": "red", "dest": "sign11"},
                             {"rid": "r2", "t": 2.0, "point": "pick", "option": "finish"}]
        self.make("A-L2-01-T1-r1", data, where=results)
        args, cells, text, _ = self.analyze("--manifest", str(manifest), runs=results)
        by_id = {c["run_id"]: c for c in cells}
        self.assertEqual(by_id["A-L2-01-T1-r1"]["first_unresolved"], True)
        for run_id in ("A-L2-01-T1-r1", "BASE-L2-01-T0-r1"):
            self.assertFalse(any("first assignment" in w for w in by_id[run_id]["warnings"]), run_id)
        self.assertIsNone(by_id["BASE-L2-01-T0-r1"]["first_unresolved"])
        self.assertIn("첫 배정 불명", text)
        self.assertNotIn("first assignment unresolved", text)

    def test_main_writes_three_outputs(self):
        results, manifest = self.write_results()
        name = "unit-test-tmp"
        out = HERE / "out" / name
        self.addCleanup(shutil.rmtree, out, True)
        with contextlib.redirect_stdout(io.StringIO()):
            am.main(["--runs", str(results), "--scenes", str(self.scene_file), "--manifest", str(manifest),
                     "--name", name, "--boots", "50", "--interim", "--note", "unit test"])
        self.assertIn("unit test", (out / "summary.md").read_text(encoding="utf-8"))
        for filename in ("summary.md", "cells.csv", "tests.json"):
            self.assertTrue((out / filename).stat().st_size > 0, filename)
        with (out / "cells.csv").open(encoding="utf-8") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 7)
        data = json.loads((out / "tests.json").read_text(encoding="utf-8"))
        self.assertEqual(data["meta"]["seed"], 2026111522)
        self.assertEqual(data["meta"]["boots"], 50)


if __name__ == "__main__":
    unittest.main()
