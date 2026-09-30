"""Authored acquisition, with no measured value feeding command selection.

Loaded collection starts at teacher staging stations. A fixed grasp attempt is
followed by the requested motion; contact/load validity is decided offline.
Changing camera pan while holding can drop a beam: those failed samples remain
in the raw record and MUST NOT be fitted as successful loaded measurements.
"""
from __future__ import annotations

from harness import zone_final_pair_contract as contract
from harness import visual_arm_v3 as arm
from harness.zone_final_pair_skill import task
from harness.zone_final_pair_vision import grasp_postures


def schedule(check):
    if check not in contract.CHECKS[2:]:
        raise ValueError('not a collection check')
    protocol = contract.base.read(contract.ROOT / 'configs/final_environment_measurement_v1.json')
    loaded = check == 'calibration-loaded'
    events = []
    def add(t, phase, rid, action):
        events.append({'t': float(t), 'phase': phase, 'robot_id': rid, 'action': action})
    if loaded:
        # Teacher stage at static catalogue stations, then actual open->close
        # and lift actuators (no weld, no online success-based adjustment).
        hover, descent = grasp_postures()
        grasp = descent[-1]
        for rid in contract.ROBOTS:
            for t, pose in ((0., {**grasp, 1: 2000}), (2., {1: 1500}), (4., hover)):
                for sid, pulse in pose.items():
                    add(t, 'teacher_grasp_attempt', rid, {'kind': 'look', 'pan_pulse': pulse}
                        if sid == 6 else {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
        # Loaded camera sweep samples the real grasp/lift trajectory and the
        # registered pan directions. It never substitutes unloaded frames.
        pans = [e['actions'][-1]['pan_pulse'] for e in protocol['events'][:8]]
        for k, pan in enumerate(pans):
            for rid in contract.ROBOTS:
                add(48.+3*k, 'loaded_camera', rid, {'kind': 'look', 'pan_pulse': pan})
        for rid in contract.ROBOTS:
            add(80., 'post_loaded_open', rid, {'kind': 'arm', 'servo_id': 1, 'pulse': 2000})
    else:
        for event in protocol['events']:
            if event['t'] >= 72:
                continue
            for action in event['actions']:
                add(event['t'], event['phase'], 'r1', action)
        from harness.owncam_pair_beam_v2 import pose_of
        if check == 'calibration-fine':
            for sid, pulse in pose_of('p45').items():
                add(70., 'fine_alignment_pose', 'r1', {'kind': 'look', 'pan_pulse': pulse}
                    if sid == 6 else {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
        # Extra fixed close views needed by the pair pixel algorithm, in the
        # same bounded run; all intermediate issued poses are also labelled.
        hover, descent = grasp_postures()
        catalogue = [('hover_open', {**hover, 1: 2000}), ('grasp_open', {**descent[-1], 1: 2000}),
                     ('p45', pose_of('p45')), ('inspect', pose_of('inspect')), ('search', pose_of('search'))]
        for k, (name, pose) in enumerate(catalogue):
            for sid, pulse in pose.items():
                add(102.+3*k, 'camera_'+name, 'r1', {'kind': 'look', 'pan_pulse': pulse}
                    if sid == 6 else {'kind': 'arm', 'servo_id': sid, 'pulse': pulse})
    for event in protocol['events']:
        if event['t'] < 72:
            continue
        for rid in (contract.ROBOTS if loaded else ('r1',)):
            action = dict(event['actions'][0])
            scale = .5 if check == 'calibration-fine' else 1.
            for axis in ('forward', 'left', 'turn'):
                # Opposed carriers translate together; yaw is deliberately
                # counter-signed as a fixed pair diagnostic, not a success.
                action[axis] *= scale * (-1 if rid == 'r2' else 1)
            add(event['t']-(60. if loaded else 0.), check.removeprefix('calibration-')+'_motion', rid, action)
    return sorted(events, key=lambda x: x['t'])


def teacher_stations(static):
    from sim.zone_model_conventions import station_offset
    pose = task(static)['beam_pose']
    return {rid: [pose[0]+offset[0], pose[1]+offset[1], offset[2]]
            for rid, role in zip(contract.ROBOTS, ('end_neg', 'end_pos'))
            for offset in [station_offset(static, 'long_beam', role)]}
