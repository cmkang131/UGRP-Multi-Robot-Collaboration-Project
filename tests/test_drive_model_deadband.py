"""Command algebra and saved-source compatibility only; no physics/rendering."""
import ast
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np
import pytest

from harness.drive_model import CommandDriveModel, DriveParameters, wheel_speed
from harness.grasp_act_visible_world import command_delta, VisibleWorld
from sim.visible_belief import odometry, rates, VisibleBelief

ROOT=Path(__file__).resolve().parents[1]


def source_parameters():
    # Execute only the simulator's parameter class (no MuJoCo import/world).
    ns={'dataclass':dataclass,'math':math,'np':np}
    for file,base in [('masterpi_drive_friction.py',None),('masterpi_drive_friction_v2.py','V1Parameters'),
                      ('masterpi_drive_friction_v7.py','V2Parameters')]:
        if base:ns[base]=ns['DriveParameters']
        tree=ast.parse((ROOT/'sim'/file).read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DriveParameters')
        # v2's default comes from the recorded public-geometry JSON.
        ns['SOURCE']=json.loads((ROOT/'sim/assets/masterpi_drive_friction_v2/source.json').read_text())
        ns['asdict']=__import__('dataclasses').asdict
        exec(compile(ast.Module(body=[cls],type_ignores=[]),file,'exec'),ns)
    return ns['DriveParameters']()


def test_relay_and_confirmed_damping_match_actual_source():
    source=source_parameters(); p=DriveParameters()
    assert p.damping_nm_s == source.speed_loss_nm_s
    for u in [-1.,-.4,-.35,-.325,-.2,-1/12,0.,1/12,.2,.325,.35,.4,1.]:
        for previous in [-1,0,1]:
            effective,state=source.command_step([u],np.array([previous]))
            speed,direction=wheel_speed(u,previous)
            assert direction==state[0]
            assert abs(speed)==pytest.approx(max(0.,abs(source.torque_cap_nm*effective[0])-p.rolling_torque_nm)/p.total_damping_nm_s)


@pytest.mark.parametrize('u,measured',[(.35,.2727),(.50,.4354),(1.,.9787)])
def test_saved_empty_forward_steady_wheel_speeds(u,measured):
    p=DriveParameters()
    assert wheel_speed(u)[0]/p.omega0==pytest.approx(measured,rel=.01)
    assert wheel_speed(-u)[0]==-wheel_speed(u)[0]
    model=CommandDriveModel()
    model.delta([u]*4,[5.]*4,5.)
    assert model.angular_speeds[0]/p.omega0==pytest.approx(measured,rel=.01)


def test_isolated_pulse_includes_coast_and_qualifies_m2_rates():
    model=CommandDriveModel()
    active=model.delta([.35]*4,[.1]*4,.1)[0]
    coast=model.delta([0.]*4,[0.]*4,.5)[0]
    pulse=active+coast
    assert 0 < active < pulse
    assert .0126 <= pulse <= .0132  # S3 measured 12.9 mm per isolated pulse.
    assert model.angular_speeds==(0.,)*4
    assert model.delta([0.]*4,[0.]*4,1.)==(0.,0.,0.)
    ax,lat,yaw=rates(drive_model_deadband_v1=True)
    assert ax==pytest.approx(pulse/.1)
    assert lat==ax
    assert yaw==pytest.approx(ax/.12435)
    assert wheel_speed(np.float64(.35)) == wheel_speed(.35)


def test_pulse_durations_start_hold_reverse_gap_and_episode_reset():
    m=CommandDriveModel()
    assert m.delta([.31]*4,[.1]*4,.1)==(0.,0.,0.)
    m.delta([.35]*4,[.1]*4,.1)
    assert m.delta([.31]*4,[.1]*4,.1)[0]>0
    assert m.delta([-.31]*4,[.1]*4,.1)[0]>0  # disabled reverse coasts forward
    m.delta([0.]*4,[0.]*4,.5)
    m.delta([.35]*4,[.05]*4,.1)
    assert m.directions==(0,0,0,0)
    assert m.delta([.31]*4,[.5]*4,.5)[0]>=0  # remaining coast, no source torque
    assert m.angular_speeds==(0.,)*4
    m.delta([.35]*4,[.15]*4,.1)
    before=m.directions;m.delta([0.]*4,[0.]*4,0.)
    assert m.directions==before
    m.reset();assert m.directions==(0,0,0,0)
    assert m.angular_speeds==(0.,)*4


def test_split_intervals_reversal_and_low_torque_sticking():
    whole=CommandDriveModel();split=CommandDriveModel()
    for wheels,duration,dt in [([.35]*4,.07,.1),([.25]*4,.1,.1),
                               ([-.5]*4,.1,.1),([0.]*4,0.,.3)]:
        expected=whole.delta(wheels,[duration]*4,dt)
        parts=[split.delta(wheels,[max(0.,duration-i*dt/10)]*4,dt/10) for i in range(10)]
        assert tuple(map(sum,zip(*parts)))==pytest.approx(expected,abs=1e-14)
        assert split.angular_speeds==pytest.approx(whole.angular_speeds,abs=1e-12)
        assert split.directions==whole.directions
    assert whole.angular_speeds==(0.,)*4
    assert wheel_speed(.09,1)==(0.,1)  # source relay remains on but contact holds
    whole.delta([.35]*4,[.1]*4,.1)
    whole.delta([.09]*4,[1.]*4,1.)
    assert whole.directions==(1,)*4
    assert whole.angular_speeds==(0.,)*4


def test_repeated_duty_pulses_accumulate_without_rectangular_shortcut():
    model=CommandDriveModel()
    distance=sum(model.delta([.35]*4,[.07]*4,.1)[0] for _ in range(200))
    # Independent saved-analysis expectation: wheel/M1 ~= .758 at 70% duty.
    nominal=200*.07*.35*DriveParameters().omega0*.0325
    assert distance/nominal==pytest.approx(.758,abs=.005)


def test_mecanum_signs_mixed_pulses_and_both_adapters():
    for wheels,axis in [([.35]*4,0),([-.35,.35,.35,-.35],1),([-.35,.35,-.35,.35],2)]:
        delta=CommandDriveModel().delta(wheels,[.1]*4,.1)
        assert delta[axis]>0
        assert all(v==0 for i,v in enumerate(delta) if i!=axis)
    wheels=[.35,-.4,.35,0.];d=[.025,.075,.15,0.];dt=.1
    first=command_delta({'wheels':wheels,'duration_s':d},dt,drive_model_deadband_v1=True)
    second=odometry(wheels,dt,drive_model_deadband_v1=True,durations_s=d)
    assert first==second
    assert first==CommandDriveModel().delta(wheels,d,dt)


def test_visible_world_and_relative_memory_use_own_commands():
    world=VisibleWorld('r1','teal',drive_model_deadband_v1=True)
    world.observe([],0.);world.issue({'wheels':[.35]*4,'duration_s':[.1]*4})
    result=world.observe([],.1)
    expected=odometry([.35]*4,.1,drive_model_deadband_v1=True)
    assert result['robots']['r1']['pose']==list(expected)
    belief=VisibleBelief();belief.observe('cargo',[1.,0.,0.],0.)
    belief.propagate(*expected)
    assert belief.get('cargo',.1)['pose'][0]==pytest.approx(1.-expected[0])
    with pytest.raises(ValueError,match='GT self pose'):
        world.observe([],.2,comparison_pose=[0.,0.,0.])
    with pytest.raises(ValueError,match='issued pose'):
        VisibleWorld('r1','teal',pose_source='perfect_self_comparison',drive_model_deadband_v1=True)


def test_visible_world_resets_relay_when_observation_has_a_command_gap():
    world=VisibleWorld('r1','teal',drive_model_deadband_v1=True)
    world.observe([],0.)
    world.issue({'wheels':[.35]*4,'duration_s':[.15]*4})
    world.observe([],.4)
    assert world.drive_model.directions==(0,0,0,0)
    assert world.drive_model.angular_speeds==(0.,)*4
    pose=list(world.pose)
    world.issue({'wheels':[.31]*4,'duration_s':[.1]*4})
    world.observe([],.5)
    assert world.pose==pose


@pytest.mark.parametrize('call',[
    lambda:command_delta({'wheels':[.35]*4,'duration_s':[.1]*4},.1,mode='search17_fixed_v1',drive_model_deadband_v1=True),
    lambda:VisibleWorld('r1','teal',odometry='search17_fixed_v1',drive_model_deadband_v1=True),
    lambda:odometry([.35]*4,.1,'gcp_probe_v1',drive_model_deadband_v1=True),
    lambda:rates('gcp_probe_v1',drive_model_deadband_v1=True),
])
def test_fixed_calibrations_are_mutually_exclusive(call):
    with pytest.raises(ValueError,match='mutually exclusive'):call()


@pytest.mark.parametrize('w,d,dt',[
    ([math.nan]*4,[.1]*4,.1),([1.01]*4,[.1]*4,.1),([.35]*3,[.1]*4,.1),
    ([.35]*4,[-.1]*4,.1),([.35]*4,[math.inf]*4,.1),([.35]*4,[.1]*4,-.1),
])
def test_invalid_commands_do_not_mutate_relay(w,d,dt):
    model=CommandDriveModel()
    with pytest.raises(ValueError):model.delta(w,d,dt)
    assert model.directions==(0,0,0,0)
    assert model.angular_speeds==(0.,)*4


def test_default_and_legacy_profiles_match_frozen_source_bytes():
    fixture=json.loads((ROOT/'tests/fixtures/drive_model_deadband/off.json').read_text())
    rng=random.Random(fixture['seed']);values=[];world=[]
    model=VisibleWorld('r1','teal')
    for i in range(fixture['samples']):
        wheels=[rng.choice([-.4,-.35,-.31,0.,.31,.35,.4]) for _ in range(4)]
        duration=[rng.choice([0.,.04,.1,.15]) if w else 0. for w in wheels]
        dt=rng.choice([.0,.04,.1,.15,.2]);issued={'wheels':wheels,'duration_s':duration}
        values.append([command_delta(issued,dt),command_delta(issued,dt,mode='search17_fixed_v1'),
                       odometry(wheels,dt),odometry(wheels,dt,'gcp_probe_v1')])
        measurements=[dict(id='band_teal',kind='band',xyz=[.3,-.1,.1],yaw=.2,radius=.01,visible_n=5,probe_N=5)] if i%3==0 else []
        world.append(model.observe(measurements,i*.1));model.issue(issued)
    assert hashlib.sha256(json.dumps(values).encode()).hexdigest()==fixture['delta_sha256']
    assert hashlib.sha256(json.dumps(world,sort_keys=True).encode()).hexdigest()==fixture['world_sha256']
