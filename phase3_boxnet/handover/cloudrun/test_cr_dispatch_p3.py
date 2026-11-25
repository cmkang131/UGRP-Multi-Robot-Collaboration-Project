"""Tests of cr_dispatch_p3.py (task T8). No network and no gcloud: `plan` runs the dispatcher's own simulation (fake gcloud, fake clock); a real run is only
refused before any gcloud call. Nothing in 20261118-cloudrun-p2/ is written (the files are checked by sha256).

  python3 -B -m unittest test_cr_dispatch_p3      (in this folder; TMPDIR set to a scratch folder in this sandbox)
"""
import contextlib
import csv
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cr_dispatch_p3 as W  # noqa: E402

P2D = W.P2D
MANIFESTS = HERE.parent / "manifests"
CHECK = MANIFESTS / "phase3v8-check.csv"
MAIN = MANIFESTS / "phase3v8-main.csv"
FAKE = "1a2b3c4d5e6f70819a0b1c2d3e4f5061728394a5"            # a 40-hex value for these tests only; never written into the real manifests
PHASE_TWO_SHA = {                                              # sha256 of the phase-2 dispatcher files, pins for the distributed, path-scrubbed copies
    "20261118-cloudrun-p2/cr_dispatch_p2.py": "9cb3db88d64d7b7a1657a228b07be16351d2c5744f3acec289fa8a359b7862e5",
    "20261115-batch/dispatch.py": "3ab487350e7d425a678739340e94c5906b78140d7443e9a77f7e04b35ee8a245",
    "20261115-batch/cloudrun/cr_dispatch.py": "85530125950b71093745e1c80beef56d3a09c366d3a1ab2bc6049f6f0fe83ebf",
}


def with_sha(source, sha, folder):
    """A copy of a manifest with every sha replaced (for tests only), written into folder."""
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        names = reader.fieldnames
    for r in rows:
        r["sha"] = sha
    out = folder / source.name
    with out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return out


class Dispatcher(unittest.TestCase):
    def test_the_phase_two_dispatcher_files_are_unchanged(self):
        root = HERE.parent / "test_support"
        for rel, digest in PHASE_TWO_SHA.items():
            self.assertEqual(hashlib.sha256((root / rel).read_bytes()).hexdigest(), digest, rel)

    def test_the_v8_groups_are_registered_the_way_the_phase_two_groups_are(self):
        for group in ("p2core", "p2pilot", "p2gate", "p3core", "p3chk", "p3v8core", "p3v8chk", "p3v10core", "p3v10chk", "p3v11", "p3v11chk"):
            self.assertIn(group, P2D.dispatch.ALL_GROUPS, group)
        self.assertEqual(W.P3_GROUPS, ("p3core", "p3chk", "p3v8core", "p3v8chk", "p3v10core", "p3v10chk", "p3v11", "p3v11chk",
                                      "p3v11budget", "p3v11budgetchk", "p3v11static", "p3v11staticchk"))

    def test_budget_groups_load_with_all_server_options(self):
        with mock.patch.object(sys, "path", [str(HERE.parent / "tools"), *sys.path]):
            import make_phase3
        with tempfile.TemporaryDirectory() as tmp:
            for name, source in make_phase3.build_v11_budget_files([1024, 8192]).items():
                path = Path(tmp) / name
                path.write_text(make_phase3.P2.csv_text(source, (*make_phase3.P2.COLUMNS, "recipient", "max_output_tokens")))
                rows = W.dispatch.load_manifest(path, real=True)
                self.assertEqual([(r["group"], r["leader"], r["server_args"]) for r in rows],
                                 [(r["group"], r["leader"], r["server_args"]) for r in source])

    def test_v11_groups_load_with_the_manifest_leader(self):
        for stage, group, size in (("main", "p3v11", 16), ("check", "p3v11chk", 2)):
            path = MANIFESTS / f"phase3v11-{stage}.csv"
            rows = W.dispatch.load_manifest(path, real=True)
            with path.open(newline="") as stream:
                source = list(csv.DictReader(stream))
            self.assertEqual(len(rows), size)
            self.assertEqual({r["group"] for r in rows}, {group})
            self.assertEqual([r["leader"] for r in rows], [r["leader"] for r in source])
            self.assertTrue(all(r["leader"] != r["recipient"] for r in source))
            self.assertEqual({r["arm"] for r in source}, {"CMAS"})

    def test_static_main_and_check_groups_load(self):
        with mock.patch.object(sys, "path", [str(HERE.parent / "tools"), *sys.path]):
            import make_phase3
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            make_phase3.main(["--design", "v11-static-budget", "--budgets", "17,41", "--output-dir", tmp, "--write", "--check"])
            for stage, count, group in (("main", 16, "p3v11static"), ("check", 4, "p3v11staticchk")):
                rows = W.dispatch.load_manifest(Path(tmp) / f"phase3v11-static-budget-{stage}.csv", real=True)
                self.assertEqual(len(rows), count)
                self.assertEqual({r["group"] for r in rows}, {group})
                self.assertTrue(all("--static-orders" in r["server_args"] for r in rows))

    def test_v10_groups_load_with_the_runner_team_values(self):
        for stage, group, size in (("main", "p3v10core", 99), ("check", "p3v10chk", 6)):
            path = MANIFESTS / f"phase3v10-{stage}.csv"
            rows = W.dispatch.load_manifest(path, real=True)
            self.assertEqual({r["group"] for r in rows}, {group})
            self.assertEqual(len(rows), size)
            self.assertEqual({r["run_id"].split("-")[2]: r["team"] for r in rows}, {"DMAS": "T1", "CMAS": "T2", "HMAS2": "T2"})

    def test_the_real_loader_of_the_dispatcher_accepts_the_placeholder_and_refuses_todo(self):
        """The gap the wrapper closes: dispatch.load_manifest(real=True) refuses TODO and PLACEHOLDER words only; the v8 placeholder has neither."""
        with tempfile.TemporaryDirectory() as tmp:
            placeholder = with_sha(CHECK, "PENDING-V8-EXEC-COMMIT", Path(tmp))
            self.assertEqual(len(P2D.dispatch.load_manifest(str(placeholder), real=True)), 12)
            (Path(tmp) / "todo").mkdir()
            todo = with_sha(CHECK, "TODO-freeze", Path(tmp) / "todo")
            with self.assertRaises(ValueError):
                P2D.dispatch.load_manifest(str(todo), real=True)

    def test_the_wrapper_adds_no_new_job_or_quota_rule(self):
        self.assertEqual(P2D.JOBS[3], "ugrp-run3")
        self.assertEqual(P2D.SHAPE[3], {"cpu": 2, "mem_gib": 6})

    def test_a_row_without_fixed_still_needs_allow_llm(self):
        with CHECK.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        problems = P2D.llm_guard(rows, allow_llm=False)
        self.assertEqual(len(problems), 12)
        self.assertEqual(P2D.llm_guard(rows, allow_llm=True), [])


class ShaGuard(unittest.TestCase):
    def test_the_placeholder_is_refused_before_the_dispatcher_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = with_sha(CHECK, "PENDING-V8-EXEC-COMMIT", Path(tmp))          # a copy: the real manifest may carry a commit by now
            with mock.patch.object(P2D, "cmd_plan") as plan, contextlib.redirect_stderr(io.StringIO()) as err:
                code = W.main(["plan", "--manifest", str(path), "--size", "3", "--regions", "us-central1=2", "--image-tag", "p3-test-1"])
        self.assertEqual(code, 2)
        self.assertIn("12 row(s) of phase3v8-check.csv have no 40-hex executor commit", err.getvalue())
        plan.assert_not_called()

    def test_the_main_placeholder_is_refused_for_a_real_run_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = with_sha(MAIN, "PENDING-V8-EXEC-COMMIT", Path(tmp))
            with mock.patch.object(P2D, "cmd_run") as run, contextlib.redirect_stderr(io.StringIO()):
                code = W.main(["run", "--manifest", str(path), "--dir", str(Path(tmp) / "runs"), "--size", "3", "--regions", "us-central1=6", "--image-tag", "p3-test-1", "--allow-llm", "--go"])
        self.assertEqual(code, 2)
        run.assert_not_called()

    def test_short_long_upper_case_and_empty_shas_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for sha in ("1a2b3c", FAKE + "0", FAKE.upper(), "", "TODO-freeze-946d966"):
                path = with_sha(CHECK, sha, folder)
                with contextlib.redirect_stderr(io.StringIO()):
                    code = W.main(["plan", "--manifest", str(path), "--size", "3", "--regions", "us-central1=2", "--image-tag", "p3-test-1"])
                self.assertEqual(code, 2, repr(sha))

    def test_a_missing_manifest_is_refused_not_crashed(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = W.main(["plan", "--manifest", str(HERE / "no-such.csv"), "--size", "3", "--regions", "us-central1=2", "--image-tag", "p3-test-1"])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err.getvalue())


class Simulation(unittest.TestCase):
    """Plan mode only: the dispatcher's own Scheduler with a fake gcloud and a fake clock. The printed commands are not run."""

    def plan(self, manifest, regions, size_rows):
        with tempfile.TemporaryDirectory() as tmp:
            path = with_sha(manifest, FAKE, Path(tmp))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = W.main(["plan", "--manifest", str(path), "--size", "3", "--regions", regions, "--image-tag", "p3-test-1", "--batch", "p3v8-test-n3"])
        text = buf.getvalue()
        self.assertEqual(code, 0, text[-400:])
        self.assertEqual(text.count("run jobs execute ugrp-run3"), size_rows)
        self.assertIn(f"PLAN end: {size_rows} execute commands", text)
        self.assertIn("gcloud-p <project-id> run jobs execute ugrp-run3", text)
        self.assertNotIn("TODO", text)
        return text

    def test_the_check_rows_pass_the_loading_and_the_simulation(self):
        text = self.plan(CHECK, "us-central1=2", 12)
        self.assertIn('"group":"p3v8chk"', text)
        self.assertIn('"scene_file":"scenes/P2R_N03_S10.json"', text)

    def test_the_main_rows_pass_the_loading_and_the_simulation(self):
        text = self.plan(MAIN, "us-central1=6,us-east1=6,us-west1=6", 88)
        self.assertIn('"group":"p3v8core"', text)
        self.assertEqual(text.count('"group":"p3v8core"'), 88)


class RealRunGuards(unittest.TestCase):
    def test_a_real_run_without_allow_llm_is_refused_before_any_gcloud_call(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(P2D.cr_dispatch, "gcloud") as gcloud, contextlib.redirect_stderr(io.StringIO()) as err:
            path = with_sha(CHECK, FAKE, Path(tmp))
            code = W.main(["run", "--manifest", str(path), "--dir", str(Path(tmp) / "runs"), "--size", "3", "--regions", "us-central1=2", "--image-tag", "p3-test-1", "--go"])
        self.assertEqual(code, 2)
        self.assertIn("pass --allow-llm only for a real LLM run", err.getvalue())
        gcloud.assert_not_called()

    def test_a_dry_run_lists_the_rows_and_calls_no_gcloud(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(P2D.cr_dispatch, "gcloud") as gcloud:
            path = with_sha(CHECK, FAKE, Path(tmp))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = W.main(["run", "--manifest", str(path), "--dir", str(Path(tmp) / "runs"), "--size", "3", "--regions", "us-central1=2", "--image-tag", "p3-test-1"])
        self.assertEqual(code, 0)
        self.assertIn("DRY (no --go): 12 rows would go to job ugrp-run3", buf.getvalue())
        gcloud.assert_not_called()


if __name__ == "__main__":
    unittest.main()
