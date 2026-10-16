import pytest
from harness.grasp_act_skill import SkillSession, task

HANDOFF = {'source': 'own_rgb_and_issued_commands', 'age_s': .1, 'distance_m': .5, 'map_arrived': True}


def test_no_free_text_or_truth_handoff():
    with pytest.raises(ValueError): task({'object_kind':'long_beam','skill': 'go to xyz', 'end': 'teal'})
    with pytest.raises(ValueError): task({'object_kind':'long_beam','skill': 'grasp', 'end': 'teal', 'x': 1.})
    with pytest.raises(ValueError): SkillSession().start({'object_kind':'long_beam','skill':'grasp','end':'blue'}, 0, handoff={**HANDOFF,'source':'truth'})
    with pytest.raises(ValueError): SkillSession().start({'object_kind':'long_beam','skill':'grasp','end':'blue'}, 0, handoff={**HANDOFF,'distance_m':1.5})


def test_stale_chunk_cannot_execute_after_end_reassignment_or_wait():
    s=SkillSession(); old=s.start({'object_kind':'long_beam','skill':'grasp','end':'teal'},0,handoff=HANDOFF)
    new=s.start({'object_kind':'long_beam','skill':'grasp','end':'blue'},.1,handoff=HANDOFF)
    assert not s.accept_chunk([{'done':False}],revision=old,now=.1)
    assert s.accept_chunk([{'done':False}],revision=new,now=.1)
    assert s.next(.1,interruption='wait')['kind']=='stop'
    assert not s.accept_chunk([{'done':False}],revision=new,now=.1)


def test_done_and_timeout_are_not_physical_success():
    s=SkillSession(); rev=s.start({'object_kind':'long_beam','skill':'grasp','end':'teal'},0,handoff=HANDOFF,timeout_s=2)
    s.accept_chunk([{'done':True}],revision=rev,now=0)
    assert s.next(0)['reason']=='verify'
    assert s.result=='unknown'
    assert s.verify(own_camera_result='unknown')=='unknown'
    assert [s.verify(own_camera_result='complete') for _ in range(3)]==['unknown','unknown','complete']
    s=SkillSession();s.start({'object_kind':'long_beam','skill':'grasp','end':'teal'},0,handoff=HANDOFF,timeout_s=2)
    assert s.next(2)['reason']=='timeout' and s.result=='failure'
