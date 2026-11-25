"""Offline integration checks. Every driver outcome, build response and object store is a fixture."""
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

import fetch
import ops
import stage
import worker

sys.path.insert(0, str(stage.ROOT / "handover/tests"))
from test_gate import layout, synthetic
from PIL import Image


IMAGE = worker.PACKAGE + "@sha256:" + "a" * 64
P2 = stage.ROOT / "test_support/20261118-cloudrun-p2"
spec = importlib.util.spec_from_file_location("archived_worker", P2 / "archive_fixture.py")
archived_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archived_worker)


class Store:
    make_tar = staticmethod(archived_worker.make_tar)

    def __init__(self):
        self.objects = {}
        self.reject = None

    def gcs_upload(self, bucket, key, path, ctype=None):
        if bucket != worker.BUCKET:
            raise AssertionError("unexpected bucket")
        if key.endswith(self.reject or "!"):
            return False
        self.objects[key] = path.read_bytes()
        return True

    def download(self, uri, path):
        key = uri.removeprefix(f"gs://{worker.BUCKET}/")
        path.write_bytes(self.objects[key])


def env(scope, index):
    first, count = worker.SELECTIONS[scope]
    return {"CLOUD_RUN_JOB": worker.JOB, "CLOUD_RUN_EXECUTION": worker.JOB + "-test-" + scope,
            "CLOUD_RUN_TASK_INDEX": str(index), "CLOUD_RUN_TASK_COUNT": str(count),
            "HANDOVER_FIRST_TRIAL": str(first), "CLOUD_RUN_TASK_ATTEMPT": "0",
            "RESULT_BUCKET": worker.BUCKET, "HANDOVER_IMAGE": IMAGE, "HANDOVER_EXPECT_IMAGE": IMAGE}


def fixture_driver(argv, **kwargs):
    k = int(argv[argv.index("--trial") + 1])
    out = Path(argv[argv.index("--out") + 1])
    out.mkdir(exist_ok=False)
    name = argv[argv.index("--trial-table")+1] if "--trial-table" in argv else layout.TABLE.name
    t, events, rows, run = synthetic(layout.trials(name)[k])
    (out / "run.json").write_text(json.dumps(run))
    (out / "trial.json").write_text(json.dumps(t))
    (out / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    with (out / "chassis.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    for name in {e["frame"] for e in events if "frame" in e}:
        Image.new("RGB", (4, 4)).save(out / name)
    (out / "cards").mkdir()
    (out / "cards/fixture.txt").write_text("test only")
    return subprocess.CompletedProcess(argv, 0)


class CloudPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.layer = self.work / "layer.json"
        self.layer.write_text(json.dumps({"exec_commit": stage.COMMIT, "base_image": IMAGE,
                                         "sha256": {"handover/scenes/trials.csv": "b" * 64}}))
        self.store = Store()
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def task(self, scope="smoke", index=0, driver=fixture_driver):
        return worker.run_task(env(scope, index), self.store, root=self.work,
                               scratch=self.work / "scratch", run=driver)

    def collect(self, scope):
        fetch.fetch_rows(self.work / "trials", env(scope, 0)["CLOUD_RUN_EXECUTION"], IMAGE,
                         worker.file_hash(self.layer), worker.SELECTIONS[scope], self.store.download)

    def test_staged_input_bytes_parent_and_commit(self):
        receipt = json.loads((P2 / "builds/p3v8-d369231-2.json").read_bytes())
        files = stage.context()
        layer = json.loads(files["layer.json"])
        self.assertEqual((receipt["exec_commit"], receipt["pinned"]), (stage.PARENT, layer["base_image"]))
        self.assertEqual(layer["exec_commit"], stage.COMMIT)
        self.assertEqual(stage.inventory(files), (stage.HERE / "verification/bundle-staged.sha256").read_text())
        self.assertEqual(files["Dockerfile"].splitlines()[0].decode(), "FROM " + receipt["pinned"])
        expected = ({"exec/" + n for n in stage.EXEC_FILES} | {"handover/" + n for n in stage.GATE_FILES}
                    | {"worker.py", "check_image.py", "Dockerfile", "cloudbuild.yaml", "layer.json", ".gcloudignore"})
        self.assertEqual(set(files), expected)
        tree = self.work / "ctx"
        stage.write_context(tree, files)
        self.assertEqual({str(p.relative_to(tree)): p.read_bytes() for p in tree.rglob("*") if p.is_file()}, files)
        for rel, sha in layer["sha256"].items():
            self.assertEqual(worker.file_hash(tree / rel), sha)
        for rel in stage.EXEC_FILES:
            pins = json.loads((stage.HERE / "verification/exec-source.json").read_text())
            self.assertEqual(worker.file_hash(stage.ROOT / "exec" / rel), pins["sha256"][rel])
            self.assertEqual(files["exec/" + rel], (stage.ROOT / "exec" / rel).read_bytes())
        with self.assertRaises(FileExistsError):
            stage.write_context(tree, files)

    def test_deploy_flags_match_job_yaml(self):
        job = yaml.safe_load(ops.job_text(IMAGE))
        self.assertEqual(job["metadata"], {"name": worker.JOB, "namespace": "<project-number>"})
        template = job["spec"]["template"]
        self.assertEqual(template["metadata"]["annotations"]["run.googleapis.com/execution-environment"], "gen2")
        config = template["spec"]
        self.assertEqual((config["taskCount"], config["parallelism"]), (12, 1))
        task = config["template"]["spec"]
        container, = task["containers"]
        limits = container["resources"]["limits"]
        self.assertEqual((task["maxRetries"], int(task["timeoutSeconds"])), (0, 1800))
        self.assertEqual(task["serviceAccountName"], "<service-account>")
        self.assertEqual(container["image"], IMAGE)
        self.assertEqual(limits, {"cpu": "2", "memory": "6Gi"})
        self.assertNotIn("volumes", task)
        self.assertEqual({e["name"]: e["value"] for e in container["env"]},
                         {"HANDOVER_IMAGE": IMAGE, "RESULT_BUCKET": worker.BUCKET, "HANDOVER_FIRST_TRIAL": "1"})
        self.assertEqual(ops.deploy_command(IMAGE), [
            "gcloud-p", worker.PROJECT, "run", "jobs", "deploy", job["metadata"]["name"], "--region", "us-central1",
            "--image", container["image"], "--cpu", limits["cpu"], "--memory", limits["memory"],
            "--task-timeout", f"{task['timeoutSeconds']}s", "--max-retries", str(task["maxRetries"]),
            "--tasks", str(config["taskCount"]), "--parallelism", str(config["parallelism"]),
            "--service-account", task["serviceAccountName"],
            "--set-env-vars", ",".join(f"{e['name']}={e['value']}" for e in container["env"]),
        ])

    def test_execute_command_and_offline_plan(self):
        self.assertEqual(ops.execute_command(self.work, "remaining", IMAGE),
                         ["gcloud-p", worker.PROJECT, "run", "jobs", "execute", worker.JOB, "--region", "us-central1",
                          "--tasks", "11", "--update-env-vars", "HANDOVER_FIRST_TRIAL=2,HANDOVER_EXPECT_IMAGE=" + IMAGE
                          + ",HANDOVER_SUBMISSION=" + ops.submission_id(self.work, "remaining"),
                          "--async", "--format=value(metadata.name)"])
        with (patch.object(ops, "cloud", side_effect=AssertionError("cloud command during plan")),
              contextlib.redirect_stdout(io.StringIO()) as preview):
            ops.plan(self.work)
        preview_image = worker.PACKAGE + "@sha256:" + "0" * 64
        self.assertIn(shlex.join(ops.deploy_command(preview_image)), preview.getvalue().splitlines())
        self.assertFalse((self.work / "build").exists())

    def test_deploy_reuses_matching_receipts_and_refuses_a_conflict(self):
        (self.work / "build").mkdir()
        ops.save(self.work / "build/image.txt", IMAGE)
        receipt = self.work / "job.yaml"
        receipt.write_text(ops.job_text(IMAGE))
        with (patch.object(ops, "cloud") as cloud,
              patch.object(ops, "save", side_effect=AssertionError("rewrote receipt"))):
            ops.deploy(self.work)
            cloud.assert_called_once_with(ops.deploy_command(IMAGE))

        receipt.write_text(ops.job_text(worker.PACKAGE + "@sha256:" + "b" * 64))
        with patch.object(ops, "cloud") as cloud:
            with self.assertRaisesRegex(ValueError, "existing deployment file differs"):
                ops.deploy(self.work)
            cloud.assert_not_called()

    def test_image_mismatch_stops_each_launch_before_reservation(self):
        (self.work / "build").mkdir()
        ops.save(self.work / "build/image.txt", IMAGE)
        other_image = worker.PACKAGE + "@sha256:" + "b" * 64
        for scope in worker.SELECTIONS:
            with self.subTest(scope=scope), patch.object(ops, "cloud", return_value=other_image) as cloud:
                with self.assertRaisesRegex(ValueError, "deployed job image differs"):
                    ops.launch(self.work, scope)
                cloud.assert_called_once_with(
                    ["gcloud-p", worker.PROJECT, "run", "jobs", "describe", worker.JOB, "--region", "us-central1",
                     "--format=value(spec.template.spec.template.spec.containers[0].image)"], output=True)
                self.assertFalse((self.work / scope).exists())

    def test_index_mapping_smoke_remaining_and_all(self):
        numbers = lambda first, count: [worker.trial_number(first, count, i) for i in range(count)]
        all_trials = numbers(*worker.SELECTIONS["all"])
        self.assertEqual(all_trials, list(range(1, 13)))
        self.assertEqual(numbers(*worker.SELECTIONS["smoke"]) + numbers(*worker.SELECTIONS["remaining"]), all_trials)
        for args in [(0, 12, 0), (1, 13, 0), (1, 12, -1), (1, 1, 1), (2, 11, 11)]:
            with self.assertRaises(ValueError):
                worker.trial_number(*args)
        bad = dict(env("smoke", 0), CLOUD_RUN_TASK_ATTEMPT="1")
        with self.assertRaises(ValueError):
            worker.run_task(bad, self.store, scratch=self.work)
        self.assertFalse(self.store.objects)

    def test_swapped_cohort_through_submission_worker_fetch_and_scorer(self):
        swapped = "trials-swapped.csv"
        build = self.work / "build"
        (build / "context").mkdir(parents=True)
        ops.save(build / "image.txt", IMAGE)
        layer = json.loads(self.layer.read_bytes())
        digest = worker.file_hash(layout.TABLE.with_name(swapped))
        layer["sha256"][f"handover/scenes/{swapped}"] = digest
        self.layer.write_text(json.dumps(layer))
        (build / "context/layer.json").write_bytes(self.layer.read_bytes())
        for scope in ("smoke", "remaining"):
            name = env(scope, 0)["CLOUD_RUN_EXECUTION"]
            options = ["--trial-table", swapped] if scope == "smoke" else []
            with patch.object(ops, "cloud", side_effect=[IMAGE, name]) as cloud:
                ops.main(["run", str(self.work), scope, *options])
            cmd = cloud.call_args.args[0]
            settings = dict(v.split("=", 1) for v in cmd[cmd.index("--update-env-vars")+1].split(","))
            self.assertEqual(settings["HANDOVER_TRIAL_TABLE"], swapped)
            for i in range(worker.SELECTIONS[scope][1]):
                task_env = dict(env(scope, i), **settings)
                self.assertEqual(worker.run_task(task_env, self.store, root=self.work,
                                                 scratch=self.work / "scratch", run=fixture_driver), 0)
            with patch.object(ops, "cloud", side_effect=lambda cmd: self.store.download(cmd[-2], Path(cmd[-1]))):
                ops.collect(self.work, scope)
            rows = sorted((self.work / "trials").glob("trial-*"))
            output = subprocess.check_output([sys.executable, "-B", str(stage.ROOT / "handover/score.py"), *rows],
                                             text=True)
            self.assertIn("trial table " + swapped, output)
            self.assertIn("gate PENDING" if scope == "smoke" else "12 evaluated", output)
        self.assertEqual(len(rows), 12)
        self.assertIn("gate PASS", output)
        self.assertEqual(ops.stored(self.work / "trial-table.txt"), swapped)
        for k, folder in enumerate(rows, 1):
            self.assertEqual(json.loads((folder / "trial.json").read_bytes()), layout.trials(swapped)[k])
            marker = json.loads((folder / "cloud-meta.json").read_bytes())
            self.assertEqual((marker["trial_table"], marker["trials_sha256"]), (swapped, digest))
            self.assertEqual(marker["driver_argv"][-2:], ["--trial-table", swapped])
        with patch.object(ops, "cloud") as cloud, self.assertRaisesRegex(ValueError, "cohort trial table"):
            ops.launch(self.work, "smoke", layout.TABLE.name)
        cloud.assert_not_called()
        # Idempotent fetch also checks table identity on a previously fetched row.
        marker_file = rows[0] / "cloud-meta.json"
        marker = json.loads(marker_file.read_bytes())
        for key, wrong, reason in (("trial_table", layout.TABLE.name, "trial table"),
                                   ("trials_sha256", "0"*64, "digest")):
            marker_file.write_text(json.dumps(dict(marker, **{key: wrong})))
            with self.assertRaisesRegex(ValueError, reason):
                fetch.fetch_one(self.work / "trials", env("smoke", 0)["CLOUD_RUN_EXECUTION"], IMAGE,
                                worker.file_hash(self.layer), 1, 1, 0, self.store.download, swapped, digest)

    def test_swapped_requires_a_compatible_image_and_a_fresh_cohort(self):
        build = self.work / "build"
        (build / "context").mkdir(parents=True)
        ops.save(build / "image.txt", IMAGE)
        (build / "context/layer.json").write_bytes(self.layer.read_bytes())
        with patch.object(ops, "cloud") as cloud:
            with self.assertRaisesRegex(ValueError, "staged image lacks"):
                ops.launch(self.work, "smoke", "trials-swapped.csv")
            self.assertFalse((self.work / "trial-table.txt").exists())
            (self.work / "smoke").mkdir()  # legacy default cohort, without a table receipt
            with self.assertRaisesRegex(ValueError, "cohort trial table"):
                ops.launch(self.work, "remaining", "trials-swapped.csv")
            cloud.assert_not_called()

    def test_split_round_trip_and_real_scorer_with_synthetic_evidence(self):
        for scope in ("smoke", "remaining"):
            for i in range(worker.SELECTIONS[scope][1]):
                self.assertEqual(self.task(scope, i), 0)
            self.collect(scope)
            rows = sorted((self.work / "trials").glob("trial-*"))
            output = subprocess.check_output([sys.executable, "-B", str(stage.ROOT / "handover/score.py"), *rows],
                                             text=True)
            if scope == "smoke":
                self.assertIn("1 evaluated", output)
                self.assertIn("gate PENDING", output)
            else:
                self.assertEqual(len(rows), 12)
                self.assertIn("12 evaluated", output)
                self.assertIn("gate PASS", output)
        self.assertEqual(len(self.store.objects), 24)
        self.assertEqual((rows[-1] / "cards/fixture.txt").read_text(), "test only")
        self.collect("remaining")

    def test_blue_first_round_trip_covers_every_row_once(self):
        self.assertEqual(len(set(worker.SELECTIONS.values())), len(worker.SELECTIONS))
        self.assertEqual(layout.trials()[2]["colour"], "blue")
        for scope, expected in (("blue-smoke", [2]), ("after-blue", [1, *range(3, 13)])):
            first, count = worker.SELECTIONS[scope]
            self.assertEqual([worker.trial_number(first, count, i) for i in range(count)], expected)
            for i in range(count):
                self.assertEqual(self.task(scope, i), 0)
            self.collect(scope)
            for index, trial in enumerate(expected):
                row = self.work / "trials" / worker.row_name(trial)
                meta = json.loads((row / "cloud-meta.json").read_bytes())
                self.assertEqual((meta["task_index"], meta["trial"], meta["execution"]),
                                 (index, trial, env(scope, index)["CLOUD_RUN_EXECUTION"]))
            if count == 1:
                self.assertEqual([p.name for p in (self.work / "trials").iterdir()], ["trial-02"])
        self.assertEqual(len(self.store.objects), 24)
        self.assertEqual(len(list((self.work / "trials").iterdir())), 12)

    def test_blue_first_reservations_reject_overlaps_with_legacy_groups(self):
        (self.work / "build").mkdir()
        ops.save(self.work / "build/image.txt", IMAGE)
        for scope in ("blue-smoke", "after-blue"):
            with patch.object(ops, "cloud", side_effect=[IMAGE, env(scope, 0)["CLOUD_RUN_EXECUTION"]]):
                ops.launch(self.work, scope)
            conflicts = ("remaining", "all") if scope == "blue-smoke" else ("smoke", "remaining", "all")
            with patch.object(ops, "cloud") as cloud:
                for other in conflicts:
                    with self.assertRaisesRegex(ValueError, "repeat trials"):
                        ops.launch(self.work, other)
                cloud.assert_not_called()

    def test_recorded_failure_error_and_unexpected_exit(self):
        for i, (rc, status, expected) in enumerate([(1, "failed", 0), (2, "error", 2), (1, "finished", 2)]):
            def driver(argv, **kw):
                out = Path(argv[argv.index("--out") + 1])
                out.mkdir()
                trial = i + 2
                (out / "trial.json").write_text(json.dumps({"trial": trial}))
                (out / "run.json").write_text(json.dumps({"schema": "handover.run.v1", "status": status, "trial": trial}))
                return subprocess.CompletedProcess(argv, rc)
            self.assertEqual(self.task("remaining", i, driver), expected)
            archive, marker = list(self.store.objects)[-2:]
            self.assertTrue(archive.endswith("full.tar.zst") and marker.endswith("meta.json"))
            meta = json.loads(self.store.objects[marker])
            self.assertEqual((meta["driver_exit"], meta["task_exit"], meta["uploaded"]), (rc, expected, True))
        with self.assertRaisesRegex(ValueError, "incomplete fetch"):
            self.collect("remaining")
        self.assertTrue((self.work / "trials/trial-04/run.json").is_file())

    def test_watchdog_and_failed_start_publish_diagnostics(self):
        for i, exc in enumerate([subprocess.TimeoutExpired(["fixture"], 1140), OSError("failed start")]):
            driver = Mock(side_effect=exc)
            self.assertEqual(self.task("all", i, driver), 2)
            self.assertEqual(driver.call_args.kwargs["timeout"], 1140)
            meta = json.loads(self.store.objects[list(self.store.objects)[-1]])
            self.assertIsNone(meta["driver_exit"])
            self.assertTrue(meta["uploaded"])
            self.assertIn(type(exc).__name__, meta["worker_error"])

    def test_upload_failures_are_reported_after_both_transfers(self):
        self.store.reject = "full.tar.zst"
        self.assertEqual(self.task(), 98)
        marker, = self.store.objects.values()
        self.assertIs(json.loads(marker)["uploaded"], False)
        self.store.reject = "meta.json"
        self.assertEqual(self.task("remaining"), 98)
        self.assertTrue(list(self.store.objects)[-1].endswith("full.tar.zst"))

    def test_partial_fetch_resumes_without_publishing_damaged_or_mixed_rows(self):
        for i in (0, 1):
            self.task("all", i)
        archive, marker = list(self.store.objects)[:2]
        blob, original = self.store.objects[archive], self.store.objects[marker]
        self.store.objects[archive] = blob + b"damaged"
        with self.assertRaisesRegex(ValueError, "incomplete fetch"):
            self.collect("all")
        results = self.work / "trials"
        self.assertFalse((results / "trial-01").exists())
        self.assertTrue((results / "trial-02/driver.log").is_file())
        self.store.objects[archive] = blob
        self.store.objects[marker] = json.dumps(dict(json.loads(original), image="another image")).encode()
        with self.assertRaisesRegex(ValueError, "incomplete fetch"):
            self.collect("all")
        self.assertFalse((results / "trial-01").exists())
        self.store.objects[marker] = original
        with self.assertRaisesRegex(ValueError, "incomplete fetch"):
            self.collect("all")
        self.assertTrue((results / "trial-01/run.json").is_file())

    def test_extractor_requires_a_regular_trial_tree(self):
        for i, (name, kind) in enumerate([("../escape", tarfile.REGTYPE), ("trial-01/link", tarfile.SYMTYPE)]):
            raw = self.work / f"bad-{i}.tar"
            with tarfile.open(raw, "w") as bundle:
                member = tarfile.TarInfo(name)
                member.type = kind
                bundle.addfile(member)
            archive = self.work / f"bad-{i}.zst"
            subprocess.run(["zstd", "-q", str(raw), "-o", str(archive)], check=True)
            with self.assertRaises(ValueError):
                fetch.extract(archive, self.work, "trial-01")

    def test_build_deploy_run_watch_against_recorded_response_shapes(self):
        build_id = "00000000-0000-0000-0000-000000000001"
        tag = ops.image_tag(self.work, stage.inventory(stage.context()))
        receipt = {"status": "SUCCESS", "results": {"images": [{"name": tag, "digest": IMAGE.split("@")[1]}]}}
        with patch.object(ops, "cloud", side_effect=["[]", build_id, json.dumps(receipt)]) as cloud:
            ops.build(self.work)
            ops.build(self.work)
        self.assertEqual((self.work / "build/staged.sha256").read_bytes(),
                         (stage.HERE / "verification/bundle-staged.sha256").read_bytes())
        self.assertEqual([c.args[0] for c in cloud.call_args_list],
                         [ops.tags_command(), ops.build_command(self.work, tag), ops.build_state(build_id)])
        with patch.object(ops, "cloud") as cloud:
            ops.deploy(self.work)
            cloud.assert_called_once_with(ops.deploy_command(IMAGE))
            self.assertEqual((self.work / "job.yaml").read_text(), ops.job_text(IMAGE))
        run = env("smoke", 0)["CLOUD_RUN_EXECUTION"]
        with patch.object(ops, "cloud", side_effect=[IMAGE, run]) as cloud:
            ops.launch(self.work, "smoke")
            ops.launch(self.work, "smoke")
            with self.assertRaisesRegex(ValueError, "repeat trials"):
                ops.launch(self.work, "all")
        self.assertEqual([c.args[0] for c in cloud.call_args_list],
                         [ops.current_image_command(), ops.execute_command(self.work, "smoke", IMAGE)])
        self.assertEqual(ops.execution(self.work, "smoke"), run)
        states = [json.dumps({"status": {"conditions": [{"type": "Completed", "status": s}]}})
                  for s in ("Unknown", "True", "False")]
        with patch.object(ops, "cloud", side_effect=states), patch.object(ops.time, "sleep"):
            ops.watch(self.work, "smoke")
            with self.assertRaisesRegex(ValueError, "fetch"):
                ops.watch(self.work, "smoke")

    def test_ambiguous_submission_reconciles_a_unique_id_without_reexecution(self):
        folder = self.work / "build"
        folder.mkdir()
        tag = worker.PACKAGE + ":test-overlay"
        ops.save(folder / "tag.txt", tag)
        build_id = "00000000-0000-0000-0000-000000000002"
        builds = [{"id": build_id, "substitutions": {"_IMAGE": tag}}]
        result = {"status": "SUCCESS", "results": {"images": [{"name": tag, "digest": IMAGE.split("@")[1]}]}}
        with patch.object(ops, "cloud", side_effect=[json.dumps(builds), json.dumps(result)]) as cloud:
            ops.build(self.work)
            self.assertFalse(any("submit" in c.args[0] for c in cloud.call_args_list))
        (self.work / "smoke").mkdir()
        name = env("smoke", 0)["CLOUD_RUN_EXECUTION"]
        v = {"name": "HANDOVER_SUBMISSION", "value": ops.submission_id(self.work, "smoke")}
        executions = [{"metadata": {"name": name}, "spec": {"template": {"spec": {"containers": [{"env": [v]}]}}}}]
        with patch.object(ops, "cloud", side_effect=["[]", json.dumps(executions)]) as cloud:
            with self.assertRaisesRegex(ValueError, "no unique execution"):
                ops.launch(self.work, "smoke")
            ops.launch(self.work, "smoke")
        self.assertEqual(ops.execution(self.work, "smoke"), name)
        self.assertTrue(all("list" in c.args[0] for c in cloud.call_args_list))


if __name__ == "__main__":
    unittest.main()
