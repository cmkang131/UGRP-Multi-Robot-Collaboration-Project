"""Synthetic own inputs only: no physics, render, model or evaluation truth."""
import hashlib

import cv2
import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_rollout import OwnHistory
from harness.beamact4_execution import PairChunkExecutor
from harness.beamact5_ready import ReadyWitness, IMAGE_HW
from harness.beamact_pair_student import (StudentBarrier, RearmingStartSync,
    STAGE_MODE, RECOVERY_MODE)
from harness.beamact_replay import protocol_class


STATION = .2032


def command(t=0., grip=2000):
    return dict(t=t, wheels=[.35]*4, duration_s=[.1]*4,
        pwm={'1':grip, '3':800, '4':2400, '5':1320, '6':1500})


def jpeg(value):
    ok, buf = cv2.imencode('.jpg', np.full((*IMAGE_HW, 3), value, np.uint8))
    assert ok
    return buf.tobytes()


def own_observation(t, payload):
    refs = []
    for i, lag in enumerate(c.RGB_LAGS_S):
        sha = hashlib.sha256(payload).hexdigest() if lag == 0. else '0'*64
        refs.append(dict(path=f'rgb/r1/{i:04d}.jpg', sha256=sha,
            t=t-lag, robot_id='r1'))
    issued = [command(t=t-1. + i*.03) for i in range(c.HISTORY)]
    return dict(schema=c.SCHEMA, robot_id='r1', sample_id=f'own:{t}', t=t,
        skill='grasp', object_kind='long_beam', role='teal', rgb=refs,
        issued=issued, skill_elapsed_s=0., pwm_elapsed_s=0.,
        destination_zone='none')


def aligned_observer(station=STATION, grip_y=0.):
    def observe(image, servo):
        assert servo[1] == 2000
        return dict(visible=True, end_visible=True,
            grip_base_m=[station, grip_y], axis_heading_rad=0.,
            lateral_spread_m=.01, visible_length_m=.2, grip_source='synthetic')
    return observe


def aligned_band(points=10):
    def evidence(image, servo, role, grip, axis):
        return {role+'_points': points, role+'_distance_m': .01,
                role+'_extent_along_m': .03, role+'_centroid_m': [STATION, 0.],
                'opposite_points': 10, 'opposite_distance_m': .5,
                'opposite_extent_along_m': .03,
                'opposite_centroid_m': [STATION+.5, 0.]}
    return evidence


def feed(witness, t, payload):
    observation = own_observation(t, payload)
    return witness.ready(observation, [jpeg(0)]*3 + [payload])


def test_ready_witness_needs_two_fresh_aligned_own_frames_and_fails_closed():
    witness = ReadyWitness(observer=aligned_observer(),
        band_evidence=aligned_band(), station_radius_m=STATION)
    ready, first = feed(witness, 10., jpeg(10))
    assert not ready and first['aligned'] and first['streak'] == 1
    ready, second = feed(witness, 10.1, jpeg(11))
    assert ready and second['reason'] == 'ALIGNED_AND_ASSIGNED_END_BAND_VISIBLE'
    assert (second['frame_t'], second['streak'], second['robot_id']) == (10.1, 2, 'r1')
    # A repeated frame may not count twice toward the two-frame streak.
    ready, duplicate = feed(witness, 10.1, jpeg(11))
    assert not ready and duplicate['streak'] == 1
    ready, _ = feed(witness, 10.2, jpeg(12))
    assert ready
    ready, _ = feed(witness, 10.3, jpeg(13))
    assert ready
    # A frame gap beyond the existing image staleness bound resets the streak.
    ready, gap = feed(witness, 10.6, jpeg(14))
    assert not ready and gap['streak'] == 1
    ready, _ = feed(witness, 10.7, jpeg(15))
    assert ready

    misaligned = ReadyWitness(observer=aligned_observer(grip_y=.02),
        band_evidence=aligned_band(), station_radius_m=STATION)
    ready, decision = feed(misaligned, 20., jpeg(20))
    assert not ready and decision['streak'] == 0
    assert decision['reason'] == 'RELATIVE_ALIGNMENT_OUTSIDE_T08B'

    no_band = ReadyWitness(observer=aligned_observer(),
        band_evidence=aligned_band(points=0), station_radius_m=STATION)
    ready, decision = feed(no_band, 30., jpeg(30))
    assert not ready and decision['reason'] == 'ASSIGNED_END_BAND_NOT_VISIBLE'

    wrong_camera = ReadyWitness(observer=aligned_observer(),
        band_evidence=aligned_band(), station_radius_m=STATION,
        camera_profile='other')
    ready, decision = feed(wrong_camera, 40., jpeg(40))
    assert not ready and decision['reason'] == 'UNSUPPORTED_CAMERA_PROFILE'


def test_pending_ready_is_frozen_and_pre_go_withdrawal_rearms():
    previous = command()
    r1 = StudentBarrier(stage_mode=STAGE_MODE)
    assert r1.propose(command(t=.1), False, previous, stage='ready') and r1.ready
    sync = RearmingStartSync(('r1', 'r2'), {'r1': 0., 'r2': 0.},
        protocol_class())
    permits = sync.tick({'r1': r1.ready, 'r2': False}, .1)
    assert not any(permits.values())
    # The original READY command is held; a later command cannot replace it.
    value, done = r1.issue(.2, previous, command(t=.2, grip=1500), False, False)
    assert not done and value['wheels'] == [0.]*4
    assert value['pwm'] == previous['pwm']
    before_withdrawal = len(sync.events)
    assert not r1.propose(previous, False, previous, stage='alignment')
    assert r1.pending is None and not r1.ready
    sync.tick({'r1': False, 'r2': False}, .3)
    assert [e['event'] for e in sync.events[before_withdrawal:]] == [
        'READY_withdrawn_rearm']
    assert [e['event'] for e in sync.events].count('GO') == 0
    # A new READY after withdrawal honors the unchanged start delay.
    assert r1.propose(previous, False, previous, stage='ready') and r1.ready
    assert not any(sync.tick({'r1': True, 'r2': True}, .4).values())
    permits = sync.tick({'r1': True, 'r2': True}, .5)
    assert permits == {'r1': True, 'r2': True}
    assert [e['event'] for e in sync.events].count('GO') == 1


def test_done_recovery_retracts_done_over_multiple_ticks_while_peer_moves():
    flags = iter([True, False, True])
    calls = []
    def predict(observation, pictures):
        calls.append(observation['t'])
        done = next(flags)
        return np.tile(c.encode_action(command(t=observation['t']), done=done),
                       (c.CHUNK, 1)).tolist()
    history = OwnHistory('r1', 'done-multitick', command())
    executor = PairChunkExecutor(predict, done_recovery=RECOVERY_MODE)
    peer = PairChunkExecutor(lambda observation, pictures:
        np.tile(c.encode_action(command(t=observation['t']), done=False),
                (c.CHUNK, 1)).tolist(), done_recovery=RECOVERY_MODE)
    peer_history = OwnHistory('r2', 'done-multitick', command())
    peer_done, done_times = False, {}
    seen, values = [], []
    for t in (0., .1, .2, .3):
        observation, pictures, _ = history.observe(t,
            b'rgb' + bytes([int(t*10)]), skill='grasp',
            object_kind='long_beam', role='teal')
        if t == .3:
            # A protocol hold/rejection re-predicts from issued history.
            executor.discard_pending()
        value, done = executor.step(observation, pictures)
        history.issue(value)
        seen.append(done);values.append(value['wheels'][0])
        if done:
            done_times['r1'] = t
        else:
            done_times.pop('r1', None)
        peer_observation, peer_pictures, _ = peer_history.observe(t,
            b'rgb2' + bytes([int(t*10)]), skill='grasp',
            object_kind='long_beam', role='blue')
        peer_value, peer_done_tick = peer.step(peer_observation, peer_pictures)
        peer_history.issue(peer_value)
        peer_done = peer_done_tick
        assert not (peer_done and len(done_times) == 2)
    # After done, the next tick re-infers and retracts it; the following tick
    # keeps moving from the fresh chunk while the peer is still incomplete.
    # A later fresh inference may request done again without permanent absorption.
    assert calls == [0., .1, .3]
    assert seen == [True, False, False, True]
    assert values[1] > 0. and values[2] > 0.
    assert done_times == {'r1': .3} and not peer_done
