"""Coordinator authorization integrity/admission; no physical execute is called."""
import copy
import json
import subprocess
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_zone_pair_dev as dev
from scripts import zone_pair_authorization as auth

SHA = 'a' * 40


@pytest.fixture(autouse=True)
def no_real_gh(monkeypatch):
    original = subprocess.run
    def run(cmd, *args, **kwargs):
        if cmd[0] == 'gh':
            pytest.fail('tests must inject gh; network forbidden')
        return original(cmd, *args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)


def registered():
    # dev13/dev14 executed under the committed v5h; after the v69 main merge
    # it is historical (see test_committed_v5h_is_historical_after_execution).
    # Admission logic is exercised on the synthetic current-source copy.
    from tests.zone_pair_current_source import current_source_v5h
    return current_source_v5h()


def test_committed_v5h_is_historical_after_execution(tmp_path):
    from tests.zone_pair_current_source import assert_executed_v5h_is_historical
    assert_executed_v5h_is_historical(tmp_path, 'dev13')
    assert_executed_v5h_is_historical(tmp_path, 'dev14')


def authorize(p):
    # Synthetic integrity fixture only; not an execution authorization artifact.
    receipt = {'by': 'coordinator', 'ref': 'https://github.com/kcm0127-dotcom/ugrp/issues/221#issuecomment-123',
               'source_sha': SHA, 'registration_sha256': p['registration_sha256'], 'run_id': 'dev13'}
    p['execution_authorization'] = {**receipt, 'sha256': auth.digest(receipt)}
    return p


def args_for(tmp_path, p, *, execute=True):
    path = tmp_path / 'registration.json'
    path.write_text(json.dumps(p))
    args = dev.parser().parse_args(['--prereg', str(path), '--run-id', 'dev13', '--output',
                                  str(dev.primary_root() / 'outputs/not-created-authorization-test'),
                                  '--expected-source-sha', SHA, '--lock-owner', 'codex'])
    args.execute = execute
    return args


def test_absent_authorization_prepares_and_execute_is_refused(tmp_path):
    p = registered()
    args = args_for(tmp_path, p, execute=False)
    assert dev.load_config(args)[1]['id'] == 'dev13'
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
    assert dev.load_config(args)[1]['seed'] == 909
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


def test_existing_v5g_is_preserved_and_refuses_new_source(tmp_path):
    p = json.loads(dev.PREREG_V5G.read_text())
    assert dev.sha_file(dev.PREREG_V5G) == registered()['supersedes']['sha256']
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
        dev.main(['--prereg', str(path), '--run-id', 'dev13', '--output', str(out),
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


def github_comment(p):
    repository = 'cmkang131/UGRP-Multi-Robot-Collaboration-Project'
    return dict(id=123, user=dict(login='kcm0127-dotcom', type='User'),
                url=f'https://api.github.com/repos/{repository}/issues/comments/123',
                issue_url=f'https://api.github.com/repos/{repository}/issues/221',
                html_url=f'https://github.com/{repository}/issues/221#issuecomment-123',
                updated_at='2026-09-28T01:02:03Z',
                body=auth.approval_digest(SHA, p['registration_sha256'], 'dev13'))


def gh_result(comment, calls):
    def fake(cmd, **kwargs):
        calls.append(cmd)
        assert cmd == ['gh', 'api', '--hostname', 'github.com',
                       'repos/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/comments/123']
        assert kwargs == dict(check=True, capture_output=True, text=True, timeout=30)
        return SimpleNamespace(returncode=0, stdout=json.dumps(comment))
    return fake


@pytest.mark.parametrize('author', ['changmin__', 'kcm0127-dotcom', 'cmkang131'])
def test_live_owner_approval_receipt_binds_exact_run(author):
    p = authorize(registered()); c = github_comment(p); c['user']['login'] = author
    c['body'] = '이 조건으로 실행 승인합니다.\n' + c['body'] + '\n'
    calls = []
    receipt = auth.verify_github_authorization(p, SHA, 'dev13', gh_runner=gh_result(c, calls))
    assert len(calls) == 1
    assert receipt['comment_id'] == 123 and receipt['author'] == author
    assert receipt['updated_at'] == c['updated_at']
    assert receipt['body_sha256'] == hashlib.sha256(c['body'].encode()).hexdigest()
    assert receipt['approval_digest'] == c['body'].splitlines()[1]


@pytest.mark.parametrize('fault', ['forged', 'other_author', 'bot', 'digest', 'source', 'registration',
                                  'run_id', 'substring', 'missing_body', 'repository', 'web_repository',
                                  'api_repository', 'issue', 'comment_id', 'updated_at', 'resealed_ref'])
def test_self_resealed_envelope_cannot_replace_live_approval(fault):
    p = authorize(registered()); c = github_comment(p)
    if fault == 'forged': c['body'] = 'No authorization has been given.'
    elif fault == 'other_author': c['user']['login'] = 'attacker'
    elif fault == 'bot': c['user']['type'] = 'Bot'
    elif fault == 'digest': c['body'] = c['body'][:-1] + ('0' if c['body'][-1] != '0' else '1')
    elif fault == 'source': c['body'] = auth.approval_digest('b'*40, p['registration_sha256'], 'dev13')
    elif fault == 'registration': c['body'] = auth.approval_digest(SHA, '0'*64, 'dev13')
    elif fault == 'run_id': c['body'] = auth.approval_digest(SHA, p['registration_sha256'], 'dev14')
    elif fault == 'substring': c['body'] = 'not approved: ' + c['body']
    elif fault == 'missing_body': c['body'] = None
    elif fault == 'repository': c['issue_url'] = 'https://api.github.com/repos/attacker/repo/issues/221'
    elif fault == 'web_repository': c['html_url'] = 'https://github.com/attacker/repo/issues/221#issuecomment-123'
    elif fault == 'api_repository': c['url'] = 'https://api.github.com/repos/attacker/repo/issues/comments/123'
    elif fault == 'issue': c['issue_url'] = c['issue_url'].replace('/221', '/222')
    elif fault == 'comment_id': c['id'] = 999
    elif fault == 'updated_at': c.pop('updated_at')
    elif fault == 'resealed_ref':
        a = p['execution_authorization']
        a['ref'] = a['ref'].replace('/221#', '/222#')
        a['sha256'] = auth.digest({k: v for k, v in a.items() if k != 'sha256'})
    # Local hashes all pass, including the forged/resealed comment reference.
    assert auth.validate_authorization(p, execute=True, expected_source_sha=SHA, run_id='dev13')
    calls = []
    with pytest.raises(ValueError):
        auth.verify_github_authorization(p, SHA, 'dev13', gh_runner=gh_result(c, calls))
    assert len(calls) == 1


@pytest.mark.parametrize('fault', ['deleted', 'offline', 'timeout', 'no_gh', 'malformed', 'nonzero', 'null'])
def test_lookup_errors_are_fail_closed(fault):
    def fake(cmd, **kwargs):
        if fault == 'deleted': raise subprocess.CalledProcessError(1, cmd, stderr='HTTP 404')
        if fault == 'offline': raise subprocess.CalledProcessError(1, cmd, stderr='offline')
        if fault == 'timeout': raise subprocess.TimeoutExpired(cmd, 30)
        if fault == 'no_gh': raise FileNotFoundError('gh')
        return SimpleNamespace(returncode=1 if fault == 'nonzero' else 0,
                               stdout='null' if fault == 'null' else 'not JSON')
    with pytest.raises(ValueError, match='GitHub approval'):
        auth.verify_github_authorization(authorize(registered()), SHA, 'dev13', gh_runner=fake)


def test_approval_for_one_run_does_not_authorize_the_other(tmp_path):
    p = authorize(registered()); args = args_for(tmp_path, p)
    args.run_id = 'dev14'
    with pytest.raises(ValueError, match='run_id differs'):
        dev.load_config(args)


@pytest.mark.parametrize('fault', [None, 'forged', 'deleted', 'offline', 'tamper_during_lookup'])
def test_execute_fetches_live_comment_and_persists_receipt_before_admission(monkeypatch, tmp_path, fault):
    from sim.workflow_manager import MANAGED_CHILD
    from scripts import agent_lock
    p = authorize(registered()); c = github_comment(p)
    path = tmp_path / 'registration.json'; path.write_text(json.dumps(p))
    out = tmp_path / 'prepared'
    monkeypatch.setattr(dev, 'load_config', lambda args: (copy.deepcopy(p), p['runs'][0]))
    monkeypatch.setenv(MANAGED_CHILD, '1')
    monkeypatch.setattr(dev, 'git', lambda *a: 'codex/test')
    monkeypatch.setattr(dev, 'primary_root', lambda: tmp_path)
    monkeypatch.setattr(agent_lock, 'status', lambda *a: dict(pid_alive=True, owner='codex', branch='codex/test'))
    checks = []
    monkeypatch.setattr(auth, 'verify_source', lambda *a: checks.append('source'))
    calls, admitted = [], []
    original = subprocess.run
    fake = gh_result(c, calls)
    def run(cmd, *args, **kwargs):
        if cmd[0] != 'gh': return original(cmd, *args, **kwargs)
        if fault in ('deleted', 'offline'): raise subprocess.CalledProcessError(1, cmd)
        if fault == 'forged': c['body'] = 'not approved'
        if fault == 'tamper_during_lookup': path.write_text(json.dumps({**p, 'execution_authorization': None}))
        return fake(cmd, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    def execute(args, prereg, case, manifest):
        saved = json.loads((out / 'manifest.json').read_text())
        assert saved['github_authorization'] == manifest['github_authorization']
        assert saved['github_authorization']['body_sha256'] == hashlib.sha256(c['body'].encode()).hexdigest()
        assert saved['github_authorization']['comment_id'] == 123
        assert len(checks) == 3 and len(calls) == 1
        admitted.append(True)
        return 0
    monkeypatch.setattr(dev, 'execute', execute)
    argv = ['--prereg', str(path), '--run-id', 'dev13', '--output', str(out),
            '--execute', '--expected-source-sha', SHA, '--lock-owner', 'codex']
    if fault:
        with pytest.raises(SystemExit) as error: dev.main(argv)
        assert error.value.code == 2 and not admitted
        assert json.loads((out / 'manifest.json').read_text())['github_authorization'] is None
    else:
        assert dev.main(argv) == 0 and admitted == [True]
