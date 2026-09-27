"""Late coordinator authorization, separate from the immutable registration.

Hashes provide integrity/binding, not authentication of the comment author.
The coordinator must write the actual issue-comment reference; no network call
or approval is manufactured by the runner.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def registration_payload(prereg):
    return {k: v for k, v in prereg.items() if k not in ('execution_authorization', 'registration_sha256')}


def validate_authorization(prereg, *, execute=False, expected_source_sha=None):
    registration = digest(registration_payload(prereg))
    if prereg.get('registration_revision') == 'v5f' or 'registration_sha256' in prereg:
        if prereg.get('registration_sha256') != registration:
            raise ValueError('registration hash mismatch')
    auth = prereg.get('execution_authorization')
    if auth is None:
        if execute:
            raise ValueError('prepare-only: execution_authorization from coordinator is required')
        return None
    keys = {'by', 'ref', 'source_sha', 'registration_sha256', 'sha256'}
    if not isinstance(auth, dict) or set(auth) != keys:
        raise ValueError('invalid execution_authorization fields')
    if auth['by'] != 'coordinator' or not isinstance(auth['ref'], str) or not re.fullmatch(
            r'https://github\.com/(?:kcm0127-dotcom/ugrp|cmkang131/UGRP-Multi-Robot-Collaboration-Project)/issues/[1-9][0-9]*#issuecomment-[1-9][0-9]*', auth['ref']):
        raise ValueError('authorization requires coordinator and an issue-comment URL')
    if not isinstance(auth['source_sha'], str) or not re.fullmatch('[0-9a-f]{40}', auth['source_sha']):
        raise ValueError('authorization source_sha must be a full commit SHA')
    if auth['registration_sha256'] != registration or prereg.get('registration_sha256') != registration:
        raise ValueError('authorization registration hash mismatch')
    if auth['sha256'] != digest({k: v for k, v in auth.items() if k != 'sha256'}):
        raise ValueError('authorization hash mismatch')
    if execute and auth['source_sha'] != expected_source_sha:
        raise ValueError('authorization source_sha differs from --expected-source-sha')
    return dict(auth)


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
