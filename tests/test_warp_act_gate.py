import hashlib
import json
import pytest
from scripts.warp_act_gate import admit


def test_gate_requires_exact_source_artifacts_rejection_table_and_unique_cases(tmp_path):
    plan=tmp_path/'plan';plan.write_text('{}')
    refs=tmp_path/'refs';refs.write_text('{}')
    table=tmp_path/'rejection_table';table.write_text('{}')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    q=dict(status='APPROVED_PINNED',approved=True,source_sha='pinned',
        review_detail='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)',plan_sha256=digest(plan),
        references_sha256=digest(refs),rejection_table=str(table),rejection_table_sha256=digest(table),
        approved_episode_indices=list(range(40)),required_success_rate=.95,minimum_independent_episodes=40)
    path=tmp_path/'queue.json';path.write_text(json.dumps(q))
    args=dict(source_sha='pinned',plan=plan,indices=[4,0],references=refs)
    assert admit(path,**args)['status']=='APPROVED_PINNED'
    with pytest.raises(ValueError,match='source SHA'):admit(path,**{**args,'source_sha':'other'})
    with pytest.raises(ValueError,match='distinct'):admit(path,**{**args,'indices':[4,4]})
    table.unlink()
    with pytest.raises(ValueError,match='rejection_table missing'):admit(path,**args)
