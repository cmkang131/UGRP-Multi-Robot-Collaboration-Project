import pytest
from scripts.warp9_first30 import summarize


def test_first30_uses_median_and_never_admits_incomplete_work():
    with pytest.raises(ValueError,match='incomplete'):
        summarize([dict(sim_s=29,delta_sim_s=1,wall_s=1)],shared_load=False)
    samples=[dict(sim_s=i,delta_sim_s=1,wall_s=3) for i in range(1,31)]
    samples[0]['wall_s']=300
    assert summarize(samples,shared_load=False)['median_wall_per_sim']==3
    assert summarize(samples,shared_load=False)['status']=='PASS'
    for s in samples:s['wall_s']=4
    assert summarize(samples,shared_load=True)['warning'] is True
    assert summarize(samples,shared_load=True)['status']=='PASS'
    for s in samples:s['wall_s']=6.01
    assert summarize(samples,shared_load=False)['status']=='SPEED_GATE_FAIL'
