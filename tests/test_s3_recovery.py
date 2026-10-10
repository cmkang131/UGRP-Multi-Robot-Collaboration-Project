import copy
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from harness import pf_resampling_diversity as pf
from harness import zone_s3_door_lease as door


def signals(pair=True, solo=True, clear=True, progress=False):
    return [door.Signal(r, pair if r != 'r3' else solo, clear, progress) for r in door.ROBOTS]


def test_opposite_requests_expiry_fifo_and_stale_epoch():
    b = door.Board()
    b.exchange(signals(), 0.)
    epoch = b.epoch
    assert b.permits(('r1','r2'), epoch)
    assert not b.permits(('r3',), epoch)
    b.exchange(signals(), door.NO_PROGRESS_S)
    assert b.owner is None and not b.permits(('r1','r2'), epoch)
    b.exchange(signals(), door.NO_PROGRESS_S+.05)
    assert b.owner == ('r3',)
    # Expiry cannot be extended indefinitely by a repeated request/heartbeat.
    b.exchange(signals(progress=True), 100.)
    assert b.owner is None


def test_expired_occupant_never_grants_opposite_team_until_clear():
    b = door.Board(); b.exchange(signals(clear=False), 0.)
    b.exchange(signals(clear=False), 10.)
    assert b.owner is None and b.blocker == ('r1','r2')
    b.exchange(signals(clear=False), 10.05)
    assert b.owner == ('r1','r2') and b.events[-1]['recovery']
    b.exchange(signals(pair=False, clear=True), 10.10)
    b.exchange(signals(pair=False, clear=True), 10.15)
    assert b.owner == ('r3',)


def test_off_identity_and_floor_is_actual_cloud():
    marker = object()
    assert pf.attach_s3(marker) is marker
    assert pf.attach_ownmap(marker) is marker
    assert door.attach(marker) is marker
    rng = np.random.default_rng(11)
    cloud = np.tile([2., 1., .2], (128, 1)); weights = np.full(128, 1/128)
    assert pf.floor_cloud(cloud, weights, rng)
    delta, centre = pf.residuals(cloud, weights)
    assert np.allclose(centre, [2.,1.,.2])
    normalized = delta/pf.SCALE
    assert np.linalg.eigvalsh((normalized.T*weights)@normalized).min() >= 1.-1e-10
    assert len(np.unique(cloud, axis=0)) == len(cloud)


def test_roughening_formula_wrap_and_rng_off():
    cloud = np.random.default_rng(2).normal(size=(100,3))*.01
    before = cloud.copy(); rng = np.random.default_rng(3)
    delta, _ = pf.residuals(cloud, np.full(100,.01))
    sigma = pf.roughen(cloud, rng)
    assert np.allclose(sigma, .2*np.ptp(delta,axis=0)*100**(-1/3))
    assert not np.array_equal(cloud, before)


def test_rbpf_floor_reaches_next_proposal_and_same_ancestry():
    grid = SimpleNamespace(poses=np.zeros((32,3)), weights=np.full(32,1/32),
        pending_cov=np.repeat((np.eye(3)*1e-10)[None],32,axis=0),
        rng=np.random.default_rng(4), odom=SimpleNamespace(t=5.))
    grid.resample_if_needed = lambda: (32.,None)
    def proposal(instance, *args):
        instance.pending_cov[:]=np.eye(3)*1e-10
        return 'rejected_no_sensor_update'
    grid._selective_proposals=proposal
    pf.attach_ownmap(grid,resampling_diversity='roughen_floor_v1')
    assert grid.resample_if_needed() == (32.,None)
    assert np.allclose(grid.pending_cov[0],np.diag(pf.SCALE**2))
    assert grid._selective_proposals(grid)=='rejected_no_sensor_update'
    assert np.allclose(grid.pending_cov[0],np.diag(pf.SCALE**2))
    assert grid.resampling_diversity_audit['proposal_floors']==1


def test_actual_s3_factory_rgb_tick_and_door_port_sweep(tmp_path, monkeypatch):
    from tests import s3_stage_probe as probe
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_s3_sweep_contract import bundle
    from harness.zone_s3_visual_alignment import OPTION
    from harness.zone_final_pair_binding import bind
    from harness import zone_s3_sweep_contract as old
    def selected(sha):
        b = bundle(sha)
        b['controller_config']['options'].update(pose_validity='defer_unmeasured_v1',
            door_lease=door.OPTION, visual_alignment=OPTION, resampling_diversity='ess_v1')
        return b
    monkeypatch.setattr(probe, 'contract', SimpleNamespace(**{**vars(old),'bundle':selected}))
    monkeypatch.setattr(probe, 'Runtime', Runtime)
    p = probe.Probe(tmp_path,monkeypatch)
    try:
        for rid,ep in p.eps.items():
            ctl=ep.controller
            # Real _align invoked by the production tick, not direct align_command.
            calls=[]
            ctl._align = lambda now,idle: calls.append((now,idle))
            ctl.state='align'; ctl.next_look=0.; ctl.arm.until=0.; ctl.arm.events.clear()
            ep.own.last_report=replace(ep.own.last_report,std_xy_m=.4,fix_age_s=10.,last_fix_t=-10.)
            ctl.tick(1.)
            assert calls, (rid,ctl.state)
            assert not ctl.claims.get('aligned')
            ctl.state='approach';ctl.driver.state='drive';ctl.driver.outcome=None
            arrived=[]
            monkeypatch.setattr(ctl.driver,'_av_settled_frame',lambda now: np.zeros((2,2,3),dtype=np.uint8))
            monkeypatch.setattr(ctl.driver.arrival_view,'check',lambda frame:dict(ok=True))
            monkeypatch.setattr(ctl.driver,'_arrive',lambda now:arrived.append(now) or [dict(kind='hold')])
            assert ctl.driver.tick(1.1)==[dict(kind='hold')]
            assert arrived==[1.1]
        # Near simultaneous requests are blocked at actual port.apply; far
        # local pickup is allowed even with the other team's resource lease.
        p.refresh(2.,xy=(-2.,-.85))
        p.runtime.exchange(2.)
        assert p.runtime.clients['r3'].permits()
        for rid in probe.ROBOTS:
            p.issue(rid,dict(kind='hold'),2.)
        protocol=p.runtime.record()['door_yield']
        assert protocol['events'] and 'lease_events' in protocol
        assert all({s['robot_id'] for s in e['signals']}==set(probe.ROBOTS)
                   for e in protocol['events'])
        for own in p.runtime.localizers.values():
            selected_update = pf._closure(own.pose.provider.loc._pf.update_obs,'selected').cell_contents
            assert selected_update.__globals__['resample'].__module__ == pf.__name__
    finally:
        p.runtime.close()


def test_full_existing_sweep_on_new_options(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness.zone_s3_recovery_runtime import Runtime
    from harness import zone_s3_sweep_contract as old
    def selected(sha):
        b=old.bundle(sha)
        b['controller_config']['options'].update(pose_validity='defer_unmeasured_v1',
            door_lease=door.OPTION,visual_alignment='own_rgb_align_v1',resampling_diversity='off')
        return b
    monkeypatch.setattr(probe,'contract',SimpleNamespace(**{**vars(old),'bundle':selected}))
    monkeypatch.setattr(probe,'Runtime',Runtime)
    report=probe.sweep(tmp_path,monkeypatch,invalid_pose_cases=True)
    assert report['error_count']==0,report['errors']


def test_door_clearance_uses_own_arm_and_loaded_formation():
    from harness.zone_own_guards_v3 import body_spheres
    from tests.s3_stage_probe import INITIAL
    report=SimpleNamespace(t_est=1.,initialized=True,x_m=0.,y_m=0.,yaw_rad=0.,
        std_xy_m=.01,std_yaw_rad=.01)
    own=SimpleNamespace(last_report=report,servo=dict(INITIAL),
        pose=SimpleNamespace(provider=SimpleNamespace(loc=SimpleNamespace(
            _pf=SimpleNamespace(load=SimpleNamespace(loaded=False))))))
    box,padding=door.estimated_bounds(report,own.servo,loaded=False)
    for x,y,z,r in body_spheres(own.servo,loaded=False):
        assert box[0]<=x-r and x+r<=box[1]
        assert box[2]<=y-r and y+r<=box[3]
    loaded,pad=door.estimated_bounds(report,own.servo,loaded=True,offset=(.7,0.,0.),envelope=(1.,.3))
    assert loaded[0]<=-1.7 and loaded[1]>=.3 and pad>padding
    # The tip can occupy the portal even while the chassis is outside it.
    portal={'center_m':[box[1]-.01,0.,0.], 'half_extents_m':[.01,.5,1.]}
    legacy=SimpleNamespace(offset=(0.,0.,0.),envelope=(.3,.3))
    client=door.Client('r3',own,door.Board(),portal,legacy)
    assert not client.offer(1.).clear
    own.last_report=SimpleNamespace(**{**vars(report),'std_yaw_rad':None})
    assert client.offer(1.)==door.Signal('r3',True,False,False)
    # DEV proceeds with nominal own geometry but records the uncertainty veto.
    own.last_report=SimpleNamespace(**{**vars(report),'x_m':-2.,'std_xy_m':1.})
    notes=[]
    client.audit=SimpleNamespace(note=lambda *a,**kw:notes.append((a,kw)))
    assert client.offer(1.).clear and notes
    client.audit=None
    assert not client.offer(1.).clear
    own.last_report=SimpleNamespace(**{**vars(report),'x_m':-2.})
    assert not client.offer(3.).clear
    client.audit=SimpleNamespace(note=lambda *a,**kw:notes.append((a,kw)))
    assert client.offer(3.).clear
    assert any('DOOR_POSE_STALE' in a for a,kw in notes)


def test_lease_deadlock_metric_ignores_epoch_churn():
    from scripts.evaluate_s3_recovery import lease_deadlocks
    protocol={'events':[], 'lease_events':[]}
    for t in range(0,181,10):
        protocol['events'].append(dict(sim_s=t,signals=[dict(robot_id=r,
            state='REQUEST' if r=='r3' or t%20==10 else 'USING') for r in door.ROBOTS]))
        protocol['lease_events'].append(dict(event='grant',sim_s=t,team=['r1','r2']))
    traj={r:[dict(t=i/10,robot_xyz_m=[0.,0.,0.],robot_yaw_rad=0.) for i in range(1801)] for r in door.ROBOTS}
    rows=lease_deadlocks(protocol,traj,180.)
    assert len(rows)==1 and rows[0]['waiters']==['r3'] and rows[0]['continuous_wait_start']==0
    for q in traj['r2']:q['robot_xyz_m'][0]=q['t']*.01
    assert not lease_deadlocks(protocol,traj,180.)


def test_early_rgb_reference_not_renewed_by_hidden_hover(monkeypatch):
    from harness import zone_s3_pregrasp_reference as pre
    from harness.zone_pair_highpose_blind_close import grasp_postures
    hover,path=grasp_postures();events=[];queued=[];notes=[]
    own=SimpleNamespace(servo={**hover,1:2000},robot_id='r1')
    track=SimpleNamespace(segment=0,beam=dict(anchor_time_s=1.,anchor_frame_id='early',
        anchor_sha256='a'*64,grip_base_m=[.14,0.]),command=lambda *a:None,
        _blind=lambda *a:(None,dict(evidence='old')))
    obs=dict(sim_time=3.,frame_id='hover-1',image='target not visible')
    ctl=SimpleNamespace(blind_track=track,port=SimpleNamespace(own=own),seg=0,rid='r1',
        state='align',blind_phase=None,blind_hover_last_frame=None,blind_hover_streak=0,
        hover=hover,blind_path=path,arm=SimpleNamespace(queue=lambda p,*a,**kw:queued.append(p),until=0.),
        look=lambda now:obs,log=lambda *a,**kw:events.append((a,kw)),
        hover_barrier_gate=lambda *a:True,_pregrasp_descend=lambda *a:None,
        _light_resume_align=lambda now:notes.append(('reacquire',now)),
        fail=lambda *a:notes.append(('fail',a)))
    def queue(now):ctl.state='pregrasp_descend';ctl.blind_phase='hover'
    ctl._queue_open_descent=queue
    audit=SimpleNamespace(note=lambda *a,**kw:notes.append(('would_stop',kw)))
    monkeypatch.setattr(pre,'controller_gate',lambda ctl:lambda *a:True)
    pre.attach(ctl,audit);ctl._queue_open_descent(2.)
    ctl._pregrasp_descend(3.,True)
    assert not queued
    obs['frame_id']='hover-2';obs['sim_time']=3.1
    ctl._pregrasp_descend(3.1,True)
    assert queued==path
    assert track.blind_window['frame_id']=='early'
    assert track.blind_window['visual_confirmed_at_s']==1.
    assert track.blind_window['confirmed_at_s']==3.1
    assert track.blind_window['hover_visual_confirmation'] is False
    # A moved base cannot keep using the earlier RGB reference.
    ctl._queue_open_descent(4.)
    track.command(dict(kind='mecanum',t=4.1,forward=.01),own.servo)
    ctl._pregrasp_descend(4.2,True)
    assert notes[-1]==('reacquire',4.2) and len(queued)==len(path)
