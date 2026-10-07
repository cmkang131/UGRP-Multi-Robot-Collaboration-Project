"""Bounded recovery, setup validity and source/gate boundaries; no MuJoCo/provider."""
import ast
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from harness.public_navigation.costmap import Costmap
from harness.public_navigation.native import ROOT
from harness.public_navigation_recovery import (
    RecoveryActor,RecoveryNavigator,navigation_output_v2,projection_clear,regulated_twist,issued_twist)
from harness.public_navigation.follower import command_from_twist
from harness.own_map_navigation import ObservedGrid

CODE=ROOT/'experiments/2026-10-07-mapfree-navigation-recovery/code'
sys.path.insert(0,str(CODE))
from cohort import generate
from run_recovery import cohort,verify_gate,write,MANIFEST,SETTINGS


def test_off_golden_bytes_and_explicit_v2():
    for p in (ROOT/'tests/fixtures/floor_goal').glob('*.json'):
        raw=p.read_bytes()
        assert navigation_output_v2(raw) is raw
    with pytest.raises(ValueError):
        RecoveryActor('static_map')
    with pytest.raises(ValueError):
        navigation_output_v2(None,navigation='public_ros_v1')


def test_cohort_generated_before_outcomes_valid_docks_no_seen_pairs():
    registered=json.loads(MANIFEST.read_text())
    assert registered==generate()
    assert len(registered['rows'])==32
    assert len({(r['scenario'],r['start'],r['seed']) for r in registered['rows']})==32
    assert all(r['seed'] not in registered['seen_confirmation_seeds'] for r in registered['rows'])
    assert all(r['pose'][1:]==r['dock_pose'][1:] for r in registered['rows'])
    assert all(0<=r['departure_shift_m']<=.5 for r in registered['rows'])
    assert SETTINGS['budget_s']==900 and SETTINGS['budget_frames']==300


def test_upstream_recovery_sources_pinned_and_license():
    data=json.loads((ROOT/'third_party/mapfree_navigation_recovery/SOURCES.json').read_text())
    for row in data['files']:
        assert hashlib.sha256((ROOT/row['file']).read_bytes()).hexdigest()==row['sha256']
    xml=(ROOT/'third_party/mapfree_navigation_recovery/navigation2/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml').read_text()
    assert 'number_of_retries="6"' in xml and 'backup_dist="0.30"' in xml


def test_context_then_round_robin_six_retries_and_abort():
    nav=RecoveryNavigator()
    actions=[]
    for i in range(7):
        nav.failure(i*10.,'fail','controller')
        assert nav.phase=='context_clear'
        nav.phase=None
        nav.failure(i*10.+1,'fail','controller')
        if not nav.failed:
            actions.append(nav.phase)
            nav.phase=None
    assert actions==['clear','spin','wait','backup','clear','spin']
    assert nav.failed and nav.events[-1]['reason']=='recovery_exhausted'


def test_clear_preserves_static_and_current_obstacles_unknown_not_free():
    grid=ObservedGrid('r1')
    grid.odds[(10,10)]=4.
    actor=RecoveryActor('static_map',grid,[2,2],navigation='public_ros_v2')
    actor.receive(dict(robot_id='r1',frame_id=0,floor_xy=[[.4,0]],wall_xy=[[.7,0]],floor_source='floor_visible'),[])
    actor.grid.odds[(15,15)]=4.
    actor.grid.wall_frames[(15,15)]={0}
    actor.latest[(15,15)]=True
    actor.clear_obstacles()
    assert actor.grid.odds[(10,10)]==4.
    assert (15,15) not in actor.grid.odds and (15,15) not in actor.latest
    assert any(actor.latest.values())
    plan=actor.plan()
    ij=actor.costmap.world_to_map([1.05,1.05])
    assert actor.costmap.raw[ij[1],ij[0]]==254


def test_projection_carrot_limit_checks_present_and_issued_command():
    raw=np.zeros((60,60),np.uint8)
    raw[:,36]=254
    cm=Costmap(raw,[-3,-3])
    assert projection_clear(cm,[0,0,0],[1,0,0],distance_limit=.2)
    assert not projection_clear(cm,[0,0,0],[1,0,0],distance_limit=1.)
    assert not projection_clear(cm,[.6,0,0],[0,0,0])
    wanted=np.array([2.,0.,2.])
    actual=issued_twist(command_from_twist(wanted,0))
    assert np.linalg.norm(actual)<np.linalg.norm(wanted)
    twist=regulated_twist([[0,0],[.15,.12],[.5,.2]],[0,0,0],0.)
    assert abs(twist[0])<=.12


def test_new_gate_rejects_29_and_requires_every_raw_episode(tmp_path):
    rows=[]
    for i,s,seed in cohort('confirmation'):
        row=dict(scenario=f's{i}',start=s,seed=seed,condition='static_map',status='B_confirmed' if len(rows)<29 else 'budget')
        rows.append(row)
        write(tmp_path/f's{i}-{s}-{seed}-static_map/result.json',row)
    write(tmp_path/'source.json',dict(stage='a',cohort='confirmation',hashes={'x':'frozen'}))
    write(tmp_path/'results.json',rows)
    with pytest.raises(ValueError,match='GATE_FAILED_STOP'):
        verify_gate(tmp_path,'a',{'x':'frozen'})


def test_actor_import_boundary_and_old_runtime_preserved():
    tree=ast.parse((ROOT/'harness/public_navigation_recovery.py').read_text())
    names=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    names += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert not any(any(word in name for word in ('mujoco','grid_world','run_grid','cohort','openai','genai')) for name in names)
