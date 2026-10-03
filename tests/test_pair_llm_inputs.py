"""Pair LLM prompt/input boundary and the three audit items (a) holding, (b) map projection, (c) wire images.
No physics, network or real model."""
import ast
import json
import re
from pathlib import Path

import pytest

from harness import pair_llm_contract as contract
from harness import pair_llm_inputs as pi
from harness import pair_llm_prompts_ko as prompts
from harness import zone_map_schematic as ms
from harness import zone_study_protocol as zp
from harness.zone_study_contract import ContractViolation
from tests.pair_llm_fakes import make_inputs, offline_only  # noqa: F401  (autouse fixture)

ROOT = contract.ROOT
HANGUL = re.compile('[가-힣]')


# --------------------------------------------------------------------------- two-robot prompt (no language rule)

@pytest.mark.parametrize('condition', prompts.PAIR_CONDITIONS)
@pytest.mark.parametrize('rid', prompts.PAIR_ROBOTS)
def test_prompt_is_two_robot_and_names_no_third_robot(condition, rid):
    text = prompts.system_prompt(condition, rid, cap_window=6, cap_robot=3)
    assert 'r3' not in text and '세 로봇' not in text and '세 대' not in text
    partner = prompts.partner_of(rid)
    assert f'로봇 {rid}입니다' in text and partner in text
    assert prompts.PAIR_ROLES[rid] in text and prompts.PAIR_ROLES[partner] in text
    assert len(HANGUL.findall(text)) / len(text) > .2
    # User decision 2026-10-03: NO language requirement anywhere in the prompt (the instruction text is Korean).
    assert '한국어' not in text
    assert 'free_ko' not in text
    if condition == 'peer_nl':
        assert '정해져 있지 않습니다' in text and '영어도 됩니다' in text
    else:
        assert '메시지' in text                       # no_comm states that there is no channel


def test_prompt_reuses_study_blocks_with_the_three_robot_text_rewritten_and_the_language_rule_dropped():
    from harness import zone_study_prompts_ko as pk
    assert 'r3' in pk.KO_ROLE_LINE['peer'] and '세 로봇' in pk.KO_ROLE_LINE['peer']   # the study text is untouched
    assert 'r3' not in prompts.system_prompt('peer_nl', 'r1') and '세 로봇' not in prompts.system_prompt('peer_nl', 'r1')
    assert 'r3' not in prompts.KO_PAIR_LITERALS and 'r3' not in prompts.KO_PAIR_MESSAGES
    assert '세 로봇' not in prompts.KO_PAIR_LITERALS and '세 로봇' not in prompts.KO_PAIR_MESSAGES
    # the study text that carries the language rule is untouched; the pair does not use it
    assert '한국어' in pk.KO_LANGUAGE and '한국어' in pk.KO_MESSAGES_KO
    assert all('한국어' not in text for slot in prompts.PAIR_CHANNEL_SLOTS.values() for text in slot.values())
    assert prompts.PROMPT_VERSION == 'ugrp.pair_llm_prompts_ko.v3'
    assert prompts.study_spec('peer_nl') == 'peer_ko' and prompts.study_spec('no_comm') == 'no_comm'
    digest = prompts.prompt_template_sha256()
    assert re.fullmatch('[0-9a-f]{64}', digest) and digest == prompts.prompt_template_sha256()


# --------------------------------------------------------------------------- closed payload

def test_payload_is_closed_and_pair_shaped():
    inputs, source, _ = make_inputs('peer_nl', 'r2')
    payload = inputs.payload_dict()
    assert pi.payload_violations(payload, pinned=source.pinned) == []
    assert set(payload) <= pi.allowlist('peer_nl')
    assert payload['order_sheet']['team_size'] == 2
    assert payload['channel']['can_send_to'] == ['r1']
    assert 'r3' not in json.dumps(payload)
    nocomm, _, _ = make_inputs('no_comm', 'r1')
    assert 'inbox' not in nocomm.payload_dict() and nocomm.payload_dict()['channel']['can_send_to'] == []


@pytest.mark.parametrize('key', ['gt_pose', 'peer_status', 'contact', 'success', 'qpos', 'beam_xyz_m',
                                 'top_camera', 'robot_poses', 'physical_success'])
def test_forbidden_or_unknown_keys_are_refused(key):
    inputs, source, _ = make_inputs('peer_nl', 'r1')
    payload = inputs.payload_dict()
    payload[key] = [0., 0., 0.]
    assert pi.payload_violations(payload, pinned=source.pinned)


def test_partner_envelope_only_and_no_inbox_in_no_comm():
    envelope = {'schema': 'ugrp.zone_study_message.v1', 'message_id': 'w1-r2-1', 'sender': 'r2',
                'recipients': ['r1'], 'created_at_sim_s': 1., 'encoding': 'free_ko', 'reply_to': None,
                'body': {'text': '시작하겠습니다.'}}
    inputs, source, _ = make_inputs('peer_nl', 'r1', inbox=[envelope], t=3.)
    assert pi.payload_violations(inputs.payload_dict(), pinned=source.pinned) == []
    wrong = dict(envelope, sender='r1')
    with pytest.raises(ContractViolation):
        make_inputs('peer_nl', 'r1', inbox=[wrong], t=3.)
    with pytest.raises(ContractViolation):
        make_inputs('no_comm', 'r1', inbox=[envelope], t=3.)


# --------------------------------------------------------------------------- exactly two images

def test_request_carries_exactly_two_images_own_frame_and_map_figure():
    inputs, _, bundle = make_inputs('peer_nl', 'r1')
    request = pi.build_request(inputs, window={'window_id': 'w1', 'max_utterances': 6, 'max_your_utterances': 3})
    assert len(request['images']) == 2 and len(request['image_refs']) == 2
    labels = [row['label'] for row in request['image_refs']]
    assert labels == ['CURRENT OWN WRIST RGB', 'STATIC MAP FIGURE']
    assert request['image_refs'][0]['sha256'] == inputs.payload_dict()['own_rgb_refs'][-1]['sha256']
    assert request['image_refs'][1]['sha256'] == bundle['schematic']['png_sha256']
    assert all(row['bytes_sha256'] == row['sha256'] for row in request['image_refs'])
    assert not any(k in request['messages'][1]['content'] for k in ('data:image', 'base64'))
    assert zp  # the protocol module is the study's


def test_archived_request_verifies_and_detects_edits():
    from harness import zone_study_prompts_ko as pk
    inputs, _, _ = make_inputs('no_comm', 'r2')
    request = pi.build_request(inputs)
    row = pk.archive_request(request)
    assert pk.verify_archived_request(row) == []
    row['user'] = row['user'].replace('r2', 'rx', 1)
    assert pk.verify_archived_request(row)


# --------------------------------------------------------------------------- audit (b): map projection

def test_audit_b_public_map_projection_has_no_landmark_tag_or_pose_keys():
    banned = ('landmark', 'tag', 'pose', 'aruco', 'marker', 'fiducial', 'xyyaw', 'gt_', 'spawn', 'start_pose')
    for detail in ('full', 'none'):
        bundle = ms.map_bundle(contract.read_registry()['map_id'], landmark_detail=detail)
        projection = bundle['public_map']
        assert bundle['has_landmarks'] is False
        keys = set()

        def walk(value):
            if isinstance(value, dict):
                for k, v in value.items():
                    keys.add(k)
                    walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)
        walk(projection)
        assert 'landmarks' not in projection
        # ``landmark_detail`` is the projection's own detail flag (a string), not map content
        assert projection['landmark_detail'] == detail
        assert not [k for k in keys - {'landmark_detail'} if any(word in k.lower() for word in banned)], sorted(keys)
        text = json.dumps(projection)
        assert not re.search(r'tag_?\d|aruco|apriltag', text, re.I)
    # the payload's static_map is exactly this projection plus its hashes
    inputs, _, bundle = make_inputs('peer_nl', 'r1')
    assert inputs.payload_dict()['static_map']['public_map'] == bundle['public_map']


# --------------------------------------------------------------------------- audit (a): holding() is an own-RGB estimate

def _imports(path):
    tree = ast.parse(Path(path).read_text())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    return names


def test_audit_a_holding_is_an_own_rgb_estimate_not_simulator_state():
    for name in ('harness/visual_box_skill.py', 'harness/zone_own_status.py'):
        direct = _imports(ROOT / name)
        assert not [m for m in direct if m.split('.')[0] in ('mujoco', 'torch') or m.startswith('sim.')], (name, direct)
    skill = (ROOT / 'harness/visual_box_skill.py').read_text()
    lines = skill.splitlines()
    sets = [i for i, line in enumerate(lines) if re.search(r'self\.held\s*=', line)]
    # initial False (constructor), True after the attachment checks, False after a confirmed release: nothing else
    assert [lines[i].strip() for i in sets] == ['self.held = False', 'self.held = True', 'self.held = False']
    before_true = '\n'.join(lines[max(0, sets[1] - 14):sets[1]])
    # True only after the own-camera attachment checks passed (both sides of the comotion sweep)
    assert 'last_attachment["attached"]' in before_true and '_probe_side_pair["attached"]' in before_true
    # False only on a visually confirmed release
    assert 'VISUAL_RELEASE_CONFIRMED' in '\n'.join(lines[sets[2] - 2:sets[2]])
    status = ast.parse((ROOT / 'harness/zone_own_status.py').read_text())
    holding = next(n for n in ast.walk(status) if isinstance(n, ast.FunctionDef) and n.name == 'holding')
    attrs = {n.attr for n in ast.walk(holding) if isinstance(n, ast.Attribute)}
    names = {n.id for n in ast.walk(holding) if isinstance(n, ast.Name)}
    assert not ({'world', 'data', 'xpos', 'qpos', 'model', 'mujoco', 'weld', 'contacts'} & (attrs | names))
    assert 'own_rgb_attachment_check (wrist skill)' in ast.unparse(holding)


def test_audit_a_holding_reads_only_the_skill_state_servos_and_own_camera_checks():
    from types import SimpleNamespace

    from harness.zone_own_status import OwnStatusMixin as Mixin
    box = SimpleNamespace(held=True)
    skill = SimpleNamespace(phase='nav_preplace', box=box, events=[])

    class Probe(Mixin):
        def __init__(self):
            self.job = SimpleNamespace(ctl=SimpleNamespace(skill=skill))
            self.servo, self.now = {}, 0.
            self._last_holding_check, self._holding_after = None, {'answer': 'no', 'source': 'x'}

    answer = Probe().holding()
    assert answer['answer'] == 'yes' and answer['source'] == 'own_rgb_attachment_check (wrist skill)'
    box.held = False
    assert Probe().holding()['answer'] != 'yes'
    # a pose/world object is never reachable from the status mixin: it holds no simulator handle
    assert not [a for a in vars(Probe()) if a in ('world', 'data', 'backend', 'physics')]


# --------------------------------------------------------------------------- evaluator boundary

def test_no_robot_side_module_imports_the_evaluator():
    importers = []
    for folder in ('harness', 'sim', 'scripts'):
        for path in sorted((ROOT / folder).glob('*.py')):
            if path.name == 'pair_llm_eval.py':
                continue
            if 'pair_llm_eval' in [m.rsplit('.', 1)[-1] for m in _imports(path)] or \
                    re.search(r'import[^\n]*pair_llm_eval|pair_llm_eval import', path.read_text()):
                importers.append(f'{folder}/{path.name}')
    assert importers == ['harness/pair_llm_case.py']
    tree = ast.parse((ROOT / 'harness/pair_llm_case.py').read_text())
    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top_level if 'pair_llm_eval' in ast.unparse(n)]       # only inside run_pair_case, after the loop
    from harness.python_source_closure import source_closure
    for module in ('pair_llm_dispatch', 'pair_llm_runtime', 'pair_llm_inputs', 'pair_llm_prompts_ko', 'pair_llm_stub'):
        assert 'harness/pair_llm_eval.py' not in source_closure(ROOT, [f'harness/{module}.py']), module


def test_bundle_records_everything_a_result_depends_on():
    for condition in contract.CONDITIONS:
        row = contract.bundle(condition, source_sha='1' * 40)
        assert row['arm'] == contract.ARMS[condition] and row['weld'] == 'off'
        assert row['render_profile'] == 'floor_light_v1' and row['sensors'] == {'ultrasonic_front': 'off'}
        assert row['shared_top_camera'] is False and row['research_result'] is False
        assert row['caps']['per_case_s'] == 300. and row['cost_model']['version'] == 'zone_sim_cost.v1'
        assert row['skill_layer']['bundle_id'] == 'zone-final-pair-v88'
        assert row['controller_inputs'] == ['own_rgb', 'static_map', 'order_sheet', 'own_command_history',
                                            'own_status', 'delivered_messages']
        assert 'harness/pair_llm_eval.py' in row['eval_source_sha256']
        assert row['model']['seed'] is None
        if condition == 'rule':
            assert row['model']['kind'] == 'none' and row['prompt'] is None
        else:
            assert row['model']['model'] == 'stub-pair-llm-v1' and row['model']['temperature'] == 0.
            assert 'No seed' in row['model']['seed_statement']
            assert re.fullmatch('[0-9a-f]{64}', row['prompt']['template_sha256'])
    live = contract.bundle('peer_nl', kind='live')['model']
    assert live['model'] == 'gemini-3.8-flash' and live['temperature'] == .2
    assert live['proxy_url'].startswith('http://127.0.0.1:') and live['driver_profile']['sha256']


# --------------------------------------------------------------------------- peer_nl naming (user decision 2026-10-03)

def test_the_robot_is_told_peer_nl_and_free_text_never_the_sealed_korean_names():
    inputs, _, _ = make_inputs('peer_nl', 'r1')
    request = pi.build_request(inputs, window={'window_id': 'w1'})
    system, user = (m['content'] for m in request['messages'])
    assert '"condition": "peer_nl"' in user and request['condition'] == 'peer_nl'
    assert pi.pair_channel_section('peer_nl', 'r1')['encoding'] == 'free_text'
    assert 'peer_ko' not in system + user and 'free_ko' not in system + user


def test_the_bundle_records_the_arm_name_the_sealed_spec_name_and_that_language_is_not_required():
    from harness import pair_llm_contract as contract
    row = contract.bundle('peer_nl')
    assert row['condition'] == 'peer_nl' and row['arm'] == 'C-llm-nl'
    assert row['prompt']['study_spec'] == 'peer_ko' and 'no language requirement' in row['prompt']['language']
    assert row['execution_bundle_id'] == 'zone-pair-llm-v100' and row['workflow_version'] == '3.12.0'
    assert row['inter_robot_channels'] == ['dialogue', 'pair_status']
    assert 'peer_ko' not in contract.CONDITIONS and contract.CONDITIONS == ('rule', 'no_comm', 'peer_nl')
