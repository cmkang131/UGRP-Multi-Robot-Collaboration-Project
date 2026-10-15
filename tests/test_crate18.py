"""Quantized pre-grasp adapter and geometric acceptance; no simulation."""
import math
from itertools import product
import pytest
from sim.crate_settle_v18 import MODE, MIN_DURATION, DELTA, INNER18, pulse, settlers
from sim.crate_alignment_v14 import grasp_valid
from scripts.run_crate_teacher import make_grasp_teacher
from scripts.zone_teacher import FOLDED
from test_crate15 import empty, hold, teacher

def make(mode=MODE):
    t=teacher('crate_motion_v17')
    t.crate18=mode;t._reset_alignment()
    return t

@pytest.mark.parametrize('axis',range(3))
@pytest.mark.parametrize('error',[-.4,-.01,-.00001,.00001,.01,.4])
def test_floor_and_single_axis(axis,error):
    c=pulse(hold(),axis,error)
    assert all(MIN_DURATION[axis]<=v<=.1 for v in c['duration_s'])
    assert all(abs(w)==.35 for w in c['wheels'])

@pytest.mark.parametrize('dx,dy,da',list(product(*[(-2*d,0,2*d) for d in DELTA])))
def test_quantum_reversal_envelope_preserves_exact_grasp_geometry(dx,dy,da):
    x=.1974+dx;y=dy;a=-da;c=math.cos(a);s=math.sin(a)
    pose=(-c*x+s*y,-s*x-c*y,a)
    w={'beam':{'ends':{'teal':(0,0,.02396)},'pose':(0,0,0)},'visibility':{'r1':{'visible_probes':15}}}
    assert grasp_valid(w,'r1','teal',pose)

def test_off_retains_crate17_command():
    a=teacher('crate_motion_v17');b=make('off')
    for axis,error in product(range(3),(-.2,-.01,.01,.2)):
        errors=[.01,.01,.2];errors[axis]=error
        drive=[0.,0.,0.];drive[axis]=.02
        for t in (a,b):t.phase='align';t.crate15_errors=errors
        assert a._continuous(1.,*drive)==b._continuous(1.,*drive)

def test_latched_settle_survives_fresh_stability_but_missing_view_resets():
    t=make();w=empty();t.phase='align';t.approach_plan_valid=True;t.folded_ready=True
    errors=(0.,0.,.006)
    assert t._alignment_settled(w,errors)
    t.stable_since=1.;t._reset_alignment()
    assert all(p.band is not None for p in t.settlers18)
    w['beam']=None;w['visibility']['r1']['visible_probes']=0
    t._observe_stable(w,1.1)
    assert all(p.band is None for p in t.settlers18)

def test_three_reversals_and_geometry_guard():
    t=make();w=empty();t.phase='align';t.approach_plan_valid=True;t.folded_ready=True
    # Only policy sees these yaw observations; the fixed visible world is valid.
    for e in (.01,-.01,.01):
        assert not t._alignment_settled(w,(0.,0.,e))
        t.settlers18[2].issued(e)
    assert t._alignment_settled(w,(0.,0.,-.01))
    assert t.settle18_states[2]['reason']=='consecutive_reversals'
    w['beam']['ends']['teal'][2]=-.5
    assert not t._alignment_settled(w,(0.,0.,0.))

def test_rejected_pulse_does_not_count_as_issued():
    t=make();w=empty();t.phase='align';t.crate15_errors=(0.,0.,.2)
    t._step=lambda *a,**k:(t._continuous(1.,0.,0.,.1),False)
    t._check_navigation_pulse=lambda *a,**k:t._hold(1.)
    value,_=t.step(w,1.)
    assert not any(value['wheels']) and sum(p.pulses for p in t.settlers18)==0
    t._check_navigation_pulse=lambda w,c,now:c
    value,_=t.step(w,1.1)
    assert any(value['wheels']) and t.settlers18[2].pulses==1

def test_toggle_requires_crate17():
    with pytest.raises(ValueError,match='crate17'):
        make_grasp_teacher('r1','teal',FOLDED,crate18=MODE)


def test_legacy_selection_reversals_do_not_preempt_issued_pulse_policy():
    t=make();t.settle18_states=[dict(settled=False) for _ in range(3)]
    t.align_sign=[1,-1,1];t.align_flips=[3,3,3]
    t._resume_alignment((.01,.01,-.01))
    assert t.align_sign==t.align_flips==[0,0,0]
