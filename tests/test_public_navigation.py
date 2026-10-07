"""Public core counterexamples and strict evaluation gate; no engine/provider calls."""
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

from harness.public_navigation.costmap import Costmap,from_grid
from harness.public_navigation.native import PublicCore,ROOT
from harness.public_navigation.follower import follow_twist,command_from_twist,projected_clear
from harness.public_navigation.stack import PublicNavigator,navigation_output
from harness.own_map_navigation import ObservedGrid
from harness.self_odom_grid import motion_profiles


def box(size=40):
    raw=np.zeros((size,size),np.uint8)
    raw[0,:]=raw[-1,:]=raw[:,0]=raw[:,-1]=254
    return raw


def test_off_keeps_old_golden_identity_and_bytes():
    for name in ('pre_goal_snapshot.json','navigation_v1.json'):
        raw=(ROOT/'tests/fixtures/floor_goal'/name).read_bytes()
        assert navigation_output(raw) is raw
        assert navigation_output(raw,navigation='off')==raw
    with pytest.raises(ValueError):
        navigation_output(None,navigation='public_ros_v0')


def test_vendored_files_have_exact_pinned_hashes_and_licenses():
    manifest=json.loads((ROOT/'third_party/mapfree_navigation/SOURCES.json').read_text())
    assert len(manifest['files'])==20
    for row in manifest['files']:
        assert hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest()==row['sha256']
    assert 'Redistribution' in (ROOT/'third_party/mapfree_navigation/m-explore/LICENSE').read_text()
    assert 'MIT License' in (ROOT/'third_party/mapfree_navigation/PythonRobotics/LICENSE').read_text()


def test_ros_world_grid_negative_edges_and_centre_roundtrip():
    m=Costmap(box(),[-2,-2])
    assert m.world_to_map([-2.00001,0]) is None
    assert m.world_to_map([-1.999,-1.999])==(0,0)
    assert m.world_to_map([2.,0]) is None
    for c in [(0,0),(1,1),(39,39),(19,20)]:
        assert m.world_to_map(m.map_to_world(c))==c


def test_native_navfn_detours_and_refuses_complete_barrier():
    raw=box()
    raw[:31,20]=254
    m=Costmap(raw,[-2,-2])
    core=PublicCore()
    path=core.plan(m.costs,(8,8),(30,8))
    assert len(path)>2 and path[:,1].max()>31
    raw[:,20]=254
    assert len(core.plan(Costmap(raw,[-2,-2]).costs,(8,8),(30,8)))==0
    raw[:,20]=255
    assert len(core.plan(Costmap(raw,[-2,-2]).costs,(8,8),(30,8)))==0


def test_rectangle_orientation_and_full_interior_unknown():
    raw=box()
    # .3m slot, within-cell pose keeps short side clear but long side overlaps wall cells.
    raw[17,:]=254
    raw[21,:]=254
    m=Costmap(raw,[-2,-2])
    assert m.pose_clear([0.,-.03,0.])
    assert not m.pose_clear([0.,-.03,math.pi/2])
    raw[19,20]=255
    assert not Costmap(raw,[-2,-2]).pose_clear([0.,-.03,0.])


def test_real_subcell_connector_and_direct_pursuit_turn():
    m=Costmap(box(),[-2,-2])
    nav=PublicNavigator()
    pose=np.array([-.6197343,.6197343,0.])
    path=nav.plan_to(m,pose,[.8,.7])
    assert path[0]==pose[:2].tolist()
    assert len(path)>2 and np.linalg.norm(np.asarray(path[1])-pose[:2])>1e-4
    twist=follow_twist(path,pose)
    gain=np.asarray(motion_profiles()['motion']['gain'])
    command=command_from_twist(twist,0.)
    assert np.allclose(gain@np.array([command['forward'],command['left'],command['turn']]),twist)
    turn=follow_twist([[0,0],[-1,0]],[0,0,0])
    assert turn[0]==0 and abs(turn[2])==.5
    assert projected_clear(m,[0,0,0],turn)


def test_frontier_original_clusters_and_blacklist_tolerance():
    raw=np.full((30,30),255,np.uint8)
    raw[8:22,8:22]=0
    m=Costmap(raw,[-1.5,-1.5])
    core=PublicCore()
    frontiers=core.frontiers(raw,m.origin,.1,[0,0])
    assert len(frontiers)==1 and frontiers[0,5]>=40
    nav=PublicNavigator()
    nav.frontier=np.array([.2,.3])
    nav.target=np.array([.1,.1])
    nav.abort(31,'progress_timeout')
    assert nav.blocked([.69,.79],.1)
    assert not nav.blocked([.701,.801],.1)  # strict boundary floating point is checked below
    assert nav.events[-1]['reason']=='progress_timeout'


def test_body_clearing_does_not_invent_camera_coverage_or_free_ring():
    grid=ObservedGrid('r1')
    view=from_grid(grid,[0,0,0])
    assert view.raw[view.world_to_map([0,0])[::-1]]==0
    assert view.raw[view.world_to_map([.4,0])[::-1]]==255
    assert grid.floor_frames=={} and grid.odds=={} and not grid.support


def test_stage_a_gate_refuses_8_of_32_and_stale_source(tmp_path):
    sys.path.insert(0,str(ROOT/'experiments/2026-10-07-mapfree-public-navigation/code'))
    from run_public import verify_gate,cohort,write
    rows=[]
    for i,start,seed in cohort('confirmation'):
        row=dict(scenario=f's{i}',start=start,seed=seed,condition='static_map',
                 status='B_confirmed' if len(rows)<8 else 'budget')
        rows.append(row)
        write(tmp_path/f's{i}-{start}-{seed}-static_map/result.json',row)
    write(tmp_path/'source.json',dict(stage='a',cohort='confirmation',hashes={'test':'one'}))
    write(tmp_path/'results.json',rows)
    with pytest.raises(ValueError,match='GATE_FAILED_STOP'):
        verify_gate(tmp_path,'a',{'test':'one'})
    with pytest.raises(ValueError,match='SOURCE_OR_COHORT'):
        verify_gate(tmp_path,'a',{'test':'two'})


def test_actor_modules_have_no_environment_ground_truth_or_provider_imports():
    for p in (ROOT/'harness/public_navigation').glob('*.py'):
        tree=ast.parse(p.read_text())
        names=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        names += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        assert not any(any(w in name for w in ('mujoco','grid_world','run_grid','openai','google.genai')) for name in names)
