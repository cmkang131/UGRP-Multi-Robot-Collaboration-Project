"""Real archived RGB regression, separate presence and metric grasp evidence."""
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from harness.e2e_color_detection import detect
from scripts.evaluate_e2e_color_detector import evaluate

ROOT = Path('experiments/2026-10-14-e2e18-color-detector')


@pytest.fixture(scope='module')
def replay():
    return evaluate(ROOT)


def test_real_rgb_cohort_recall_false_positives_and_legacy_regression(replay):
    old = replay['summary']['anchor_v2']
    assert [old['positives'][c]['metric_grasp_admitted'] for c in ('teal','blue')] == [14,7]
    assert old['false_grasp_admission'] == 0
    for mode in ('component_v3', 'component_short_v3'):
        result = replay['summary'][mode]
        for color in ('teal', 'blue'):
            counts = result['positives'][color]
            assert counts['n'] >= 30
            assert counts['band_presence'] / counts['n'] >= .9
        assert result['negative_n'] >= 30
        assert result['false_band_presence'] / result['negative_n'] <= .05
        assert result['false_grasp_admission'] == 0


def test_real_large_band_support_fix_and_clipped_band_not_grasp_permission(replay):
    by = {r['id']:r for r in replay['records']}
    clear = by['064']['results']  # v423, r2, 45.3 SIM s
    assert clear['anchor_v2']['reason'] == 'OWN_COLOR_GEOMETRY_UNRESOLVED'
    assert clear['component_short_v3']['end_visible']
    clipped = by['058']['results']['component_short_v3']
    assert clipped['band_visible'] and not clipped['end_visible']
    far = by['417']['results']['component_short_v3']
    assert far['band_visible'] and not far['end_visible']


def test_no_lime_context_and_other_color_are_not_assigned_band():
    image = np.zeros((480,640,3), np.uint8)
    image[100:150,100:150] = [255,0,0]
    assert not detect(image, 'blue')[1]['band_visible']
    image = cv2.imread(str(ROOT/'frames/064.jpg'))
    assert not detect(image, 'teal')[1]['band_visible']


def test_candidate_registration_and_default_off():
    from scripts.run_e2e_stage_probe import MODES
    from harness.e2e_end_colors import install
    from types import SimpleNamespace
    tr=SimpleNamespace();install(tr);assert not vars(tr)
    for version in (430,431):
        assert MODES[f'v{version}']=='track_gaze_v1'
        w=json.loads(Path(f'configs/simulation_workflows.d/e2e18_v{version}.json').read_text())['workflows'][0]
        assert w['id']==f'e2e18-v{version}'
