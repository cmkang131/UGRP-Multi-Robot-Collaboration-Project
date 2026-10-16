from types import SimpleNamespace
import dataclasses
import numpy as np
import pytest
from harness.e2e_arm_clearance import Clearance,evidence,PARAMS,OPTIONS,VERSIONS,compose
from harness.range_provider import RangeReport,source_label
from harness.owncam_pair_beam_v2 import pose_of
from harness.e2e_pregrasp_acquire import busy
from tests.test_e2e_align_progress import setup_transport


def setup(option='range_v1',distance=.08):
    tr=setup_transport(align_queues='per_robot_v1');tr.state='align'
    tr.arm_clearance=Clearance(option)
    for r in tr.robots.values():
        r.now=0.;r.wall_segments=[]
        r.range_provider=SimpleNamespace(report=lambda now:RangeReport(now,0.,True,distance,.002,source=source_label(),status='ok'))
    return tr


def test_actual_pose_queue_defers_arm_and_replaces_navigation_with_backup():
    tr=setup();tr._poses('r1',0.,[(pose_of('p45'),.3,.6)])
    assert not tr.queue and busy(tr,'r1',0.)
    batch=[('r1',dict(kind='arm',servo_id=4,pulse=1800)),('r2',dict(kind='hold'))]
    out=tr.arm_clearance.filter(tr,.05,batch)
    assert not any(r=='r1' and a['kind']=='arm' for r,a in out)
    assert next(a for r,a in out if r=='r1')['forward']<0
    assert ('r2',dict(kind='hold')) in out


def test_recovery_rechecks_range_and_reschedules_whole_pose_after_own_motion():
    tr=setup();r=tr.robots['r1'];tr._poses('r1',0.,[(pose_of('p45'),.3,.6)])
    s=tr.arm_clearance.pending['r1'];r.goal.explorer.local_pose[:2]+=np.array([-.31,0.])
    tr.arm_clearance.filter(tr,1.,[]);assert s['phase']=='turn'
    r.goal.explorer.local_pose[2]=s['yaw']
    tr.arm_clearance.filter(tr,1.1,[]);assert s['phase']=='verify'
    r.range_provider.report=lambda now:RangeReport(now,0.,True,1.,.002,source=source_label(),status='ok')
    tr.arm_clearance.filter(tr,2.,[])
    assert not tr.arm_clearance.pending and tr.queue
    final={}
    for _,rid,a in tr.queue:
        if a['kind']=='arm':final[a['servo_id']]=a['pulse']
    assert final[4]==pose_of('p45')[4]


def test_same_location_is_excluded_even_after_echo_disappears():
    tr=setup();r=tr.robots['r1'];tr._poses('r1',0.,[(pose_of('p45'),.3,.6)])
    tr.arm_clearance.pending.clear()
    r.range_provider.report=lambda now:RangeReport(now,0.,True,1.,.002,source=source_label(),status='ok')
    tr._poses('r1',1.,[(pose_of('p45'),.3,.6)])
    assert tr.arm_clearance.pending['r1']['phase']=='backup'
    assert tr.events[-1]['repeated_location']


def test_default_off_and_actual_grasp_are_unchanged():
    tr=setup('off');tr._poses('r1',0.,[(pose_of('p45'),.3,.6)])
    assert tr.queue and not tr.arm_clearance.pending
    tr=setup();tr._poses('r1',0.,[(pose_of('p45'),.3,.6),({1:1500},.5,.4)])
    assert tr.queue and not tr.arm_clearance.pending


def test_own_rgb_wall_adds_near_evidence_without_peer_or_world_inputs():
    tr=setup(distance=1.);r=tr.robots['r1'];r.wall_segments=[([.2,-.2],[.2,.2])]
    assert not evidence(r,0.,'range_v1')['near']
    assert evidence(r,0.,'range_wall_v1')['near']
    assert not evidence(r,2.,'range_wall_v1')['near']


@pytest.mark.parametrize('status,valid,near',[('blind',False,True),('no_echo',False,False)])
def test_missing_echo_is_not_fabricated_as_a_numeric_clearance(status,valid,near):
    tr=setup();r=tr.robots['r1']
    r.range_provider.report=lambda now:RangeReport(now,0.,valid,source=source_label(),status=status)
    ev=evidence(r,0.,'range_v1');assert ev['near']==near and ev['range_m'] is None


def test_stale_or_foreign_range_does_not_trigger_recovery():
    tr=setup();r=tr.robots['r1']
    for report in [RangeReport(-1.,1.,True,.01,.002,source=source_label(),status='ok'),RangeReport(0.,0.,True,.01,.002,source='peer',status='ok')]:
        r.range_provider.report=lambda now:report
        assert not evidence(r,0.,'range_v1')['near']


def test_fixed_slots_defer_second_arm_without_reading_peer_state():
    tr=setup('range_wall_slots_v1',distance=1.)
    tr._poses('r2',0.,[(pose_of('p45'),.3,.6)])
    assert tr.arm_clearance.pending['r2']['phase']=='slot' and not tr.queue
    tr.arm_clearance.filter(tr,3.,[])
    assert not tr.arm_clearance.pending and tr.queue


@pytest.mark.parametrize('option',OPTIONS)
def test_three_candidates_are_explicit_and_have_distinct_versions(option):
    b=dict(execution_bundle_id='e2e18-v241',e2e_options={})
    paths=compose(b,option)
    assert b['execution_bundle_id']==f'e2e18-v{VERSIONS[option]}'
    assert paths==(f'configs/simulation_workflows.d/e2e18_v{VERSIONS[option]}.json',)
    assert b['arm_clearance_parameters']==PARAMS
