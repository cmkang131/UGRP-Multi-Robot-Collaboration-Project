"""Self-occlusion masking for the height-free wall probe: per-column ``self_top``.

The wrist camera of a loaded robot looks past the thing it is carrying. The carried
beam (yellow-green tape plus a black band across its middle) and, in the box
scenario, the carried cyan crate both sit in the lower part of the own image and
cover the floor. The wall detector has no way to know that: a floor-contact row
underneath the cargo still back-projects onto the floor plane, still shows a
luminance step across it, and still looks uniform above it, so it is accepted as a
wall face. Worse, the cargo is by definition the *nearest* thing in view, so the
near-clip pseudo-range scan ranks the cargo boundary as the closest candidate and
the reported near distance is the cargo itself.

``self_top`` is the fix: the topmost row that is occluded in each detector column.
The detector excludes candidates at rows ``>= self_top - self_margin_px``, i.e. it
keeps only what is above the cargo, where the floor it should actually see is.

Inputs are the own RGB frame and the own commanded load state, nothing else. Map
walls, robot pose, simulator state and ground truth are never read here.

WHY THESE COLOURS
-----------------
The beam is scenario cargo: the tape colour and the dark stripe are part of the
object, not the room, so they are far better separated than any wall/floor cue.
The two HSV bands below are copied verbatim from
``experiments/2026-10-03-vo-feasibility/code/vo_eval.py`` (``beam_mask``), the only
code in the repository that already identifies the carried beam in the own camera.
Reusing them means this mask and the VO probe agree on what "beam" means instead of
drifting apart.

  green  HSV(25..55, S>=90, V>=60)  the yellow-green tape running along the beam
  black  HSV(H all, S<=255, V<=35)   the dark band across the beam's middle

Both halves are needed and neither alone is enough:

  * green alone misses the middle of the beam, and the top and bottom edges of the
    black band are exactly the rows that produce a strong contrast step against the
    band above them and against the floor below. Those are the rows the near-clip
    scan picks.
  * black alone is far too permissive. Measured on the v98 dev episode
    ``zone_wide_door_geometry_v3``, the black band alone lights up 17.7% of every
    *raw* frame including frames where the beam is nowhere in view: the fisheye
    padding outside the image circle is (0, 0, 0) and the raw frame is cut off
    black below row 463. So the per-column walk runs on the **undistorted** frame,
    which the same episode shows to be 0.08% black on a beam-free frame, and only a
    blob that reaches the bottom of that frame counts.

``beam_mask`` itself is frame-agnostic (it is an HSV test, exactly as in ``vo_eval``,
where it runs on raw frames); it is the row indexing that has to move to the
undistorted frame, because ``self_top`` is a row index into the detector's frame and
a row of the mask must be the same row as the detector's row. Measured on the raw
frame the same code drives ``self_top`` to 0 on 96/96 columns on *every* frame,
including ones with no beam in view at all.

The bottom-connectivity requirement is what keeps the definition honest in the other
direction too: when the wrist drops and the beam swings up to the *top* of the image,
the floor below it is still visible and ``self_top`` correctly stays at ``HEIGHT``.

The cyan box test (``box_mask_top``) is a *ratio* test (G and B well above R), not a
hue test, so it survives shadow, which the beam's HSV test does not. It is only
meaningful while the own commands say the robot is loaded; an unloaded robot looking
at a cyan wall would otherwise mask its own view.

Both masks are combined by taking the topmost of the two per column: whatever is
highest in the image occludes everything below it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))

import markerless_probe as mp  # noqa: E402

WIDTH, HEIGHT = mp.WIDTH, mp.HEIGHT

# Beam: yellow-green tape + the black middle band. See the module docstring for why
# both halves and why they must not be trusted on their own.
BEAM_HSV = (((25, 90, 60), (55, 255, 255)), ((0, 0, 0), (180, 255, 35)))
BEAM_DILATE = 9

# The last rows can carry remap border effects, so the bottom-connectivity search
# starts just above them and requires the rows below the start row to be occluded
# (same reason and same constants as the frozen ``markerless_probe.carried_mask_top``).
BOTTOM_MARGIN = 6
GATE_ROWS = 10          # rows above the start row that must be occluded
GATE_FRAC = .8           # ... by at least this fraction of the column strip
GAP_ROWS = 3             # tolerated misses while walking up


def beam_mask(bgr: np.ndarray) -> np.ndarray:
    """Carried beam (yellow-green tape) and its black middle band, dilated.

    HSV ranges copied from ``vo_eval.beam_mask``; the dilation merges the tape and
    the band into one blob so a column strip is not split by the seam between them.
    The test is frame-agnostic - it takes the raw frame as in ``vo_eval``, and the
    undistorted frame in ``beam_top``.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = np.zeros(hsv.shape[:2], np.uint8)
    for lo, hi in BEAM_HSV:
        m |= cv2.inRange(hsv, lo, hi)
    return cv2.dilate(m, np.ones((BEAM_DILATE, BEAM_DILATE), np.uint8))


def _strip_flags(mask: np.ndarray, columns, half: int, min_frac: float) -> np.ndarray:
    """(HEIGHT, n_columns) bool: fraction of each column strip that ``mask`` covers."""
    hit = (mask > 0).astype(np.float64)
    cs = np.concatenate([np.zeros((hit.shape[0], 1)), np.cumsum(hit, 1)], 1)
    lo = np.clip(np.asarray(columns, int) - half, 0, WIDTH)
    hi = np.clip(np.asarray(columns, int) + half + 1, 0, WIDTH)
    return (cs[:, hi] - cs[:, lo])/np.maximum(hi - lo, 1)[None, :] >= min_frac


def _bottom_run_top(flags: np.ndarray, gap_rows: int = GAP_ROWS) -> np.ndarray:
    """Topmost row of the bottom-connected run per column of a (HEIGHT, n) flag array.

    HEIGHT where the run does not reach the bottom rows. A column is only considered
    occluded if it is actually masked just above the frame edge; from there the
    search walks up, tolerating up to ``gap_rows`` consecutive unmasked rows.
    """
    n = flags.shape[1]
    top = np.full(n, HEIGHT, int)
    start = HEIGHT - BOTTOM_MARGIN
    if flags.shape[0] <= GATE_ROWS:
        return top
    gated = flags[start - GATE_ROWS:start].mean(0) > GATE_FRAC
    if not gated.any():
        return top

    idx = np.arange(n)
    v = np.full(n, start, int)
    miss = np.zeros(n, int)
    run = gated.copy()
    while run.any():
        v = np.maximum(v - 1, 0)
        hit = flags[v, idx]
        miss = np.where(hit, 0, miss + 1)
        run &= (v > 0) & (miss < gap_rows)
    return np.where(gated, v + miss, HEIGHT)


def beam_top(bgr: np.ndarray, columns, half: int, min_frac: float = .6,
             gap_rows: int = GAP_ROWS) -> np.ndarray:
    """Topmost row of the carried beam reaching the image bottom, per column.

    HEIGHT where the beam is not in that column. ``beam_mask`` supplies the pixels,
    this supplies the per-column row: only a bottom-connected blob counts, so a dark
    patch that is not the carried beam does not masquerade as an occluder.

    ``bgr`` must be the *undistorted* own frame (see the module docstring): the raw
    fisheye frame's black surround is inside ``BEAM_HSV`` and would occlude everything.
    """
    flags = _strip_flags(beam_mask(bgr), columns, half, min_frac)
    return _bottom_run_top(flags, gap_rows)


def _cyan_mask(und_bgr: np.ndarray) -> np.ndarray:
    """Cyan pixels: G and B both well above R.

    A ratio test rather than a hue test, so it survives shadow - which the beam's
    HSV test does not. ``und_bgr`` is the undistorted own frame (rows must line up
    with the detector); the remap adds no border black here.
    """
    img = und_bgr.astype(np.float32)
    b, g, r = img[..., 0], img[..., 1], img[..., 2]
    return ((g > 1.6*r + 8.) & (b > 1.6*r + 8.) & (g > 40.)).astype(np.uint8)


def box_mask_top(und_bgr: np.ndarray, columns, half: int, min_frac: float = .6,
                 gap_rows: int = GAP_ROWS) -> np.ndarray:
    """Top row of a carried cyan box reaching the image bottom, per column (HEIGHT if none).

    Port of the frozen ``markerless_probe.carried_mask_top`` (defined but never
    called in the live path) and of the copy in ``height_free_wall.box_mask_top``.
    Cyan is a ratio test - see ``_cyan_mask`` - so the box still counts in shadow.
    Applied only while the own commands say the robot is loaded.
    """
    return _bottom_run_top(_strip_flags(_cyan_mask(und_bgr), columns, half, min_frac), gap_rows)


def self_top_for(bgr: np.ndarray, und_bgr, columns, half: int, loaded: bool) -> np.ndarray:
    """Per-column ``self_top`` for one frame: the topmost occluded row, ``HEIGHT`` if clear.

    The single entry point. ``bgr`` is the own (raw, distorted) RGB frame and
    ``und_bgr`` the same frame undistorted, or ``None`` to undistort it here - the
    per-column walk always runs on the undistorted rows because those are the rows
    ``height_free_wall.detect`` indexes. ``columns``/``half`` are the detector's
    column positions and strip half-width. ``loaded`` is the own commanded load
    state; while it is false there is nothing carried and nothing is masked.

    When loaded, the beam and the box are combined by taking the topmost of the two:
    whichever occluder reaches higher in the image hides everything below it.

    Reads only the own frame and the own load state. No map, no pose, no ground
    truth.
    """
    cols = np.asarray(columns, int)
    if not loaded:
        return np.full(len(cols), HEIGHT, int)
    if und_bgr is None:
        und_bgr = mp.undistort(bgr)
    return np.minimum(beam_top(und_bgr, cols, half), box_mask_top(und_bgr, cols, half))


def annotate(bgr, und_bgr, columns, half, loaded, out_path, margin=3):
    """Draw the masks and the resulting per-column ``self_top``; write one PNG."""
    vis = und_bgr.copy()
    top = self_top_for(bgr, und_bgr, columns, half, loaded)
    bm = beam_mask(und_bgr)
    cyan = _cyan_mask(und_bgr)
    overlay = vis.copy()
    overlay[bm > 0] = (0, 0, 255)          # beam tape + black band
    overlay[cyan > 0] = (255, 128, 0)      # cyan box
    vis = cv2.addWeighted(overlay, .45, vis, .55, 0)
    vis[bm > 0] = np.maximum(vis[bm > 0], (0, 0, 140))

    for j, u in enumerate(columns):
        t = int(top[j])
        if t >= HEIGHT:
            continue
        cv2.line(vis, (u, t), (u, HEIGHT - 1), (0, 255, 255), 1)
        gate = max(0, t - margin)
        cv2.line(vis, (u, gate), (u, t - 1), (0, 0, 255), 1)
        cv2.circle(vis, (u, t), 2, (0, 255, 255), -1)
    cv2.putText(vis, f'loaded={int(bool(loaded))} occluded_cols={int((top < HEIGHT).sum())}/{len(top)}',
                (8, 20), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1, cv2.LINE_AA)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), vis)
    return out_path


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--frame', required=True, help='own RGB frame (raw, as recorded)')
    ap.add_argument('--out', default=None, help='annotated PNG (default: primary checkout outputs/)')
    ap.add_argument('--loaded', type=int, default=1, help='own commanded load state')
    ap.add_argument('--columns', type=int, default=96)
    ap.add_argument('--half', type=int, default=2)
    args = ap.parse_args()

    bgr = cv2.imread(args.frame, cv2.IMREAD_COLOR)
    if bgr is None:
        raise SystemExit(f'frame not readable: {args.frame}')
    und_bgr = mp.undistort(bgr)
    columns = mp.column_positions(args.columns, args.half)
    loaded = bool(args.loaded)

    top = self_top_for(bgr, und_bgr, columns, args.half, loaded)
    bt = beam_top(und_bgr, columns, args.half) if loaded else np.full(len(columns), HEIGHT, int)
    bx = box_mask_top(und_bgr, columns, args.half) if loaded else np.full(len(columns), HEIGHT, int)

    print(f'frame {args.frame}  loaded={int(loaded)}  columns={len(columns)}')
    print(f'occluded columns: {int((top < HEIGHT).sum())}/{len(columns)}'
          f'  ({100.*float((top < HEIGHT).mean()):.1f}%)')
    for j in range(0, len(columns), 12):
        print('  ' + '  '.join(f'u={int(columns[k]):3d}:{int(top[k]):3d}' for k in range(j, min(j + 12, len(columns)))))
    span = top[top < HEIGHT]
    if span.size:
        print(f'self_top range: {int(span.min())}..{int(span.max())}  median={int(np.median(span))}')
    print(f'beam columns={int((bt < HEIGHT).sum())}  box columns={int((bx < HEIGHT).sum())}')

    out = Path(args.out) if args.out else Path(
        '/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe')/f'{Path(args.frame).stem}_self_mask.png'
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        out = Path('/tmp')/out.name
    annotate(bgr, und_bgr, columns, args.half, loaded, out)
    print(f'wrote {out}')


if __name__ == '__main__':
    main()
