"""State-machine regressions with explicit synthetic own RGB, never GT/contact.

A low-lift success is the starting precondition; every new raise/lower tick,
barrier, anchor and open command below uses the real HIGH implementation.
"""
import hashlib
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from tests.test_zone_final_pair_v3 import offline_only
from harness import zone_pair_highpose_grip as grip
from harness import zone_pair_highpose as pose
from harness.zone_pair_highpose_runtime import HighController
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint
from scripts import study_owncam_pair_beam as legacy
from scripts.zone_teacher import ArmSequence


def rgb_for(servo, slip=False, edge_only=False):
    xs, ys, _, mask = grip.support(servo)
    small = mask.reshape(120,160).astype(np.uint8)
    image = np.full((480,640,3), 155, np.uint8)
    colour = cv2.cvtColor(np.uint8([[[40,190,205]]]),cv2.COLOR_HSV2BGR)[0,0]
    dense = cv2.resize(small,(640,480),interpolation=cv2.INTER_NEAREST).astype(bool)
    if slip: dense = np.roll(dense,120,axis=0)
    if edge_only:
        dense[:] = False;dense[40:180,140:500] = True
    image[dense] = colour
    return image


class LowConfirmed(legacy.PairStudent):
    def _lift(self, now, idle):
        if idle: self.set('wait_carry',now)

    def door_schedule(self, now):
        return [(now,now+.1,{'forward':.01,'left':0.,'turn':0.})]


class Controller(HighController,LowConfirmed):
    def __init__(self, rid, bus):
        self.ep=PairStatusEndpoint(bus,rid)
        issued={1:1500,**pose.grasp_postures()[0]}
        self.events=[];self.issued_log=[];self.now=0.;self.frame=0;self.slip=False;self.edge_only=False
        self.port=SimpleNamespace(own=SimpleNamespace(servo=issued,
            pose=SimpleNamespace(provider=SimpleNamespace(beam_edge=SimpleNamespace(available=lambda now:True)))))
        self.port.hold=lambda now:self.issued_log.append((now,{'kind':'hold'}))
        def apply(action,now):
            self.issued_log.append((now,dict(action)))
            if action['kind']=='arm':issued[action['servo_id']]=action['pulse']
            elif action['kind']=='look':issued[6]=action['pan_pulse']
        self.port.apply=apply
        arm=ArmSequence(self.port,issued)
        legacy.PairStudent.__init__(self,rid,self.port,arm,
            lambda key:self.ep.sync_for(f'{key}@{self.seg}'),
            lambda rid,event,t,**kw:self.events.append({'event':event,'t':t,**kw}),
            status=(bus,self.ep),hold_check='fullframe_v3')
        self.state='lift';self.seg=0;self.segments=[.1]
        self.grip_epoch=1;self.pose_anchors={};self.transit=None
        self.high_raising=self.high_ready=self.floor_return_verified=False
        self.hover,self.descent=pose.grasp_postures();self.grasp_pose=self.descent[-1]
        self.grasp_estimate=[0.,0.,0.]
        floor={1:1500,**self.grasp_pose}
        self._anchor('floor',self.observation(0.,floor),0.)

    def observation(self,now,servo=None):
        self.frame+=1
        servo=dict(self.port.own.servo if servo is None else servo)
        image=rgb_for(servo,self.slip,self.edge_only)
        return {'robot_id':self.rid,'sim_time':now,'frame_id':self.frame,
            'sha256':hashlib.sha256(image.tobytes()).hexdigest(),'image':image,
            'actuator_state':{'servo_pulses':servo}}

    def look(self,now):return self.observation(now)


def pair():
    bus=PairStatusChannel('high-transit')
    return bus,[Controller(r,bus) for r in ('r1','r2')]


def apply_fault(c, fault, now, start):
    if c.rid!='r2' or not fault or now<start: return
    if fault=='grip_loss':c.slip=True
    elif fault=='open_command':c.port.own.servo[1]=2000
    elif fault=='edge_only':c.edge_only=True


def run_raise(ctls, *, fault=None, until=22.):
    # 'stall': r2's arm ticks stop for 2 s during the VIA_130 move (own-queue
    # desync). 'offset': r2 starts the whole raise 2 s late (relative delay).
    for i in range(int(round(until/.1))):
        now=round(i*.1,8)
        for c in ctls:
            c.ep.tick('abort' if c.state=='failed' else ('lift' if c.state in ('lift','wait_carry') else 'carry'),now)
        for c in ctls:
            if c.state=='failed':continue
            apply_fault(c,fault,now,2.)
            if fault=='offset' and c.rid=='r2' and now<2.:continue
            if c.state=='lift':c._lift(now,now>=c.arm.until and not c.arm.events)
            elif c.state=='wait_carry':c._wait_carry(now,now>=c.arm.until and not c.arm.events)
        for c in ctls:
            if c.state=='failed':continue
            if fault=='stall' and c.rid=='r2' and 4.<=now<6.:continue
            c.arm.tick(now)
    return ctls


def run_lower(ctls, *, fault=None, start=23., floor_glitch=None):
    for c in ctls:
        if c.state!='failed':c.set('wait_lower',20.);c.next_look=20.
    for i in range(205):
        now=round(20+i*.1,8)
        for c in ctls:
            c.ep.tick('abort' if c.state=='failed' else ('carry' if c.state=='wait_lower' else 'put_down'),now)
        for c in ctls:
            if c.state=='failed':continue
            apply_fault(c,fault,now,start)
            if floor_glitch is not None and c.rid=='r2' and getattr(c,'floor_check_until',None) is not None:
                # Only inside the post-lowering floor re-check window.
                c.slip = now < c.floor_check_until-grip.FLOOR_CONFIRM_MAX_S+floor_glitch
            handler={'wait_lower':c._wait_lower,'lower':c._lower,'wait_open':c._wait_open}.get(c.state)
            if handler:handler(now,now>=c.arm.until and not c.arm.events)
        for c in ctls:
            if c.state=='failed':continue
            if fault=='stall' and c.rid=='r2' and 24.<=now<26.:continue
            c.arm.tick(now)
    return ctls


def test_normal_raise_lower_release_uses_original_floor_anchor():
    bus,ctls=pair()
    original={c.rid:c.pose_anchors['floor'] for c in ctls}
    run_raise(ctls,until=17.8)
    assert all(c.state in ('wait_carry','carry') and c.high_ready for c in ctls)
    for c in ctls:
        assert c.transit.good_frames >= 171 and c.transit.stable(17.2)
        assert c.pose_anchors['floor'] is original[c.rid]
        assert not np.array_equal(c.pose_anchors['high'].mask,original[c.rid].mask)
    run_lower(ctls)
    for c in ctls:
        assert c.failure is None and c.state=='released'
        assert c.floor_return_verified and c.pose_anchors['floor'] is original[c.rid]
        assert any(a.get('servo_id')==1 and a.get('pulse')==2000 for _,a in c.issued_log)
        assert not any('BARRIER_OPEN_TIMEOUT' in str(e) for e in c.events)
        assert c.hold_state(c.look(40.))['decided_by']=='pose_epoch_anchor:floor'


def _no_false_ready(bus, rid, since, prefixes):
    return not any(m['state'].startswith(prefixes) for m in bus.log
                   if m['robot_id']==rid and m['sent_at_s'] >= since)


@pytest.mark.parametrize('phase',['raise','lower'])
@pytest.mark.parametrize('fault',['stall','grip_loss','open_command','edge_only'])
def test_one_side_fault_aborts_without_false_ready_or_carry(phase,fault):
    bus,ctls=pair()
    if phase=='raise':
        run_raise(ctls,fault=fault)
    else:
        run_raise(ctls,until=17.8); run_lower(ctls,fault=fault)
    broken=ctls[1]
    assert broken.state=='failed' and not broken.high_ready
    assert broken.failure.startswith(('TRANSIT_','GRIP_RELATION_'))
    assert not broken.arm.events and not broken.pose_anchors
    since = 2. if phase=='raise' else 23.
    assert _no_false_ready(bus,'r2',since,('carry_ready_','open_ready_'))
    assert not any(a.get('servo_id')==1 and a.get('pulse')==2000 for _,a in broken.issued_log)
    # The healthy partner never carries/opens alone after the abort.
    assert ctls[0].state not in ('carry','released') and _no_false_ready(bus,'r1',since,('open_ready_',))


def test_relative_two_second_raise_offset_waits_without_carry_go():
    bus,ctls=pair()
    run_raise(ctls,fault='offset',until=21.)
    r1,r2=ctls
    assert r1.failure is None and r2.failure is None
    mint={c.rid:next(e['t'] for e in c.events if e['event']=='high_carry_view') for c in ctls}
    assert mint['r2']-mint['r1'] == pytest.approx(2.,abs=.11)
    # No carry GO while one robot is still unverified at HIGH.
    assert not any(e['event']=='barrier_go' and e.get('barrier')=='carry' and e['t'] < mint['r2']
                   for c in ctls for e in c.events)


def test_floor_return_distinguishes_normal_lowering_from_slip():
    # A short own-view disturbance at the floor (partner still settling) is
    # re-checked within the bound; a persistent slip is refused before open.
    _,ok=pair(); run_raise(ok,until=17.8)
    run_lower(ok,floor_glitch=1.)
    assert all(c.state=='released' for c in ok)
    _,bad=pair(); run_raise(bad,until=17.8)
    run_lower(bad,floor_glitch=99.)
    assert bad[1].failure=='FLOOR_RETURN_GRIP_CHANGED' and bad[1].state=='failed'
    assert not any(a.get('servo_id')==1 and a.get('pulse')==2000 for _,a in bad[1].issued_log)


def test_edge_only_high_cannot_mint_anchor_after_observation_gap():
    _,ctls=pair();c=ctls[0]
    c.ep.tick('lift',0.);ctls[1].ep.tick('lift',0.)
    c._lift(0.,True)
    c.arm.tick(c.arm.until)
    c.edge_only=True
    ctls[1].ep.tick('lift',17.2)
    c._lift(17.2,True)
    assert c.state=='failed' and not c.high_ready and 'high' not in c.pose_anchors


def test_unknown_peer_phase_and_stale_image_are_not_ready():
    _,ctls=pair();c=ctls[0]
    ctls[1].ep.tick('aligning',0.);c._lift(0.,True)
    assert c.failure=='TRANSIT_PARTNER_DESYNC'
    monitor=grip.TransitMonitor('raise',0.,{1:1500,**pose.HIGH},[],1.,1)
    obs=c.observation(0.,{1:1500,**pose.HIGH})
    assert not monitor.observe(.3,obs,{1:1500,**pose.HIGH},True)
    assert monitor.failure=='TRANSIT_FRESH_RGB_REQUIRED'
