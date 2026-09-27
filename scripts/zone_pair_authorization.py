"""Late coordinator authorization, separate from the immutable registration.

Local hashes bind content. Physical admission additionally authenticates the
exact approval against a live GitHub issue comment using the pinned owner list.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

POLICY_PATH = Path(__file__).resolve().parents[1] / 'configs/zone_pair_authorization.json'


def approval_policy():
    return json.loads(POLICY_PATH.read_text())


def comment_reference(ref):
    match = re.fullmatch(
        r'https://github\.com/([^/]+/[^/]+)/issues/([1-9][0-9]*)#issuecomment-([1-9][0-9]*)',
        ref if isinstance(ref, str) else '')
    if not match or match[1].casefold() not in {r.casefold() for r in approval_policy()['repository_aliases']}:
        raise ValueError('authorization requires a project issue-comment URL')
    return match[1], int(match[2]), int(match[3])


def approval_digest(source_sha, registration_sha256, run_id):
    """Exact standalone line the owner must post; never generated as approval."""
    binding = dict(source_sha=source_sha, registration_sha256=registration_sha256, run_id=run_id)
    return (f'UGRP_ZONE_PAIR_APPROVAL source_sha={source_sha} '
            f'registration_sha256={registration_sha256} run_id={run_id} sha256={digest(binding)}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def registration_payload(prereg):
    return {k: v for k, v in prereg.items() if k not in ('execution_authorization', 'registration_sha256')}


def validate_authorization(prereg, *, execute=False, expected_source_sha=None, run_id=None):
    registration = digest(registration_payload(prereg))
    if prereg.get('registration_revision') in ('v5f', 'v5g') or 'registration_sha256' in prereg:
        if prereg.get('registration_sha256') != registration:
            raise ValueError('registration hash mismatch')
    auth = prereg.get('execution_authorization')
    if auth is None:
        if execute:
            raise ValueError('prepare-only: execution_authorization from coordinator is required')
        return None
    keys = {'by', 'ref', 'source_sha', 'registration_sha256', 'run_id', 'sha256'}
    if not isinstance(auth, dict) or set(auth) != keys:
        raise ValueError('invalid execution_authorization fields')
    if auth['by'] != 'coordinator':
        raise ValueError('authorization requires coordinator and an issue-comment URL')
    comment_reference(auth['ref'])
    if (not isinstance(auth['run_id'], str) or not re.fullmatch('[A-Za-z0-9_-]+', auth['run_id'])
            or auth['run_id'] not in [r['id'] for r in prereg['runs']]):
        raise ValueError('authorization run_id must be preregistered')
    if not isinstance(auth['source_sha'], str) or not re.fullmatch('[0-9a-f]{40}', auth['source_sha']):
        raise ValueError('authorization source_sha must be a full commit SHA')
    if auth['registration_sha256'] != registration or prereg.get('registration_sha256') != registration:
        raise ValueError('authorization registration hash mismatch')
    if auth['sha256'] != digest({k: v for k, v in auth.items() if k != 'sha256'}):
        raise ValueError('authorization hash mismatch')
    if execute and auth['source_sha'] != expected_source_sha:
        raise ValueError('authorization source_sha differs from --expected-source-sha')
    if execute and run_id is not None and auth['run_id'] != run_id:
        raise ValueError('authorization run_id differs from --run-id')
    return dict(auth)


def verify_github_authorization(prereg, source_sha, run_id, *, gh_runner=None):
    """Fail closed on lookup/errors; only a live owner comment admits execution.

    gh_runner is a subprocess.run-compatible seam for offline unit tests, never
    a CLI option. The policy is committed and covered by verify_source().
    """
    auth = validate_authorization(prereg, execute=True, expected_source_sha=source_sha, run_id=run_id)
    policy = approval_policy()
    _, issue_id, comment_id = comment_reference(auth['ref'])
    endpoint = f'repos/{policy["repository"]}/issues/comments/{comment_id}'
    try:
        result = (gh_runner or subprocess.run)(
            ['gh', 'api', '--hostname', 'github.com', endpoint],
            check=True, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise ValueError('GitHub approval lookup failed')
        comment = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValueError('GitHub approval lookup failed; execution refused') from exc
    if not isinstance(comment, dict) or type(comment.get('id')) is not int or comment['id'] != comment_id:
        raise ValueError('GitHub approval comment id mismatch')
    # Validate the API and web identities, including redirects/renamed-repo aliases.
    _, returned_issue, returned_id = comment_reference(comment.get('html_url'))
    aliases = policy['repository_aliases']
    if (returned_issue != issue_id or returned_id != comment_id
            or comment.get('issue_url') not in [f'https://api.github.com/repos/{r}/issues/{issue_id}' for r in aliases]
            or comment.get('url') not in [f'https://api.github.com/repos/{r}/issues/comments/{comment_id}' for r in aliases]):
        raise ValueError('GitHub approval repository/issue/comment mismatch')
    user = comment.get('user')
    if (not isinstance(user, dict) or user.get('type') != 'User'
            or not isinstance(user.get('login'), str)
            or user['login'].casefold() not in {a.casefold() for a in policy['allowed_authors']}):
        raise ValueError('GitHub approval author is not an allowed repository owner')
    body, updated = comment.get('body'), comment.get('updated_at')
    expected = approval_digest(source_sha, prereg['registration_sha256'], run_id)
    if not isinstance(body, str) or expected not in body.splitlines():
        raise ValueError('GitHub approval digest mismatch')
    if not isinstance(updated, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', updated):
        raise ValueError('GitHub approval updated_at missing or invalid')
    return {'comment_id': comment_id, 'author': user['login'], 'updated_at': updated,
            'body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
            'approval_digest': expected, 'repository': policy['repository'],
            'ref': comment['html_url'], 'policy_sha256': hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()}


def verify_source(root, prereg_path, prereg, source_sha):
    """Allow only the authorization envelope to differ from clean committed source.

    Check both index and worktree and include untracked files. Restrict the
    exception to the selected tracked prereg and compare its committed payload.
    """
    root = Path(root).resolve()
    path = Path(prereg_path).resolve()
    if not path.is_relative_to(root) or Path(prereg_path).is_symlink():
        raise ValueError('authorized prereg must be a tracked file in the execution checkout')
    rel = path.relative_to(root).as_posix()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root)
    if git('rev-parse', 'HEAD').decode().strip() != source_sha:
        raise ValueError('execution source must match pinned HEAD')
    committed = json.loads(git('show', f'HEAD:{rel}'))
    committed_digest = digest(registration_payload(committed))
    if (committed_digest != digest(registration_payload(prereg))
            or committed.get('registration_sha256') != prereg.get('registration_sha256')):
        raise ValueError('registered content differs from committed source')
    validate_authorization(prereg, execute=True, expected_source_sha=source_sha)
    status = git('status', '--porcelain=v1', '-z', '--untracked-files=all').split(b'\0')
    allowed = rel.encode()
    if any(row and not (row[:2] in (b' M', b'M ', b'MM') and row[3:] == allowed) for row in status):
        raise ValueError('execution source must be clean except the selected authorization envelope')
    staged = json.loads(git('show', f':{rel}'))
    if (digest(registration_payload(staged)) != committed_digest
            or staged.get('registration_sha256') != committed.get('registration_sha256')):
        raise ValueError('staged registration differs from committed source')
