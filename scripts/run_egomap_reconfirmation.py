"""egomap71: Azure paired DEV replay; own RGB only, evaluation isolated."""
import argparse
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from harness.active_camera import bind
from harness.own_route_reference import Options, install as route_install
from harness.turn_lateral_calibration import OPTION as MOTION, install as motion_install
from scripts import run_own_route_turn_lateral as previous

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'experiments/2026-10-11-egomap-reconfirmation/prereg.json'
ref = previous.ref
OPTIONS = Options(return_own_free_astar=True)
CONDITIONS = {'off': OPTIONS, 'on': OPTIONS}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def registration():
    return json.loads(PLAN.read_text())


def read_archive(path):
    if path.is_file():
        return path.read_bytes()
    compressed = Path(str(path) + '.zst')
    if compressed.is_file():
        return subprocess.check_output(['zstd', '-qdc', str(compressed)], timeout=90)
    raise FileNotFoundError(path)


def relocate_imports(table):
    """Only rewrite recorded repository paths; preserve checkpoint bytes/hash."""
    table = copy.deepcopy(table)
    marker = '/ugrp-sim/src/'
    def relocate(path):
        if marker not in path:
            return path
        suffix = path.split(marker, 1)[1].split('/', 1)
        return str(ROOT / suffix[1]) if len(suffix) == 2 else str(ROOT)
    table['sys_path'] = [relocate(p) for p in table['sys_path']]
    table['modules'] = {k: relocate(v) for k, v in table['modules'].items()}
    return table


def prepare_inputs(out, archive):
    """Materialize immutable ARM checkpoint prefixes onto Azure persistent disk."""
    out.mkdir(parents=True, exist_ok=False)
    inventory = []
    for cp in registration()['checkpoints']:
        source = archive / 'egomap63-batch/data' / f"prepare-{cp['seed']}"
        target = out / f"prepare-{cp['seed']}"
        records = [json.loads(x) for x in read_archive(source / 'checkpoints/manifest.jsonl').splitlines() if x]
        row = next(r for r in records if r['file'] == cp['file'])
        raw = read_archive(source / 'checkpoints' / cp['file'])
        if digest(raw) != cp['sha256'] or row['sha256'] != cp['sha256']:
            raise ValueError('CHECKPOINT_HASH_MISMATCH')
        files = {**{k: (v, None) for k, v in row['files'].items()},
                 **{k: (v['prefix_sha256'], v['offset']) for k, v in row['streams'].items()}}
        files['checkpoints/' + cp['file']] = (cp['sha256'], None)
        for name, (expected, limit) in files.items():
            data = read_archive(source / name)
            if limit is not None:
                data = data[:limit]
            if digest(data) != expected:
                raise ValueError('PREFIX_HASH_MISMATCH:' + name)
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            inventory.append(dict(seed=cp['seed'], path=str(dest.relative_to(out)), sha256=expected,
                                  bytes=len(data), source=str(source / name), prefix_bytes=limit))
        # Original manifest is preserved; relocation is in-memory at restore.
        (target / 'checkpoints/manifest.jsonl').write_text(json.dumps(row) + '\n')
    bank = out / 'banks'
    bank.mkdir()
    for cp in registration()['checkpoints']:
        for extension in ('json', 'npz'):
            name = f"bank-{cp['seed']}.{extension}"
            data = read_archive(archive / 'egomap68-banks/data' / name)
            (bank / name).write_bytes(data)
            inventory.append(dict(path='banks/' + name, bytes=len(data), sha256=digest(data),
                                  source=str(archive / 'egomap68-banks/data' / name)))
    dump(out / 'materialization.json', dict(source_sha=ROOT.name, files=inventory,
         inputs='checkpoint prefix and causal own RGB feature bank; no new physics'))
    return out


def checkpoint_load(path, out):
    from scripts.dev_pair_checkpoint import DevCheckpoint, find_checkpoint
    row = copy.deepcopy(find_checkpoint(path))
    row['case_dir'] = str(path.parents[1])
    row['imports'] = relocate_imports(row['imports'])
    cp = DevCheckpoint(resume=dict(row=row, file=str(path), source_case_dir=row['case_dir'],
                         labels={'egomap71': True, 'host': 'azure', 'path_relocation_only': True}))
    out.mkdir(parents=True, exist_ok=False)
    result = {'loadavg_start': list(os.getloadavg())}
    backend, c, start, tick, _ = cp.restore(out, result, stream_aliases=True)
    return backend, c, start, tick, row


@contextlib.contextmanager
def server_slot():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or os.getenv('UGRP_EXECUTION_HOST') != 'azure':
        raise RuntimeError('AZURE_X86_ONLY_NO_MAC_PHYSICS')
    if os.getenv('MUJOCO_GL') != 'osmesa':
        raise RuntimeError('OSMESA_REQUIRED')
    yield 'azure_batch_resource_admitted'


def bundle(args):
    b = previous.bundle(args.seed, ROOT.name, 'calib_traversed', 'stage')
    b.update(execution_bundle_id=f'egomap71-{args.condition}-{args.seed}-v1', host='azure',
             host_alarm_s=registration()['per_run_wall_s'],
             admission='DEV resumed same six checkpoints; paired combined toggles; no E2E/confirmation claim')
    b['options'].update(rgb_reconfirmation=args.rgb_reconfirmation, covariance_inflation=args.covariance_inflation)
    return b


def run(args):
    from harness.own_route_reconfirmation import install as gate_install
    from harness.egomap_covariance import install as covariance_install
    from scripts import run_own_route_homing as homing
    args.profile = 'baseline'
    args.stage_schedule = ref.SCHEDULE
    b = bundle(args)
    audit, controllers = [], []
    bank = bind(homing.load_memory, bank_root=lambda: args.inputs / 'banks')(args.seed) if args.rgb_reconfirmation != 'off' else None
    def load(path, out):
        backend, c, start, tick, cp = checkpoint_load(path, out)
        route_install(c, OPTIONS, traversed_free='footprint_history_v1')
        motion_install(c, motion_model_turn_lateral_v2=MOTION)
        covariance_install(c, covariance_inflation=args.covariance_inflation)
        gate_install(c, rgb_reconfirmation=args.rgb_reconfirmation, memory=bank)
        controllers.append(c)
        ref.arrival_audit(c, audit)
        def emit(row):
            row.update(rgb_reconfirmation=args.rgb_reconfirmation, covariance_inflation=args.covariance_inflation)
            if args.rgb_reconfirmation != 'off':
                row['rgb_calls'] = getattr(c, '_rgb_reconfirmation_calls', None)
                row['valid'] = row['valid'] and row['rgb_calls'] == row['call']
            if args.covariance_inflation != 'off':
                row['covariance_artifact'] = getattr(c, '_covariance_inflation', None)
                row['valid'] = row['valid'] and row['covariance_artifact'] is not None
            with (out / 'execution-path.jsonl').open('a') as stream:
                stream.write(json.dumps(row) + '\n')
            if not row['valid']:
                raise RuntimeError('EGOMAP71_REFERENCE_NOT_EXECUTED')
        previous.previous.execution_audit(c, OPTIONS, emit)
        return backend, c, start, tick, cp
    def alarm(n):
        return signal.alarm(b['host_alarm_s'] if n else 0)
    result = bind(ref.old.run, bundle=lambda *a: b, checkpoint_load=load, server_slot=server_slot,
                  install=ref.previous.previous.install,
                  signal=SimpleNamespace(**{**vars(signal), 'alarm': alarm}))(args)
    result.update(host='azure', condition=args.condition, options={k: b['options'][k]
                  for k in ('rgb_reconfirmation', 'covariance_inflation')})
    dump(args.output / 'result.json', result)
    dump(args.output / 'arrival-gates.json', audit)
    if controllers:
        c = controllers[0]
        dump(args.output / 'rgb-reconfirmation.json', dict(
            rows=getattr(getattr(c, '_rgb_reconfirmation_gate', None), 'rows', []),
            acquisitions=getattr(c, '_rgb_reconfirmation_acquisitions', [])))
    # Final per-file manifest includes adapters' sidecars and final host metadata.
    dump(args.output / 'artifacts.sha256.json', {str(p.relative_to(args.output)): digest(p.read_bytes())
        for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def read_result(folder):
    path = folder / 'result.json'
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError('result is not an object')
        return value
    except (ValueError, OSError) as exc:
        return dict(status='HOST_ERROR_MALFORMED_RESULT', failure=repr(exc))


def summarize(plan, out):
    from scripts.score_own_route_full_budget import score
    reports = []
    for job in plan:
        folder = Path(job['output'])
        result = read_result(folder)
        report = dict(job)
        if result.get('status', '').startswith('HOST_ERROR'):
            report['status'] = result['status']
        try:
            if result.get('start_sim_s') is not None:
                report.update(score(folder))
        except Exception as exc:
            report['scoring_error'] = repr(exc)
        declarations = report.get('declarations', [])
        report.update(false_return=sum(d['kind'] == 'return_start_declared' and not d['valid'] for d in declarations),
                      false_B=sum(d['kind'] == 'goal_reached' and not d['valid'] for d in declarations),
                      return_declarations=sum(d['kind'] == 'return_start_declared' for d in declarations),
                      B_declarations=sum(d['kind'] == 'goal_reached' for d in declarations),
                      wall_s=result.get('wall_s'), model_calls=result.get('model_calls', 0),
                      failure=result.get('failure', job.get('failure')))
        report['host_error'] = report['status'].startswith('HOST_ERROR') or 'scoring_error' in report
        reports.append(report)
    conditions = {}
    for condition in CONDITIONS:
        group = [r for r in reports if r['condition'] == condition]
        measured = [r for r in group if r.get('samples', 0) and not r.get('scoring_error')]
        conditions[condition] = dict(registered=6, attempted=sum(r.get('pid') is not None for r in group),
            measured=len(measured), host_errors=sum(r['host_error'] for r in group),
            false_return=dict(count=sum(r['false_return'] for r in measured), run_denominator=6,
                              measured_run_denominator=len(measured), declaration_denominator=sum(r['return_declarations'] for r in measured)),
            false_B=dict(count=sum(r['false_B'] for r in measured), run_denominator=6,
                         measured_run_denominator=len(measured), declaration_denominator=sum(r['B_declarations'] for r in measured)),
            true_return=sum(bool(r.get('returned')) for r in measured), true_B=sum(bool(r.get('B_arrived')) for r in measured),
            both_arrived=sum(bool(r.get('both_arrived')) for r in measured),
            wall_s=sum(r['wall_s'] for r in group if r.get('wall_s') is not None),
            commands=sum(r.get('command_audit', {}).get('commands', 0) for r in measured), model_calls=0,
            physical_failures=sum(r['status'] == 'PHYSICAL_FAILURE' for r in group))
    summary = dict(round='egomap71', source_sha=ROOT.name, host='azure', registered=12, class_='dev', pr=405,
                   conditions=conditions, runs=reports, host_errors=[r for r in reports if r['host_error']],
                   confirmation=False, threshold_retuning=False, model_calls=0,
                   scope='combined on/off DEV repeated six seeds; no separate toggle effect or continuous E2E claim')
    dump(out / 'scores.json', reports)
    dump(out / 'summary.json', summary)
    return summary


def batch(args):
    import shutil
    from harness.own_rgb_reconfirmation import OPTION as RGB
    from harness.egomap_covariance import OPTION as COV
    with server_slot():
        out = args.output.resolve()
        out.mkdir(parents=True, exist_ok=False)
        started = time.monotonic()
        inputs = Path.home() / 'ugrp-sim/inputs' / out.parent.name
        plan = []
        for cp in registration()['checkpoints']:
            for condition in ('off', 'on') if cp['seed'] % 2 else ('on', 'off'):
                name = f"egomap71-{cp['seed']}-{condition}"
                output = out / name
                command = [sys.executable, '-m', 'scripts.run_egomap_reconfirmation', '--mode', 'stage',
                           '--seed', str(cp['seed']), '--condition', condition, '--inputs', str(inputs),
                           '--rgb-reconfirmation', RGB if condition == 'on' else 'off',
                           '--covariance-inflation', COV if condition == 'on' else 'off', '--output', str(output)]
                plan.append(dict(name=name, seed=cp['seed'], condition=condition, output=str(output),
                                 checkpoint_sha256=cp['sha256'], command=command, status='QUEUED'))
        dump(out / 'batch-plan.json', dict(source_sha=ROOT.name, jobs=plan, registration=registration()))
        def admission_timeout(*_):
            raise TimeoutError('INPUT_ADMISSION_300S_DEADLINE')
        signal.signal(signal.SIGALRM, admission_timeout)
        signal.alarm(300)
        try:
            if shutil.disk_usage(out).free < 16 * 2**30:
                raise OSError('INSUFFICIENT_DISK_16GIB_RESERVE')
            prepare_inputs(inputs, args.archive)
            shutil.copyfile(inputs / 'materialization.json', out / 'input-materialization.json')
        except Exception as exc:
            for job in plan:
                job.update(status='HOST_ERROR_INPUT_ADMISSION', failure=repr(exc))
            dump(out / 'batch-status.json', plan)
            summarize(plan, out)
            return 2
        finally:
            signal.alarm(0)
        queue, running = list(plan), []
        stopped = False
        def interrupt(*_):
            nonlocal stopped
            stopped = True
        signal.signal(signal.SIGINT, interrupt)
        signal.signal(signal.SIGTERM, interrupt)
        while queue or running:
            elapsed = time.monotonic() - started
            expired = stopped or elapsed >= args.wall_budget_s
            load, available = ref.resources()
            if expired:
                for job in queue:
                    job.update(status='HOST_ERROR_TASK_DEADLINE_NOT_STARTED', failure='two_hour_task_budget')
                queue.clear()
            if queue and len(running) < args.workers and load < max(1, os.cpu_count() - 4) and available > 8 and shutil.disk_usage(out).free >= 10 * 2**30:
                job = queue.pop(0)
                stream = (out / (job['name'] + '.log')).open('x')
                process = subprocess.Popen(job['command'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                job.update(status='RUNNING', pid=process.pid, launch_monotonic=time.monotonic(), loadavg=list(os.getloadavg()))
                running.append((job, process, stream))
            for job, process, stream in running.copy():
                if expired and process.poll() is None:
                    if 'deadline_signal_at' not in job:
                        process.send_signal(signal.SIGALRM)
                        job['deadline_signal_at'] = time.monotonic()
                    elif time.monotonic() - job['deadline_signal_at'] > 60:
                        os.killpg(process.pid, signal.SIGKILL)
                if process.poll() is None:
                    continue
                stream.close()
                job['exit_code'] = process.returncode
                folder = Path(job['output'])
                folder.mkdir(parents=True, exist_ok=True)
                (folder / 'EXIT').write_text(str(process.returncode) + '\n')
                result = read_result(folder)
                job['status'] = result.get('status', 'HOST_ERROR_NO_RESULT')
                if process.returncode != 0 and job['status'] == 'RECORDED':
                    job['status'] = 'HOST_ERROR_WRAPPER_EXIT'
                running.remove((job, process, stream))
            dump(out / 'batch-status.json', plan)
            if queue or running:
                time.sleep(5)
        summary = summarize(plan, out)
        return 2 if summary['host_errors'] else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=('stage', 'batch'), required=True)
    p.add_argument('--condition', choices=tuple(CONDITIONS), default='off')
    p.add_argument('--seed', type=int, choices=range(63001, 63007), default=63001)
    p.add_argument('--rgb-reconfirmation', default='off')
    p.add_argument('--covariance-inflation', default='off')
    p.add_argument('--inputs', type=Path)
    p.add_argument('--archive', type=Path, default=Path.home() / 'ugrp-sim/arm')
    p.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    p.add_argument('--wall-budget-s', type=int, default=5400)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if not 1 <= args.wall_budget_s <= 5400:
        p.error('batch budget must be within 5400 s; archive/cleanup reserve is 1800 s')
    if args.mode == 'batch':
        return batch(args)
    if args.inputs is None:
        p.error('--inputs is required for stage')
    cp = next(c for c in registration()['checkpoints'] if c['seed'] == args.seed)
    args.checkpoint = args.inputs / f"prepare-{args.seed}" / 'checkpoints' / cp['file']
    result = run(args)
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'RECORDED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
