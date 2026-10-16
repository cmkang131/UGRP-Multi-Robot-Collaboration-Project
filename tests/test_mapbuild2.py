import numpy as np
from scripts.mapbuild2_capture import stimulus


def test_issued_stimulus_preserves_calibrated_pulse_durations():
    tape=np.asarray([stimulus(i/100) for i in range(400)])
    active=np.flatnonzero(np.any(tape!=0,axis=1))
    assert active.tolist()==list(range(100,110))+list(range(200,206))+list(range(300,310))
    assert tape[100].tolist()==[.35]*4
    assert tape[200].tolist()==[-.35,.35,.35,-.35]
    assert tape[300].tolist()==[-.35,.35,-.35,.35]
    assert not np.any(tape[310:])
