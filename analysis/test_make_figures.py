import contextlib
import io
import json
import shutil
import unittest
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import analyze_main as am
import make_figures as mf
from test_analyze_main import Base, team

HERE = Path(__file__).resolve().parent
NAME = "unit-figures-tmp"


def messages(n):
    return {"messages": [{"from": "r1" if i % 2 == 0 else "r2", "time": float(i)} for i in range(n)]}


class Figures(Base):
    """Synthetic grid: baseline + mainA T0/T1/T2 on three scenes, two reps each. Numbers are fixtures, not results."""

    def build(self, with_baseline=True):
        results = self.root / "results"
        results.mkdir()
        cover = {("T0", "L2-01"): False, ("T0", "C2-01"): True, ("T0", "X2-01"): True,
                 ("T1", "L2-01"): True, ("T1", "C2-01"): True, ("T1", "X2-01"): True,
                 ("T2", "L2-01"): True, ("T2", "C2-01"): False, ("T2", "X2-01"): True}
        lines = ["run_id,group,scene_id,team,rep,vm_args,server_args"]
        for sid in self.scene_ids:
            if with_baseline:
                run_id = "BASE-%s-T0-r1" % sid
                lines.append("%s,baseline,%s,T0,1,%s --fixed oracle," % (run_id, sid, am.COMMON_ARGS))
                self.make(run_id, team(sid, brain={"kind": "fixed_plan"}, success=sid != "X2-01"), where=results)
            for structure in am.STRUCTS:
                for rep in (1, 2):
                    run_id = "A-%s-%s-r%d" % (sid, structure, rep)
                    lines.append("%s,mainA,%s,%s,%d,%s," % (run_id, sid, structure, rep, am.COMMON_ARGS))
                    brain = messages({"T0": 0, "T1": 6, "T2": 5}[structure])
                    self.make(run_id, team(sid, cover=cover[(structure, sid)], brain=brain), where=results)
        manifest = self.root / "manifest.csv"
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out = HERE / "out" / NAME
        self.addCleanup(shutil.rmtree, out, True)
        with contextlib.redirect_stdout(io.StringIO()):
            am.main(["--runs", str(results), "--scenes", str(self.scene_file), "--manifest", str(manifest), "--name", NAME, "--boots", "300"])
        figures = self.root / "figures"
        mf.make(name=NAME, out=figures, backend="svg", note="unit test")
        return out, figures, json.loads((figures / "figures.json").read_text(encoding="utf-8"))

    def test_cells_parse_back_to_what_book_reads(self):
        out, _, _ = self.build()
        cells = mf.parse_cells(out / "cells.csv")
        sp = [c for c in cells if c["structure"] == "T1" and c["state"] == "ok"][0]
        self.assertEqual(sp["C"], 1)
        self.assertEqual(sp["SP02"], Fraction(1) - Fraction(2, 50))        # M=6, 2R=4: 1 - 0.02*2, exact decimal
        self.assertIsInstance(sp["tags"], list)
        self.assertIs(sp["complete"], True)
        book = am.Book(cells, False, "exclude")
        self.assertEqual(book.scene_means("T0", "C", "zero", "mainA"), {"L2-01": Fraction(0), "C2-01": Fraction(1), "X2-01": Fraction(1)})

    def test_fig_a_matches_analysis_numbers(self):
        out, _, nums = self.build()
        tests = json.loads((out / "tests.json").read_text(encoding="utf-8"))
        a = nums["fig_a_structure_means"]["C"]
        self.assertAlmostEqual(a["T0"]["mean"], 2 / 3)
        self.assertAlmostEqual(a["T1"]["mean"], 1.0)
        self.assertAlmostEqual(a["T2"]["mean"], 2 / 3)
        values = [a["T0"]["scenes"][s] for s in sorted(a["T0"]["scenes"])]
        self.assertEqual(tuple(a["T0"]["ci95"]), am.bootstrap_ci(values, tests["meta"]["boots"], tests["meta"]["seed"]))
        sp = nums["fig_a_structure_means"][tests["meta"]["penalty"]["primary"]]
        self.assertAlmostEqual(sp["T1"]["mean"], 1 - 0.02 * 2)             # every T1 run sent 6 messages, allowance 4
        self.assertAlmostEqual(sp["T0"]["mean"], 2 / 3)                    # T0: SP = C

    def test_fig_b_parts_sum_to_shortfall_and_use_primary_tag(self):
        _, _, nums = self.build()
        for structure, row in nums["fig_b_shortfall_causes"].items():
            self.assertAlmostEqual(sum(row["parts_pp"].values()), row["shortfall_pp"])
        t0 = nums["fig_b_shortfall_causes"]["T0"]
        self.assertAlmostEqual(t0["shortfall_pp"], 100 / 3)
        self.assertAlmostEqual(t0["parts_pp"]["no_info_T0"], 100 / 3)

    def test_fig_c_counts_and_baseline_column(self):
        _, _, nums = self.build()
        c = nums["fig_c_plan_vs_physical"]
        self.assertEqual(c["ORACLE"], {"P1/S1": 2, "P1/S0": 1})            # X2-01 baseline: plan right, physical failed
        self.assertEqual(sum(c["T1"].values()), 6)

    def test_fig_d_message_counts(self):
        _, _, nums = self.build()
        d = nums["fig_d_message_counts"]
        self.assertEqual(d["T0"]["M_counts"], {"0": 6})
        self.assertEqual(d["T1"]["M_counts"], {"6": 6})
        self.assertEqual(d["T2"]["M_counts"], {"5": 6})

    def test_fig_e_gap_on_common_scenes(self):
        _, _, nums = self.build()
        e = nums["fig_e_vs_baseline"]["C"]["by_structure"]
        self.assertEqual(e["T0"]["common_scenes"], 3)
        self.assertAlmostEqual(e["T0"]["gap_pp"], 100 / 3)                 # baseline 1 - T0 2/3
        self.assertAlmostEqual(e["T1"]["gap_pp"], 0.0)

    def test_fig_e_without_baseline_renders_and_says_so(self):
        _, figures, nums = self.build(with_baseline=False)
        e = nums["fig_e_vs_baseline"]["C"]
        self.assertEqual(e["baseline_scenes"], 0)
        self.assertIsNone(e["by_structure"]["T0"]["gap_pp"])
        self.assertIn("기준선 칸 없음", (figures / "fig_e_vs_baseline.svg").read_text(encoding="utf-8"))

    def test_svg_files_are_well_formed_and_carry_the_note(self):
        _, figures, _ = self.build()
        svgs = sorted(figures.glob("fig_*.svg"))
        self.assertEqual(len(svgs), 5)
        for svg in svgs:
            root = ET.fromstring(svg.read_text(encoding="utf-8"))
            self.assertTrue(root.tag.endswith("svg"))
            self.assertIn("unit test", svg.read_text(encoding="utf-8"))

    def test_main_group_missing_stops_with_the_arm_list(self):
        out, _, _ = self.build()
        cells = mf.parse_cells(out / "cells.csv")
        with self.assertRaises(SystemExit) as stop:
            mf.pick_arm(cells, {"main_group": "nope"})
        self.assertIn("mainA", str(stop.exception))
        self.assertEqual(mf.pick_arm(cells, {"main_group": "nope"}, "mainA"), "mainA")

    def test_helpers(self):
        self.assertEqual(mf.nice_ticks(100), [0, 20, 40, 60, 80, 100])
        self.assertEqual(mf.nice_ticks(8)[0], 0)
        self.assertTrue(all(mf.text_width(line, 11) <= 100 for line in mf.wrap("가나다 라마바 사아자 차카타 파하", 100, 11)))


if __name__ == "__main__":
    unittest.main()
