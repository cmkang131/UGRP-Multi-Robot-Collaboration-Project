import hashlib,json
from pathlib import Path
import sys
import numpy as np
import pytest
from harness.public_navigation_monitor import (MonitorCore,ApproachMonitor,MonitorActor,MonitorNavigator,
    navigation_output_v8,PARAMETERS)
from harness.public_navigation_unknown import UnknownCore
from harness.public_navigation.follower import command_from_twist
from harness.public_navigation_recovery import issued_twist
ROOT=Path(__file__).resolve().parents[1]


def test_upstream_six_point_ttc_and_approach_speed_not_a_costmap_lookup():
    core=MonitorCore()
    points=np.c_[np.full(6,.255),np.linspace(-.04,.04,6)]
    assert core.collision_time(points,[.12,0,0])==pytest.approx(.9)
    assert core.collision_time(points[:5],[.12,0,0])==-1.
    assert core.collision_time(points,[0,0,0])==-1.
    monitor=ApproachMonitor(core);monitor.observe(points,[0,0,0],2.)
    cmd=command_from_twist(np.array([.12,0,0]),2.)
    filtered,info=monitor.filter(cmd,[0,0,0],2.)
    assert info['scale']==pytest.approx(.75)
    assert issued_twist(filtered)==pytest.approx([.09,0,0])
    monitor.observe(np.zeros((6,2)),[0,0,0],2.)
    assert monitor.filter(cmd,[0,0,0],2.)[1]['scale']==0.


def test_sensor_timeouts_empty_frames_and_own_motion_compensation():
    monitor=ApproachMonitor();cmd=command_from_twist(np.array([.12,0,0]),0.)
    assert monitor.filter(cmd,[0,0,0],0.)[1]['reason']=='invalid_source'
    monitor.observe([], [0,0,0],0.)
    assert monitor.filter(cmd,[0,0,0],1.)[0] is cmd
    assert monitor.filter(cmd,[0,0,0],1.000000001)[1]['reason']=='invalid_source'
    points=np.c_[np.full(6,.35),np.linspace(-.04,.04,6)]
    monitor.observe(points,[1.,2.,np.pi/2],2.)
    # Own robot translates .3 m toward an observed wall; TF base shift finds it inside.
    assert monitor.filter(cmd,[1.,2.3,np.pi/2],2.1)[1]['scale']==0.
    with pytest.raises(ValueError):monitor.observe([[np.nan,0]],[0,0,0],3.)


def test_original_frontier_launch_size_and_cost_preserve_old_core():
    raw=np.full((80,80),255,np.uint8);raw[30:50,30:50]=0
    old,new=UnknownCore(),MonitorCore()
    before=old.frontiers(raw,[-2,-2],.05,[0,0]).tobytes()
    a=old.frontiers(raw,[-2,-2],.05,[0,0]);b=new.frontiers(raw,[-2,-2],.05,[0,0])
    assert len(a) and len(b)
    np.testing.assert_array_equal(a[:,:6],b[:,:6])
    assert b[:,6]==pytest.approx(3*b[:,4]*.05-b[:,5]*.05)
    assert old.frontiers(raw,[-2,-2],.05,[0,0]).tobytes()==before
    tiny=np.full((12,12),255,np.uint8);tiny[5:7,5:7]=0
    assert len(old.frontiers(tiny,[-.3,-.3],.05,[0,0]))
    assert len(new.frontiers(tiny,[-.3,-.3],.05,[0,0]))==0


def test_default_off_lazy_bytes_and_all_old_hashes():
    sentinel=b'{"legacy":true}\n'
    class Poison:
        def update(self,**kw):raise AssertionError('off evaluated')
    assert navigation_output_v8(sentinel,navigator=Poison(),hidden=object()) is sentinel
    with pytest.raises(ValueError):MonitorActor('own_frontier')
    frozen=json.loads((ROOT/'experiments/2026-10-07-mapfree-unknown-footprint/freeze.json').read_text())
    assert len(frozen['hashes'])==121
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==s for p,s in frozen['hashes'].items())
    vendor=ROOT/'third_party/mapfree_navigation_monitor'
    assert all(hashlib.sha256((vendor/r['path']).read_bytes()).hexdigest()==r['sha256']
               for r in json.loads((vendor/'SOURCES.json').read_text())['files'])
    assert PARAMETERS['min_points']==6 and PARAMETERS['costmap_update_hz']==5.
    assert 'mujoco' not in sys.modules


def test_actor_has_no_truth_inputs_and_costmap_five_hz():
    a=MonitorActor('own_frontier',navigation='public_ros_v8')
    assert not a.grid.odds and not a.static_hits and a.static_goal is None
    first=a.make_costmap()
    a.t=.1;a.odom.correct([.025,0,0],np.zeros((3,3)))
    assert a.make_costmap() is first
    a.t=.2
    assert a.make_costmap() is not first
    assert a.last_costmap_ns==200_000_000
