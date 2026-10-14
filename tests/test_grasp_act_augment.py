"""Augmentation toggle: identity equals the deployed tensor path; ranges bounded."""
import io
import numpy as np
import pytest
torch = pytest.importorskip('torch')
from PIL import Image
from harness.grasp_act_augment import augmented_tensor, draw, IDENTITY, RANGES


def jpeg():
    a = (np.indices((48, 64)).sum(0) % 255).astype(np.uint8)
    b = io.BytesIO(); Image.fromarray(np.stack([a, a[::-1], 255-a], -1)).save(b, format='JPEG'); return b.getvalue()


def test_identity_matches_deployed_tensor():
    pytest.importorskip('lerobot')
    from harness.grasp_act import tensor
    assert torch.equal(augmented_tensor(jpeg(), 96, IDENTITY), tensor(jpeg(), 'smoke'))


def test_draw_ranges_and_geometry_limits():
    rng = np.random.default_rng(1)
    for _ in range(200):
        p = draw(rng)
        assert abs(p['brightness']-1) <= RANGES['brightness'] and abs(p['hue']) <= RANGES['hue']
        assert max(map(abs, p['shift'])) <= RANGES['shift_frac']
    x = augmented_tensor(jpeg(), 96, draw(np.random.default_rng(3)))
    assert x.shape == (3, 96, 96) and torch.isfinite(x).all()


def test_augmented_differs_but_same_params_same_output():
    p = draw(np.random.default_rng(7)); p['brightness'] = 1.2
    a, b = augmented_tensor(jpeg(), 96, p), augmented_tensor(jpeg(), 96, p)
    assert torch.equal(a, b) and not torch.equal(a, augmented_tensor(jpeg(), 96, IDENTITY))
