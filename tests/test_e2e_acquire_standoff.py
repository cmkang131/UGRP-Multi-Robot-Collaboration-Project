import copy
import math
import numpy as np
import pytest
from harness import e2e_acquire_standoff as m
from harness import e2e_pregrasp_acquire as acq
from harness.e2e_arm_clearance import Clearance
from tests.test_e2e_align_progress import setup_transport


def lost(center=(-.6,0.,0.),standoff='v1',dev_light=True):
    tr=setup_transport(pregrasp_acquire=acq.OPTION,dev_light=dev_light)
    install_guards(tr)
    r=tr.robots['r2'];r.last_beam=copy.deepcopy(r.beam);r.last_beam['pose_own_m']=list(center)
    r.beam=None;r.goal.explorer.map_to_odom=np.zeros(3);r.goal.explorer.grid=None
    m.install(tr,standoff)
    return tr,r


def install_guards(tr):
    import harness.public_navigation_unknown as u,harness.public_navigation.follower as f
    tr._guards=(u.from_observed_grid,f.projected_clear)


@pytest.fixture(autouse=True)
def stub_costmap(monkeypatch):
    import harness.public_navigation_unknown as u,harness.public_navigation.follower as f
    monkeypatch.setattr(u,'from_observed_grid',lambda *a:None)
    monkeypatch.setattr(f,'projected_clear',lambda *a:True)


def test_defaults_are_off_and_scan_timing_unchanged():
    tr=setup_transport(pregrasp_acquire=acq.OPTION)
    assert m.scan_timing(tr)==(2.,3.)
    tr,r=lost(standoff='off')
    state={};out=acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff' and not any(e['event'].startswith('own_beam_lost_standoff') for e in tr.events)


def test_close_loss_backs_off_with_own_reverse_pulses_then_faces_remembered_side():
    tr,r=lost();state={};B=r.goal.entities['B']
    fine,[cmd]=acq.acquire(tr,'r2',20.,state,B)
    assert cmd['kind']=='mecanum' and cmd['forward']<0 and state['acquisition']['phase']=='standoff'
    assert [e['event'] for e in tr.events].count('own_beam_lost_standoff_begin')==1
    # gate holds until a new settled frame; own odometry (not truth) decides distance.
    assert acq.acquire(tr,'r2',20.1,state,B)[1]==[dict(kind='hold')]
    r.goal.explorer.local_pose=np.array([-1.32,0.,0.])
    r.last_obs={'frame_id':11,'sim_time':21.}
    _,acts=acq.acquire(tr,'r2',21.,state,B)
    a=state['acquisition']
    assert a['phase']=='turn' and acts==[dict(kind='hold')]
    end=[e for e in tr.events if e['event']=='own_beam_lost_standoff_end'][0]
    assert end['reason']=='distance' and end['own_odom_displacement_m']>=.3
    assert a['yaw']==pytest.approx(0.,abs=1e-9)  # remembered side is ahead (+x)
    acq.acquire(tr,'r2',21.5,state,B)
    assert a['phase']in('turn','scan') and [e['event'] for e in tr.events].count('own_beam_lost_standoff_begin')==1


def test_far_loss_or_mapping_scan_does_not_back_off():
    tr,r=lost(center=(3.,0.,0.));state={}
    acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff'
    tr,r=lost();state={}
    acq.acquire(tr,'r2',20.,state,None)
    assert state['acquisition']['phase']!='standoff'


def test_pulse_cap_and_collision_guard_outside_dev(monkeypatch):
    tr,r=lost(dev_light=False);state={}
    import harness.public_navigation.follower as f
    monkeypatch.setattr(f,'projected_clear',lambda *a:False)
    acq.acquire(tr,'r2',20.,state,r.goal.entities['B'])
    assert state['acquisition']['phase']!='standoff'
    assert [e for e in tr.events if e['event']=='own_beam_lost_standoff_end'][0]['reason']=='collision_guard'


def test_fast_scan_shortens_view_period_and_turn_cap():
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.acquire_scan_fast='v1'
    assert m.scan_timing(tr)==(1.2,2.)


def test_align_skip_near_own_station_and_repeat_cap_only_when_enabled():
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.state='align'
    pose=np.array([-1.,0.,0.])
    tr.approach['r2']={'station':np.array([-1.2,0.,0.])}
    assert m.skip_reason(tr,'r2',pose,[],'off') is None
    assert m.skip_reason(tr,'r2',pose,[],m.SKIP)=='near_own_station'
    tr.approach['r2']={'station':np.array([-3.,0.,0.])}
    assert m.skip_reason(tr,'r2',pose,[pose[:2]],m.SKIP) is None
    assert m.skip_reason(tr,'r2',pose,[pose[:2],pose[:2]+.1],m.SKIP)=='repeat_location_cap'
    tr.state='mapping'
    assert m.skip_reason(tr,'r2',pose,[pose[:2]]*3,m.SKIP) is None


def test_compose_registered_combinations_only():
    b=lambda:dict(e2e_options={},execution_bundle_id='e2e18-v273')
    x=b();assert m.compose(x,'v1')==('configs/simulation_workflows.d/e2e18_v295.json',) and x['execution_bundle_id']=='e2e18-v295'
    x=b();m.compose(x,'v1','v1','v1');assert x['execution_bundle_id']=='e2e18-v296' and x['workflow_version']=='7.189.0'
    assert m.compose(b())==()
    for key in (('off','v1','off'),('v1','v1','off'),('v1','off','v1')):
        with pytest.raises(ValueError):m.compose(b(),*key)
    with pytest.raises(ValueError):m.compose(dict(e2e_options={},execution_bundle_id='e2e18-v275'),'v1')


def test_clearance_defer_wiring_skips_only_when_enabled_and_logs_sensor_evidence():
    from harness.owncam_pair_beam_v2 import pose_of
    tr=setup_transport(pregrasp_acquire=acq.OPTION);tr.state='align'
    r=tr.robots['r2'];r.servo={**pose_of('search'),1:2000};r.now=0.;r.wall_segments=[]
    tr.approach['r2']={'station':np.array([-1.2,0.,0.])}
    path=[({**pose_of('inspect'),1:2000},.3,.6)]
    c=Clearance('range_wall_v1');tr.events=getattr(tr,'events',[])
    tr.event=lambda now,event,**kw:tr.events.append(dict(t=now,event=event,**kw))
    c.align_skip='v1'
    assert c.defer(tr,'r2',1.,path) is False
    assert [e['event'] for e in tr.events]==['own_arm_clearance_align_skipped']
    assert tr.events[0]['reason']=='near_own_station' and 'range_status' in tr.events[0]
    c2=Clearance('range_wall_v1')
    assert c2.align_skip=='off'


def _pan_parent(monkeypatch):
    import copy
    from scripts.run_e2e_ownmap_live import bundle
    from tests import test_e2e_camera_hold as parent_test
    captured = {}
    def save(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return bundle(*args, **kwargs)
    monkeypatch.setattr(parent_test, 'bundle', save)
    parent_test.test_registered_wheel_wait_candidate('zero_wheel_v1', 276, 'range_wall_v1')
    return captured['args'], captured['kwargs']


def test_v297_v298_stack_standoff_on_pan_relook_and_release(monkeypatch):
    import copy
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    on = dict(beam_lost_standoff='v1', arm_clearance_align_skip='v1', acquire_scan_fast='v1')
    b = bundle(*args, **dict(kw, **on))
    assert b['execution_bundle_id'] == 'e2e18-v297' and b['e2e_options']['relook_search'] == 'view5_pan_v1'
    require_current(b, ROOT)
    for field in ('beam_lost_standoff', 'relook_search'):
        bad = copy.deepcopy(b); bad['e2e_options'][field] = 'off'
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    r = bundle(*args, **dict(kw, **on, stage_physics='release_dt1_v1'))
    assert r['execution_bundle_id'] == 'e2e18-v298' and r['e2e_options']['stage_physics'] == 'release_dt1_v1'
    assert r['e2e_options']['beam_lost_standoff'] == 'v1' and r['e2e_options']['relook_search'] == 'view5_pan_v1'
    require_current(r, ROOT)
    bad = copy.deepcopy(r); bad['stage_physics_profile']['contact_dt_s'] = .001
    with pytest.raises(ValueError):
        require_current(bad, ROOT)
    # parts alone keep their old identities
    assert bundle(*args, **kw)['execution_bundle_id'] == 'e2e18-v276'


def test_v302_relook_giveup_bundle_and_dev_light_only_behavior(monkeypatch):
    import copy
    from types import SimpleNamespace as NS
    from harness.e2e_runtime_registration import require_current
    from harness.e2e_relook_giveup import install, GIVEUP_S
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    on = dict(beam_lost_standoff='v1', stage_physics='release_dt1_v1')
    assert bundle(*args, **dict(kw, beam_lost_standoff='v1'))['execution_bundle_id'] == 'e2e18-v300'
    b = bundle(*args, **dict(kw, **on, relook_giveup='dev_light_v1'))
    assert b['execution_bundle_id'] == 'e2e18-v302' and b['e2e_options']['relook_giveup'] == 'dev_light_v1'
    require_current(b, ROOT)
    bad = copy.deepcopy(b); bad['relook_giveup_parameters']['giveup_after_relook_s'] = 10
    with pytest.raises(ValueError):
        require_current(bad, ROOT)
    assert bundle(*args, **dict(kw, **on))['execution_bundle_id'] == 'e2e18-v301'
    with pytest.raises(ValueError):
        bundle(*args, **dict(kw, relook_giveup='dev_light_v1'))   # needs the v301 parent

    class RL:
        def __init__(s): s.pending = dict(node=3, matches=[]); s.receipt = None; s.events = []
        def emit(s, row): s.events.append(row)
    def transport(dev_light):
        events = []
        tr = NS(state='relook', stage_t=100., dev_light=dev_light, failure=None, seg=2, epoch=1, plan='p', aligned={1: 1},
                approach={1: 1}, first_seg=1, events=events, queue=[],
                dialogue=NS(approved=True, proposal=1, claims={1}, key=1, votes={1: 1}),
                robots={r: NS(goal=NS(e2e_relook=RL()), packet='old' if r == 'r1' else None) for r in ('r1', 'r2')})
        tr.event = lambda t, kind, **d: events.append(dict(t=t, event=kind, **d))
        tr.set = lambda state, t: (setattr(tr, 'state', state), setattr(tr, 'stage_t', t))
        tr.step = lambda now: []
        return tr
    tr = install(transport(True), 'dev_light_v1')
    assert tr.step(100 + GIVEUP_S - 1) == [] and tr.state == 'relook'
    out = tr.step(100 + GIVEUP_S + 1)
    assert tr.state == 'mapping' and tr.plan is None and tr.seg == 0 and tr.robots['r1'].packet is None
    assert all(r.goal.e2e_relook.pending is None and r.goal.e2e_relook.receipt is None for r in tr.robots.values())
    assert {e['event'] for e in tr.events} >= {'would_stop', 'e2e_relook_giveup'}
    assert [e for e in tr.events if e['event'] == 'e2e_relook_giveup'][0]['correction_applied'] is False
    assert len(out) == 2
    tr = install(transport(False), 'dev_light_v1')       # formal runs keep the stop semantics
    tr.step(100 + GIVEUP_S + 50); assert tr.state == 'relook'
    tr = install(transport(True), 'off')
    tr.step(100 + GIVEUP_S + 50); assert tr.state == 'relook'


def test_v303_giveup_on_release_pan_without_standoff(monkeypatch):
    import copy
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    b = bundle(*args, **dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1'))
    assert b['execution_bundle_id'] == 'e2e18-v303' and b['relook_giveup_parent'] == 'e2e18-v280'
    assert b['e2e_options'].get('beam_lost_standoff', 'off') == 'off'
    require_current(b, ROOT)
    bad = copy.deepcopy(b); bad['e2e_options']['stage_physics'] = 'pregrasp_dt1_v1'
    with pytest.raises(ValueError):
        require_current(bad, ROOT)


def test_rest_drop_guard_ignores_resting_beam_flicker_but_not_a_real_fall():
    from sim.s4_beam_drop_guard import DropGuard
    def run(rest, flicker_after):
        g = DropGuard(rest_clear=rest); t = 0.; drops = []
        for z in (.12, .12, .10):                       # lifted and held
            drops.append(g.observe(t=t, com_z=z, origin_z=z, finger_contact=True, floor_contact=False)['drop']); t += .05
        for i in range(30):                              # set down and resting on the floor
            drops.append(g.observe(t=t, com_z=.016, origin_z=0., finger_contact=False, floor_contact=True)['drop']); t += .05
        for i in range(flicker_after):                   # one-sample contact flicker
            drops.append(g.observe(t=t, com_z=.016, origin_z=0., finger_contact=False, floor_contact=False)['drop']); t += .05
        return drops
    assert any(run(False, 1))          # old guard: false positive after lifting once
    assert not any(run(True, 1))       # rest guard: resting beam is not a drop
    g = DropGuard(rest_clear=True)     # a real unsupported fall is still flagged
    out = [g.observe(t=i*.05, com_z=z, origin_z=z, finger_contact=False, floor_contact=False)['drop']
           for i, z in enumerate((.12, .10, .05, .03))]
    assert out[-1] is True


def test_v304_v305_rest_guard_variants(monkeypatch):
    import copy
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    b = bundle(*args, **dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_rest_v1'))
    assert b['execution_bundle_id'] == 'e2e18-v304' and 'drop_guard_rest_parameters' in b and b['pair_drop_guard'] == 'contact_com_v1'
    require_current(b, ROOT)
    bad = copy.deepcopy(b); bad.pop('drop_guard_rest_parameters')
    with pytest.raises(ValueError):
        require_current(bad, ROOT)
    c = bundle(*args, **dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1'))
    assert c['execution_bundle_id'] == 'e2e18-v303' and 'drop_guard_rest_parameters' not in c
    on = dict(beam_lost_standoff='v1', stage_physics='release_dt1_v1', relook_giveup='dev_light_rest_v1')
    assert bundle(*args, **dict(kw, **on))['execution_bundle_id'] == 'e2e18-v305'


def test_v310_v311_approach_floor_bundle(monkeypatch):
    import copy
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    base = dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1')
    assert bundle(*args, **base)['execution_bundle_id'] == 'e2e18-v303'
    for opt, num, floor in (('v1', 310, .30), ('v2', 311, .22)):
        b = bundle(*args, **dict(base, approach_floor=opt))
        assert b['execution_bundle_id'] == f'e2e18-v{num}' and b['approach_floor_parameters']['floor_m'] == floor
        assert b['relook_giveup_parent'] == 'e2e18-v280'
        require_current(b, ROOT)
        bad = copy.deepcopy(b); bad['approach_floor_parameters']['floor_m'] = .1
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    with pytest.raises(ValueError):
        bundle(*args, **dict(kw, approach_floor='v1'))        # needs the v303 parent


def test_approach_floor_filter(monkeypatch):
    from types import SimpleNamespace as NS
    from harness import e2e_approach_floor as f

    class Gate:
        def __init__(s): s.ok = True
        def ready(s, now, obs): return s.ok
        def issued(s, now, profile, obs): s.ok = False
    import harness.zone_s3_settled_servo as gate_mod
    import harness.zone_solo_cyan_pulse_cal as cal
    monkeypatch.setattr(gate_mod, 'SettleGate', Gate)
    monkeypatch.setattr(cal, 'action_of', lambda p: dict(kind='mecanum', forward=p['u'], left=0., turn=0., duration_s=.1))
    prof = dict(loaded=False, axis='forward', u=-.35, duration_s=.1)

    def tr(mode, x, end_visible=False, t=10.):
        res = dict(visible=True, reason='BAND_CLIPPED', end_visible=end_visible, near_end_base_m=[x, .1], band=dict(touches_invalid_border=True))
        r = NS(beam_observation=dict(rgb=dict(t_sim=t, frame_id=1), result=res), last_obs=None)
        t_ = NS(approach_floor=mode, robots={'r2': r}, profiles={'a': prof}, dev_light=True, events=[])
        t_.event = lambda now, kind, **d: t_.events.append(kind)
        return t_
    go = dict(kind='mecanum', forward=.35, left=0., turn=0., duration_s=.5)
    assert f.apply(tr('off', .1), 'r2', 10., {}, go, {}) is go                     # off: unchanged
    assert f.apply(tr('v1', .5), 'r2', 10., {}, go, {}) is go                      # far: unchanged
    assert f.apply(tr('v1', .1, end_visible=True), 'r2', 10., {}, go, {}) is go     # end visible: unchanged
    assert f.apply(tr('v1', .1), 'r2', 10.7, {}, go, {}) is go                     # stale observation
    t = tr('v1', .28); st = {}
    assert f.apply(t, 'r2', 10., st, go, {})['kind'] == 'hold'                     # at the floor: no forward
    t = tr('v1', .15); st = {}
    out = f.apply(t, 'r2', 10., st, go, {})
    assert out['forward'] < 0 and st['approach_floor']['pulses'] == 1              # close: one reverse pulse
    assert f.apply(t, 'r2', 10.1, st, go, {})['kind'] == 'hold'                    # gate not settled: no 2nd pulse
    st['approach_floor']['gate'].ok = True
    assert f.apply(t, 'r2', 10.2, st, go, {})['forward'] < 0 and st['approach_floor']['pulses'] == 2
    st['approach_floor']['gate'].ok = True
    t.robots['r2'].beam_observation['rgb']['t_sim'] = 31.
    assert f.apply(t, 'r2', 31., st, go, {}) is go and 'approach_floor_released' in t.events   # released after 20 s


def test_v312_v313_clip_hysteresis_bundle(monkeypatch):
    import copy
    from harness.e2e_runtime_registration import require_current
    from scripts.run_e2e_ownmap_live import ROOT, bundle
    args, kw = _pan_parent(monkeypatch)
    base = dict(kw, stage_physics='release_dt1_v1', relook_giveup='dev_light_v1')
    for extra, num, parent in (({'approach_floor': 'v1'}, 312, 'e2e18-v310'), ({}, 313, 'e2e18-v303')):
        b = bundle(*args, **dict(base, **extra, clip_hysteresis='v1'))
        assert b['execution_bundle_id'] == f'e2e18-v{num}' and b['clip_hysteresis_parent'] == parent
        assert (b['e2e_options'].get('approach_floor') == 'v1') == (num == 312)
        require_current(b, ROOT)
        bad = copy.deepcopy(b); bad['clip_hysteresis_parameters']['exit_frames'] = 1
        with pytest.raises(ValueError):
            require_current(bad, ROOT)
    with pytest.raises(ValueError):
        bundle(*args, **dict(kw, clip_hysteresis='v1'))      # needs the v303/v310 parent


def test_clip_hysteresis_breaks_servo_clip_cycle_and_keeps_budget():
    from types import SimpleNamespace as NS
    from harness import e2e_clip_hysteresis as hy
    tr = NS(clip_hysteresis='v1', dev_light=True, events=[])
    tr.event = lambda now, kind, **d: tr.events.append(kind)
    off = NS(clip_hysteresis='off')
    assert hy.blocked(off, 'r1', 1., {'clip_hyst': dict(hold_t=0.)}) is False      # off: never blocks
    st = {}
    obs = lambda i, t: dict(rgb=dict(frame_id=i, t_sim=t))
    assert not hy.clipped_seen(tr, 'r1', 1., st, obs(1, 1.))                        # 1 clipped frame: debounced
    assert hy.clipped_seen(tr, 'r1', 1.4, st, obs(2, 1.4))
    assert hy.clipped_seen(tr, 'r1', 1.4, st, obs(2, 1.4))                          # same frame: no double count
    hy.pulsed(st, 1.4)
    assert hy.blocked(tr, 'r1', 1.8, st)                                            # servo handoff held
    att = dict(count=1)
    for i in range(3, 5):                                                           # 2 visible frames: still held
        assert not hy.end_visible_seen(tr, 'r1', 1.4+.4*i, st, obs(i, 1.4+.4*i), att)
    assert hy.blocked(tr, 'r1', 3.0, st)
    assert not hy.end_visible_seen(tr, 'r1', 3.2, st, obs(5, 3.2), att)             # 3 frames + >=1.6 s dwell: released
    assert not hy.blocked(tr, 'r1', 3.2, st)
    assert not hy.clipped_seen(tr, 'r1', 3.6, st, obs(6, 3.6))                      # flicker: visible run resets
    for i in range(7, 12):                                                          # lone flicker never resets the budget
        reset = hy.end_visible_seen(tr, 'r1', 3.6+.4*i, st, obs(i, 3.6+.4*i), att)
    assert not reset
    assert hy.end_visible_seen(tr, 'r1', 9., st, obs(12, 9.), att)                  # 6 consecutive frames: reset
    hy.pulsed(st, 10.)
    assert not hy.blocked(tr, 'r1', 22.5, st) and 'clip_hysteresis_released' in tr.events   # bounded hold
