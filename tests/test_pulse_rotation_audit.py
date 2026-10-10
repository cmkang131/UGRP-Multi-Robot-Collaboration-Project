from collections import Counter
import json
from scripts.run_pulse_rotation_audit import schedule, acquire


def test_preregistered_balanced_clock_schedule():
    blocks,commands,ticks=schedule()
    assert len(blocks)==20 and len(commands)==110 and ticks==1200
    assert Counter((b['mode'],b['sign']) for b in blocks)=={
        ('single',1):5,('single',-1):5,('continuous',1):5,('continuous',-1):5}
    assert all(b['split']==('fit' if b['repeat']<=3 else 'check') for b in blocks)
    for b in blocks:
        assert all(commands[b['start_tick']+4*j]['turn']==b['sign']*.35 for j in range(b['pulses']))
        assert not any(t in commands for t in range(b['end_tick'],b['end_tick']+36))


def test_acquisition_does_not_receive_measurements(tmp_path):
    class Backend:
        def __init__(self,*args,**kwargs):self.now=1.3
        def reset(self,*args):pass
        def set_deadline(self,*args):pass
        def issue(self,*args):pass
        def capture(self):return {'forbidden_truth':object()}
        def eval_sample(self):return {'forbidden_truth':object()}
        def advance_to(self,t):self.now=t
        def close(self):pass
    result=acquire(tmp_path/'fake','f'*40,Backend)
    assert result['status']=='RECORDED' and result['samples']==1201
    assert result['total_sim_s']-result['start_sim_s']==60.
    bundle=json.loads((tmp_path/'fake/bundle.json').read_text())
    assert bundle['options']['servo_stiffness']=='real_v1'
    assert bundle['task']['seed']==32001


def test_gain_only_fit_rejects_mode_dependent_response():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'experiments/2026-10-08-pulse-rotation-audit/code/fit.py'
    spec=importlib.util.spec_from_file_location('rotation_fit',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records=[]
    for b in schedule()[0]:
        pred=b['sign']*5*b['pulses']
        records.append(dict(**b,predicted_deg=pred,actual_deg=pred*(1.1+.001*b['repeat'])))
    r=module.fit(records)
    assert r['eligible']
    assert abs(r['directions']['1']['gain']-1.102)<1e-12
    for row in records:
        if row['mode']=='continuous':row['actual_deg']*=1.2
    r=module.fit(records)
    assert not r['eligible']
    assert not r['gates']['1']['single_continuous_agree']
