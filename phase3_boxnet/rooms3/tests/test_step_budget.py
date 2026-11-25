"""Wall budgets of the step check: the local default stays 1,500 s and the cloud step job passes 5,400 s."""
import contextlib
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import call, patch

from rooms3 import check_step, checks


class StepBudget(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.scene = self.root / "scene"
        self.scene.mkdir()
        (self.scene / "map.json").write_text(json.dumps({"source": {"seed": 0}}))
        (self.scene / "scene.xml").write_text("<mujoco/>")

    def check(self, name, *extra, fire=False):
        # run() stands in for the physical check. With fire=True it runs the SIGALRM handler that main installed,
        # which is what the kernel does when the budget expires.
        out = self.root / name
        handlers = []

        def fake_run(*_args):
            if fire:
                handlers[0](signal.SIGALRM, None)
            return 0

        def record_handler(_signum, handler):
            handlers.append(handler)
            return signal.SIG_DFL

        with patch.object(check_step, "configure"), patch.object(check_step, "run", side_effect=fake_run), \
                patch.object(check_step.signal, "signal", side_effect=record_handler), \
                patch.object(check_step.signal, "alarm") as alarm:
            rc = check_step.main(["--scene", str(self.scene), "--out", str(out), *extra])
        return rc, alarm, json.loads((out / "check.json").read_bytes())

    def test_default_budget_is_the_local_1500_seconds(self):
        rc, alarm, record = self.check("default", fire=True)
        self.assertEqual(alarm.call_args_list, [call(1500), call(0)])
        self.assertEqual((rc, record["status"], record["budget_s"]), (2, "error", 1500))
        self.assertEqual(record["reason"], "TimeoutError: 1500 s step-check budget")

    def test_cloud_budget_is_passed_as_an_argument(self):
        rc, alarm, record = self.check("cloud", "--budget-s", "5400", fire=True)
        self.assertEqual(alarm.call_args_list, [call(5400), call(0)])
        self.assertEqual((rc, record["budget_s"]), (2, 5400))
        self.assertEqual(record["reason"], "TimeoutError: 5400 s step-check budget")

    def test_budget_must_be_positive_and_writes_nothing(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.check("bad", "--budget-s", "0")
        self.assertFalse((self.root / "bad").exists())

    def test_limits_nest_alarm_inside_child_timeout_inside_task_limit(self):
        step = checks.LIMITS["rooms3-step"]
        self.assertEqual((step["budget"], step["driver"], step["task"]), (5400, 5520, 7200))
        self.assertLess(step["budget"], step["driver"])
        self.assertLess(step["driver"], step["task"])
        self.assertEqual(checks.LIMITS["rooms3-camera"], {"driver": 1620})
        self.assertEqual(check_step.DEFAULT_BUDGET_S, 1500)


if __name__ == "__main__":
    unittest.main()
