import math
import numpy as np
import pytest
from harness.mapbuild_own_grid import OwnGrid, AugmentedField, OPTION, LIMIT, MIN_HITS


def scan():
    return dict(camera=[0.,0.], columns=[dict(status='hit',range_m=1.,bearing_rad=0.)]*96+
                [dict(status='unknown',range_m=None,bearing_rad=1.)])


def test_distinct_frames_hits_priority_missing_unknown_and_free_rays():
    g=OwnGrid();g.insert(0,[0,0,0],scan())
    assert g.cells[(20,0)][1:] == [1,0]  # repeated beams vote only once
    assert g.cells[(10,0)][1:] == [0,1]
    assert (0,20) not in g.cells
    assert not len(g.stable_points())
    for t in range(1,MIN_HITS):g.insert(t,[0,0,0],scan())
    assert len(g.stable_points())==1 and g.cells[(20,0)][0]==LIMIT
    with pytest.raises(ValueError,match='NONCAUSAL'):g.insert(0,[0,0,0],scan())


def test_field_off_exact_and_reference_precedes_current_scan():
    class Static:
        free=np.array([[0,0]])
        def distances(self,p):return np.full(np.asarray(p).shape[:-1],2.)
    g=OwnGrid();off=AugmentedField(Static(),g);on=AugmentedField(Static(),g,option=OPTION)
    for t in range(MIN_HITS):
        before=on.distances([[1.025,.025]])[0]
        assert before==2.  # current hit has not been inserted yet
        g.insert(t,[0,0,0],scan())
    assert on.distances([[1.025,.025]])[0]==0.
    assert off.distances([[1.025,.025]])[0]==2.
    assert on.last_reference_t==MIN_HITS-1


def test_insertion_uses_estimated_pose_and_no_pose_leaves_unknown():
    g=OwnGrid();g.insert(0,None,scan());assert not g.cells
    g.insert(1,[2.,1.,math.pi/2],scan())
    assert (40,40) in g.cells and g.cells[(40,40)][1]==1
