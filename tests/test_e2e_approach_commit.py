import numpy as np
import pytest
from harness import e2e_approach_commit as m
from harness.e2e_carrier_approach import advance
from tests.test_e2e_align_progress import setup_transport


def setup(mode):
    tr=setup_transport(dev_light=True,pregrasp_recovery='bounded_search_v1')
    tr.approach_commit=mode;tr.stale_station='expire12_v1'
    r=tr.robots['r1'];advance(tr,'r1',2.);tr.queue.clear();r.beam=None
    return tr,r


@pytest.mark.parametrize('mode,until',[(o,m.AGE[o]) for o in m.OPTIONS])
def test_actual_approach_moves_on_own_hypothesis_but_never_promotes_stale_rgb(mode,until):
    tr,r=setup(mode);r.last_obs['frame_id']=11
    fine,actions=advance(tr,'r1',15.)
    assert not fine and actions[-1]['kind']=='mecanum' and r.beam is None
    assert 'station' in tr.approach['r1'] and not tr.queue
    assert any(e['event']=='would_reacquire_during_staging' for e in tr.events)
    r.last_obs['frame_id']=12
    fine,actions=advance(tr,'r1',2.+until+.1)
    assert not fine and 'station' not in tr.approach['r1'] and r.beam is None


def test_default_old_timeout_and_staging_boundary_keep_fresh_fine_gate():
    tr,r=setup('off');r.last_obs['frame_id']=11
    fine,actions=advance(tr,'r1',5.)
    assert not fine and actions==[{'kind':'hold'}] and tr.queue
    tr,r=setup('memory60_v1');state=tr.approach['r1']
    r.goal.explorer.local_pose=state['station'].copy();r.last_obs['frame_id']=11
    fine,actions=advance(tr,'r1',5.)
    assert not fine and actions==[{'kind':'hold'}] and r.carrier_approach['status']=='reacquire_own_beam'


def test_view_uses_visible_band_range_and_hysteresis_without_changing_assigned_grasp():
    tr=setup_transport();tr.approach_commit='memory60_view_v1';r=tr.robots['r1'];state={}
    r.beam['grip_base_m']=[.32,0.]
    assert m.view(tr,'r1',state,True,1.1)[0]=='p45'
    r.beam['grip_base_m']=[.35,0.]
    assert m.view(tr,'r1',state,True,1.1)[0]=='p45'
    r.beam=None
    assert m.view(tr,'r1',state,False,1.1)[0]=='p45' and m.gaze_target(tr,'r1',False,[5.,5.]) is None
    assert 'station' not in state and 'grip' not in state
