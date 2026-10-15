import math
import numpy as np
from sim.settle_pulse import PulseSettler
from harness.reloc10_settle import settle_turn, turn_quantum
from harness.selfmap5_registration import MultiFrameEvidence


class Clear:
    def pose_clear(self,pose): return True


def test_quantized_plant_finishes_instead_of_99_reversals():
    model='s2_pulse_v122_rotL_v1'; q=turn_quantum(model)
    assert q > math.radians(2)
    for target in (-.785,.785):
        s=PulseSettler(math.radians(2)); yaw=0.
        for i in range(30):
            cmd,receipt=settle_turn(s,target-yaw,i*.2,costmap=Clear(),pose=np.zeros(3),motion_model=model)
            if receipt['settled']: break
            assert cmd['kind']=='mecanum'
            yaw += receipt['pulse']['predicted_delta'][2]
        assert receipt['settled'] and i<12 and s.total_reversals<=3
        assert abs(target-yaw)<=receipt['acceptance_band']


def test_blocked_pulse_does_not_accumulate_reversals():
    class Blocked:
        def pose_clear(self,pose): return False
    s=PulseSettler(0.)
    for i in range(10):
        cmd,r=settle_turn(s,(-1)**i*.2,i*.2,costmap=Blocked(),pose=np.zeros(3),motion_model='s2_pulse_v122_rotL_v1')
        assert cmd['kind']=='hold' and not r['settled']
    assert s.pulses==s.total_reversals==0


def test_rolling_evidence_keeps_live_views_beyond_30_seconds_only_when_on():
    line=dict(kind='floor_line',hue=10,endpoints=[[0,0],[1,0]],normal=[0,1])
    a,b=MultiFrameEvidence(),MultiFrameEvidence(); b.rolling=True
    for e in (a,b):
        e.begin(0.); e.add(dict(features=[line]),np.zeros(3),1.)
        e.add(dict(features=[line]),np.zeros(3),32.)
    assert not a.frames and not a.active
    assert [f['t'] for f in b.frames]==[32.]
    b.end(); b.add(dict(features=[line]),np.zeros(3),33.)
    assert [f['t'] for f in b.frames]==[32.,33.]


def test_bundle_toggles_off_unchanged_and_on_recorded():
    from scripts.run_self_map_diagnostic import bundle
    kw=dict(bootstrap='command_prior_v1', initial_sweep='required_360_v1', recovery_profile='selfmap4_recovery_v1',
        revision_gate='selfmap4_revision_gate_v2',multiframe_registration='selfmap4_multiframe_registration_v1',
        correction_safety='selfmap6_correction_safety_v1', active_relocalization='reloc8_active_vision_v1')
    a=bundle('a'*40,93571,60,**kw)
    assert a==bundle('a'*40,93571,60,**kw,reloc10_settle_v1=False,reloc10_registration_v1=False)
    b=bundle('a'*40,93571,60,**kw,reloc10_settle_v1=True,reloc10_registration_v1=True)
    assert b['options']['reloc10_settle_v1'] and b['options']['reloc10_registration_v1']
