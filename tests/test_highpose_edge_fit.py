"""v98 robust beam-edge fit (``harness/zone_pair_highpose_edge``) on the HIGH frames recorded by probe d5ca2ec3.

In that probe both robots reached HIGH, but the shared ``edge_line`` returned None on every HIGH frame (a few right-end
columns read the upper band's edge and tilt the least-squares line), so ``wait_carry`` timed out. Recorded input:
``tests/fixtures/highpose_edge/columns_d5ca2ec3.json`` holds the column samples of all 464 commanded-HIGH frames per
robot (with the frame sha256 list) and four recorded JPEGs (their sha256 is in the table). When the raw probe output
is on disk (``outputs/`` of this checkout or ``$UGRP_PRIMARY_OUTPUTS``), every raw frame is replayed as well.
"""
import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from harness import own_beam_edge as be
from harness import zone_pair_highpose as pose
from harness import zone_pair_highpose_edge as ed

FIX = Path(__file__).parent/'fixtures'/'highpose_edge'
XS = be.COLUMNS.astype(float)
LATE = 84.75        # HIGH reached on the arm (commanded 76.75 s + 8 s settle): the PR's 302 frames start one frame later
RUN = 'v98-dev-probe-align_to_carry-d5ca2ec3/before_door'
LIME = (170, 255, 20)


def recorded():
    return json.loads((FIX/'columns_d5ca2ec3.json').read_text())


def frames(rid):
    data = recorded()['robots'][rid]
    for frame_id, t, sha, index in data['frames']:
        yield frame_id, t, sha, np.array(data['table'][index], float)


def bits(line):
    return None if line is None else struct.pack('<ddq', *line)


def ols(ys, xs=XS):
    return ed.accept(xs, ys, np.polyfit(xs, ys, 1))


def render(ends, height=480, width=640):
    """Black frame with a lime band ending at ``ends[i]`` in the sampled column i (4 px wide, 59 px thick)."""
    img = np.zeros((height, width, 3), np.uint8)
    for c, end in zip(be.COLUMNS, ends):
        img[max(int(end) - 59, 0):int(end) + 1, c:c + 4] = LIME
    return img


def line_ys(slope, intercept=170., noise=0., seed=0):
    rng = np.random.default_rng(seed)
    return np.round(intercept + slope*(XS - 320.) + rng.normal(0., noise, len(XS))) if noise else intercept + slope*(XS - 320.)


# --- recorded HIGH frames ------------------------------------------------------------------------------------------

@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_recorded_high_frames_old_fit_rejects_and_consensus_accepts_all(rid):
    late = [(t, ys) for _, t, _, ys in frames(rid) if t >= LATE]
    assert len(late) >= 302
    for t, ys in late:
        assert ols(ys) is None                        # the PR's failure: the shared fit never accepts a HIGH frame
        line = ed.fit_consensus(XS, ys)
        assert line is not None and line[2] >= 54
        # independent reference: the lower band's edge alone (rows > 120), refit without the outlier columns
        low = ys > 120
        ref = np.polyfit(XS[low], ys[low], 1)
        assert abs(line[0] - ref[0]) < 2e-4 and abs(line[1] - (ref[1] + 320*ref[0])) < .5
        assert (~low).sum() <= 10 and line[2] >= low.sum() - 1


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_recorded_clean_frames_are_bit_identical_even_on_the_consensus_path(rid):
    accepted = [(ys, ols(ys)) for _, t, _, ys in frames(rid) if ols(ys) is not None]
    clean = [(ys, shared) for ys, shared in accepted if shared[2] == len(ys)]     # no column dropped: no outlier
    assert len(accepted) >= 40 and len(clean) >= 20                  # frames before the arm reached HIGH
    assert len(clean) < len(accepted)                               # transition frames drop 1-7 outlier columns
    for ys, shared in clean:
        assert bits(ed.fit_consensus(XS, ys)) == bits(shared)


@pytest.mark.parametrize('rid', ['r1', 'r2'])
def test_opencv_huber_agrees_on_the_recorded_frames(rid):
    cv2 = pytest.importorskip('cv2')
    for _, t, _, ys in frames(rid):
        if t < LATE:
            continue
        vx, vy, x0, y0 = cv2.fitLine(np.stack([XS, ys], 1).astype(np.float32), cv2.DIST_HUBER, 0, .01, .01).ravel()
        slope = vy/vx
        huber = ed.accept(XS, ys, np.array([slope, y0 - slope*x0]))
        mine = ed.fit_consensus(XS, ys)
        assert huber is not None and abs(huber[0] - mine[0]) < 2e-4 and abs(huber[2] - mine[2]) <= 1


def test_fixture_is_the_recorded_run():
    data = recorded()
    assert data['columns_x'] == [int(c) for c in be.COLUMNS]
    for rid in ('r1', 'r2'):
        rows = data['robots'][rid]['frames']
        assert len(rows) == 464 and rows[0][1] == pytest.approx(76.75) and rows[-1][1] == pytest.approx(99.9)
        assert len({row[0] for row in rows}) == 464 and len({row[2] for row in rows}) >= 400   # static frames repeat bytes
    for path in FIX.glob('*.jpg'):                    # the JPEG name carries the first 8 hex digits of its sha256
        assert hashlib.sha256(path.read_bytes()).hexdigest()[:8] == path.stem[-8:]


@pytest.mark.parametrize('name', sorted(p.name for p in FIX.glob('*.jpg')))
def test_recorded_jpegs_columns_and_results(name):
    rid, tag = name.split('_')[:2]
    sha = Path(name).stem[-8:]
    rgb = np.asarray(Image.open(FIX/name).convert('RGB'))
    xs, ys = ed.edge_columns(rgb)
    row = next(f for f in frames(rid) if f[2].startswith(sha))
    assert list(xs) == list(XS) and list(ys) == list(row[3])       # same columns as the table the other tests use
    shared = be.edge_line(rgb)
    assert bits(ols(ys)) == bits(shared)                            # extraction + acceptance copy == the shared function
    robust = ed.robust_edge_line(rgb)
    if tag == 't076.75':                                            # before HIGH: a clean 90-column frame
        assert shared is not None and bits(robust) == bits(shared) and robust.fit == ed.FIT_SHARED
        assert shared[2] == 90 and bits(ed.fit_consensus(xs, ys)) == bits(shared)
    elif tag == 't079.00':                                          # transition: the shared fit accepts but drops columns
        assert shared is not None and shared[2] < 90 and bits(robust) == bits(shared) and robust.fit == ed.FIT_SHARED
        assert ed.fit_consensus(xs, ys)[2] > shared[2]              # shared-first keeps the old answer; consensus differs
    else:
        assert shared is None and robust.fit == ed.FIT_CONSENSUS
        assert robust[2] == {'r1': 85, 'r2': 80}[rid]
        assert abs(robust[0]) < .01 and 165 < robust[1] < 180        # the lower band's nearly horizontal edge


def test_every_raw_probe_frame_when_available():
    roots = [Path(__file__).resolve().parents[1]/'outputs']
    if os.environ.get('UGRP_PRIMARY_OUTPUTS'):
        roots.insert(0, Path(os.environ['UGRP_PRIMARY_OUTPUTS']))
    run = next((r/RUN for r in roots if (r/RUN/'robots').is_dir()), None)
    if run is None:
        pytest.skip('raw probe output not on this host')
    for rid in ('r1', 'r2'):
        table = {row[2]: row for row in recorded()['robots'][rid]['frames']}
        for line in (run/'robots'/rid/'frames.jsonl').read_text().splitlines():
            rec = json.loads(line)
            if rec['sha256'] not in table:
                continue
            raw = (run/rec['path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == rec['sha256']
            rgb = np.asarray(Image.open(run/rec['path']).convert('RGB'))
            shared, robust = be.edge_line(rgb), ed.robust_edge_line(rgb)
            if shared is not None:
                assert bits(robust) == bits(shared) and robust.fit == ed.FIT_SHARED
            else:
                assert robust is not None and robust.fit == ed.FIT_CONSENSUS and robust[2] >= 54
            xs, ys = ed.edge_columns(rgb)
            assert list(ys) == list(recorded()['robots'][rid]['table'][table[rec['sha256']][3]])


# --- synthetic cases -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize('outliers', [2, 5, 10, 20, 36])
@pytest.mark.parametrize('where,offset', [('right', -91.), ('right', 40.), ('left', -60.)])
def test_one_sided_outlier_columns_do_not_tilt_the_line(outliers, where, offset):
    ys = line_ys(.003, noise=.5)
    index = np.arange(90 - outliers, 90) if where == 'right' else np.arange(outliers)
    ys[index] += offset
    assert ols(ys) is None if outliers >= 5 else True            # the shared least-squares fit fails (>= 5: always here)
    line = ed.fit_consensus(XS, ys)
    assert line is not None and line[2] >= 90 - outliers - 3
    assert abs(line[0] - .003) < 2e-3 and abs(line[1] - 170.) < 1.


@pytest.mark.parametrize('slope', [.5, -.5, .6, -.6])
def test_steep_line_with_outliers(slope):
    ys = line_ys(slope, intercept=190.)                           # rows 82..296 over the 90 columns: no noise, exact
    ys[-10:] -= 70.
    line = ed.fit_consensus(XS, ys)
    assert line is not None and line[2] == 80
    assert line[0] == pytest.approx(slope, abs=1e-9) and line[1] == pytest.approx(190., abs=1e-6)


def test_steep_line_on_an_image():
    ends = line_ys(.5, intercept=190.)
    ends[-10:] -= 70.
    rgb = render(ends)
    line = ed.robust_edge_line(rgb)
    assert line is not None and line.fit == ed.FIT_CONSENSUS and line[2] == 80
    assert line[0] == pytest.approx(.5, abs=2e-3) and line[1] == pytest.approx(190., abs=1.)


def test_too_many_outliers_empty_and_unstructured_inputs_are_rejected():
    ys = line_ys(.003, noise=.5)
    ys[-37:] += 80.                                                 # 53 of 90 on the line: below 0.6 x n = 54
    assert ed.fit_consensus(XS, ys) is None
    ys = line_ys(.003, noise=.5)
    ys[45:] += 80.                                                  # two equal groups
    assert ed.fit_consensus(XS, ys) is None
    rng = np.random.default_rng(3)
    assert ed.fit_consensus(XS, np.round(rng.uniform(100, 290, 90))) is None
    assert ed.edge_columns(np.zeros((480, 640, 3), np.uint8)) is None
    assert ed.robust_edge_line(np.zeros((480, 640, 3), np.uint8)) is None


def test_majority_group_wins_with_two_lines():
    ys = line_ys(.002, intercept=175., noise=.4)
    ys[-30:] = line_ys(.002, intercept=100., noise=.4)[-30:]       # 60 columns lower band, 30 upper band
    line = ed.fit_consensus(XS, ys)
    assert line is not None and line[2] >= 58 and abs(line[1] - 175.) < 1.5


def test_fewer_than_min_columns_is_none():
    ends = np.full(90, 170.)
    ends[:80] = 0.                                                  # columns with no band at all
    rgb = render(ends)
    assert ed.edge_columns(rgb) is None and ed.robust_edge_line(rgb) is None


def test_image_with_upper_band_intrusion_uses_consensus():
    ends = line_ys(.002, noise=.4)
    ends[-8:] = 81.                                                 # upper band's lower edge at rows ~80 in the last columns
    rgb = render(ends)
    assert be.edge_line(rgb) is None
    line = ed.robust_edge_line(rgb)
    assert line is not None and line.fit == ed.FIT_CONSENSUS and line[2] == 82
    clean = render(line_ys(.002, noise=.4))
    assert ed.robust_edge_line(clean).fit == ed.FIT_SHARED
    assert bits(ed.robust_edge_line(clean)) == bits(be.edge_line(clean))


def test_deterministic_and_independent_of_global_random_state():
    ys = line_ys(.003, noise=.7, seed=5)
    ys[-12:] -= 90.
    np.random.seed(1)
    first = ed.fit_consensus(XS, ys)
    np.random.seed(999)
    second = ed.fit_consensus(XS, ys)
    assert bits(first) == bits(second)
    reverse = ed.fit_consensus(XS[::-1].copy(), ys[::-1].copy())
    assert reverse[2] == first[2] and reverse[0] == pytest.approx(first[0], abs=1e-9)


def test_exact_tie_goes_to_the_first_pair_in_column_order():
    xs = XS[:30].copy()
    ys = np.full(30, 170.)
    ys[15:] = 230.                                                  # two exact horizontal lines, 15 columns each
    forward = ed.consensus_line(xs, ys)
    assert forward[0] == pytest.approx(0., abs=1e-12) and forward[1] == pytest.approx(170., abs=1e-9)
    backward = ed.consensus_line(xs[::-1].copy(), ys[::-1].copy())  # same data, other order: the first pair is in the other line
    assert backward[1] == pytest.approx(230., abs=1e-9)
    assert bits((*ed.consensus_line(xs, ys), 0)) == bits((*forward, 0))


def test_the_inlier_band_is_the_shared_four_pixels_in_the_consensus():
    ys = np.full(90, 170.)
    ys[::3] = 180.                                                  # 30 columns 10 px off, 60 on the line
    line = ed.fit_consensus(XS, ys)
    assert line is not None and line[2] == 60
    assert abs(line[0]) < 1e-9 and line[1] == pytest.approx(170., abs=1e-9)


@pytest.mark.parametrize('seed', [0, 1, 2, 3])
def test_consensus_set_is_refit_by_least_squares_before_the_band_is_applied(seed):
    ys = line_ys(.004, noise=1.8, seed=seed)                        # noisy line: a two-point line loses many inliers
    ys[:20] += 90.
    line = ed.fit_consensus(XS, ys)
    assert line is not None and line[2] >= 66 and abs(line[0] - .004) < 3e-3


def test_exact_consensus_tie_is_broken_by_the_smaller_residual_sum():
    xs = XS[:40].copy()
    ys = np.full(40, 170.)
    ys[20:] = 230. + 2.*np.where(np.arange(20) % 2 == 0, 1., -1.)  # 20 noisy columns, 20 exact columns, same count
    line = ed.consensus_line(xs, ys)
    assert line[1] == pytest.approx(170., abs=1e-9)
    swapped = ed.consensus_line(xs, ys[::-1].copy())                # the exact columns now come last: still chosen
    assert swapped[1] == pytest.approx(170., abs=1e-9) and abs(swapped[0]) < 1e-12


def test_rms_limit_of_the_shared_acceptance_still_applies():
    ys = 170. + 3.9*np.cos(2*np.pi*(XS - 140.)/(356./3))            # every column within 4 px of one line, RMS 2.8 px
    assert np.sqrt(np.mean((ys - 170.)**2)) > be.MAX_RMS_PX and np.abs(ys - 170.).max() < be.INLIER_TOL_PX
    assert ols(ys) is None and ed.fit_consensus(XS, ys) is None


# --- tracker and wiring --------------------------------------------------------------------------------------------

HIGH_SERVO = {1: 1500, 2: 1500, **pose.HIGH}


def run_tracker(cls, rgb, seconds=12.):
    tracker = cls(1.1066809450069606)
    t = 90.
    available_at = None
    while t < 90. + seconds:
        tracker.observe(t, rgb, HIGH_SERVO, True)
        if available_at is None and tracker.available(t):
            available_at = t
        t += .6
    return tracker, available_at


@pytest.mark.parametrize('name', sorted(p.name for p in FIX.glob('*_t095.00_*.jpg')))
def test_tracker_gets_a_reference_on_the_recorded_hold_where_the_shared_one_never_does(name):
    rgb = np.asarray(Image.open(FIX/name).convert('RGB'))
    shared, never = run_tracker(be.BeamEdgeTracker, rgb)
    robust, at = run_tracker(ed.HighBeamEdgeTracker, rgb)
    assert never is None and not shared.available(101.) and shared.stats['no_edge'] == shared.stats['frames'] > 0
    assert at is not None and at <= 90. + 3. + 2.5 and robust.available(101.)      # settle 3 s + 2 reference samples
    assert robust.stats['no_edge'] == 0 and robust.stats['rejected'] == 0
    assert abs(robust.total_rad) < 1e-4                                          # a static hold yields no yaw shift


def test_tracker_is_the_shared_code_with_one_name_replaced():
    shared = be.BeamEdgeTracker.observe
    robust = ed.HighBeamEdgeTracker.frozen_observe
    assert robust.__code__ is shared.__code__ and robust.__defaults__ == shared.__defaults__
    logged = ed.HighBeamEdgeTracker(1.1067)._logged_observe
    assert logged.__func__.__code__ is shared.__code__ and logged.__func__.__defaults__ == shared.__defaults__
    assert robust.__globals__['edge_line'] is ed.robust_edge_line
    assert shared.__globals__['edge_line'] is be.edge_line          # the shared module is not patched
    assert robust.__globals__['np'] is shared.__globals__['np']
    assert not hasattr(be, 'robust_edge_line')
    assert issubclass(ed.HighBeamEdgeTracker, be.BeamEdgeTracker)


def test_provider_and_runtime_use_the_robust_fit(tmp_path, monkeypatch):
    from tests.test_highpose_dev_pilot import dev_file, admit, MAPS, c
    from harness import zone_pair_highpose_runtime as runtime
    from harness.vision_pose_source_highpose import HighPoseSource
    assert runtime.edge_line is ed.robust_edge_line
    path, _ = dev_file(tmp_path)
    sha = c.base.sha(path)
    admit(monkeypatch, sha)
    provider = HighPoseSource(c.resolve(MAPS[0])[0], path, sha)
    try:
        assert type(provider.beam_edge) is ed.HighBeamEdgeTracker
        assert provider.beam_edge.ratio == pytest.approx(float(provider.calibration['pair_model']['slope_to_yaw_ratio']))
    finally:
        provider.close()


@pytest.mark.parametrize('name', sorted(p.name for p in FIX.glob('*.jpg')))
def test_fit_rows_log_every_fitted_frame_and_do_not_change_the_answers(name):
    # Coordinator ruling 3 (2026-10-04): log the fitted intercept row so an upper/lower band switch is visible.
    rgb = np.asarray(Image.open(FIX/name).convert('RGB'))
    logged, reference = ed.HighBeamEdgeTracker(1.1067), ed.HighBeamEdgeTracker(1.1067)
    t = 90.
    while t < 101.:
        assert logged.observe(t, rgb, HIGH_SERVO, True) == reference.frozen_observe(t, rgb, HIGH_SERVO, True)
        assert logged.available(t) == reference.available(t)
        t += .6
    rows = logged.stats['fit_rows']
    line = ed.robust_edge_line(rgb)
    assert len(rows) == logged.stats['frames'] - logged.stats['no_edge'] == logged.stats['fit_'+line.fit] > 0
    assert all(r[1] == line.fit and r[2] == pytest.approx(line[1], abs=1e-3) and r[4] == line[2] for r in rows)
    assert [r[0] for r in rows] == sorted(r[0] for r in rows) and rows[0][0] >= 90.
    json.dumps(logged.stats)
