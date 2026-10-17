"""Future supervision must stop at completion, time gaps and skill boundaries."""
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from act18_policy import extend_targets
from act18_diagnose import confusion
from act18_evaluate import allowed_seeds


def test_extended_chunk_never_fabricates_a_future_across_completion_or_gap():
    actions=np.arange(5*14,dtype=np.float32).reshape(5,14)
    actions[:,-1]=[0,1,0,0,0]
    rows=[dict(sample_id='same:'+str(i),skill='grasp' if i<3 else 'release',t=t)
          for i,t in enumerate([0,.1,.2,.3,.5])]
    values,pad=extend_targets(actions,rows,100)
    assert np.array_equal(values[0,:2],actions[:2])
    assert pad[0,2:].all() and pad[1,1:].all()
    assert pad[2,1:].all()  # skill change
    assert pad[3,1:].all()  # missing .4s observation
    assert np.array_equal(values[pad],np.zeros_like(values[pad]))


def test_raw_wrong_sign_and_projection_stop_are_separate_counts():
    counts=confusion([.35,.35,0,-.35],[-.02,.2,.1,.3],[0,.31,0,.31])
    assert counts['teacher_moving']==3
    assert counts['projected_stop_while_teacher_moves']==1
    assert counts['raw_opposite_sign_while_teacher_moves']==2
    assert counts['projected_opposite_sign_while_teacher_moves']==1


def test_val_and_final_cannot_run_on_an_unverified_fit_claim():
    protocol=dict(train4_seeds=[1,2,3,4],validation8_seeds=list(range(20,28)),final_seeds=list(range(100,140)))
    assert allowed_seeds(protocol,'train',{},'model')=={1,2,3,4}
    with pytest.raises(ValueError,match='TRAIN4'):
        allowed_seeds(protocol,'validation',{},'model')
    with pytest.raises(ValueError,match='receipt'):
        allowed_seeds(protocol,'validation',dict(TRAIN_n=4,TRAIN_N=4,checkpoint_sha256='model',TRAIN_raw_recount_verified=True),'model')
    with pytest.raises(ValueError,match='frozen selection'):
        allowed_seeds(protocol,'final',{},'model')
