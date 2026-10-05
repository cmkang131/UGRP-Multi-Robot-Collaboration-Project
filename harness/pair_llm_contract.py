"""Execution bundle of the pair LLM viability test (v100). Static: never imports a simulator or a model client.

``zone-pair-llm-v100`` (workflow 3.12.0) puts an LLM decision layer on top of the #363 v98 HIGH scripted two-robot pair
skill and compares three arms on the SAME map, order, 900 SIM s cap and evaluator:

* ``rule``     C-rule         both robots submit the scripted claim as soon as they are idle (no model);
* ``no_comm``  C-llm-nocomm   each robot's model decides on its own RGB, the map and the order sheet; no messages;
* ``peer_nl``  C-llm-nl       the same plus a natural-language peer channel between r1 and r2 (no language
                               requirement: user decision 2026-10-03, "걍 한국어 조건 뺴주라").

The fixed-enum pair status wire stays on in every arm. This bundle records what a result of a run depends
on (model id, prompt template hash, temperature, the absence of a seed, the cost model, the condition, the v98
skill layer it sits on) so a number is never detached from its configuration. It does not seal, preregister or
admit anything: ``research_result`` is false.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from harness import pair_llm_billing as billing
from harness import pair_llm_decisions as decisions
from harness import pair_llm_status as status
from harness import zone_final_environment as base
from harness import zone_final_pair_contract as skill_layer
from harness import zone_final_pair_skill as skill
from harness import zone_pair_highpose_contract as high_skill

ROOT = base.ROOT
REGISTRY = 'configs/pair_llm_v100.json'
SCENARIO = 'configs/pair_llm_scenario_v3.json'
WORKFLOW = 'configs/simulation_workflows.d/pair_llm_v100.json'
BUNDLE_ID = 'zone-pair-llm-v100'
WORKFLOW_ID = 'zone-pair-llm-v100'
WORKFLOW_VERSION = '3.12.0'
BUNDLE_SCHEMA = 'ugrp.pair_llm_bundle.v100'
REGISTRY_SCHEMA = 'ugrp.pair_llm.v100'
CONDITIONS = ('rule', 'no_comm', 'peer_nl')
ARMS = {'rule': 'C-rule', 'no_comm': 'C-llm-nocomm', 'peer_nl': 'C-llm-nl'}
CAP_S = 900.
RESET_CAP_S = skill_layer.RESET_CAP_S
SMOKE_MAX_S = 60.
#: Not an allow-list: the entries whose import closure is hashed into the bundle.
SOURCE_ENTRIES = ('scripts/run_pair_llm.py', 'harness/pair_llm_case.py', 'harness/pair_llm_contract.py')
EVAL_ENTRIES = ('harness/pair_llm_eval.py',)
CONFIG_FILES = (REGISTRY, SCENARIO, WORKFLOW, 'configs/zone_study_integration/llm_driver.json')


@lru_cache(maxsize=8)
def _closure(root, entries) -> tuple:
    """The import closure (file NAMES only; the hashes are computed fresh on every call)."""
    from harness.python_source_closure import source_closure
    return tuple(source_closure(Path(root), entries))


@lru_cache(maxsize=4)
def _high_bundle(map_id, admission_mode):
    return high_skill.bundle(map_id, 'carry', admission_mode)


def read_registry(*, root=ROOT) -> dict:
    value = base.read(Path(root) / REGISTRY)
    if (value.get('schema') != REGISTRY_SCHEMA or value.get('execution_bundle_id') != BUNDLE_ID
            or value.get('workflow_id') != WORKFLOW_ID or value.get('workflow_version') != WORKFLOW_VERSION
            or value.get('status') != 'DRAFT_UNSEALED' or value.get('research_result') is not False
            or value.get('weld') != 'off' or value.get('render_profile') != 'floor_light_v1'
            or value.get('contact_profile') != 'cargo_noslip_v1'
            or value.get('sensors') != {'ultrasonic_front': 'off'}
            or tuple(value.get('conditions', ())) != CONDITIONS
            or {k: v['arm'] for k, v in value['conditions'].items()} != ARMS
            or value['caps']['per_case_s'] != CAP_S or value['caps']['reset_per_case_s'] != RESET_CAP_S
            or value['model']['seed'] is not None):
        raise ValueError('invalid pair LLM registry')
    if value.get('decision_limits') != {
            'max_calls_total': decisions.CALLS_TOTAL,
            'max_utterances_per_actor': decisions.UTTERANCES_PER_ACTOR,
            'max_utterances_total': decisions.UTTERANCES_TOTAL} or value.get('stop_decisions') != decisions.record():
        raise ValueError('pair LLM decision limits drift from coordinator decisions')
    return value


def scenario(*, root=ROOT) -> dict:
    """The scenario file; it must be exactly the order the v88 scripted skill carries (same task in every arm)."""
    value = base.read(Path(root) / SCENARIO)
    if value['orders'] != [{**skill.ORDER['orders'][0], 'identity': 'kind_fungible'}]:
        raise ValueError('pair LLM scenario differs from the v88 scripted skill order')
    if value['map_id'] != read_registry(root=root)['map_id'] or value.get('eval', {}).get('hidden_events'):
        raise ValueError('pair LLM scenario map/hidden events differ from the registry')
    return value


def driver_profile(*, root=ROOT) -> dict:
    """The registered Gemini proxy profile, read-only (``llm_driver.json``); checked against the study PLANNED_MODEL."""
    from harness import zone_study_integration as zi
    from harness.zone_pilot_network import proxy_address
    reg = read_registry(root=root)['model']
    table = base.read(Path(root) / reg['driver_profiles_file'])
    profile = dict(table['driver_profiles'][reg['driver_profile']])
    model = profile['model']
    planned = {k: zi.PLANNED_MODEL[k] for k in ('model', 'temperature', 'reasoning_effort')}
    if {k: model[k] for k in planned} != planned:
        raise ValueError('driver profile drifts from the study PLANNED_MODEL')
    proxy_address(profile['proxy_url'])
    return {**profile, 'profile_id': reg['driver_profile'], 'sha256': base.digest(profile)}


def physics_bundle(*, root=ROOT, admission_mode=high_skill.MEASURED_SIM) -> dict:
    """The #363 v98 physics/skill bundle shared by all three arms, capped at 900 SIM seconds."""
    reg = read_registry(root=root)
    row = copy.deepcopy(_high_bundle(reg['map_id'], admission_mode))
    return {**row, 'case': {'id': 'pair_llm', 'map_id': reg['map_id'], 'checkpoint': None, 'sim_cap_s': CAP_S}}


def physics_profile(physics) -> dict:
    """The DEV-light / partial-fix / render / guard settings of the shared #363 physics bundle, for plan, bundle and result."""
    nearclip = physics['render_nearclip']
    return {'dev_light': copy.deepcopy(physics['dev_light']), 'partial_fix': copy.deepcopy(physics['partial_fix']),
            'collision_guard': copy.deepcopy(physics['collision_guard']),
            'render_profile_effective': {'id': nearclip['id'], 'sha256': nearclip['sha256'],
                                         'base_profile': nearclip['base_profile']}}


def model_record(condition, *, kind, root=ROOT) -> dict:
    """What a run records about the model. ``kind``: ``none`` (rule), ``stub`` (plumbing) or ``live``."""
    reg = read_registry(root=root)['model']
    if condition == 'rule':
        return {'kind': 'none', 'model': None, 'temperature': None, 'seed': None, 'seed_statement': None,
                'note': 'the rule arm makes no model call'}
    if kind == 'stub':
        from harness.pair_llm_stub import STUB_MODEL_ID, STUB_SETTINGS
        return {'kind': 'stub', 'model': STUB_MODEL_ID, 'temperature': STUB_SETTINGS['temperature'],
                'reasoning_effort': STUB_SETTINGS['reasoning_effort'], 'max_tokens': STUB_SETTINGS['max_tokens'],
                'timeout_s': STUB_SETTINGS['timeout'], 'proxy_url': None, 'driver_profile': None,
                'seed': None, 'seed_statement': reg['seed_statement'],
                'note': 'deterministic stub behind FixtureWire; no network, no provider; plumbing only'}
    if kind != 'live':
        raise ValueError(f'unknown model kind {kind!r}')
    from harness.zone_pilot_budget import PROXY_SHA256
    profile = driver_profile(root=root)
    model = profile['model']
    return {'kind': 'live', 'model': model['model'], 'temperature': model['temperature'],
            'reasoning_effort': model['reasoning_effort'], 'max_tokens': model['max_tokens'],
            'timeout_s': model['timeout'], 'proxy_url': profile['proxy_url'],
            'driver_profile': {'profile_id': profile['profile_id'], 'sha256': profile['sha256']},
            'min_request_interval_s': profile['min_request_interval_s'],
            'proxy_source': profile['proxy_source'], 'audited_proxy_sha256': PROXY_SHA256,
            'transport': 'GeminiProxyCompleter -> MainStudySendLedger (durable budget row before the wire, raw '
                         'request/response bytes + sha256, provider usage, wall latency) -> loopback proxy under '
                         'NetworkFence; the proxy is checked read-only (audited source hash + PID listener) and '
                         'never started or edited',
            'retry_layers': {
                'scheduler': 'CallPolicy.max_retries=0: a failed call is never re-sent as a new POST',
                'run': {'policy': profile['retry_policy'], 'max_attempts': 2,
                        'note': 'once, in place, only for a host error before the first model request; a 429, an '
                                'API error or a host error after the first request is never retried'},
                'proxy_internal': {'internal_429_retry': True, 'upstream_attempts_per_post_bound': 2,
                                   'note': 'the audited proxy retries an upstream 429 inside one POST'}},
            'rate_limit_rule': 'HTTP 429, or quota / rate-limit / resource-exhausted wording in an error body, is '
                               'failure label RATE_LIMIT (study class infra:API); the run stops at the next tick '
                               'and is invalid; nothing retries it',
            'api_failure_trial_rule': profile['api_failure_trial_rule'],
            'seed': None, 'seed_statement': reg['seed_statement']}


def admission_record(mode, synthetic=False):
    """Reuse #363's labels; DEV results never become MEASURED_SIM evidence.

    A MEASURED_SIM label is refused while any DEV-only switch is on (#363 ``require_dev_only_flags``, review #371 P2),
    except for a synthetic plumbing run, which stays MEASURED_SIM-shaped but is marked never promotable."""
    if mode == high_skill.DEV_PILOT:
        return dict(high_skill.DEV_PILOT_LABELS)
    if mode != high_skill.MEASURED_SIM:
        raise ValueError('unknown admission mode')
    if synthetic:
        return {'admission_mode': mode, 'promotable': False, 'measured_sim_evidence': False}
    high_skill.require_dev_only_flags(mode)
    return {'admission_mode': mode}


def bundle(condition, *, kind='stub', calibration=None, synthetic_calibration=False, source_sha=None,
           root=ROOT, admission_mode=high_skill.MEASURED_SIM) -> dict:
    """The run bundle of one arm. ``calibration`` is ``{'path', 'sha256'}`` or None (plan only)."""
    from harness.pair_llm_dispatch import PAIR_ACTION_KINDS, PAIR_POLICY
    from harness.pair_llm_prompts_ko import (PROMPT_VERSION, STUDY_SPEC, fixed_prompt_reference_tokens,
                                             prompt_template_sha256)
    from harness.zone_sim_cost import params as cost_params
    if condition not in CONDITIONS:
        raise ValueError(f'{condition!r} is not one of {CONDITIONS}')
    reg = read_registry(root=root)
    if synthetic_calibration and admission_mode == high_skill.DEV_PILOT:
        raise ValueError('DEV_PILOT requires the exact admitted calibration, not synthetic plumbing')
    admission_record(admission_mode, synthetic_calibration)
    physics = physics_bundle(root=root, admission_mode=admission_mode)
    cost = cost_params()
    llm = condition != 'rule'
    paths = set(_closure(str(root), SOURCE_ENTRIES)) | set(CONFIG_FILES)
    eval_paths = set(_closure(str(root), EVAL_ENTRIES))
    limits = reg['decision_limits']
    row = {
        'schema': BUNDLE_SCHEMA, 'execution_bundle_id': BUNDLE_ID, 'workflow_id': WORKFLOW_ID,
        'workflow_version': WORKFLOW_VERSION, 'status': 'DRAFT_UNSEALED', 'research_result': False,
        'condition': condition, 'arm': ARMS[condition], 'llm': llm, 'source_sha': source_sha,
        **admission_record(admission_mode, synthetic_calibration), **physics_profile(physics),
        'scenario': {'file': SCENARIO, 'sha256': base.sha(Path(root) / SCENARIO),
                     'scenario_id': scenario(root=root)['scenario_id']},
        'map_id': reg['map_id'], 'map_sha256': physics['map_sha256'], 'robots': list(skill_layer.ROBOTS),
        'roles': {'r1': 'end_neg', 'r2': 'end_pos'},
        'skill_layer': {'bundle_id': high_skill.BUNDLE_ID, 'workflow_id': high_skill.WORKFLOW_ID,
                        'bundle_sha256': base.digest(physics), 'controller_family': physics['controller_family'],
                        'controller_variant': physics['controller_variant'],
                        'note': 'the #363 v98 HIGH runtime and sigma re-fix hooks; own-only claim and stop decisions'},
        'calibration': None if calibration is None else {
            'path': str(calibration['path']), 'sha256': calibration['sha256'],
            'synthetic_plumbing_only': bool(synthetic_calibration),
            'note': ('SYNTHETIC plumbing-only calibration: the controller is blind; no carry result'
                     if synthetic_calibration else ('admitted DEV_PILOT HIGH calibration; FUNCTIONAL_DEV, never promotable'
                     if admission_mode == high_skill.DEV_PILOT else 'admitted measured HIGH calibration'))},
        'model': model_record(condition, kind=kind, root=root),
        'prompt': None if not llm else {
            'version': PROMPT_VERSION, 'template_sha256': prompt_template_sha256(),
            'fixed_reference_tokens': fixed_prompt_reference_tokens(),
            'language': 'no language requirement; language_report is recorded per message, never a gate',
            'instruction_text_language': 'ko (reused study text)',
            'study_spec': STUDY_SPEC[condition],
            'study_spec_note': 'sealed study name of the open free-text peer channel (wire encoding free_ko); '
                               'its language check only flags',
            'action_kinds': list(PAIR_ACTION_KINDS),
            'look_around': 'pair-owned action kind over the robot\'s own executor look_around() (a guarded wide '
                           'own-camera look sweep; refused while any own job runs). The sealed study vocabulary '
                           'does not list it: harness.pair_llm_dispatch.validate_reply checks such a reply with a '
                           'placeholder continue and restores the action. Whether it helps depends on the pose '
                           'provider; with the blind plumbing worker it ends LOOKED_POSE_UNCERTAIN',
            'own_status': status.record()},
        'cost_model': {'version': cost.version, 'digest': cost.digest(), 'provisional': cost.provisional,
                       'charged': 'deterministic token-based SIM seconds; wall latency recorded, not charged',
                       'applies_to': 'LLM arms only (the rule arm makes no call)',
                       'input_billing': billing.record() if llm else None},
        'call_policy': {k: getattr(PAIR_POLICY, k) for k in PAIR_POLICY.__dataclass_fields__} if llm else None,
        'decision_limits': dict(limits) if llm else None,
        'stop_decisions': decisions.record(),
        'channel': reg['conditions'][condition]['channel'],
        'inter_robot_channels': (['dialogue'] if condition == 'peer_nl' else []) + ['pair_status'],
        'caps': {'per_case_s': CAP_S, 'reset_per_case_s': RESET_CAP_S,
                 'smoke_max_per_case_s': SMOKE_MAX_S, 'same_in_all_arms': True},
        'timing': physics['timing'],
        'render_profile': 'floor_light_v1', 'contact_profile': 'cargo_noslip_v1', 'weld': 'off',
        'sensors': {'ultrasonic_front': 'off'}, 'shared_top_camera': False,
        'controller_inputs': ['own_rgb', 'static_map', 'order_sheet', 'own_command_history', 'own_status', 'own_belief', 'decision_window',
                              'delivered_messages'],
        'evaluation': {'judge': 'harness/pair_llm_eval.py', 'status': 'PROVISIONAL_GEOMETRIC_JUDGE_NOT_THE_363_JUDGE',
                       'success_source': 'separate evaluator over eval_only/trajectory.jsonl; never a robot input'},
        'rule_arm_runtime': 'harness.zone_pair_highpose_runtime.Runtime (unmodified)',
        'llm_arm_runtime': 'harness.pair_llm_runtime.GatedHighRuntime (claim permit and own stop-hook adapter)',
        'physical_ready': False,
        'source_sha256': {p: base.sha(Path(root) / p) for p in sorted(paths)},
        'eval_source_sha256': {p: base.sha(Path(root) / p) for p in sorted(eval_paths)}}
    json.dumps(row, allow_nan=False)           # also rejects non-finite values
    return row


__all__ = ['BUNDLE_ID', 'WORKFLOW_ID', 'WORKFLOW_VERSION', 'CONDITIONS', 'ARMS', 'CAP_S', 'RESET_CAP_S',
           'SMOKE_MAX_S', 'read_registry', 'scenario', 'driver_profile', 'physics_bundle', 'model_record',
           'bundle', 'physics_profile']
