"""Reuse egomap32's sealed data and exact fit; user authorizes CW identity."""
from pathlib import Path
import hashlib
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
OLD=ROOT/'experiments/2026-10-08-pulse-rotation-audit'
RAW=Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-audit-v1/measurement')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def dump(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def main():
    for p,h in load(RAW/'artifacts.sha256.json').items():assert sha(RAW/p)==h,p
    frozen=load(OLD/'freeze.json')['files']
    old_fit=OLD/'code/fit.py'
    assert sha(old_fit)==frozen[str(old_fit.relative_to(ROOT))]
    spec=importlib.util.spec_from_file_location('sealed_rotation_fit',old_fit)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    measurements=load(OLD/'results/measurement.json')
    fitted=m.fit(measurements['records'])
    assert fitted==measurements['fit']
    left=fitted['directions']['1']
    assert all(fitted['gates']['1'].values())
    artifact=dict(option='s2_pulse_v122_rotL_v1',profile='0:turn:0.35:0.10',gain=left['gain'],
        base_model_sha256=measurements['base_model_sha256'],cw_gain=1.,
        training_repeats=[1,2,3],check_repeats=[4,5],condition='unloaded SEARCH, servo_stiffness real_v1',
        measurement_source=measurements['source'],
        method='egomap32 unchanged per-pulse normalized zero-intercept least squares; left only',
        sources={str(p.relative_to(ROOT)):sha(p) for p in [old_fit,OLD/'results/measurement.json']},
        raw_manifest=dict(path=str(RAW/'artifacts.sha256.json'),sha256=sha(RAW/'artifacts.sha256.json')),
        scope='runtime own issued commands only; no live GT; CW/loaded/XY/variance unchanged')
    report=dict(left=left,left_gate=fitted['gates']['1'],right=dict(gain=1.,byte_identity_required=True,
        check_rmse_deg_per_pulse_off=fitted['directions']['-1']['check_rmse_deg_per_pulse_off'],
        check_rmse_deg_per_pulse_on=fitted['directions']['-1']['check_rmse_deg_per_pulse_off']),
        user_authorized_rule='CW original identity passes; egomap32 bilateral failure preserved',eligible=True)
    dump(EXP/'results/calibration.json',report)
    dump(ROOT/'harness/data/s2_pulse_v122_rotL_v1.json',artifact)
    print('left gain',left['gain'],'calibration sha256',sha(ROOT/'harness/data/s2_pulse_v122_rotL_v1.json'))


if __name__=='__main__':main()
