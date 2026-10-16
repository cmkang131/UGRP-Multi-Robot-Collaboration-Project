#!/usr/bin/env python3
"""Real-adapter pilot on stored wrist RGB; dry-run by default, no physics.

Initial stage: 4 conditions x ONE call. Cohort: 4 conditions x 3 actors x one
initial call, with at most one retry each and no idle/message re-asks. All requests share an
explicit, existing SQLite budget. Expansion requires complete reconciliation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.gemini_proxy import _to_gemini_multi_image_messages
from harness.llm_completion import (ACCEPTED_UNVERIFIED_LABEL, COMPLETION_POLICY,
                                    PROXY_COMPLETION_LIMITATION, completion_aggregate)
from harness.zone_study_eval import model_aggregate
from harness.zone_event_scheduler import CallPolicy, EventScheduler, PendingCall, TransportFailure
from harness.zone_pilot_budget import (ATTEMPT_CAP, TOKEN_CAP, UPSTREAM_BOUND, EFFECTIVE, REQUESTED,
                                       PilotBudget, sha, state_sha256, token_envelope, usage_total)
from harness.rgb_execution_bundle import RUNNABLE_ID, REGISTRY, load_bundle, source_closure
from harness.zone_pilot_ledger import PilotSendLedger, proxy_profile, runtime_identity
from harness.zone_pilot_reconcile import reconcile, require_preflight
from harness.zone_pilot_proxy_log import ACCEPTED_EVIDENCE_LEVELS
from harness.zone_sim_cost import Attempt
from harness.zone_study_contract import MAIN_CONDITIONS, condition_manifest, digest, registry_sha256
from harness.zone_study_inputs import provenance
from harness.zone_study_llm_transport import ModelCallTransport, gemini_client_factory
from harness import zone_study_offline as off
from harness import zone_study_prompts_ko as pk
from harness.zone_study_scenarios import load as load_scenario, scenario_ids

VERSION = 'ugrp.zone_study_adapter_pilot.v2'


def write_new(path, value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise OSError('saved pilot artifact failed read-back')
    return sha(data)


def source_identity(profile):
    # Content as well as git SHA: uncommitted source cannot impersonate the
    # committed version, and fixture/image changes invalidate the budget seal.
    paths = {ROOT / 'scripts/run_zone_study_pilot.py', ROOT / 'scripts/build_proxy_log_telemetry.py',
             ROOT / 'configs/simulation_workflows.json'}
    bundle, bundle_sha = load_bundle(RUNNABLE_ID)
    paths.update(ROOT / name for name in source_closure())
    paths.add(ROOT / REGISTRY / (RUNNABLE_ID + '.json'))
    for pattern in ('harness/*.py', 'sim/*.py', 'configs/zone_study_scenarios/*.json', 'maps/**/*.json',
                    'tests/fixtures/markerless_box/blue_floor_release/*'):
        paths.update(p for p in ROOT.glob(pattern) if p.is_file())
    files = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(paths)}
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                          text=True, capture_output=True).stdout.strip()
    return {'runner': VERSION, 'pipeline': 'AdapterTrial', 'client_factory': 'gemini_client_factory',
            'source_head': head, 'source_root': str(ROOT), 'files': files, 'proxy': profile,
            'rgb_execution_bundle': {'id': RUNNABLE_ID, 'sha256': bundle_sha,
                                     'status': bundle['status'],
                                     'effective': bundle['effective'],
                                     'physical_validation': 'unverified; pilot does not execute physics'},
            'python': sys.version, 'pillow': package_version('Pillow'),
            'effective_settings': EFFECTIVE, 'requested_settings': REQUESTED,
            'completion_policy': COMPLETION_POLICY,
            'completion_limitation': dict(PROXY_COMPLETION_LIMITATION),
            'sim_input_cost': pk.FIXED_PROMPT_POLICY,
            'sim_output_cost': 'frozen_local_tokenizer_on_actual_reply_text',
            'input_mode': 'stored_wrist_rgb_and_static_map_no_physics'}


def require_committed_source(identity):
    """Shared real-run/migration gate; this command never commits for the user."""
    dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT,
                           check=True, capture_output=True, text=True).stdout
    if dirty:
        raise ValueError('commit reviewed source before real pilot or migration (tracked worktree is dirty)')
    if identity.get('files'):
        subprocess.run(['git', 'ls-files', '--error-unmatch', '--', *identity['files']],
                       cwd=ROOT, check=True, capture_output=True)


def pilot_call_policy(stage):
    return CallPolicy(max_calls_per_actor=1 if stage == 'preflight' else 2,
                      max_http_attempts_per_actor=1 if stage == 'preflight' else 3,
                      max_attempts_total=1 if stage == 'preflight' else 12,
                      max_retries=0 if stage == 'preflight' else 1,
                      idle_reask_s=999., busy_reask_s=999., trigger_on_message=False)


def pilot_contract(scenario, seed, stage):
    """Freeze the review checklist from actual input builders; never sends."""
    conditions = []
    for condition in MAIN_CONDITIONS:
        trial = off.OfflineTrial(scenario, condition=condition, seed=seed)
        requests = []
        for actor in (trial.actors[:1] if stage == 'preflight' else trial.actors):
            prepared = trial.prepare_call(PendingCall(call_id='contract-' + actor, actor=actor,
                                                      trigger='start', started_sim_s=0.))
            requests.append({'actor': actor, **pk.archive_request(prepared.request)})
        conditions.append({'condition': condition_manifest(condition, seed),
                           'scenario': trial.source.manifest(), 'leader_id': trial.leader_id,
                           'wrist_originals': trial.library.manifest(), 'initial_inputs': requests})
    return {'execution_bundle_id': RUNNABLE_ID, 'stage': stage, 'seed': seed,
            'conditions': conditions, 'registry_sha256': registry_sha256(),
            'leader_rule': 'r1/r2/r3 indexed by seed % 3; hub-and-spoke, one robot also leads',
            'prompt_version': pk.PROMPT_VERSION,
            'protocol_version': off.zp.PROTOCOL_VERSION,
            'preprocessing_files_sha256': {name: sha((ROOT / name).read_bytes()) for name in (
                'harness/zone_study_prompts_ko.py', 'harness/zone_study_inputs.py',
                'harness/zone_study_protocol.py', 'harness/gemini_proxy.py')},
            'calls': {'preflight_posts_per_condition': 1, 'client_retries': 0,
                      'scheduler_policy': asdict(pilot_call_policy(stage)),
                      'cohort_initial_posts': 12, 'cohort_max_posts': 24,
                      'client_timeout_s': REQUESTED['timeout'],
                      'upstream_attempts_reserved_per_post': UPSTREAM_BOUND,
                      'global_attempt_cap': ATTEMPT_CAP, 'global_token_cap': TOKEN_CAP,
                      'refunds': 0, 'existing_send_budget': 'preserved across all runs and stages'},
            'sim_cost': {'parameters': trial.params.to_dict(), 'sha256': trial.params.digest(),
                         'input_policy': pk.FIXED_PROMPT_POLICY, 'tokenizer': pk.TOKENIZER_VERSION,
                         'output_policy': 'actual_reply_text_including_rejected_generations'},
            'validation_scope': 'stored wrist RGB adapter only; no physics or verified upstream STOP',
            'physical_success': None}


class AdapterTrial(off.OfflineTrial):
    """Reuse validated A/C/D input/channel pipeline; never fixture output costs."""
    def __init__(self, scenario, *, condition, seed, stage, run_id, budget, profile,
                 runtime, output, proxy_log=None, wire=None):
        policy = pilot_call_policy(stage)
        super().__init__(scenario, condition=condition, seed=seed, run_id=run_id,
                         policy=policy, horizon_s=120., code_sha=budget.meta['identity']['source_head'])
        self.stage = stage
        self.input_records = []
        self.client_factory = gemini_client_factory(url=profile['url'], study_json=True, **REQUESTED)
        self.send_ledger = PilotSendLedger(store_dir=output / 'wire', budget=budget, profile=profile,
                                           runtime=runtime, proxy_log=proxy_log, wire=wire,
                                           context={'run_id': output.parent.name, 'trial_id': run_id,
                                                    'condition': condition, 'seed': seed})
        self.transport = ModelCallTransport(self, send_ledger=self.send_ledger,
                                            client_factory=self.client_factory)
        self.scheduler = EventScheduler(self.transport, cost_params=self.params, policy=policy,
                                        actors=self.actors, on_action=self._on_action,
                                        bus=self.channel, bus_owner=off.BUS_OWNER)
        self.provenance = provenance(source=self.source, code_sha=self.code_sha,
                                     execution_bundle_id=VERSION, model=REQUESTED['model'],
                                     provider='gemini_subscription_proxy',
                                     model_settings_sha256=digest(profile),
                                     prompt_template_sha256=digest(pk.PROMPT_VERSION),
                                     cost_profile_id=self.params.version)

    def sim_output_tokens(self, raw, utterances):
        return pk.count_tokens(raw)

    def prepare_call(self, call):
        prepared = super().prepare_call(call)
        self.input_records.append({'call_id': call.call_id, 'payload_validated': True,
                                   'input_keys': sorted(prepared.bundled.payload),
                                   **pk.archive_request(prepared.request),
                                   'effective_settings': EFFECTIVE})
        return prepared

    def finish_call(self, call, prepared, raw, *, provider_usage=None):
        if usage_total(provider_usage) is None:
            raise TransportFailure('unknown provider usage: preflight stop, no action/message',
                                   attempts=(Attempt(outcome='error'),), usage_known=False)
        return super().finish_call(call, prepared, raw, provider_usage=provider_usage)

    def run_adapter(self):
        for actor in (self.actors[:1] if self.stage == 'preflight' else self.actors):
            self.scheduler.trigger(actor, 'start', at=0.)
        with self.send_ledger.guard:
            report = self.scheduler.run(until_s=self.horizon_s)
        self._collect()
        for call in self.calls:
            call['effective_settings'] = dict(EFFECTIVE)
            call['requested_settings'] = dict(REQUESTED)
        for record in self.input_records:
            record['completion'] = self.scheduler.ledger[record['call_id']].get('completion')
        return {'schema': VERSION, 'trial_id': self.run_id, 'condition': self.condition,
                'model_evaluation': model_aggregate({'calls': self.calls, 'messages': self.messages}),
                'completion_policy': COMPLETION_POLICY,
                'completion_limitation': dict(PROXY_COMPLETION_LIMITATION),
                'stage': self.stage, 'physical_success': None, 'input_mode': 'stored_wrist_rgb',
                'actions_are': 'accepted_high_level_adapter_outputs_no_physical_execution',
                'calls': self.calls, 'messages': self.messages, 'actions': self.actions,
                'request_archive': self.input_records, 'send_ledger': self.send_ledger.to_dict(),
                'scheduler': report.to_dict(), 'scheduler_ledger': self.scheduler.ledger,
                'censored': self.scheduler.censored, 'channel': self.channel_summary(),
                'effective_settings': EFFECTIVE, 'requested_settings': REQUESTED,
                'sim_cost': self.cost_summary()}


def dry_run(out, stage, scenario, seed, profile, *, limitation_acknowledged=False):
    plans = []
    for condition in MAIN_CONDITIONS:
        trial = off.OfflineTrial(scenario, condition=condition, seed=seed)
        call = PendingCall(call_id='dry-call-r1', actor='r1', trigger='start', started_sim_s=0.)
        prepared = trial.prepare_call(call)
        request = prepared.request
        body = json.dumps({'model': REQUESTED['model'], 'max_tokens': REQUESTED['max_tokens'],
                           'reasoning_effort': REQUESTED['reasoning_effort'],
                           'temperature': REQUESTED['temperature'],
                           'messages': _to_gemini_multi_image_messages(request['messages'], request['images'])}).encode()
        path = out / condition / 'request.json'
        write_new(path, json.loads(body))
        saved = path.read_bytes()
        envelope = token_envelope(body)
        plans.append({'condition': condition, 'actor': 'r1', 'request_id': prepared.request_id,
                      'request_path': str(path), 'saved_sha256': sha(saved), 'wire_body_sha256': sha(body),
                      'archive': pk.archive_request(request), 'reservation': envelope})
    value = {'schema': VERSION, 'mode': 'dry_run', 'stage': stage, 'model_calls': 0,
             'reconciliation_evidence_levels': [],
             'accepted_reconciliation_evidence_levels': list(ACCEPTED_EVIDENCE_LEVELS),
             'completion_policy': COMPLETION_POLICY,
             'completion_limitation': dict(PROXY_COMPLETION_LIMITATION),
             'upstream_finish_limitation_acknowledged': limitation_acknowledged,
             'accepted_upstream_unverified_calls': 0,
             'json_fence_removed_calls': 0,
             'source_identity': source_identity(profile),
             'pilot_contract': pilot_contract(scenario, seed, stage),
             'proxy_runtime': None,
             'network_calls': 0, 'effective_settings': EFFECTIVE, 'proxy': profile,
             'preflight_calls': 4, 'cohort_initial_calls': 12, 'cohort_max_proxy_posts': 24,
             'preflight_reserved_attempts_bound': 8,
             'preflight_reserved_tokens_bound': sum(p['reservation']['reserved_tokens'] for p in plans),
             'plans': plans, 'cohort_gate': 'four_stop_schema_valid_calls_plus_explicit_limitation_acknowledgement_and_full_billing_reconciliation'}
    write_new(out / 'manifest.json', value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new run directory; never overwritten')
    parser.add_argument('--execute', action='store_true', help='EXPLICIT real LLM authorization')
    parser.add_argument('--budget-file', type=Path)
    parser.add_argument('--init-budget', action='store_true', help='local-only create, never reset')
    parser.add_argument('--migrate-source', action='store_true', help='audit and reseal the SAME budget; no calls/refunds')
    parser.add_argument('--migration-reason')
    parser.add_argument('--from-identity-sha256', help='reviewed old source hash from --reconcile-only')
    parser.add_argument('--expected-state-sha256', help='reviewed state hash from --reconcile-only')
    parser.add_argument('--settle-reconciled', action='store_true', help='explicit audited budget settlement; no calls')
    parser.add_argument('--dry-run', action='store_true', help='with --settle-reconciled: plan only, no DB writes')
    parser.add_argument('--reconciliation-report', type=Path)
    parser.add_argument('--expected-report-sha256')
    parser.add_argument('--reservation-id', action='append', help='settle only these sends; ineligible IDs are errors')
    parser.add_argument('--stage', choices=('preflight', 'cohort'), default='preflight')
    parser.add_argument('--scenario', default=scenario_ids()[0], choices=scenario_ids())
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--proxy-url', default='http://127.0.0.1:8391/v1/chat/completions')
    parser.add_argument('--proxy-source', type=Path, default=Path.home() / '.local/bin/gemini_subscription_proxy.py')
    parser.add_argument('--proxy-pid', type=int)
    parser.add_argument('--proxy-log', type=Path, default=Path.home() / '.hermes/logs/gemini-subscription-proxy.log')
    parser.add_argument('--preflight-manifest', type=Path)
    parser.add_argument('--acknowledge-upstream-finish-limitation', action='store_true',
                        help='accept proxy stop + valid schema without claiming verified upstream STOP')
    parser.add_argument('--upstream-telemetry', type=Path)
    parser.add_argument('--reconcile-only', action='store_true')
    parser.add_argument('--recover-run', help='with --reconcile-only: close an interrupted driver after terminal evidence')
    args = parser.parse_args(argv)
    if sum((args.execute, args.init_budget, args.reconcile_only, args.migrate_source, args.settle_reconciled)) > 1:
        parser.error('execute/init/reconcile/migrate/settle modes are mutually exclusive')
    migration_options = (args.migration_reason, args.from_identity_sha256, args.expected_state_sha256)
    if args.migrate_source and (not all(migration_options) or args.stage != 'preflight'):
        parser.error('--migrate-source requires reason, both reviewed hashes and stage preflight')
    if (args.migration_reason or args.from_identity_sha256) and not args.migrate_source:
        parser.error('migration options require --migrate-source')
    if args.expected_state_sha256 and not (args.migrate_source or args.settle_reconciled):
        parser.error('--expected-state-sha256 requires migration or settlement')
    if args.settle_reconciled and not all((args.reconciliation_report, args.expected_report_sha256,
                                         args.expected_state_sha256, args.upstream_telemetry)):
        parser.error('--settle-reconciled requires report, telemetry and both reviewed hashes')
    if any((args.dry_run, args.reconciliation_report, args.expected_report_sha256, args.reservation_id)) and not args.settle_reconciled:
        parser.error('settlement options require --settle-reconciled')
    if args.recover_run and not args.reconcile_only:
        parser.error('--recover-run requires --reconcile-only')
    if (args.execute or args.init_budget or args.reconcile_only or args.migrate_source or args.settle_reconciled) and args.budget_file is None:
        parser.error('an explicit persistent --budget-file is required')
    out = args.output.resolve()
    if out.exists():
        parser.error('--output must be a new directory (frozen records are never overwritten)')
    if args.settle_reconciled:
        budget = PilotBudget(args.budget_file)
        proposal = {'budget_file': str(budget.path), 'report_path': str(args.reconciliation_report),
                    'telemetry_path': str(args.upstream_telemetry),
                    'expected_report_sha256': args.expected_report_sha256,
                    'expected_state_sha256': args.expected_state_sha256,
                    'dry_run': args.dry_run, 'reservation_ids': args.reservation_id}
        write_new(out / 'settlement-proposal.json', proposal)
        receipt = budget.settle_reconciled(**{k: v for k, v in proposal.items() if k != 'budget_file'})
        # A receipt write failure cannot undo the transaction: audits remain
        # recoverable through --reconcile-only, with their hashes and debits.
        after = budget.snapshot()
        if any(row not in after['budget_settlements'] for row in receipt['audits']):
            raise RuntimeError('committed budget settlement read-back mismatch')
        write_new(out / 'budget-settlement.json', receipt)
        print(json.dumps({'dry_run': args.dry_run, 'eligible': len(receipt['eligible']),
                          'skipped': len(receipt['skipped']), 'before': receipt['before'],
                          'after': receipt['after'], 'network_calls': 0,
                          'audit': str(out / 'budget-settlement.json')}))
        return 0
    telemetry = [] if args.upstream_telemetry is None else [
        json.loads(line) for line in args.upstream_telemetry.read_text().splitlines() if line.strip()]
    if args.reconcile_only:
        budget = PilotBudget(args.budget_file, read_only=not args.recover_run)
        report = reconcile(budget.snapshot(), telemetry)
        write_new(out / 'reconciliation.json', report)
        if args.recover_run:
            budget.recover_run(args.recover_run, report=report, report_path=out / 'reconciliation.json')
        print(json.dumps({'complete': report['complete'], 'evidence_levels': report['evidence_levels'],
                          'report': str(out / 'reconciliation.json')}))
        return 0 if report['complete'] else 2
    profile = proxy_profile(args.proxy_source, args.proxy_url)
    if args.migrate_source:
        identity = source_identity(profile)
        require_committed_source(identity)
        budget = PilotBudget(args.budget_file)
        # Save the proposal first. A crash after the DB commit is recoverable
        # from snapshot.source_migrations; never reinitialize or repeat blindly.
        write_new(out / 'migration-proposal.json', {
            'budget_file': str(budget.path), 'pilot_id': budget.meta['pilot_id'],
            'from_identity_sha256': args.from_identity_sha256,
            'expected_state_sha256': args.expected_state_sha256,
            'to_identity': identity, 'reason': args.migration_reason})
        migration = budget.migrate_source(identity, reason=args.migration_reason,
                                         expected_identity_sha256=args.from_identity_sha256,
                                         expected_state_sha256=args.expected_state_sha256)
        # Reopen and verify the committed record before exporting the receipt.
        after = PilotBudget(args.budget_file, identity=identity).snapshot()
        if after['source_migrations'][-1] != migration:
            raise RuntimeError('committed migration read-back mismatch')
        write_new(out / 'source-migration.json', migration)
        print(json.dumps({'source_revision': after['meta']['source_revision'],
                          'reserved_attempts': after['reserved_attempts'],
                          'reserved_tokens': after['reserved_tokens'], 'refunds': 0,
                          'network_calls': 0, 'audit': str(out / 'source-migration.json')}))
        return 0
    if args.init_budget:
        identity = source_identity(profile)
        budget = PilotBudget.create(args.budget_file, identity=identity)
        write_new(out / 'budget-created.json', budget.meta)
        print(json.dumps({'budget_file': str(budget.path), 'pilot_id': budget.meta['pilot_id'], 'network_calls': 0}))
        return 0
    scenario = load_scenario(args.scenario)
    if not args.execute:
        value = dry_run(out, args.stage, scenario, args.seed, profile,
                        limitation_acknowledged=args.acknowledge_upstream_finish_limitation)
        print(json.dumps({'mode': 'dry_run', 'network_calls': 0, 'manifest': str(out / 'manifest.json'),
                          'reserved_tokens_bound': value['preflight_reserved_tokens_bound']}))
        return 0
    identity = source_identity(profile)
    require_committed_source(identity)
    budget = PilotBudget(args.budget_file, identity=identity)
    before = budget.snapshot()
    prior_report = reconcile(before, telemetry)
    cohort_gate = {'admitted': False, 'billing_complete': prior_report['complete'],
                   'billing_evidence_levels': prior_report['evidence_levels'],
                   'accepted_evidence_levels': list(ACCEPTED_EVIDENCE_LEVELS)}
    if args.stage == 'cohort':
        if args.preflight_manifest is None:
            parser.error('--stage cohort requires --preflight-manifest')
        cohort_gate = require_preflight(before, prior_report, json.loads(args.preflight_manifest.read_text()))
    elif before['sends']:
        # Restart/retry is not permission to ignore unresolved requests.
        if not prior_report['complete']:
            raise ValueError('prior pilot sends unresolved; reconcile before restarting preflight')
    runtime = runtime_identity(profile, args.proxy_pid)
    run_id = out.name
    run = {'schema': VERSION, 'run_id': run_id, 'mode': 'real_adapter', 'stage': args.stage,
           'cohort_gate': cohort_gate,
           'reconciliation_evidence_levels': prior_report['evidence_levels'],
           'accepted_reconciliation_evidence_levels': list(ACCEPTED_EVIDENCE_LEVELS),
           'completion_policy': COMPLETION_POLICY,
           'completion_limitation': dict(PROXY_COMPLETION_LIMITATION),
           'upstream_finish_limitation_acknowledged': (args.acknowledge_upstream_finish_limitation
                                                      or args.stage == 'cohort'),
           'accepted_upstream_unverified_calls': 0,
           'json_fence_removed_calls': 0,
           'source_revision': budget.meta.get('source_revision', 0),
           'source_migration_sha256': budget.meta.get('source_migration_sha256'),
           'pilot_contract': pilot_contract(scenario, args.seed, args.stage),
           'pilot_id': budget.meta['pilot_id'], 'budget_file': str(budget.path),
           'source_identity': identity, 'proxy_runtime': runtime, 'proxy': profile,
           'effective_settings': EFFECTIVE, 'requested_settings': REQUESTED,
           'scenario': args.scenario, 'seed': args.seed, 'trials': [],
           'physical_success': None, 'loadavg': list(os.getloadavg())}
    out.mkdir(parents=True)
    write_new(out / 'started.json', run)
    budget.start_run(run_id, args.stage, {'output': str(out)},
                     expected_state=state_sha256(before))
    failed = False
    try:
        for condition in MAIN_CONDITIONS:
            trial_id = f'{run_id}-{condition}-s{args.seed}'
            trial = AdapterTrial(scenario, condition=condition, seed=args.seed, stage=args.stage,
                                 run_id=trial_id, budget=budget, profile=profile, runtime=runtime,
                                 output=out / condition, proxy_log=args.proxy_log)
            result = trial.run_adapter()
            digest_file = write_new(out / condition / 'trial.json', result)
            completion = completion_aggregate(result['calls'])
            successes = completion['successful_calls']
            row = {'trial_id': trial_id, 'condition': condition, 'successful_calls': successes,
                   'accepted_upstream_unverified_calls': completion['accepted_upstream_unverified_calls'],
                   'json_fence_removed_calls': completion['json_fence_removed_calls'],
                   'completion': completion,
                   'sent': trial.send_ledger.sends(), 'trial_path': str(out / condition / 'trial.json'),
                   'trial_sha256': digest_file}
            run['trials'].append(row)
            # Stop at the first failed/unknown/censored call; no silent retry of
            # a failed four-call preflight. Cohort scheduler retries are bounded.
            if (any(r['status'] != 'done' for r in trial.scheduler.ledger.values())
                    or successes != len(result['calls']) or successes == 0):
                failed = True
                break
    except BaseException as exc:
        failed = True
        run['error_type'] = type(exc).__name__
        raise
    finally:
        after = budget.snapshot()
        run['global_budget'] = {'reserved_attempts': after['reserved_attempts'],
                                'reserved_tokens': after['reserved_tokens'],
                                'charged_attempts': after['charged_attempts'],
                                'charged_tokens': after['charged_tokens'],
                                'budget_settlement_count': len(after['budget_settlements']), 'refunds': 0}
        run['call_links'] = [s for s in after['sends'] if s['run_id'] == run_id]
        run['accepted_upstream_unverified_calls'] = sum(
            t['accepted_upstream_unverified_calls'] for t in run['trials'])
        run['json_fence_removed_calls'] = sum(t['json_fence_removed_calls'] for t in run['trials'])
        run['status'] = 'failed' if failed else 'recorded'
        report = reconcile(after, telemetry)
        run['reconciliation_complete'] = report['complete']
        run['reconciliation_evidence_levels'] = report['evidence_levels']
        grades = {r['reservation_id']: r['evidence_level'] for r in report['calls']}
        run['call_links'] = [{**s, 'evidence_level': grades[s['reservation_id']]}
                             for s in run['call_links']]
        write_new(out / 'reconciliation.json', report)
        digest_file = write_new(out / 'manifest.json', run)
        budget.finish_run(run_id, status=run['status'], manifest_sha256=digest_file)
    print(json.dumps({'manifest': str(out / 'manifest.json'), 'status': run['status'],
                      'accepted_upstream_unverified_calls': run['accepted_upstream_unverified_calls'],
                      'json_fence_removed_calls': run['json_fence_removed_calls'],
                      'accepted_upstream_unverified_label': ACCEPTED_UNVERIFIED_LABEL,
                      'reconciliation_evidence_levels': report['evidence_levels'],
                      'reconciliation_complete': report['complete']}))
    return 0 if not failed and report['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
