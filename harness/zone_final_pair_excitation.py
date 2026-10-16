"""V88 acquisition revision 2, adapted from #347/eaeaaff0 and #348.

Several amplitudes and both signs separate gain from static deadband; long
steps identify steady state, PRBS probes dynamics. These are diagnostic
commands, not fitted parameters or a claim that the loaded grasp will hold.
"""
from __future__ import annotations

MAP_ID = 'zone_wide_two_doors_final_v3'
COLLECTION_S = 370.
PERIOD_S = .05
AXES = ('forward', 'left', 'turn')
CLEARANCE = {'minimum_m': .3, 'abort_buffer_m': .05,
             'robot_radius_bound_m': .4, 'max_substep_displacement_m': .01}
# Empty-floor authored reset; loaded stations remain teacher-only. The beam
# centre is chosen in the large room, not at a student checkpoint.
LOADED_BEAM_POSE = [3.55, -.85, 0.]
UNLOADED_POSE = [3.25, -.85, 0.]


def prbs31():
    bits = [1] * 5
    for i in range(26):
        bits.append(bits[i + 2] ^ bits[i])
    return [2*b-1 for b in bits]


def design(check):
    magnitudes = {'calibration-unloaded': [.01, .02, .03],
                  'calibration-fine': [.004, .016, .028],
                  'calibration-loaded': [.006, .015, .025, .04]}[check]
    segments = []
    for axis in AXES:
        for magnitude in magnitudes:
            for sign in (1, -1):
                segments += [{'axis': axis, 'duration_s': 10., 'value': magnitude*sign, 'phase': 'step'},
                             {'axis': axis, 'duration_s': 1., 'value': 0., 'phase': 'coast'}]
        segments += [{'axis': axis, 'duration_s': .5, 'value': magnitudes[1]*bit, 'phase': 'prbs'}
                     for bit in prbs31()]
        segments.append({'axis': axis, 'duration_s': 2.5, 'value': 0., 'phase': 'coast'})
    return {'schema': 'ugrp.final_pair_measurement.v2', 'check': check,
            'method_source': 'PR #347 eaeaaff05553ea02c649b4db9ff82470fe6372b5',
            'model_evidence': 'PR #348 dba873d4b0e77e017373e5539ac077abb7c6f4b1',
            'qualification': 'Hammerstein input design only; no fitted calibration',
            'map_id': MAP_ID, 'magnitudes': magnitudes, 'step_duration_s': 10.,
            'prbs': {'polynomial': 'x^5+x^2+1', 'bits': prbs31(), 'chip_s': .5},
            'motion_start_s': 12. if check == 'calibration-loaded' else 74.,
            'control_period_s': PERIOD_S, 'eval_pose_period_s': PERIOD_S,
            'camera_period_s': .2, 'command_lease_s': PERIOD_S,
            'sim_cap_s': COLLECTION_S, 'reset_cap_s': 5., 'total_including_reset_cap_s': 375.,
            'clearance': dict(CLEARANCE), 'segments': segments}


def motion_events(check):
    plan = design(check)
    step = round(plan['motion_start_s']/PERIOD_S)
    for segment in plan['segments']:
        for _ in range(round(segment['duration_s']/PERIOD_S)):
            for rid in (('r1', 'r2') if check == 'calibration-loaded' else ('r1',)):
                action = {'kind': 'mecanum', **dict.fromkeys(AXES, 0.), 'duration_s': PERIOD_S}
                action[segment['axis']] = segment['value']*(-1 if rid == 'r2' else 1)
                yield {'t': round(step*PERIOD_S, 8), 'robot_id': rid,
                       'phase': check.removeprefix('calibration-')+'_'+segment['phase'], 'action': action}
            step += 1
