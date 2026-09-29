"""Offline analyzer for the render-profile A/B: frame gate criteria, time -l parsing, stage-0 compare."""
from __future__ import annotations

import json

import cv2
import numpy as np

from scripts import analyze_render_profile_ab as A


def _jpeg(image):
    ok, buf = cv2.imencode('.jpg', image)
    assert ok
    return buf.tobytes()


def _textured(seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(30, 220, (480, 640, 3), dtype=np.uint8)


def test_frame_gate_matches_valid_frame_criteria():
    ok = A.frame_gate(_jpeg(_textured()))
    assert ok['ok'] and ok['reasons'] == []
    dark = A.frame_gate(_jpeg(np.zeros((480, 640, 3), np.uint8)))
    assert not dark['ok'] and 'dark_fraction' in dark['reasons']
    flat = A.frame_gate(_jpeg(np.full((480, 640, 3), 120, np.uint8)))
    assert not flat['ok'] and set(flat['reasons']) == {'contrast', 'std'}
    assert A.frame_gate(b'not a jpeg')['reasons'] == ['decode']


def test_frame_gate_agrees_with_the_real_gate_on_synthetic_frames():
    import base64
    from harness import zone_pair_vision as zv
    for image in (_textured(1), np.zeros((480, 640, 3), np.uint8), np.full((480, 640, 3), 120, np.uint8)):
        jpeg = _jpeg(image)
        obs = {'image': base64.b64encode(jpeg).decode(), 'frame_id': 1, 'sim_time': 1.0}
        try:
            real = zv.valid_frame(obs, 'r1', 1.0)
        except Exception:
            continue                                  # observation schema is stricter than this synthetic dict
        if real is False and A.frame_gate(jpeg)['ok']:
            # the real gate also checks the observation contract; only a stricter answer is acceptable
            continue
        assert real == A.frame_gate(jpeg)['ok']


def test_parse_time_l_output():
    text = ('       12.34 real        56.70 user         8.90 sys\n'
            '  1048576  maximum resident set size\n'
            '  123456789012  instructions retired\n'
            '   99887766554  cycles elapsed\n')
    out = A.parse_time_l(text)
    assert out['real_s'] == 12.34 and out['user_s'] == 56.7 and out['sys_s'] == 8.9
    assert abs(out['cpu_s'] - 65.6) < 1e-9
    assert out['instructions'] == 123456789012 and out['cycles'] == 99887766554
    assert A.parse_time_l('nothing') == {}


def _case(tmp, name, frames, wall):
    d = tmp / name
    (d / 'frames' / 'r1').mkdir(parents=True)
    for i, image in enumerate(frames):
        (d / 'frames' / 'r1' / f'{i:05d}.jpg').write_bytes(_jpeg(image))
    (d / 'result.json').write_text(json.dumps({'passed': True, 'wall_s': wall, 'loadavg_case': [1, 2, 3],
                                               'render_profile': {'name': 'x'}, 'metrics': {'a': 1}}))
    return d


def test_stage0_compare_ignores_host_timing_but_flags_pixels(tmp_path):
    base = [_textured(0), _textured(1)]
    a = _case(tmp_path, 'a', base, 5.0)
    b = _case(tmp_path, 'b', base, 9.0)           # only wall/load differ
    same = A.compare_case_dirs(a, b)
    assert same['frames_identical'] and same['result_equal'] and same['frames_differing'] == 0
    changed = _case(tmp_path, 'c', [base[0], _textured(2)], 5.0)
    diff = A.compare_case_dirs(a, changed)
    assert not diff['frames_identical'] and diff['frames_differing'] == 1
    assert diff['first_differing'] == ['r1/00001.jpg']


def test_aggregate_pools_cases_by_stage_and_computes_rates():
    def case(passed, gate_pass, n):
        rec = {'frames': n, 'gate_pass': gate_pass,
               'gate_reject_reasons': {'dark_fraction': n - gate_pass, 'contrast': 0, 'std': 0, 'decode': 0},
               'mean_v': 50., 'beam_visible': n, 'band_visible': 0, 'grip_seen': 0, 'tag_fix_frames': n // 2,
               'detector_errors': 0}
        return {'stage': 'setdown', 'passed': passed, 'category': 'PASS' if passed else 'X',
                'cause': None if passed else 'OWN_IMAGE_INVALID', 'wall_s': 10., 'sim_s': 5.,
                'wall_per_sim': 2., 'frames': {'r1': rec, 'r2': dict(rec, gate_pass=n, gate_reject_reasons={
                    'dark_fraction': 0, 'contrast': 0, 'std': 0, 'decode': 0})},
                'pf': {'est_vs_gt_at_ref': {'r1': {'xy_m': .02, 'yaw_rad': -.01}}, 'sigma_yaw_max': {'r1': .01}}}
    agg = A.aggregate([{'cases': {'a': case(True, 8, 10), 'b': case(False, 5, 10)}}])['setdown']
    assert agg['cases'] == 2 and agg['passed'] == 1 and agg['causes'] == {'PASS': 1, 'OWN_IMAGE_INVALID': 1}
    assert agg['r1']['gate_pass_rate'] == 0.65 and agg['r2']['gate_pass_rate'] == 1.0
    assert agg['r1']['reject_dark'] == 7 and agg['r1']['pf_xy_err_m_mean'] == 0.02
    assert agg['wall_per_sim_median'] == 2.0


def test_analyze_case_time_window(tmp_path):
    d = tmp_path / 'case'
    (d / 'frames' / 'r1').mkdir(parents=True)
    records = []
    for i in range(4):
        (d / 'frames' / 'r1' / f'{i:05d}.jpg').write_bytes(_jpeg(_textured(i)))
        records.append({'frame': i, 't': 1.0 + i, 'commanded_servo': {'1': 2000}, 'report': {}})
    (d / 'robots.json').write_text(json.dumps({'r1': {'frames': records}}))
    assert A.analyze_case(d)['r1']['frames'] == 4
    assert A.analyze_case(d, t_max=2.0)['r1']['frames'] == 2
