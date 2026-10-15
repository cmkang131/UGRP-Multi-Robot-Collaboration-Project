"""Static/recorded command tests only. No MuJoCo world, step or renderer."""
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from harness.visual_arm_v3 import tool_pose, MOUNT_X_M
from scripts.zone_teacher import FOLDED
from sim.crate_cartesian_lift import plan_lift, static_torques, STATION_M, RISE_M, DURATION_S
from sim.crate_lift_pose import CARTESIAN_OPTION, angles
from sim.crate_grasp_teacher import CrateGraspTeacher
from sim.grasp_act_teacher import grasp_poses
from sim.s2_servo_stiffness import TORQUE_NM


def closed(radius=.148):
    return {1: 1500, **grasp_poses((MOUNT_X_M+radius, 0., .024))[1][-1]}


def teacher():
    return CrateGraspTeacher('r1', 'teal', FOLDED, bounds=(-20,20,-20,20),
        crate_lift_pose=CARTESIAN_OPTION, teacher_stability='align_relook_v1',
        teacher_search='search_reacquire_v1', approach_goal_set='approach_goal_set_v1')


def world(distance=STATION_M):
    return {'t': 0., 'robots': {'r1': {'pose': [0.,0.,0.]}}, 'objects': {}, 'walls': [],
            'beam': {'pose': [distance+.1,0.,0.], 'ends': {'teal': [distance,0.,.024]}},
            'visibility': {'r1': {'visible_probes': 15, 'objects': [], 'peers': []}}}


def test_cartesian_lift_keeps_separation_pitch_and_has_clearance_margin():
    for radius in (.147, .148, .150, .151):
        p=closed(radius); origin=tool_pose(p); best,report=plan_lift(p)
        assert best is not None and report['samples']==25
        for at in sorted({x[0] for x in best['events']}):
            p.update({sid:value for t,sid,value in best['events'] if t==at})
            pose=tool_pose(p)
            assert math.hypot(pose.x_m-origin.x_m,pose.y_m-origin.y_m)<.0004
            assert pose.pitch_deg==pytest.approx(origin.pitch_deg,abs=1e-10)
            assert all(abs(torque)<=.9*TORQUE_NM[j] for j,torque in static_torques(p).items())
        assert pose.z_m-origin.z_m==pytest.approx(RISE_M,abs=.0003)
        assert best['prefix_duration_s']==DURATION_S
    assert plan_lift(closed(.158))[0] is None


def test_static_torques_match_independent_xml_potential_energy_derivative():
    root=ET.parse(Path(__file__).parent/'fixtures/crate6-elbow.xml').getroot()
    body=root.find('.//body'); qs=angles(closed())
    def potential(q):
        total=0.
        def rotate(x,z,a):return x*math.cos(a)-z*math.sin(a),x*math.sin(a)+z*math.cos(a)
        def walk(b,x,z,parent_angle):
            nonlocal total
            dx,_,dz=map(float,b.get('pos','0 0 0').split());dx,dz=rotate(dx,dz,parent_angle)
            x+=dx;z+=dz
            joint=b.find('joint');angle=parent_angle
            if joint is not None and joint.get('type')=='hinge':
                index={'r2__shoulder':0,'r2__elbow':1,'r2__wrist_pitch':2}[joint.get('name')]
                angle+=q[index]
            inertial=b.find('inertial')
            if inertial is not None:
                cx,_,cz=map(float,inertial.get('pos').split())
                total+=9.81*float(inertial.get('mass'))*(z+rotate(cx,cz,angle)[1])
            for site in b.findall('site'):
                if site.get('name')=='r2__grip_site':
                    sx,_,sz=map(float,site.get('pos').split());total+=.125*9.81*(z+rotate(sx,sz,angle)[1])
            for child in b.findall('body'):walk(child,x,z,angle)
        walk(body,0.,0.,0.)
        return total
    for i,name in enumerate(('shoulder','elbow','wrist')):
        plus=list(qs);minus=list(qs);plus[i]+=1e-6;minus[i]-=1e-6
        numeric=(potential(plus)-potential(minus))/2e-6
        assert static_torques(closed())[name]==pytest.approx(numeric,abs=1e-9)


def test_readiness_checks_full_path_before_closing_and_keeps_visibility_gate():
    t=teacher();t.folded_ready=True
    # Readiness requires an accepted collision-checked approach plan.
    assert t._plan_approach(world(), 0.)
    assert t.ready_geometry(world())
    assert not t.ready_geometry(world(MOUNT_X_M+.158))
    hidden=world();hidden['visibility']['r1']['visible_probes']=4
    assert not t.ready_geometry(hidden)


def test_held_lift_uses_no_world_and_both_teachers_use_same_times():
    class Forbidden(dict):
        def __getitem__(self,key):raise AssertionError('held world read')
    sequences=[]
    for radius in (.147,.150):
        t=teacher();t.sink.pwm=closed(radius);t._set('complete',1.)
        assert t.lift_ready()
        t.step(Forbidden(),1.1,permit_pick=False,permit_lift=False)
        assert not t.arm.events
        t.step(Forbidden(),1.2,permit_pick=False,permit_lift=True)
        sequences.append(sorted({e[0] for e in t.arm.events}))
    assert sequences[0]==sequences[1]


def test_stalled_stance_is_excluded_and_replan_checks_existing_collision_rules():
    t=teacher();t.folded_ready=True;w=world(.4)
    initial=t.approach_choice
    t._begin_relook(1.,'no_visible_error_progress_3s')
    assert initial in t.approach_excluded and t.phase=='relook'
    t._set('approach',1.5);t._plan_approach(w,1.5)
    assert t.approach_choice != initial
    checked=t.goal_set_log[-1]['candidates']
    assert any(r['reason']=='previously_stalled' for r in checked)
    assert all(r['distance_m']==STATION_M for r in checked)


def test_eval_contact_frame_is_rotated_and_sign_is_for_cargo():
    from sim.crate_eval_load import force_on_cargo
    frame=np.array([[0,0,1],[1,0,0],[0,1,0]])
    assert force_on_cargo(frame,[2,3,4,0,0,0],True)==pytest.approx([3,4,2])
    assert force_on_cargo(frame,[2,3,4,0,0,0],False)==pytest.approx([-3,-4,-2])


def test_failure_does_not_fall_back_to_old_lift():
    t=teacher();t.sink.pwm=closed(.158);t._set('complete',1.)
    assert t.outcome=='crate_lift_pose_no_candidate' and not t.lift_ready()
    t._queue_lift(2.)
    assert not t.arm.events


def test_queue_caps_include_other_jobs_and_have_no_gate():
    import importlib.util
    path=Path(__file__).parents[1]/'experiments/2026-10-14-crate-teacher/make_crate8_queue.py'
    spec=importlib.util.spec_from_file_location('crate8_queue',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.available_slots(0,0)==10
    assert module.available_slots(35,5)==5
    assert module.available_slots(39,0)==1
    assert module.available_slots(40,0)==0
    assert module.available_slots(10,10)==0
    with pytest.raises(ValueError):module.available_slots(2,3)
    # Local queue generation depends on the operations baseline, so portable
    # CI checks the admission arithmetic without requiring the user's outputs.
