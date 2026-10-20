"""Pinned MJWarp gate admission, separate from training permission."""
import hashlib
import json
from pathlib import Path


def admit(path, *, source_sha, plan, indices, references):
    path=Path(path);q=json.loads(path.read_text())
    if q.get('status')!='APPROVED_PINNED' or q.get('approved') is not True:
        raise ValueError('teacher gate queue is not APPROVED_PINNED')
    if q.get('review_detail')!='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)':
        raise ValueError('missing explicit user run-first admission record')
    if q.get('source_sha')!=source_sha:
        raise ValueError('gate source SHA mismatch')
    for field,artifact in [('plan_sha256',plan),('references_sha256',references)]:
        if artifact is None or hashlib.sha256(Path(artifact).read_bytes()).hexdigest()!=q.get(field):
            raise ValueError('gate artifact mismatch: '+field)
    rejection=Path(q.get('rejection_table',''))
    if not rejection.is_file():raise ValueError('gate rejection_table missing')
    if hashlib.sha256(rejection.read_bytes()).hexdigest()!=q.get('rejection_table_sha256'):
        raise ValueError('gate rejection_table hash mismatch')
    if len(set(indices))!=len(indices) or not set(indices)<=set(q['approved_episode_indices']):
        raise ValueError('gate worlds must be distinct approved cases')
    return dict(queue=str(path),queue_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        status=q['status'],review_detail=q['review_detail'],rejection_table=str(rejection),
        required_success_rate=q['required_success_rate'],minimum_independent_episodes=q['minimum_independent_episodes'])
