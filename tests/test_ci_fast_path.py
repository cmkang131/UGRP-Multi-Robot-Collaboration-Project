"""CI routing and its required gate must fail closed without heavy dependencies."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from itertools import product
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from scripts import check_ci_fixtures as fixtures, ci_paths

ROOT = Path(__file__).resolve().parents[1]


class CiFastPathTests(unittest.TestCase):
    def test_new_push_preserves_queued_and_running_ci(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        concurrency = workflow.split("\nconcurrency:\n", 1)[1].split("\njobs:\n", 1)[0]
        # A shared PR group can replace even a pending run; every run needs its own group.
        self.assertIn("${{ github.run_id }}", concurrency)
        self.assertNotIn("github.ref", concurrency)
        self.assertIn("cancel-in-progress: false", concurrency)

    def test_only_allowed_documentation_uses_fast_path(self):
        paths = ["README.md", "AGENTS.md", "docs/guide.md", "docs/images/example.png",
                 "experiments/2026-09-30-process-review/NOTES.md"]
        self.assertFalse(ci_paths.requires_full_suite(paths))

    def test_mixed_code_config_tests_and_unknown_paths_run_full_suite(self):
        for path in ["scripts/run.py", "harness/a.py", "sim/a.py", "configs/a.json",
                     "tests/test_a.py", "tests/fixtures/README.md", "requirements-test.txt",
                     ".github/workflows/tests.yml", "docs/example.py", "docs/config.yaml",
                     "docs/input.json", "docs/unknown.bin", "experiments/run/data.csv",
                     "experiments/run/example_trial_record.json.gz", "maps/README.md"]:
            with self.subTest(path=path):
                self.assertTrue(ci_paths.requires_full_suite(["README.md", path]))
        self.assertTrue(ci_paths.requires_full_suite([]))

    def test_invalid_paths_run_full_suite(self):
        for path in ["", "/docs/a.md", "docs/../tests/a.md", "docs//a.md", "docs/./a.md"]:
            with self.subTest(path=path):
                self.assertTrue(ci_paths.requires_full_suite([path]))

    def test_main_push_and_missing_comparison_run_full_suite(self):
        with patch.object(ci_paths, "changed_paths", side_effect=AssertionError("unexpected diff")):
            for event, base, head in [("push", "a", "b"), ("unknown", "a", "b"),
                                      ("pull_request", "", "b"), ("pull_request", "a", "")]:
                with self.subTest(event=event, base=base, head=head), redirect_stdout(StringIO()):
                    self.assertTrue(ci_paths.select_full_suite(event, base, head))

    def test_diff_failure_runs_full_suite(self):
        with patch.object(ci_paths, "changed_paths", side_effect=subprocess.CalledProcessError(128, "git")), \
                redirect_stdout(StringIO()):
            self.assertTrue(ci_paths.select_full_suite("pull_request", "a", "b"))

    def test_cli_appends_explicit_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.write_text("existing=value\n")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                    patch.object(ci_paths, "changed_paths", return_value=["docs/a.md"]), \
                    redirect_stdout(StringIO()):
                self.assertEqual(ci_paths.main(["--event", "pull_request", "--base", "a", "--head", "b"]), 0)
            self.assertEqual(output.read_text(), "existing=value\nfull_suite=false\n")

    def test_git_diff_checks_both_rename_paths_and_preserves_unusual_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

            def commit():
                git("add", "-A")
                git("-c", "user.name=CI Fixture", "-c", "user.email=ci@example.invalid",
                    "commit", "-qm", "fixture")
                return git("rev-parse", "HEAD")

            git("init", "-q")
            (root / "scripts").mkdir()
            (root / "scripts/tool.py").write_text("print('test')\n")
            base = commit()
            (root / "docs").mkdir()
            unusual = "docs/space and\nnewline.md"
            (root / unusual).write_text("# example\n")
            docs_head = commit()
            self.assertEqual(ci_paths.changed_paths(root, base, docs_head), [unusual])
            (root / "scripts/tool.py").rename(root / "docs/tool.md")
            rename_head = commit()
            paths = ci_paths.changed_paths(root, docs_head, rename_head)
            self.assertEqual(set(paths), {"scripts/tool.py", "docs/tool.md"})
            self.assertTrue(ci_paths.requires_full_suite(paths))
            (root / unusual).unlink()
            delete_head = commit()
            self.assertFalse(ci_paths.requires_full_suite(ci_paths.changed_paths(root, rename_head, delete_head)))

    def test_missing_fixtures_fail_with_repair_instructions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in fixtures.REQUIRED_FIXTURES[:-1]:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"fixture")
            message = StringIO()
            with redirect_stderr(message):
                self.assertFalse(fixtures.check_fixtures(root))
            self.assertIn(fixtures.REQUIRED_FIXTURES[-1], message.getvalue())
            self.assertIn("git sparse-checkout add ", message.getvalue())
            target = root / fixtures.REQUIRED_FIXTURES[-1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"fixture")
            self.assertTrue(fixtures.check_fixtures(root))

    def test_runner_refuses_missing_fixtures_before_lock_or_pytest(self):
        from scripts import run_ci_tests as runner

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/test_ci_fast_path.py").touch()
            with patch.object(runner, "ROOT", root), \
                    patch.object(runner, "local_lock_root", side_effect=AssertionError("lock started")), \
                    patch.object(runner.subprocess, "call", side_effect=AssertionError("pytest started")), \
                    redirect_stderr(StringIO()):
                self.assertEqual(runner.main([]), 2)

    def test_gate_accepts_only_explicit_docs_skip_or_complete_full_suite(self):
        workflow = (ROOT / ".github/workflows/tests.yml").read_text()
        gate = workflow.split("  offline-regressions:\n", 1)[1].split("\n  ubuntu-simulation-runtime:", 1)[0]
        self.assertIn("    name: offline-regressions\n", gate)
        self.assertIn("    if: ${{ always() }}\n", gate)
        self.assertIn("    needs: [ci-preflight, offline-regression-shards, offline-regression-checks]\n", gate)
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        results = ["success", "failure", "cancelled", "skipped"]
        for preflight, selection, shards, checks in product(results, ["true", "false", "", "invalid"], results, results):
            with self.subTest(preflight=preflight, selection=selection, shards=shards, checks=checks):
                result = subprocess.run(["sh", "-eu", "-c", script], capture_output=True,
                                        env={"PREFLIGHT_RESULT": preflight, "FULL_SUITE": selection,
                                             "SHARDS_RESULT": shards, "CHECKS_RESULT": checks})
                expected = preflight == "success" and (
                    (selection == "true" and shards == checks == "success") or
                    (selection == "false" and shards == checks == "skipped"))
                self.assertEqual(result.returncode == 0, expected)


if __name__ == "__main__":
    unittest.main()
