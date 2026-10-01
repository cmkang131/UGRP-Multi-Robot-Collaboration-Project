"""Offline calibration regressions; physics/render/model/network forbidden."""
import copy
import hashlib
import json
import socket
import sys

import numpy as np
import pytest

from scripts import fit_final_environment_unloaded as fit

RECORD = fit.ROOT / 'experiments/2026-10-01-final-env-v87-calibration-fit'
FIT_RECORD_COMMIT = 'a5cc1402049a249253893762e1ca347e448a5f3f'


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    for name in ('mujoco', 'torch', 'torchvision', 'sim.multi_masterpi_production',
                 'sim.final_environment_floor_light'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('network forbidden'))


def test_contiguous_renewals_are_not_four_starts():
    commands = []
    for axis in range(3):
        for sign in (1, -1):
            start = 72 + len(commands) / 4 * 5
            for i in range(4):
                u = np.eye(3)[axis] * .03 * sign
                commands.append({'kind': 'mecanum', 't': start + i * .25, 'duration_s': .25,
                                 **dict(zip(('forward', 'left', 'turn'), u))})
    blocks = fit.blocks(commands)
    assert len(blocks) == 6
    assert all(b['end'] - b['start'] == 1. and b['command_count'] == 4 for b in blocks)
    assert [float(b['u'][i // 2]) for i, b in enumerate(blocks)] == [.03, -.03] * 3
    commands[-1]['t'] += .05
    with pytest.raises(ValueError, match='six contiguous'):
        fit.blocks(commands)


def test_exact_response_continuity_and_coast():
    tau, stop, duration = .3, .08, 1.
    t = np.array([0., duration, duration + 10.])
    out = fit.response(t, duration, tau, stop)
    assert out[0] == 0.
    assert out[1] == pytest.approx(duration - tau * (1 - np.exp(-duration / tau)))
    assert out[2] - out[1] == pytest.approx(stop * (1 - np.exp(-duration / tau)))
    assert abs(fit.response(duration - 1e-8, duration, tau, stop) - fit.response(duration + 1e-8, duration, tau, stop)) < 2e-8


@pytest.mark.parametrize('axis', [0, 1, 2])
def test_known_positive_negative_gain_and_lag_recovered(axis):
    # Analytical synthetic target, not a SIM run. Both signs + observed stop.
    times = np.arange(21) * .2
    tau, stop, gain = .3, .08, 1.5
    distance = np.where(times <= 1., times - tau * (1 - np.exp(-times / tau)),
                        1. - tau * (1 - np.exp(-1. / tau))
                        + stop * (1 - np.exp(-1. / tau)) * (1 - np.exp(-(times - 1.) / stop)))
    windows = []
    for sign in (1., -1.):
        body = np.zeros((21, 3))
        body[:, axis] = sign * .03 * gain * distance
        windows.append({'axis': axis, 'u': np.eye(3)[axis] * sign * .03, 'times': times,
                        'duration': 1., 'body': body, 'start': 0., 'command_count': 4})
    got = fit.fit_axis(windows, axis)
    assert got['gain'] == pytest.approx(gain)
    assert got['tau_s'] == tau and got['tau_stop_s'] == stop
    assert got['rms'] < 1e-14 and got['gain_lag_identified'] and not got['degenerate']
    for window in windows:
        window['body'][:] = 0
    got = fit.fit_axis(windows, axis)
    assert got['degenerate'] and not got['gain_lag_identified']


def test_camera_optical_axes_full_chassis_transform_and_height():
    angle = .4
    base = np.array([[np.cos(angle), 0., np.sin(angle)], [0., 1., 0.], [-np.sin(angle), 0., np.cos(angle)]])
    origin, position = np.array([.15, -.02, .18]), np.array([2., -1., .032])
    optical = np.array([[0., 0., 1.], [-1., 0., 0.], [0., -1., 0.]])
    label = {'base_position_m': position, 'base_rotation': base,
             'camera_position_m': position + base @ origin,
             'camera_rotation': base @ optical @ np.diag([1., -1., -1.])}
    got_o, got_r = fit.camera_in_chassis(label)
    np.testing.assert_allclose(got_o, origin)
    np.testing.assert_allclose(got_r, optical, atol=1e-15)
    label['base_rotation'] = np.zeros((3, 3))
    with pytest.raises(ValueError, match='invalid recorded'):
        fit.camera_in_chassis(label)


def test_visit_end_frame_precedes_next_command_and_reference_pan_is_repeated():
    protocol = {'events': []}
    labels, frames = [], []
    # An eight-visit synthetic sweep; 1500 appears twice. No renderer.
    pans = (1500, 1230, 970, 700, 1770, 2030, 2300, 1500)
    for j, pan in enumerate(pans):
        actions = [{'kind': 'arm', 'servo_id': k, 'pulse': v} for k, v in ((1, 2000), (3, 740), (4, 2320), (5, 1320))]
        actions.append({'kind': 'look', 'pan_pulse': pan})
        protocol['events'].append({'t': j * 3., 'phase': 'search', 'actions': actions})
        for offset in (1., 2., 3.):
            yaw = (pan - 1500) * 2e-5
            rb = np.array([[np.cos(yaw), -np.sin(yaw), 0.], [np.sin(yaw), np.cos(yaw), 0.], [0., 0., 1.]])
            frames.append({'t': j * 3. + offset, 'frame_id': len(frames),
                           'commanded_servo': {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': pan}})
            labels.append({'base_rotation': rb.tolist(), 'base_position_m': [0., 0., .03],
                           'camera_rotation': (rb @ np.diag([1., -1., -1.])).tolist(),
                           'camera_position_m': (rb @ np.array([.15, 0., .18]) + [0., 0., .03]).tolist()})
    # The recorder starts with an initial frame before the t=0 issued command.
    frames.insert(0, {**frames[0], 't': 0., 'frame_id': -1})
    labels.insert(0, copy.deepcopy(labels[0]))
    camera, pan, visits = fit.camera_fit(frames, labels, protocol, 1.)
    assert len(visits) == 8 and len(camera) == 7
    assert camera['740,2320,1320,1500']['n'] == 6
    assert pan['rad_per_pwm'] == pytest.approx(2e-5)
    assert all(v['n'] == 3 for v in visits)


def test_no_writing_inside_or_over_collection(tmp_path):
    with pytest.raises(ValueError, match='disjoint'):
        fit.run(tmp_path, tmp_path / 'derived')
    with pytest.raises(ValueError, match='disjoint'):
        fit.run(tmp_path / 'raw', tmp_path)


def test_p03_status_gate_rejects_partial_even_with_otherwise_complete_fields(tmp_path):
    from harness import zone_final_environment as env
    from tests.test_zone_final_environment_runnable import synthetic_measurement, MAPS
    path, value = synthetic_measurement(tmp_path)
    assert env.measured_calibration(path, env.sha(path), MAPS[0])['status'] == 'MEASURED_SIM'
    value['status'] = 'PARTIAL_UNLOADED_SIM'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='combination mismatch'):
        env.measured_calibration(path, env.sha(path), MAPS[0])


def test_v87_p03_refuses_actual_partial_before_physics_or_factory(tmp_path, monkeypatch):
    from scripts import run_final_environment_floor_light as runner
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(runner, 'check_source', lambda sha: sha)
    monkeypatch.setattr(VisionWorkerClient, '__init__', lambda *a, **k: pytest.fail('student worker forbidden'))
    path = RECORD / 'calibration_partial.json'
    with pytest.raises(ValueError, match='FINAL_V3_PAIR_CHAIN_ADAPTER_REQUIRED'):
        runner.main(['--check', 'p03', '--expected-source-sha', fit.SOURCE_SHA,
                     '--execute', '--output', str(tmp_path / 'p03'), '--calibration', str(path),
                     '--calibration-sha256', fit.sha(path)])
    assert not (tmp_path / 'p03').exists()


def test_partial_artifact_provenance_unknowns_and_proper_rotations():
    from scripts.zone_pair_registered_source import committed_blob
    def recorded_blob(path):
        return committed_blob(str(fit.ROOT), FIT_RECORD_COMMIT, path)

    for name in ('calibration_partial.json', 'input_manifest.tsv'):
        path = RECORD / name
        assert path.read_bytes() == recorded_blob(path.relative_to(fit.ROOT).as_posix())
    value = fit.read(RECORD / 'calibration_partial.json')
    assert value['status'] == 'PARTIAL_UNLOADED_SIM'
    assert value['measurement_manifest_sha256'] == fit.sha(RECORD / 'input_manifest.tsv')
    assert value['contract_sha256'] == hashlib.sha256(recorded_blob(fit.CONTRACT)).hexdigest()
    assert value['source_sha'] == fit.SOURCE_SHA
    assert value['params']['motion_loaded'] is None
    assert value['params']['motion_profiles']['fine'] is None
    assert value['pan_base_yaw']['loaded'] is None and value['camera_models']['loaded'] is None
    assert set(value['missing_reasons'].values()) == {fit.MISSING}
    motion = value['params']['motion']
    assert motion['gain'][0][0] is None and motion['gain'][1][1] is None
    assert motion['tau_stop_axis_s'] == [None, None, None]
    assert len(value['camera_models']['unloaded']) == 21
    for record in value['camera_models']['unloaded'].values():
        r = np.array(record['rotation'])
        np.testing.assert_allclose(r.T @ r, np.eye(3), atol=1e-8)
        assert np.linalg.det(r) == pytest.approx(1.)
    # Audit the fit record's Git objects, not later main (notably PHYSICS_HANDOFF).
    # The fitter was added after the measurement SOURCE_SHA, so use its own
    # recorded commit. Raw remains optional for CI.
    for line in (RECORD / 'input_manifest.tsv').read_text().splitlines()[1:]:
        scope, path, sha, size = line.split('\t')
        if scope == 'repo':
            data = recorded_blob(path)
            assert hashlib.sha256(data).hexdigest() == sha, path
            assert len(data) == int(size), path


def test_ci_collects_offline_fit_once():
    from scripts.run_ci_tests import collect_test_files, TEST_PATTERNS
    assert collect_test_files(fit.ROOT, TEST_PATTERNS).count('tests/test_final_environment_unloaded_fit.py') == 1
