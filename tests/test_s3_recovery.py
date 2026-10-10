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
