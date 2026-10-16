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


def test_standard_orb_diagnostic_reports_real_pair_counts_and_unknowns():
    from scripts.mapbuild2_analyze import pipeline
    from harness.active_camera import SEARCH
    rng=np.random.default_rng(123)
    image=rng.integers(0,256,(480,640,3),dtype=np.uint8)
    import cv2
    after=cv2.warpAffine(image,np.float32([[1,0,2],[0,1,1]]),(640,480))
    frames=[dict(frame_id=i,servo=SEARCH) for i in range(2)]
    images={0:{'jpg':image},1:{'jpg':after}}
    rows=pipeline(images,frames)
    assert len(rows)==1 and rows[0]['ratio_n']>=5
    assert rows[0]['features_a']<=500
    frames[0]['servo']={**SEARCH,1:1500}
    assert pipeline(images,frames,masked=True)[0]['reason']=='unqualified_camera'
