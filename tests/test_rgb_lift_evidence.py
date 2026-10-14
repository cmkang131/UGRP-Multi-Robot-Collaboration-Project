"""Shared crate-v3 policy and actual GCP solo frames; no physics/render."""
from pathlib import Path

import numpy as np
import pytest

from scripts.replay_solo_lift import replay
from sim.rgb_lift_evidence import confirm_parts_v3


def crate_frames():
    before = np.zeros((100, 100, 3), np.uint8)
    before[20:50, 20:50, 0] = 255  # rigid lug
    before[50:80, 20:80, 1] = 255  # separate body
    after = before.copy()
    after[..., 1] = 0
    after[50:80, 10:90, 1] = 255   # rotates: extent changes .20, centre stable
    return before, after


def check(before, after, settled):
    commands = [{'t': t, 'pwm': {1: 1500, 3: arm, 4: 2100, 5: 2400, 6: 1500},
                 'wheels': [0]*4} for t, arm in [(0., 1200), (1.7, 750)]]
    return confirm_parts_v3(before, after, settled=settled, commands=commands,
                            masks=lambda f: (f[..., 0] > 0, f[..., 1] > 0), names=('lug', 'pink'),
                            relative_to={'pink': 'lug'}, rule='crate_rgb_lift_v3')


def test_body_rotation_keeps_rigid_lug_requirement_and_relative_drop_veto():
    b, a = crate_frames()
    assert check(b, a, a)['verdict'] == 'confirmed'
    shifted_lug = a.copy(); shifted_lug[..., 0] = np.roll(a[..., 0], 10, axis=0)
    assert check(b, shifted_lug, a)['verdict'] == 'undetermined'
    dropped_body = a.copy(); dropped_body[..., 1] = np.roll(a[..., 1], 10, axis=0)
    assert check(b, a, dropped_body)['verdict'] == 'not_confirmed'


@pytest.mark.parametrize('sample', ['after', 'settled'])
def test_exact_repeated_before_blocks_even_with_valid_issued_lift(sample):
    b, a = crate_frames()
    out = check(b, b if sample == 'after' else a, b if sample == 'settled' else a)
    assert out['verdict'] == 'undetermined' and 'identical' in out['reason']


def test_disappearance_still_records_both_comparisons_and_all_parts():
    b, a = crate_frames()
    lost = np.zeros_like(a)
    out = check(b, lost, a)
    assert out['verdict'] == 'not_confirmed'
    assert out['comparisons'][0]['parts']['lug']['after'] is None
    assert out['comparisons'][0]['parts']['lug']['after_pixels'] == 0
    assert out['comparisons'][0]['parts']['lug']['area_ratio'] == 0.
    assert out['comparisons'][0]['parts']['pink']['after'] is None
    assert out['comparisons'][1]['parts']['pink']['area_ratio'] == pytest.approx(4/3)


def test_all_six_real_sequences_keep_unobservability_and_same_image_denominator():
    manifest = Path(__file__).parent/'fixtures/solo_rgb_lift_v3/manifest.json'
    result = replay(manifest)
    assert result['ready'] is False
    assert result['totals'] == {'N': 6, 'verified_images': 18, 'recovered': 0, 'failed_N': 4,
                                'preserved': 2, 'passed_N': 2, 'same_image_false_positive': 0,
                                'v3_confirmed': 2, 'v3_not_confirmed': 2, 'v3_undetermined': 2}
    for row in result['runs']:
        assert len(row['v3']['comparisons']) == 2
        assert all(row['kind'] in c['parts'] for c in row['v3']['comparisons'])
