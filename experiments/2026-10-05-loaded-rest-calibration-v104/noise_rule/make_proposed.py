#!/usr/bin/env python3
"""PROPOSED calibration = a04371f6 file with ONLY params.motion_loaded.noise_abs/noise_rel (forward, left; turn index 2 = parent)
and their two field_provenance labels changed.  Not applied anywhere."""
import json, hashlib, sys
sys.dont_write_bytecode = True
OUT = '/Users/changmin/projects/ugrp/outputs/v98-loaded-noise-rule-20261005'
BASE = '/Users/changmin/projects/ugrp-wt/pair-carry-highpose/experiments/2026-10-05-loaded-rest-calibration-v104/products/calibration_dev_pilot_loaded_v102_rest_v104.json'
raw = open(BASE).read()
assert hashlib.sha256(raw.encode()).hexdigest() == 'a04371f614bd7f6f7583ef4f4121abce1c337fd5652899dbfe0fe6df1703f926'
cal = json.loads(raw)
prop = json.load(open(f'{OUT}/fit_noise_loaded_result.json'))['proposed']
ml = cal['params']['motion_loaded']
assert prop['abs'][2] == ml['noise_abs'][2] and prop['rel'][2] == ml['noise_rel'][2]
ml['noise_abs'], ml['noise_rel'] = prop['abs'], prop['rel']
for k in ('noise_abs', 'noise_rel'):
    cal['field_provenance'][f'params.motion_loaded.{k}'] = 'measured_loaded_noise_v105_PROPOSED'
text = json.dumps(cal, indent=1, sort_keys=True, ensure_ascii=False) + '\n'
name = 'calibration_dev_pilot_loaded_v102_rest_v104_noise_v105_PROPOSED.json'
open(f'{OUT}/{name}', 'w').write(text)
print(name, hashlib.sha256(text.encode()).hexdigest())
