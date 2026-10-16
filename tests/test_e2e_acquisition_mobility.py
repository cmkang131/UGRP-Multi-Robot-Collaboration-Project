import copy
from types import SimpleNamespace
import numpy as np
import pytest
from harness import e2e_acquisition_mobility as m,e2e_pregrasp_acquire as acq
from tests.test_e2e_align_progress import setup_transport


def setup(option):
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.acquisition_mobility=option
    r=tr.robots['r2'];r.last_beam=copy.deepcopy(r.beam);r.beam=None;r.nav_command={'kind':'hold'}
    n=SimpleNamespace(blacklist=[1],visited=[2],finished=True,reset_action=lambda:None,event=lambda *a:None)
    r.goal.explorer.navigator=n;r.goal.explorer.grid=object()
    state={'acquisition':dict(phase='explore',started=30.,yaw=0.,cycles=2,view=4)}
    return tr,r,n,state


def test_reproduced_exhausted_explorer_hold_is_resumed_through_actual_acquire():
    old,r,n,state=setup('off');acq.acquire(old,'r2',30.,state,None)
    assert n.finished and not old.queue
    tr,r,n,state=setup('resume_v1');grid=r.goal.explorer.grid;pose=r.goal.explorer.local_pose.copy()
    fine,actions=acq.acquire(tr,'r2',30.,state,None)
    assert not fine and not n.finished and not n.blacklist and not n.visited and tr.queue
    assert r.goal.explorer.grid is grid and np.array_equal(r.goal.explorer.local_pose,pose)
    assert r.beam is None and 'station' not in state
    r.nav_command=dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
    assert acq.acquire(tr,'r2',32.,state,None)==(False,[r.nav_command])
    # Rotation alone never resets the position-only window.
    r.goal.explorer.local_pose[2]+=2.
    assert acq.acquire(tr,'r2',40.1,state,None)==(False,[{'kind':'hold'}])
    assert state['acquisition']['phase']=='turn'


def test_old_memory_is_only_a_viewpoint_and_has_no_direct_line_fallback(monkeypatch):
    tr,r,n,state=setup('remembered_view_v1');r.goal.explorer.local_pose=np.zeros(3)
    r.goal.explorer.map_to_odom=np.zeros(3);r.goal.explorer.latest={}
    r.last_beam={'pose_own_m':[3.,0.,0.],'rgb':{'t_sim':2.,'frame_id':1}}
    r.carrier_approach={};targets=[]
    monkeypatch.setattr(m,'from_observed_grid',lambda *a:object())
    from harness import e2e_beam_avoidance
    monkeypatch.setattr(e2e_beam_avoidance,'add',lambda costmap,*a:costmap)
    def plan(costmap,pose,target):targets.append(target);return [[0.,0.],target]
    n.plan_to=plan
    action=m.remembered_command(tr,'r2',600.,state['acquisition'])
    assert action['forward']>0 and np.allclose(targets[-1],[2.,0.])
    assert r.carrier_approach['hypothesis_age_s']==598. and r.beam is None and 'station' not in state
    n.plan_to=lambda *a:[]
    assert m.remembered_command(tr,'r2',600.,state['acquisition']) is None


@pytest.mark.parametrize('option',m.OPTIONS)
def test_default_off_preserves_bundle_and_requires_exact_parent(option):
    b={'execution_bundle_id':'e2e18-v246','e2e_options':{}}
    before=copy.deepcopy(b);assert m.compose(b,'off')==() and b==before
    m.compose(b,option);assert b['execution_bundle_id']==f'e2e18-v{m.VERSIONS[option]}'
    with pytest.raises(ValueError):m.compose(b,option)
