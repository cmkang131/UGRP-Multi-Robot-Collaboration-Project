"""Saved visible inputs and command planning only; no physics/renderer."""
import json,math
from pathlib import Path
from copy import deepcopy
import pytest
from scripts.zone_teacher import FOLDED
from sim.crate_antipodal import check,visible_grasp
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.crate_lift_pose import ANTIPODAL_OPTION,CARTESIAN_OPTION
from sim.crate_cartesian_lift import STATION_M,plan_lift
from harness.visual_arm_v3 import solve_grip_site_ik

CASES=json.loads((Path(__file__).parent/'fixtures/crate9-visible-picks.json').read_text())['cases']

def teacher(mode=ANTIPODAL_OPTION):
 return CrateGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20),crate_lift_pose=mode,
   teacher_stability='align_relook_v1',teacher_search='search_reacquire_v1',approach_goal_set='approach_goal_set_v1')

@pytest.mark.parametrize('case',CASES,ids=lambda x:f"{x['seed']}-{x['rid']}")
def test_saved_picks_reject_four_box_contacts_keep_all_ten_successful_arm_grasps(case):
 assert visible_grasp(case['world'],case['rid'],case['end'])['valid']==case['valid']
 assert case['valid']==((case['seed'],case['rid']) not in {(77962,'r2'),(77965,'r2'),(77966,'r1'),(77968,'r1')})


def test_aperture_and_body_clearance_reject_large_angles_without_using_measured_load():
 for deg in (0,-15,15):assert check(math.radians(deg),math.radians(-66))['valid']
 for deg in (-90,-75,-60,-45,-30,30,45,60,75,90,180):
  assert not check(math.radians(deg),math.radians(-66))['valid']
 case=deepcopy(CASES[0]);case['world']['visibility'][case['rid']]['visible_probes']=4
 assert not visible_grasp(case['world'],case['rid'],case['end'])['valid']
 # A hidden beam must be rejected before any lookup into its geometry.
 case['world']['beam']=None
 assert not visible_grasp(case['world'],case['rid'],case['end'])['valid']


def test_stalled_nominal_stance_retains_safe_feasible_alternatives_and_collision_checks():
 t=teacher();t.folded_ready=True
 world={'t':1.,'robots':{'r1':{'pose':[0.,0.,0.]}},'objects':{},'walls':[],
  'beam':{'pose':[.5,0.,0.],'ends':{'teal':[.4,0.,.024]}},
  'visibility':{'r1':{'visible_probes':12,'objects':[],'peers':[]}}}
 t._begin_relook(1.,'test');t._set('approach',1.5);t._plan_approach(world,1.5)
 assert t.approach_plan_valid and t.path
 assert abs(math.degrees(t.approach_choice[0]))==pytest.approx(15)
 checked=t.goal_set_log[-1]['candidates']
 assert all(x['reason']=='grasp_geometry' for x in checked if abs(x['offset_deg'])>=30)
 assert all(abs(x['offset_deg'])<=15 for x in checked if x['reason']=='feasible')
 from sim.grasp_act_visible_route import constraints,segment_free
 radius,discs,rects=constraints(world,'r1',True,t.cargo_profile)
 assert all(segment_free(a,b,discs,rects,radius) for a,b in zip(t.path,t.path[1:]))


def test_bad_current_grasp_cannot_queue_and_default_old_mode_is_unchanged():
 c=next(x for x in CASES if not x['valid']);w=deepcopy(c['world']);t=CrateGraspTeacher(c['rid'],c['end'],FOLDED,
  bounds=(-20,20,-20,20),crate_lift_pose=ANTIPODAL_OPTION,teacher_stability='align_relook_v1',approach_goal_set='approach_goal_set_v1')
 t.arm.events.clear();t._queue_pick(w,1.)
 assert not t.arm.events and t.phase=='relook'
 assert not hasattr(teacher(CARTESIAN_OPTION),'approach_grasp_filter')
 assert CrateGraspTeacher('r1','teal',FOLDED,bounds=(-20,20,-20,20)).crate_lift_pose=='off'


def test_new_mode_held_phase_uses_only_owned_commands_and_retains_cartesian_lift():
 class Forbidden(dict):
  def __getitem__(self,k):raise AssertionError('held world input read')
 t=teacher();t.sink.pwm={1:1500,**solve_grip_site_ik((STATION_M,0,.024))};expected=plan_lift(t.sink.pwm)[0]
 t._set('complete',1.);t.step(Forbidden(),1.1,permit_lift=True)
 assert t.lift_prefix==expected and t.phase=='lift'
 for i in range(1,32):t.step(Forbidden(),1.1+i*.1)
 assert t.lift_done
