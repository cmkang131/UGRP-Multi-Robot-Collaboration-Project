"""Build, deploy and collect the dedicated hand-over job. 'plan' is completely offline."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time

import fetch
import stage
from handover import layout
from worker import (BUCKET, JOB, PACKAGE, PROJECT, REGION, REGISTRY_DIGEST, SCRATCH, SELECTIONS, TRIAL_GROUPS,
                    driver_argv, execution_name, file_hash, row_name, trial_number)


def command(*args):
    return ["gcloud-p", PROJECT, *map(str, args)]


def cloud(argv, *, output=False):
    print(shlex.join(argv), file=sys.stderr, flush=True)
    result = subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE if output else None)
    return result.stdout.strip() if output else None


def save(path, value):
    with path.open("x") as stream:
        stream.write(value + "\n")


def stored(path):
    return path.read_text().strip()


def image_tag(work, inventory):
    key = hashlib.sha256((str(work.resolve()) + "\n" + inventory).encode()).hexdigest()[:20]
    return f"{PACKAGE}:handover-{stage.COMMIT[:7]}-{key}"


def build_command(work, tag):
    context = work / "build/context"
    return command("builds", "submit", context, "--config", context / "cloudbuild.yaml",
                   "--substitutions", "_IMAGE=" + tag, "--async", "--format=value(id)")


def build_state(build_id):
    return command("builds", "describe", build_id, "--format=json")


def tags_command():
    return command("artifacts", "docker", "tags", "list", PACKAGE, "--format=json")


def tag_exists(rows, tag):
    for row in rows:
        field = row.get("tag") or row.get("name")
        if not field:
            raise ValueError("unrecognized registry tag listing")
        if field.rsplit("/", 1)[-1].rsplit(":", 1)[-1] == tag.rsplit(":", 1)[1]:
            return True
    return False


def build(work):
    folder = work / "build"
    if (folder / "image.txt").is_file():
        print("Build already recorded:", pinned_image(work))
        return
    if not folder.exists():
        inputs = stage.context()
        inventory = stage.inventory(inputs)
        tag = image_tag(work, inventory)
        if tag_exists(json.loads(cloud(tags_command(), output=True)), tag):
            raise ValueError("image tag already exists: " + tag)
        folder.mkdir()
        stage.write_context(folder / "context", inputs)
        save(folder / "staged.sha256", inventory.rstrip("\n"))
        save(folder / "tag.txt", tag)
        build_id = cloud(build_command(work, tag), output=True)
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", build_id):
            raise ValueError("build submitted without a recognizable ID; inspect Cloud Build before retrying")
        save(folder / "id.txt", build_id)
    if not (folder / "id.txt").is_file():
        tag = stored(folder / "tag.txt")
        builds = json.loads(cloud(command("builds", "list", "--filter", f"substitutions._IMAGE={tag}",
                                          "--format=json"), output=True))
        matches = [b["id"] for b in builds if b.get("substitutions", {}).get("_IMAGE") == tag]
        if len(matches) != 1:
            raise ValueError("no unique Cloud Build receipt for " + tag)
        save(folder / "id.txt", matches[0])
    build_id, tag = stored(folder / "id.txt"), stored(folder / "tag.txt")
    while True:
        receipt = json.loads(cloud(build_state(build_id), output=True))
        status = receipt["status"]
        print(f"build {build_id}: {status}", flush=True)
        if status == "SUCCESS":
            images = [i["digest"] for i in receipt["results"]["images"] if i["name"] == tag]
            if len(images) != 1 or not REGISTRY_DIGEST.fullmatch(PACKAGE + "@" + images[0]):
                raise ValueError("successful build lacks the expected tagged result digest")
            image = PACKAGE + "@" + images[0]
            save(folder / "image.txt", image)
            print(image)
            return
        if status not in {"PENDING", "QUEUED", "WORKING"}:
            raise ValueError("Cloud Build stopped: " + status)
        time.sleep(20)


def pinned_image(work):
    value = stored(work / "build/image.txt")
    if not REGISTRY_DIGEST.fullmatch(value):
        raise ValueError("invalid hand-over image receipt")
    return value


SERVICE_ACCOUNT = os.environ.get("HANDOVER_SERVICE_ACCOUNT", "<service-account>")
PROJECT_NUMBER = os.environ.get("HANDOVER_PROJECT_NUMBER", "<project-number>")


def job_text(image):
    if not REGISTRY_DIGEST.fullmatch(image):
        raise ValueError("expected an immutable image in the project package")
    template = (stage.HERE / "job.yaml.in").read_text()
    return (template.replace("@IMAGE@", image).replace("<service-account>", SERVICE_ACCOUNT)
            .replace("<project-number>", PROJECT_NUMBER).replace("<bucket>", BUCKET))


def deploy_command(image):
    first, count = SELECTIONS["all"]
    variables = f"HANDOVER_IMAGE={image},HANDOVER_FIRST_TRIAL={first},RESULT_BUCKET={BUCKET}"
    # Cloud Run jobs always use the gen2 execution environment.
    return command("run", "jobs", "deploy", JOB, "--region", REGION, "--image", image,
                   "--cpu", "2", "--memory", "6Gi", "--task-timeout", "1800s", "--max-retries", "0",
                   "--tasks", count, "--parallelism", "1",
                   "--service-account", SERVICE_ACCOUNT,
                   "--set-env-vars", variables)


def deploy(work):
    image = pinned_image(work)
    path = work / "job.yaml"
    value = job_text(image)
    if path.exists():
        if path.read_text() != value:
            raise ValueError("existing deployment file differs from the built image")
    else:
        save(path, value.rstrip("\n"))
    cloud(deploy_command(image))


def current_image_command():
    return command("run", "jobs", "describe", JOB, "--region", REGION,
                   "--format=value(spec.template.spec.template.spec.containers[0].image)")


def submission_id(work, scope):
    return hashlib.sha256(str(work.resolve()).encode()).hexdigest()[:24] + "-" + scope


def cohort_table(work, requested=None):
    receipt = work / "trial-table.txt"
    if receipt.is_file():
        name = stored(receipt)
    elif any((work / scope).exists() for scope in TRIAL_GROUPS):
        name = layout.TABLE.name  # Cohorts reserved by the original worker.
    else:
        name = requested or layout.TABLE.name
    if name not in layout.TRIAL_TABLES or (requested is not None and name != requested):
        raise ValueError(f"cohort trial table is {name!r}, requested {requested!r}")
    return name


def execute_command(work, scope, image, table_name=layout.TABLE.name):
    first, count = SELECTIONS[scope]
    variables = (f"HANDOVER_FIRST_TRIAL={first},HANDOVER_EXPECT_IMAGE={image},"
                 f"HANDOVER_SUBMISSION={submission_id(work, scope)}")
    if table_name != layout.TABLE.name:
        variables += f",HANDOVER_TRIAL_TABLE={table_name}"
    return command("run", "jobs", "execute", JOB, "--region", REGION, "--tasks", count,
                   "--update-env-vars", variables, "--async", "--format=value(metadata.name)")


def execution(work, scope):
    return execution_name(stored(work / scope / "execution.txt"))


def recover_execution(work, scope):
    listed = json.loads(cloud(command("run", "jobs", "executions", "list", "--job", JOB,
                                      "--region", REGION, "--format=json"), output=True))
    matches = []
    for item in listed:
        containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if any(v.get("name") == "HANDOVER_SUBMISSION" and v.get("value") == submission_id(work, scope)
               for c in containers for v in c.get("env", [])):
            matches.append(execution_name(item["metadata"]["name"]))
    if len(matches) != 1:
        raise ValueError(f"no unique execution receipt for the reserved {scope} submission")
    return matches[0]


def launch(work, scope, requested=None):
    image = pinned_image(work)
    # A reservation survives an interrupted submission. Overlapping paid slices cannot race.
    fd = os.open(work, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        table_name = cohort_table(work, requested)
        folder = work / scope
        if (folder / "execution.txt").is_file():
            print("Execution already recorded:", execution(work, scope))
            return
        if folder.exists():
            name = recover_execution(work, scope)
            save(folder / "execution.txt", name)
            print("Recovered execution:", name)
            return
        reserved = [name for name in TRIAL_GROUPS if (work / name).exists()]
        requested_rows = set(TRIAL_GROUPS[scope])
        if any(requested_rows.intersection(TRIAL_GROUPS[name]) for name in reserved):
            raise ValueError("would repeat trials already reserved in this cohort")
        if table_name != layout.TABLE.name:
            layer = json.loads((work / "build/context/layer.json").read_bytes())
            if f"handover/scenes/{table_name}" not in layer["sha256"]:
                raise ValueError(f"the staged image lacks {table_name}")
        if cloud(current_image_command(), output=True) != image:
            raise ValueError("deployed job image differs from the build receipt")
        if not (work / "trial-table.txt").exists() and not reserved:
            with tempfile.TemporaryDirectory(dir=work) as tmp:
                receipt = Path(tmp) / "trial-table.txt"
                save(receipt, table_name)
                receipt.replace(work / receipt.name)
        folder.mkdir()
        result = cloud(execute_command(work, scope, image, table_name), output=True)
        try:
            name = execution_name(result.strip().splitlines()[-1].rsplit("/", 1)[-1])
        except (ValueError, IndexError):
            name = recover_execution(work, scope)
        save(folder / "execution.txt", name)
        print(name)
    finally:
        os.close(fd)


def status_command(name):
    return command("run", "jobs", "executions", "describe", name, "--region", REGION,
                   "--format=json")


def watch(work, scope):
    name = execution(work, scope)
    while True:
        state = json.loads(cloud(status_command(name), output=True))["status"]
        done = next((c for c in state.get("conditions", []) if c.get("type") == "Completed"), {})
        print(f"{name}: {state.get('succeededCount', 0)} succeeded, {state.get('failedCount', 0)} failed, "
              f"Completed={done.get('status', 'Unknown')}", flush=True)
        if done.get("status") == "True":
            return
        if done.get("status") == "False":
            raise ValueError(f"{name} ended unsuccessfully; fetch its available evidence")
        if state.get("completionTime"):
            if int(state.get("succeededCount", 0)) == SELECTIONS[scope][1]:
                return
            raise ValueError(f"{name} completed with missing or failed tasks; fetch its available evidence")
        time.sleep(20)


def copy_command(uri, path):
    return command("storage", "cp", uri, path)


def collect(work, scope):
    table_name = cohort_table(work)
    layer = work / "build/context/layer.json"
    table_hash = json.loads(layer.read_bytes())["sha256"][f"handover/scenes/{table_name}"]
    fetch.fetch_rows(work / "trials", execution(work, scope), pinned_image(work),
                     file_hash(layer), SELECTIONS[scope], lambda uri, path: cloud(copy_command(uri, path)),
                     table_name=table_name, table_hash=table_hash)


def plan(work, requested=None):
    table_name = cohort_table(work, requested)
    inputs = stage.context()
    tag = image_tag(work, stage.inventory(inputs))
    image = PACKAGE + "@sha256:" + "0" * 64
    print("OFFLINE PLAN. Zero digest, build ID, execution IDs and fetch temp directory are examples.")
    for argv in (tags_command(), build_command(work, tag), build_state("00000000-0000-0000-0000-000000000000"),
                 deploy_command(image)):
        print(shlex.join(argv))
    print(job_text(image), end="")
    for scope, (first, count) in SELECTIONS.items():
        name = JOB + "-preview-" + scope
        print(f"\n{scope} ({count} tasks)")
        for argv in (current_image_command(), execute_command(work, scope, image, table_name), status_command(name)):
            print(shlex.join(argv))
        for index in range(count):
            k = trial_number(first, count, index)
            out = SCRATCH / name / f"task-{index}" / row_name(k)
            print(f"index {index} -> {k}: {shlex.join(driver_argv(k, out, table_name=table_name))}")
            for uri in fetch.sources(name, k):
                dest = work / "trials" / (".preview-" + row_name(k)) / uri.rsplit("/", 1)[1]
                print(shlex.join(copy_command(uri, dest)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    for op in ("plan", "build", "deploy", "run", "watch", "fetch"):
        sub = subs.add_parser(op)
        sub.add_argument("work", type=Path, help="fresh cohort directory from mktemp -d")
        if op in ("run", "watch", "fetch"):
            sub.add_argument("scope", choices=SELECTIONS)
        if op in ("plan", "run"):
            sub.add_argument("--trial-table", choices=layout.TRIAL_TABLES,
                             help="select the table for the cohort on its first submission")
    args = parser.parse_args(argv)
    work = args.work.resolve()
    try:
        if args.operation == "plan":
            plan(work, args.trial_table)
        elif args.operation == "run":
            launch(work, args.scope, args.trial_table)
        elif args.operation in ("build", "deploy"):
            {"build": build, "deploy": deploy}[args.operation](work)
        else:
            {"watch": watch, "fetch": collect}[args.operation](work, args.scope)
    except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{args.operation}: {exc}\n")


if __name__ == "__main__":
    main()
