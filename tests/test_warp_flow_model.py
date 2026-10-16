import pytest
from scripts.warp_flow_model import canonical_xml, model_arrays_equal


def test_only_free_pose_can_change():
    a='<mujoco><worldbody><body name="cargo" pos="1 2 3"><freejoint/><geom size="1" mass="2" friction=".5"/></body><body name="wall" pos="4 0 0"/></worldbody></mujoco>'
    b=a.replace('pos="1 2 3"','pos="2 3 4"')
    result,audit=canonical_xml(b,a)
    assert audit['moved'][0]['body']=='cargo'
    assert audit['mass_size_friction_unchanged']
    assert canonical_xml(result,a)[0]==result
    for old,new in [('size="1"','size="2"'),('mass="2"','mass="3"'),('friction=".5"','friction=".6"'),('pos="4 0 0"','pos="5 0 0"')]:
        with pytest.raises(ValueError,match='non-pose'):
            canonical_xml(b.replace(old,new),a)


def test_dof_length_is_not_exempted():
    import numpy as np
    from types import SimpleNamespace
    models=[SimpleNamespace(dof_length=np.array([1.])),SimpleNamespace(dof_length=np.array([2.]))]
    audit=model_arrays_equal(models)
    assert not audit['exact']
    assert audit['differences'][0]['field']=='dof_length'


def test_legacy_world_parameters_retained_without_admitting_camera_change():
    a='<mujoco><option iterations="80"/><worldbody><body name="cargo"><freejoint/><geom name="warehouse_oak_plank_geom" size="1" mass="2"/></body><camera name="r1" fovy="60"/></worldbody></mujoco>'
    b=a.replace('mass="2"','mass="3"')
    result,audit=canonical_xml(b,a,world_parameters=True)
    assert 'mass="3"' in result and not audit['strict_identical_model']
    for text in [b.replace('fovy="60"','fovy="70"'),b.replace('iterations="80"','iterations="40"')]:
        with pytest.raises(ValueError,match='unsupported world parameter'):
            canonical_xml(text,a,world_parameters=True)


def test_zero_grasp_support_rejected_before_world_construction():
    from scripts.warp_flow_admission import certify,MODE
    family=[(0.,.2,None,'existing-certificate')]
    # Both assigned ends need support; a single blocked end rejects the setup.
    blocked=certify([0,0,0],[('cargo',(0,0,1,1,0))],family,
        lambda goal,discs,rects:-1. if goal[0]<0 else 1.,0.,mode=MODE)
    assert not blocked['accepted'] and blocked['ends']['teal']['free_goal_N']==0
    assert blocked['ends']['teal']['blocked_object']=='cargo'
    assert certify([0,0,0],[],family,lambda *a:1.,0.,mode=MODE)['accepted']
    assert certify([0,0,0],[('cargo',(0,0,1,1,0))],family,lambda *a:-1.,0.)['accepted']


def test_default_mjwarp_entry_refuses_mac_before_metadata_or_output(monkeypatch,tmp_path):
    import sys
    from scripts import run_warp_flow_teacher as runner
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    monkeypatch.setattr(sys,'argv',['runner','--flow','release','--adapter-source',str(tmp_path),
        '--cases',str(tmp_path/'absent.json'),'--cap-s','180','--out',str(tmp_path/'output'),
        '--vm-hourly-usd','1.096'])
    with pytest.raises(SystemExit,match='2'):runner.main()
    assert not (tmp_path/'output').exists()


def test_multigeom_contact_map_keeps_four_fingers_and_worlds_separate():
    from scripts.warp_act_core import contact_maps
    targets,fingers=contact_maps(12,[[0,1,2],[2,3]],
        [{4:0,5:1,6:2,7:3},{5:0,6:1,7:2,8:3}])
    assert targets[0].sum()==3 and targets[1].sum()==2
    assert fingers[0,4]==0 and fingers[1,4]==-1
    assert fingers[0,7]==3 and fingers[1,7]==2


def test_jpeg_ring_survives_missing_finalizer_and_partial_slot_write(tmp_path):
    from scripts.warp_flow_recording import DiskRing
    ring=DiskRing(tmp_path/'ring')
    for i in range(105):ring.add(i/10,{'r1':str(i).encode(),'r2':('peer'+str(i)).encode()})
    # Recover with no Python finally/close call, as after a native segfault.
    rows=DiskRing.recover(ring.root)
    assert [r['sequence'] for r in rows]==list(range(5,105))
    (ring.root/'050-r1.jpg').write_bytes(b'partial-next-slot')
    with (ring.root/'journal.jsonl').open('a') as f:f.write('{incomplete')
    recovered=DiskRing.recover(ring.root)
    assert len(recovered)==99 and all(r['sequence']!=50 for r in recovered)


def test_release_cannot_silently_fall_back_to_held_truth_or_other_scene():
    from scripts.run_warp_flow_teacher import require_case_profiles
    case=dict(plan={'scene_profile':'walls_floor_contrast_v5_indigo110_s80'},profile=dict(
        held_object='hidden_v1',pose_anchor='command_relative_v1',lookaround='setdown_global_v1',
        placement='global_localized_release_v1',review_top='off',release_sweep_wall_aware='release_sweep_wall_aware_v1'))
    require_case_profiles('release',[case])
    case['profile']['held_object']='visible_v0'
    with pytest.raises(ValueError,match='own-RGB'):require_case_profiles('release',[case])
    case['plan']['scene_profile']='off'
    with pytest.raises(ValueError,match='scene-v5'):require_case_profiles('beampair',[case])


def test_speed_does_not_credit_padding_after_teacher_returns():
    from types import SimpleNamespace as NS
    from scripts.run_warp_flow_teacher import world_sim_clocks
    # Both mirrors read30 SIM, but one task completed at5. Crediting60 rather
    # than35 aggregate seconds would turn a speed failure into a false pass.
    contexts=[{'world':NS(data=NS(time=32.)), 'origin':2.} for _ in range(2)]
    clocks=world_sim_clocks(contexts,{0:{'sim_s':5.}})
    assert clocks==[5.,30.]
    assert 211./sum(clocks)>6.
