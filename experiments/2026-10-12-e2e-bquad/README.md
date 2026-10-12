# B quad detection (`not_convex_quad`) — 2026-10-12, Refs #453 #456

Toggle: `b_marker_detect=contrast_v2` (default off; `--b-marker-detect contrast_v2`). No bundle ID registered.
Mark pixels are the same as `contrast_v1`. Only the B region/quad stage changes (`harness/e2e_b_quad.py`).

## What `not_convex_quad` is (saved frames)
- Wall and B floor are both in the blue HSV band (wall hue ≈105, S 73–78; B floor hue 112–113, S 118–144; measured on v213 frames).
  They merge into blobs of 50 % of the frame (144k–175k px²). v2 uses hue ≥109 for the region mask.
- B is large and the robot is at or beside it: all 42 saved B-visible frames (e2e11, labeled) have the B patch cut by the lens circle/image edge,
  0/42 with all four corners. A complete 4-corner quad therefore does not exist in these frames.
- A body mask applied before `findContours` can carve a bite (not confirmed on frames).

## v2
undistort contour (fisheye model) → convex hull (fit only) → `approxPolyDP` with growing epsilon (1–4 %) → corners distorted back for the ray lookup.
Guards: reject image border, lens circle (`lens_valid`), solidity < 0.9, fit area error > 10 %, floor area/aspect outside 0.04–4 m² / 5. Hull is never promoted to a complete B.

## Offline result (394 labeled e2e11 frames + 120 unlabeled e2e14 frames; labels used only in evaluation)
| | off | v1 | v2 |
|---|---|---|---|
| accepted, e2e11 | 0/394 | 0/394 | 0/394 |
| false accepts (B not in view) | 0/352 | 0/352 | 0/352 |
| accepted, e2e14 (unlabeled) | 0/120 | 0/120 | 0/120 |

v2 reasons on the 42 partial-B frames: lens_clipped 42/42. So v2 does **not** make B confirmable; it removes the wall merge and the lens-bend vertices and
reports the true cause (clipping). The next lever is view planning (a viewpoint where all four corners are inside the lens circle), not polygon tolerance.
Only 2 v213 JPEGs were available locally; the rest were not fetched (`ssh arm` does not resolve). Not scored.

## References (checked = read here)
- OpenCV `approxPolyDP`, `convexHull`, `minAreaRect`, `fisheye.undistortPoints/distortPoints`: used and run (cv2 4.13); docs text not re-read.
- ArUco quad candidate: `polygonalApproxAccuracyRate` default 0.03 (checked in cv2 4.13); corner refinement default 0 = none. AprilTag line fitting: unverified (from memory).
- Undistort before quad fitting: standard for rectified detection; unverified citation.
