"""One opt-in S3 smoke. Default plan only; no lock or simulator at import."""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from harness import zone_s3_no_prior_contract as contract
from harness.zone_s3_no_prior import Runtime, IntegratedTrial, ROBOTS
from scripts.run_final_environment_checks import check_source, write
from scripts.run_s3_host import environment_record, artifact_manifest


def run(bundle, out, *, backend_factory=None, runtime_factory=Runtime):
    contract.verify(bundle)
    scenario, mapped, sheet = contract.inputs()
    static = contract.hp.resolve(bundle['map_id'])[0]
    if backend_factory is None:
        from sim.zone_s3_no_prior import PhysicsBackend
        backend_factory = PhysicsBackend
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', bundle)
    result = dict(execution_bundle_id=contract.BUNDLE_ID, source_sha=bundle['source_sha'],
        seed=bundle['seed'], status='HOST_ERROR', research_result=False, physical_success=None,
        model_calls=0, http_attempts=0, tokens=0, commands_issued={r: 0 for r in ROBOTS},
        known_start_information=False, evaluation=None, loadavg_start=list(os.getloadavg()))
    started = time.monotonic()
    backend = runtime = trial = None
    try:
        write(out/'environment.json', environment_record())
        backend = backend_factory(bundle, out, seed=bundle['seed'])
        reset = backend.reset(bundle['reset_cap_s'])
        start = backend.now
        backend.set_deadline(start+bundle['case_cap_s'])
        runtime = runtime_factory(static, sheet['orders'], contract.ROOT/bundle['calibration'],
            bundle['calibration_sha256'], seed=bundle['seed'], config=bundle['controller_config'])
        runtime.initial_commands(start, backend.commands)
        trial = IntegratedTrial(scenario, seed=bundle['seed'], links=runtime.links, map_bundle=mapped,
            horizon_s=start+bundle['case_cap_s'], code_sha=bundle['source_sha'], pair_records=runtime.pair.team.records)
        runtime.trial = trial
        trial.begin(start)
        ended = None
        steps = round(bundle['case_cap_s']/bundle['tick_s'])
        for i in range(steps+1):
            if time.monotonic()-started > bundle['wall_cap_s']:
                raise TimeoutError('WALL_CAP_EXCEEDED')
            if i % 20 == 0 and shutil.disk_usage(out).free < 10*1024**3:
                raise OSError(errno.ENOSPC, '10 GiB free-space boundary reached')
            if i % 600 == 0 and sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) > bundle['raw_budget_bytes']:
                raise OSError(errno.ENOSPC, 'registered raw budget exceeded')
            backend.eval_sample()  # write-only; never passed to any robot
            if i == steps:
                break
            if ended is None:
                runtime.on_frames(backend.now, backend.capture())
                actions = runtime.step(backend.now)
                if runtime.terminal:
                    ended = backend.now
                    actions = [(r, {'kind': 'hold'}) for r in ROBOTS]
                for rid, action in actions:
                    backend.issue(rid, action)
                    runtime.on_command(rid, backend.now, action)
                    result['commands_issued'][rid] += 1
            if ended is not None and backend.now-ended >= bundle['settle_s']-1e-8:
                break
            backend.advance_to(start+(i+1)*bundle['tick_s'])
        for rid in ROBOTS:
            backend.issue(rid, {'kind': 'hold'})
            runtime.on_command(rid, backend.now, {'kind': 'hold'})
        failures = runtime.failures
        result.update(reset_sim_s=reset, check_sim_s=backend.now-start,
            controller_failures=failures, commands_complete=bool(runtime.terminal and not failures),
            end_reason='controller_failure' if failures else 'commands_ended' if ended is not None else 'sim_horizon')
        result['evaluation'] = backend.evaluate(sheet['orders'], static)
        result['status'] = ('DEV_DELIVERED' if result['commands_complete'] and
                            result['evaluation']['orders_complete'] else 'DEV_NOT_DELIVERED')
    except Exception as exc:
        physical_stop = type(exc).__name__ == 'PhysicalStop'
        result.update(status='DEV_PHYSICAL_STOP' if physical_stop else 'HOST_ERROR', commands_complete=False,
            failure=dict(type=type(exc).__name__, message=str(exc),
            category='ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'))
        if backend is not None and 'start' in locals():
            result.update(reset_sim_s=reset, check_sim_s=backend.now-start)
            try:
                result['evaluation'] = backend.evaluate(sheet['orders'], static)
            except Exception as evaluation_error:
                result['evaluation_error'] = str(evaluation_error)
        if physical_stop:
            result['failure']['category'] = 'PHYSICAL_STOP'
    finally:
        for name, producer in [('student_record.json', runtime.record if runtime else None),
                               ('trial.json', (lambda: trial.finish(backend.now)) if trial else None)]:
            if producer:
                try:
                    write(out/name, producer())
                except Exception as exc:
                    result.update(status='HOST_ERROR', record_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result.update(wall_s=time.monotonic()-started, loadavg_end=list(os.getloadavg()))
        result['wall_per_sim'] = result['wall_s']/result['check_sim_s'] if result.get('check_sim_s') else None
        write(out/'result.json', result)
        artifact_manifest(out)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, choices=contract.SEEDS, default=contract.SEEDS[0])
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--no-prior', choices=('off', contract.OPTION), default='off')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--release-s3-simulation', action='store_true')
    a = p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False, no_prior=a.no_prior,
            execution_bundle_id=contract.BUNDLE_ID, seed=a.seed)))
        return 0
    if a.no_prior != contract.OPTION or not a.release_s3_simulation:
        raise ValueError('explicit no-prior option and coordinator S3 release required')
    check_source(a.expected_source_sha)
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if branch != 'codex/s3-no-prior-smoke' or os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('own S3 branch and nice zero required')
    from scripts import agent_lock
    primary = agent_lock.DEFAULT_ROOT.parent
    expected = primary/f's3-no-prior-{a.expected_source_sha[:8]}-s{a.seed}-v142'
    if not a.output.is_absolute() or a.output.resolve() != expected.resolve() or a.output.exists():
        raise ValueError('new exact registered primary output required')
    b = contract.bundle(a.expected_source_sha, seed=a.seed)
    if shutil.disk_usage(primary).free < b['raw_budget_bytes']+10*1024**3:
        raise OSError(errno.ENOSPC, 'raw budget plus 10 GiB reserve required')
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch=branch,
        purpose='S3 v142 single mixed no-prior smoke', pid=os.getpid(), expected_minutes=180, timing_sensitive=True)
    from harness.zone_pair_highpose_exact_speedups import install
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        result = run(b, a.output)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 0 if result['status'] == 'DEV_DELIVERED' else 1
    finally:
        if undo:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        if a.output.exists():
            write(a.output/'lock.json', dict(acquired=held, released=released,
                status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))
            artifact_manifest(a.output)


if __name__ == '__main__':
    raise SystemExit(main())
