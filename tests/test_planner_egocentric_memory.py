"""Unit tests for the default-off egocentric-memory prompt projection.

No physics, no network, no model call.  The paired experiment is
experiments/2026-10-17-llmnomap/probe_paired.py.
"""
import json
import math
import re
from pathlib import Path

import pytest

from harness import planner_egocentric_memory as eg
from harness import pair_llm_billing as billing
from harness import pair_llm_inputs as pi
from harness import pair_llm_prompts_ko as pp
from harness import s4_llm_inputs as s4
from harness import zone_study_prompts_ko as pk
from tests.pair_llm_fakes import make_inputs, offline_only  # noqa: F401  (autouse fixture)

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile('[가-힣]')


def _fact(pose=(2.0, 0.0, 0.0), observed=100.0, **extra):
    row = {'subject': 'beam_1', 'predicate': 'help_request', 'value': 'needs_help',
           'observed_at': observed, 'source': 'own RGB + issued commands (synthetic inference)',
           'entity': {'id': 'beam_1'}, 'pose_own_m': list(pose),
           'observer_pose_own_m': [0.0, 0.0, 0.0],
           'rgb': {'robot_id': 'r1', 'frame_id': 4, 't_sim': observed}}
    row.update(extra)
    return row


def _context(pose=(0.0, 0.0, 0.0), facts=None):
    fact = _fact()
    facts = [fact] if facts is None else facts
    return {
        'schema': 'ugrp.task_planner.v1', 'robot_id': 'r1', 'condition': 'no_comm',
        'task': 'Select route. Static map has both doors; current blockage may differ.',
        'order_sheet': [{'order_id': 'order-1', 'kind': 'long_beam', 'item_ids': ['beam_1'],
                         'destination_zone': 'A', 'initial_location': {'pickup_bay': 'P1', 'slot': 'P1-3'}}],
        'public_rules': {'cost_rule': 'minimise expected team cost'},
        'now_s': 110.0,
        'static_map': {'map_id': 'zone_wide_door_tags_v1',
                       'frame': 'world metres; x east, y north',
                       'bounds_m': [-1.05, 5.4, -3.15, 1.45],
                       'passages': [{'id': 'door_1', 'center_m': [2.2, 0.05]}]},
        'own': {'robot_id': 'r1', 'gripper': 'parallel', 'command_stage': 'idle',
                'pose': {'mean': list(pose),
                         'covariance': [[0.04, 0.0, 0.0], [0.0, 0.09, 0.0], [0.0, 0.0, 0.01]]},
                'observed_facts': facts, 'local_view': 'own wrist view'},
        'evidence_assessment': {'own_observed_facts': [dict(f) for f in facts], 'reports': []},
        'received_messages': [], 'candidates': [{'act': 'help', 'args': {'partner': 'r2'}}],
    }


def _request(context=None, *, images=(), refs=()):
    context = _context() if context is None else context
    system = ('You are one robot\'s task planner. Use only the order sheet, static map, '
              'your camera/command pose estimate, own\nact results, and messages.')
    user = json.dumps(context)
    request = {'messages': [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': user}], 'images': list(images)}
    if refs:
        request['image_refs'] = list(refs)
        request['request_sha256'] = pk.request_digest_from_refs(system, user, list(refs))
    request['tokens'] = pk.request_tokens(system, user, list(images))
    if images:
        request['billed_tokens'] = billing.billed_tokens(request['tokens'], system_billed=100)
    return request


def test_toggle_defaults_off_and_off_is_identity():
    request = _request()
    for value in (None, '', '0', 'off', 'false', 'no'):
        assert eg.enabled(value=value) is False
        if value is None:
            assert eg.apply_request_if_enabled(request, environ={}) is request
        else:
            assert eg.apply_request_if_enabled(request, value=value) is request
    assert eg.enabled(value=eg.OPTION) and eg.enabled(value='1') and eg.enabled(value='true')


def test_toggle_rejects_unknown_value():
    with pytest.raises(ValueError):
        eg.enabled(value='planner_static_map_v2')


def test_projection_removes_map_pose_and_duplicate_facts():
    body = eg.project_context(_context())
    assert 'static_map' not in body
    assert 'pose' not in body['own'] and 'observed_facts' not in body['own']
    assert 'own_observed_facts' not in body['evidence_assessment']
    assert 'both doors may be remembered' in body['task'].lower()
    entry = body['egocentric_memory']['entries'][0]
    assert entry['kind'] == 'help_request' and entry['signature'] == 'beam_1=needs_help'
    assert entry['range_m'] == 2.0 and entry['bearing_rad'] == 0.0
    assert entry['age_s'] == 10.0
    assert entry['radius95_m'] == 0.73
    assert set(entry) == {'kind', 'signature', 'range_m', 'bearing_rad', 'age_s', 'radius95_m'}


def test_memory_shifts_opposite_to_own_motion_and_uses_current_heading():
    # Same world landmark [2,0]; after moving 1 m forward the remembered range is 1 m.
    body = eg.project_context(_context(pose=(1.0, 0.0, 0.0)))
    entry = body['egocentric_memory']['entries'][0]
    assert entry['range_m'] == 1.0 and entry['bearing_rad'] == 0.0
    # Heading +90 deg (left): world [0,2] is straight ahead, world [1,0] is right (-90).
    body = eg.project_context(_context(pose=(0.0, 0.0, math.pi / 2)))
    entry = body['egocentric_memory']['entries'][0]
    assert entry['range_m'] == 2.0 and entry['bearing_rad'] == pytest.approx(-math.pi / 2, abs=1e-3)


def test_empty_memory_is_explicit():
    body = eg.project_context(_context(facts=[]))
    assert body['egocentric_memory'] == {'schema': eg.SCHEMA, 'item_schema': 'ugrp.memory_item.v1',
                                         'frame': 'self/current', 'entries': [], 'count': 0}


def test_fixed_then_variable_order():
    body = eg.project_context(_context())
    keys = list(body)
    assert keys.index('schema') < keys.index('order_sheet') < keys.index('now_s')
    assert keys.index('now_s') < keys.index('own') < keys.index('egocentric_memory')
    assert keys.index('egocentric_memory') < keys.index('received_messages') < keys.index('candidates')
    assert keys.index('candidates') < keys.index('evidence_assessment')


def test_prose_rewrite_is_not_a_paraphrase_of_received_text():
    context = _context()
    context['received_messages'] = [{'message_id': 'm1', 'body': 'I see the beam.'}]
    body = eg.project_context(context)
    assert body['received_messages'] == [{'message_id': 'm1', 'body': 'I see the beam.'}]


def test_variant_system_rewrites_every_surveyed_prompt():
    systems = []
    for condition in pp.PAIR_CONDITIONS:
        for rid in pp.PAIR_ROBOTS:
            systems.append(pp.system_prompt(condition, rid, cap_window=6, cap_robot=3))
    for condition in pk.MAIN_CONDITIONS:
        for rid in pk.zp.actors(condition):
            systems.append(pk.system_prompt(condition, rid, seed=0))
    for condition in s4.MODEL_CONDITIONS:
        for rid in s4.ROBOTS:
            systems.append(s4.system_prompt(condition, rid))
    systems.append('You are one robot\'s task planner. Use only the order sheet, static map, '
                   'your camera/command pose estimate, own\nact results, and messages.')
    systems.append('No truth, peer images or authored map.')
    for system in systems:
        variant = eg.variant_system(system)
        low = variant.lower()
        for token in ('static_map', 'static map', '정적 지도', 'schematic',
                      'camera/command pose estimate'):
            assert token not in low, (token, system[:100])
        instruction = eg.INSTRUCTION_KO if HANGUL.search(variant) else eg.INSTRUCTION_EN
        assert instruction in variant
        assert eg.variant_system(variant) == variant          # idempotent


def test_audit_projection_zero_leaks_and_coordinate_audit():
    original = _request()
    variant = eg.apply_request_if_enabled(original, value=eg.OPTION)
    report = eg.audit_projection(original, variant)
    assert report['ok'] and report['leaks'] == []
    assert report['static_map_keys_before'] > 0 and report['static_map_keys_after'] == 0
    assert report['world_pose_keys_before'] > 0 and report['world_pose_keys_after'] == 0
    assert report['memory_entries'] == 1 and report['top_level_order_ok']
    assert report['tokens_after']['total_text'] < report['tokens_before']['total_text']

    # A re-introduced map key and a removed coordinate pair are both caught.
    injected = json.loads(variant['messages'][1]['content'])
    injected['received_messages'] = [{'message_id': 'm1', 'body': 'estimate', 'xy': [2.2, 0.05]}]
    bad = dict(variant, messages=[variant['messages'][0],
                                  {'role': 'user', 'content': json.dumps(injected)}])
    report = eg.audit_projection(original, bad)
    assert not report['ok']
    assert any(leak['kind'] == 'removed_coordinate' for leak in report['leaks'])


def test_map_figure_is_dropped_and_own_image_is_last():
    own = {'label': pk.IMAGE_OWN, 'image': 'data:image/jpeg;base64,aGVsbG8='}
    mp = {'label': pk.IMAGE_MAP, 'image': 'data:image/png;base64,aGVsbG8='}
    refs = [{'label': pk.IMAGE_OWN, 'ref': 'own-r1-0004', 'sha256': 'a' * 64,
             'bytes_sha256': 'a' * 64, 'captured_at_sim_s': 0.0},
            {'label': pk.IMAGE_MAP, 'ref': 'sheet-map', 'sha256': 'b' * 64,
             'bytes_sha256': 'b' * 64, 'captured_at_sim_s': None}]
    request = _request(images=[mp, own], refs=refs)
    before = request['request_sha256']
    variant = eg.apply_request_if_enabled(request, value=eg.OPTION)
    assert [row['label'] for row in variant['images']] == [pk.IMAGE_OWN]
    assert [row['label'] for row in variant['image_refs']] == [pk.IMAGE_OWN]
    assert variant['request_sha256'] != before
    assert variant['billed_tokens']['images'] == 1
    assert variant['billed_tokens']['image_tokens_billed'] == billing.IMAGE_TOKENS_PER_IMAGE


def test_projection_is_idempotent():
    request = _request()
    once = eg.apply_request_if_enabled(request, value=eg.OPTION)
    twice = eg.apply_request_if_enabled(once, value=eg.OPTION)
    assert twice is once
    body = json.loads(once['messages'][1]['content'])
    again = eg.project_context(body)
    assert again['egocentric_memory'] == body['egocentric_memory']


def test_pair_builder_hook_removes_static_map_and_figure(monkeypatch):
    inputs, _, _ = make_inputs('peer_nl', 'r1')
    off = pi.build_request(inputs, window={'window_id': 'w1', 'max_utterances': 6,
                                           'max_your_utterances': 3})
    assert 'static_map' in off['messages'][1]['content'] and len(off['images']) == 2
    monkeypatch.setenv(eg.ENV_VAR, eg.OPTION)
    on = pi.build_request(inputs, window={'window_id': 'w1', 'max_utterances': 6,
                                          'max_your_utterances': 3})
    assert 'static_map' not in on['messages'][1]['content']
    assert 'static map' not in on['messages'][0]['content'].lower()
    assert [row['label'] for row in on['images']] == [pk.IMAGE_OWN]
    assert on['image_refs'][0]['label'] == pk.IMAGE_OWN
    assert on['tokens']['images'] == 1 and on['billed_tokens']['images'] == 1
    assert on[eg.PROJECTION_KEY]['memory_entries'] == 0
    assert on[eg.PROJECTION_KEY]['audit_leaks'] == 0
    monkeypatch.delenv(eg.ENV_VAR)
    window = {'window_id': 'w1', 'max_utterances': 6, 'max_your_utterances': 3}
    assert pi.build_request(inputs, window=window)['messages'][0]['content'] == off['messages'][0]['content']


def test_every_surveyed_builder_has_the_one_line_hook():
    for name in ('zone_study_prompts_ko.py', 'pair_llm_inputs.py', 's4_llm_inputs.py',
                 'e2e_own_inputs.py'):
        source = (ROOT / 'harness' / name).read_text()
        assert 'egocentric_memory.apply_request_if_enabled(request)' in source, name
