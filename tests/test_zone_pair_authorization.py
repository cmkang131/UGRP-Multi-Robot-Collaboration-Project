"""Coordinator authorization integrity/admission; no physical execute is called."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_zone_pair_dev as dev
from scripts import zone_pair_authorization as auth

SHA = 'a' * 40


def registered():
    return json.loads(dev.PREREG_V5F.read_text())


def authorize(p):
    # Synthetic integrity fixture only; not an execution authorization artifact.
    receipt = {'by': 'coordinator', 'ref': 'https://github.com/kcm0127-dotcom/ugrp/issues/221#issuecomment-123',
               'source_sha': SHA, 'registration_sha256': p['registration_sha256']}
    p['execution_authorization'] = {**receipt, 'sha256': auth.digest(receipt)}
    return p


def args_for(tmp_path, p, *, execute=True):
    path = tmp_path / 'registration.json'
    path.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'dev11', '--output',
                                  str(dev.primary_root() / 'outputs/not-created-authorization-test'),
                                  '--expected-source-sha', SHA, '--lock-owner', 'codex'])
    args.execute = execute
    return args


def test_absent_authorization_prepares_and_execute_is_refused(tmp_path):
    p = registered()
    args = args_for(tmp_path, p, execute=False)
    assert dev.load_config(args)[1]['id'] == 'dev11'
    args.execute = True
    with pytest.raises(ValueError, match='prepare-only.*execution_authorization'):
        dev.load_config(args)
    assert not args.output.exists()


def test_late_authorization_does_not_change_registration_or_source_receipts(tmp_path):
    p = registered()
    original = copy.deepcopy(p)
    authorize(p)
    assert auth.digest(auth.registration_payload(p)) == original['registration_sha256']
    assert p['grasp_contract'] == original['grasp_contract']
    assert p['scene_contract'] == original['scene_contract']
    args = args_for(tmp_path, p)
    assert dev.load_config(args)[1]['seed'] == 907
    assert not args.output.exists()


@pytest.mark.parametrize('fault', ['by', 'ref', 'source', 'registration', 'signature', 'extra', 'body', 'nan'])
def test_altered_authorization_or_registration_is_rejected(tmp_path, fault):
    p = authorize(registered())
    a = p['execution_authorization']
    if fault == 'by': a['by'] = 'agent'
    elif fault == 'ref': a['ref'] = 'https://example.org/issues/221#issuecomment-123'
    elif fault == 'source': a['source_sha'] = 'b' * 40
    elif fault == 'registration': a['registration_sha256'] = '0' * 64
    elif fault == 'signature': a['sha256'] = '0' * 64
    elif fault == 'extra': a['skip_lock'] = True
    elif fault == 'body': p['criteria']['lift_bottom_m'] /= 2
    else: p['limits']['sim_s'] = float('nan')
    # Even a resealed envelope cannot approve a different source/registration.
    if fault in ('by', 'ref', 'source', 'registration'):
        a['sha256'] = auth.digest({k: v for k, v in a.items() if k != 'sha256'})
    args = args_for(tmp_path, p)
    with pytest.raises(ValueError):
        dev.load_config(args)
    assert not args.output.exists()


def test_existing_v5e_is_preserved_and_refuses_new_source(tmp_path):
    p = json.loads(dev.PREREG_V5E.read_text())
    assert dev.sha_file(dev.PREREG_V5E) == registered()['supersedes']['sha256']
    with pytest.raises(ValueError, match='scene contract/hash mismatch'):
        dev.load_config(args_for(tmp_path, p, execute=False))


@pytest.mark.parametrize('fault', [None, 'other_dirty', 'untracked', 'head', 'body', 'staged_body',
                                  'body_json_type', 'staged_json_type', 'body_seal', 'staged_seal', 'rename'])
def test_clean_source_exception_is_only_the_selected_authorization(monkeypatch, tmp_path, fault):
    p = authorize(registered())
    path = tmp_path / 'experiments/prereg.json'
    path.parent.mkdir(); path.write_text(json.dumps(p))
    committed = registered()
    staged = copy.deepcopy(committed)
    status = b' M experiments/prereg.json\0'
    head = SHA
    if fault == 'other_dirty': status += b' M harness/controller.py\0'
    elif fault == 'untracked': status += b'?? hidden.py\0'
    elif fault == 'head': head = 'b' * 40
    elif fault == 'body': committed['limits']['sim_s'] += 1
    elif fault == 'staged_body': staged['limits']['sim_s'] += 1
    elif fault == 'body_json_type': committed['runs'][0]['seed'] = float(committed['runs'][0]['seed'])
    elif fault == 'staged_json_type': staged['runs'][0]['seed'] = float(staged['runs'][0]['seed'])
    elif fault == 'body_seal': committed['registration_sha256'] = '0' * 64
    elif fault == 'staged_seal': staged['registration_sha256'] = '0' * 64
    elif fault == 'rename': status = b'R  experiments/prereg.json\0old.json\0'
    def git(cmd, **kwargs):
        args = cmd[1:]
        if args == ['rev-parse', 'HEAD']: return (head+'\n').encode()
        if args == ['show', 'HEAD:experiments/prereg.json']: return json.dumps(committed).encode()
        if args == ['show', ':experiments/prereg.json']: return json.dumps(staged).encode()
        if args == ['status', '--porcelain=v1', '-z', '--untracked-files=all']: return status
        pytest.fail(f'unexpected git command: {args}')
    monkeypatch.setattr(subprocess, 'check_output', git)
    if fault:
        with pytest.raises(ValueError): auth.verify_source(tmp_path, path, p, SHA)
    else:
        auth.verify_source(tmp_path, path, p, SHA)


def test_prereg_byte_change_after_prepare_blocks_execution(monkeypatch, tmp_path):
    from sim.workflow_manager import MANAGED_CHILD
    from scripts import agent_lock
    p = authorize(registered())
    path = tmp_path / 'registration.json'; path.write_text(json.dumps(p))
    out = tmp_path / 'prepared'
    monkeypatch.setattr(dev, 'load_config', lambda args: (copy.deepcopy(p), p['runs'][0]))
    monkeypatch.setenv(MANAGED_CHILD, '1')
    monkeypatch.setattr(dev, 'git', lambda *a: 'codex/test')
    monkeypatch.setattr(dev, 'primary_root', lambda: tmp_path)
    monkeypatch.setattr(agent_lock, 'status', lambda *a: dict(pid_alive=True, owner='codex', branch='codex/test'))
    monkeypatch.setattr(auth, 'verify_source', lambda *a: None)
    original = dev.write_json
    def write(where, value):
        original(where, value)
        if Path(where).name == 'static.json':
            path.write_text(json.dumps({**p, 'execution_authorization': None}))
    monkeypatch.setattr(dev, 'write_json', write)
    monkeypatch.setattr(dev, 'execute', lambda *a: pytest.fail('execute reached after tampering'))
    with pytest.raises(SystemExit) as error:
        dev.main(['--prereg', str(path), '--run-id', 'dev11', '--output', str(out),
                  '--execute', '--expected-source-sha', SHA, '--lock-owner', 'codex'])
    assert error.value.code == 2


@pytest.mark.parametrize('repo,ok', [('kcm0127-dotcom/ugrp', True),
                                    ('cmkang131/UGRP-Multi-Robot-Collaboration-Project', True),
                                    ('unrelated/project', False)])
def test_only_project_issue_comment_aliases_are_accepted(repo, ok):
    p = authorize(registered())
    a = p['execution_authorization']
    a['ref'] = f'https://github.com/{repo}/issues/221#issuecomment-123'
    a['sha256'] = auth.digest({k: v for k, v in a.items() if k != 'sha256'})
    if ok:
        assert auth.validate_authorization(p, execute=True, expected_source_sha=SHA) == a
    else:
        with pytest.raises(ValueError, match='issue-comment'):
            auth.validate_authorization(p, execute=True, expected_source_sha=SHA)
