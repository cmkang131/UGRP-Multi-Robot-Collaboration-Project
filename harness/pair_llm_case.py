"""One case of the pair LLM viability test: the physics loop with the optional LLM decision layer.

The loop is ``scripts.run_final_pair_v3.run_case`` (non-collection branch) with three additions that exist
only in the LLM arms and never in ``rule``:

* the runtime is ``GatedHighRuntime`` (``Team.start`` behind a released-claim permit), not ``Runtime``;
* each tick feeds the robot's OWN capture to its ``PairLink`` and drains its OWN executor events into the
  study scheduler, and the scheduler is advanced to the episode-relative tick time before the control step;
* a ``PairTrial`` (two-robot study layer) runs the calls, the SIM cost charge, the message transport and
  the send ledger.

The ``rule`` arm builds the unmodified #363 HIGH ``Runtime`` and runs the identical sequence of ``eval_sample ->
capture -> on_frames -> step -> arm_step -> advance_to`` calls as ``run_case``; a test pins that its issued
commands equal ``run_case``'s for the same runtime and cap.

Evaluation is write-only: ``backend.eval_sample()`` writes the private trajectory, and the judge reads it
only AFTER the loop (``pair_llm_eval``). Nothing in this module reads a pose, a joint, a contact or a result
to choose actions during the run, and no robot-side module imports the evaluator.
Own hook decisions are copied to evaluation records; the model-facing projection contains only closed own belief bands
and window times.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import time
from pathlib import Path

from harness import pair_llm_billing as billing
from harness import pair_llm_contract as contract
from harness import zone_final_pair_contract as skill_layer
from harness import zone_map_schematic as ms
from harness import zone_study_integration as zi
from harness import zone_study_prompts_ko as pk
from harness.pair_llm_prompts_ko import PAIR_ROBOTS
from harness.zone_final_environment import digest, sha

LOOP_VERSION = 'ugrp.pair_llm_case.v1'


def write(path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + '\n')


def jsonl(path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False, default=str) + '\n' for r in rows))


class TimedWire:
    """Records the wall seconds of every request that reaches the wire (recorded, never charged as SIM time)."""

    def __init__(self, inner):
        self.inner = inner
        self.rows = []

    def __call__(self, request, *, timeout=None):
        started = time.perf_counter()
        error = None
        try:
            return self.inner(request, timeout=timeout)
        except BaseException as exc:
            error = type(exc).__name__
            raise
        finally:
            self.rows.append({'index': len(self.rows), 'wall_s': round(time.perf_counter() - started, 6),
                              'request_bytes': len(bytes(request.data)),
                              'request_sha256': hashlib.sha256(bytes(request.data)).hexdigest(), 'error': error})

    @property
    def walls(self) -> list:
        return [row['wall_s'] for row in self.rows]


def stub_adapter(model, store_dir):
    """``(ModelAdapter, TimedWire)``: the stub model behind the real proxy completer and send ledger."""
    from harness.pair_llm_stub import STUB_SETTINGS
    from harness.zone_send_ledger import FixtureWire, SendLedger
    from harness.zone_study_llm_transport import gemini_client_factory
    wire = TimedWire(FixtureWire(model))
    ledger = SendLedger(wire, store_dir=store_dir)
    factory = gemini_client_factory(model=STUB_SETTINGS['model'], url=STUB_SETTINGS['url'],
                                    max_tokens=STUB_SETTINGS['max_tokens'], temperature=STUB_SETTINGS['temperature'],
                                    reasoning_effort=STUB_SETTINGS['reasoning_effort'],
                                    timeout=STUB_SETTINGS['timeout'], study_json=True)
    return zi.ModelAdapter(factory, ledger), wire


def sabotage_events(links, gate) -> list:
    """Own decisions that cut the pair carry short. Counted from OWN actions only (never from physics).

    * ``abort_pair_carry``: an accepted ``abort`` (the model's ``wait``/``release`` while busy) of a pair job;
    * ``claim_refused``: a released claim that ``Team.start`` refused for a reason waiting cannot fix (wrong
      destination, wrong role, mismatching partner submission).
    """
    rows = []
    for rid, link in links.items():
        for row in link.abort_log:
            if row['accepted'] and row['job_kind'] == 'pair_carry':
                rows.append({'kind': 'abort_pair_carry', **row})
    for row in gate.log:
        if row['event'] == 'claim_submitted' and not row['accepted']:
            rows.append({'kind': 'claim_refused', 'sim_s': row['sim_s'], 'robot_id': row['robot_id'],
                         'reason': row['reason']})
    return sorted(rows, key=lambda r: (r['sim_s'], r['robot_id']))


def claim_counts(gate) -> dict:
    log = gate.log
    submitted = [r for r in log if r['event'] == 'claim_submitted']
    return {'released': sum(r['event'] == 'claim_released' for r in log), 'submitted': len(submitted),
            'accepted': sum(bool(r['accepted']) for r in submitted),
            'rejected': sum(not r['accepted'] for r in submitted),
            'revoked': sum(r['event'] == 'claim_revoked' for r in log),
            'not_released_ticks': dict(gate.refused_without_permit),
            'refusals': {rid: dict(rows) for rid, rows in gate.refusals.items()}}


def write_llm_artifacts(out, trial, adapter_wire, runtime, links) -> dict:
    """Everything the LLM layer did: exact requests (text + images), raw responses, calls, messages, actions."""
    study = Path(out) / 'llm'
    images = study / 'request_images'
    images.mkdir(parents=True, exist_ok=True)
    for sha_hex, jpeg in trial.request_images.items():
        (images / f'{sha_hex}.jpg').write_bytes(jpeg)
    (study / 'map_figure.png').write_bytes(trial.map_png)
    jsonl(study / 'requests.jsonl', trial.requests)
    jsonl(study / 'token_measurements.jsonl', [
        {'call_id': r['call_id'], 'robot': r['robot'], 'sim_s': r['sim_s'], **r['token_measurement']}
        for r in trial.requests])
    problems = [p for row in trial.requests for p in pk.verify_archived_request(row)]
    problems += [p for row in trial.requests
                 for p in billing.billing_problems(row, require=billing.IMAGE_BILLING_VERSION)]
    jsonl(study / 'dispatch.jsonl', trial.dispatch_log)
    jsonl(study / 'inputs.jsonl', trial.input_log)
    jsonl(study / 'executor_events.jsonl', trial.executor_events)
    jsonl(study / 'scheduler_events.jsonl', trial.scheduler.events)
    jsonl(study / 'decision_events.jsonl', trial.scheduler.decision_events)
    jsonl(study / 'language.jsonl', trial.language_rows)
    jsonl(study / 'claims.jsonl', trial.claim_results)
    jsonl(study / 'wire_wall.jsonl', adapter_wire.rows if adapter_wire is not None else [])
    write(study / 'claim_gate.json', runtime.gate.record())
    write(study / 'study_config.json', trial.study_config())
    write(study / 'send_ledger.json', trial.send_ledger.to_dict())
    write(study / 'channel.json', trial.channel_summary())
    summary = {'archived_request_problems': problems, 'requests': len(trial.requests),
               'images': len(trial.request_images), 'live': None}
    from harness import pair_llm_live as live
    records = live.live_records(trial.send_ledger)
    if records is not None:                       # a live ledger: per-POST rows (tokens, latency, hashes, failures)
        jsonl(study / 'model_calls.jsonl', records['rows'])
        summary['live'] = {'posts': records['usage']['requests'], 'model_usage': records['usage'],
                           'reply_format': records['reply_format']}
    return summary


def run_pair_case(bundle, out, *, condition, seed, backend_factory, calibration, calibration_sha,
                  provider_factory=None, adapter_factory=None, cap_s=contract.CAP_S, kind='stub',
                  runtime_factory=None, trial_class=None, source_sha='unknown', root=contract.ROOT, health=None,
                  finalize=None):
    """Run one arm. Returns the result row (also written to ``result.json``).

    ``adapter_factory(out) -> (ModelAdapter, wire_recorder)`` supplies the model path of the LLM arms; the
    ``rule`` arm needs none. ``runtime_factory`` replaces the runtime class (tests only). ``health(trial,
    final=False)`` is the live driver's per-tick stop check (rate limit, fatal error, cohort cap); it raises to
    end the case, and the artifacts are still written. ``finalize(out, result)`` runs after the LLM artifacts and
    before the artifact hashes, so a driver can add its own record to the hashed set.
    """
    from harness.pair_llm_dispatch import PairLink, PairTrial
    from harness.pair_llm_eval import judge, read_trajectory, trial_metrics
    from harness.pair_llm_runtime import GatedHighRuntime
    from harness.zone_pair_highpose_runtime import Runtime
    from harness.pair_llm_stop_adapter import StopAdapter
    if condition not in contract.CONDITIONS or bundle['condition'] != condition:
        raise ValueError('condition differs from the bundle')
    if not 0 < float(cap_s) <= contract.CAP_S:
        raise ValueError(f'case cap {cap_s} must be in (0, {contract.CAP_S}] SIM s')
    llm = condition != 'rule'
    if llm and adapter_factory is None:
        raise ValueError('an LLM arm needs a model adapter')
    mode = bundle.get('admission_mode', contract.high_skill.MEASURED_SIM)
    if mode == contract.high_skill.DEV_PILOT:
        from harness.zone_pair_highpose_starts import require_dev_seed
        require_dev_seed(seed)
        contract.high_skill.calibration_for(mode, calibration, calibration_sha, bundle['map_id'])
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out / 'bundle.json', bundle)
    physics = {**contract.physics_bundle(root=root, admission_mode=mode)}
    physics['case'] = {**physics['case'], 'sim_cap_s': float(cap_s)}
    scenario = contract.scenario(root=root)
    target = scenario['orders'][0]['destination_zone']
    result = {'schema': LOOP_VERSION, 'execution_bundle_id': contract.BUNDLE_ID, 'condition': condition,
              'arm': contract.ARMS[condition], 'status': 'HOST_ERROR', 'protocol_complete': False,
              'research_result': False, 'model_kind': bundle['model']['kind'], 'reset_sim_cap_s': skill_layer.RESET_CAP_S,
              'case_sim_cap_s': float(cap_s), 'registered_case_cap_s': contract.CAP_S,
              'bundle_sha256': digest(bundle), 'physics_bundle_sha256': digest(physics),
              'loadavg_start': list(os.getloadavg()), 'failure': None,
              'failure_class': None, **contract.admission_record(mode, bool((bundle.get('calibration') or {}).get('synthetic_plumbing_only'))),
              **contract.physics_profile(physics)}
    from sim import final_pair_highpose_clock as clock
    # Identify the actual host, including failed attempts; fake/legacy hosts must not claim clock v2.
    result['host_clock'] = clock.record() if getattr(backend_factory, 'host_clock', None) == clock.ID else None
    backend = runtime = trial = static = None
    links, wire, adapter, counts = {}, None, None, {r: {} for r in PAIR_ROBOTS}
    stops = {}
    started_wall = time.time()
    try:
        static, _, _ = skill_layer.resolve(physics['map_id'])
        backend = backend_factory(physics, out, seed=seed)
        reset = backend.reset(skill_layer.RESET_CAP_S)
        if not 0 <= reset <= skill_layer.RESET_CAP_S + 1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start + cap_s)
        result['reset_sim_s'] = reset
        make = runtime_factory or (GatedHighRuntime if llm else Runtime)
        kwargs = {'provider_factory': provider_factory} if provider_factory is not None else {}
        runtime = make(static, calibration, calibration_sha, seed=seed, **kwargs)
        runtime.initial_commands(start, backend.commands)
        stops = {rid: StopAdapter(ex, condition=condition, origin_s=start)
                 for rid, ex in getattr(runtime, 'actors', {}).items()}
        if llm:
            adapter, wire = adapter_factory(out)
            map_bundle = ms.map_bundle(physics['map_id'], landmark_detail=scenario.get('landmark_detail', 'full'))
            links = {rid: PairLink(runtime, rid, origin_s=start, stop_adapter=stops[rid]) for rid in PAIR_ROBOTS}
            reg = contract.read_registry(root=root)
            from harness.zone_study_decisions import DecisionLimits
            trial = (trial_class or PairTrial)(
                scenario, condition=condition, seed=seed, links=links, horizon_s=float(cap_s),
                code_sha=source_sha,
                map_bundle=map_bundle, model_adapter=adapter,
                model_settings=_model_settings(adapter, bundle),
                decision_limits=DecisionLimits(**reg['decision_limits']), bundle_id=contract.BUNDLE_ID,
                run_id=f'{condition}-{scenario["scenario_id"]}-s{seed}')
            runtime.gate.listeners.append(trial.on_claim_result)
        steps = round(cap_s / skill_layer.TICK_S)
        # DEV light early end (same rule and helper as scripts.run_pair_highpose.student_run_case, all three arms):
        # stop CASE_END_SETTLE_S after both robots' pair/carry jobs ended (control-side job records only).
        from scripts.run_pair_highpose import CASE_END_SETTLE_S, jobs_ended_all
        case_end_at = None
        for i in range(steps + 1):
            elapsed = round(i * skill_layer.TICK_S, 6)
            backend.eval_sample()                      # raw labels have no return channel into any selector
            frames = backend.capture()
            runtime.on_frames(backend.now, frames)
            hook_events = [event for stop in stops.values() for event in stop.poll()]
            if llm:
                for rid in PAIR_ROBOTS:
                    links[rid].observe(frames[rid][0])
                    links[rid].tick(backend.now)
                if i == 0:
                    trial.begin(0.)
                else:
                    for rid in PAIR_ROBOTS:
                        for event in runtime.actors[rid].drain_events():
                            trial.on_executor_event(event, at_s=elapsed)
                    for event in hook_events:
                        trial.on_executor_event(event, at_s=elapsed)
                    trial.step_to(elapsed)
                if health is not None:
                    health(trial)
            if i == steps:
                break
            for rid, action in runtime.step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
                counts[rid][action['kind']] = counts[rid].get(action['kind'], 0) + 1
            for rid, action in runtime.arm_step(backend.now):
                backend.issue(rid, action)
                runtime.on_command(rid, backend.now, action)
                counts[rid][action['kind']] = counts[rid].get(action['kind'], 0) + 1
            backend.advance_to(start + (i + 1) * skill_layer.TICK_S)
            if contract.high_skill.DEV_LIGHT:
                if jobs_ended_all(runtime) and case_end_at is None:
                    case_end_at = backend.now
                    result['case_end'] = {'rule': 'dev_light_both_jobs_ended', 'jobs_ended_sim_s': backend.now - start,
                                          'settle_s': CASE_END_SETTLE_S}
                if case_end_at is not None and backend.now - case_end_at >= CASE_END_SETTLE_S - 1e-9:
                    break
        if abs(backend.now - start - cap_s) > 1e-7 and result.get('case_end') is None:
            raise RuntimeError('INCOMPLETE_BOUNDED_PROTOCOL')
        result.update(protocol_complete=True, status='COLLECTED_UNQUALIFIED', case_sim_s=backend.now - start)
        if llm:
            if health is not None:
                health(trial, final=True)
            trial_result = trial.finish(float(backend.now - start) if result.get('case_end') else float(cap_s))
            result['trial'] = {'calls': len(trial_result.calls), 'messages': len(trial_result.messages),
                               'actions': len(trial_result.actions), 'end_reason': trial_result.end_reason,
                               'end_state': trial_result.end_state}
            result['failure_class'] = _trial_failure_class(trial)
    except Exception as exc:                          # noqa: BLE001 - recorded, never swallowed silently
        result.update(status='HOST_ERROR', failure={
            'type': type(exc).__name__, 'message': str(exc)[:2000],
            'class': getattr(exc, 'failure_label', None)
            or ('ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR')},
            failure_class=_study_failure_class(exc))
    finally:
        try:
            for stop in stops.values():
                stop.poll()
            result['stop_decisions'] = [row for stop in stops.values() for row in stop.decisions]
            jsonl(out / 'stop_hook_events.jsonl', [row for stop in stops.values() for row in stop.events])
            jsonl(out / 'stop_decisions.jsonl', result['stop_decisions'])
        except Exception as exc:                  # noqa: BLE001 - preserve partial records and cleanup
            result.update(status='HOST_ERROR', stop_record_error=str(exc))
        if runtime is not None:
            try:
                write(out / 'student_record.json', runtime.record())
            except Exception as exc:                  # noqa: BLE001
                result.update(status='HOST_ERROR', record_error=str(exc))
        if trial is not None:
            try:
                result['llm_artifacts'] = write_llm_artifacts(out, trial, wire, runtime, links)
            except Exception as exc:                  # noqa: BLE001
                result.update(status='HOST_ERROR', llm_record_error=str(exc))
        if finalize is not None:
            try:
                finalize(out, result)
            except Exception as exc:                  # noqa: BLE001
                result.update(status='HOST_ERROR', finalize_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:              # noqa: BLE001
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result['loadavg_end'] = list(os.getloadavg())
        result['wall_s'] = round(time.time() - started_wall, 3)
        result['command_counts'] = counts
        from harness.pair_llm_live import live_records, live_walls
        walls = list(wire.walls) if wire is not None else live_walls(trial)
        result['metrics'] = _evaluate(out, result, condition, static, target, trial, walls, links, runtime, cap_s,
                                      judge, read_trajectory, trial_metrics)
        usage = live_records(getattr(trial, 'send_ledger', None))
        if usage is not None:
            result['metrics']['model_usage'] = usage['usage']
            result['metrics']['reply_format'] = usage['reply_format']
        result['metrics']['failure_class'] = result.get('failure_class')
        write(out / 'metrics.json', result['metrics'])
        write(out / 'result.json', result)
        write(out / 'artifacts.sha256.json', {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*'))
                                              if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def _study_failure_class(exc):
    """The study's failure class of an exception (``infra:HOST_ERROR`` / ``infra:API`` / ``other``)."""
    from harness import zone_study_llm_driver as llm
    return llm.classify_exception(exc)


def _trial_failure_class(trial):
    """Trial-level class of a COMPLETED live case: any API error / cap / no normal reply is ``infra:API``."""
    from harness import zone_study_llm_driver as llm
    ledger = getattr(trial, 'send_ledger', None)
    if not isinstance(ledger, llm.MainStudySendLedger):
        return None
    return llm.trial_failure_class(None, ledger, transport=trial.transport)


def _model_settings(adapter, bundle) -> dict:
    settings = dict(adapter.client_factory.settings)
    settings['provider'] = bundle['model']['kind'] if bundle['model']['kind'] == 'stub' else 'gemini_subscription_proxy'
    return settings


def _evaluate(out, result, condition, static, target, trial, walls, links, runtime, cap_s, judge, read_trajectory,
              trial_metrics) -> dict:
    """The separate evaluator, run after the loop. Its verdict is written under ``eval_only/`` only."""
    trajectory = Path(out) / 'eval_only' / 'trajectory.jsonl'
    if static is None or not trajectory.is_file():
        verdict = {'success_provisional': False, 'reason': 'NO_TRAJECTORY', 'judge_status': None}
    else:
        verdict = judge(read_trajectory(trajectory), static_map=static, target_zone=target,
                        start_s=result.get('reset_sim_s', 0.))
    write(Path(out) / 'eval_only' / 'verdict.json', verdict)
    counts = {rid: sum(result['command_counts'][rid].values()) for rid in PAIR_ROBOTS}
    sabotage = sabotage_events(links, runtime.gate) if (links and runtime is not None
                                                      and hasattr(runtime, 'gate')) else []
    row = trial_metrics(condition=condition, verdict=verdict, command_counts=counts, trial=trial,
                        ledger_walls=walls, sabotage=sabotage,
                        end_sim_s=result.get('case_sim_s'))
    if runtime is not None and hasattr(runtime, 'gate'):
        row['claims'] = claim_counts(runtime.gate)
    row['host_status'] = result['status']
    row['model_kind'] = result['model_kind']
    from harness.pair_llm_eval import decision_evidence
    row['decision_evidence'] = decision_evidence(
        condition=condition, success=row['success'], decisions=result.get('stop_decisions', ()),
        scheduler_events=(() if trial is None else trial.scheduler.events + trial.scheduler.decision_events),
        failure_class=result.get('failure_class'))
    # Keep the geometric success separate; exhausted/default-dominated LLM cases are not LLM success evidence.
    row['success_provisional'] = row['success']
    row['success'] = row['decision_evidence']['primary_success']
    return row


__all__ = ['LOOP_VERSION', 'TimedWire', 'stub_adapter', 'sabotage_events', 'claim_counts', 'run_pair_case']
