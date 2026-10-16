"""B boundary quad fitting for b_marker_detect=contrast_v2 (default off).

Own RGB + fixed camera calibration only. The fisheye lens bends the straight B
edges, so a 2 % approxPolyDP on raw pixels returns 5-8 vertices. Standard
remedy (OpenCV fisheye model; ArUco/AprilTag fit quads on rectified points):
undistort the contour, take the convex hull, fit a quad with a growing
approxPolyDP epsilon, then map the four corners back to the raw image for the
ray lookup. The hull is used for FITTING only. A region cut by the image
border, the lens circle, the body mask or a concave bite is never promoted to
a complete B quad (solidity, lens and border tests below).
"""
import cv2
import numpy as np
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

FLOOR_BLUE_V2 = ((109, 70, 35), (135, 255, 255))  # walls are hue ~105, B floor ~112
FIT = dict(eps_fractions=(.01, .015, .02, .03, .04), max_fit_area_error=.10, min_solidity=.90,
           lens_margin_px=4, border_px=3, min_area_px2=100)


def floor_blue_mask(hsv, self_mask):
    mask = cv2.inRange(hsv, FLOOR_BLUE_V2[0], FLOOR_BLUE_V2[1])
    mask[self_mask] = 0
    return mask


def _camera(width, height):
    return np.asarray(scaled_camera_matrix(width, height), np.float64), np.asarray(CAMERA_FISHEYE_D, np.float64)


def undistort(points, width, height):
    k, d = _camera(width, height)
    out = cv2.fisheye.undistortPoints(np.asarray(points, np.float64).reshape(-1, 1, 2), k, d, P=k)
    return out.reshape(-1, 2)


def undistort_norm(points, width, height):
    """Raw pixels -> normalised pinhole rays (x/z, y/z), fisheye model."""
    k, d = _camera(width, height)
    return cv2.fisheye.undistortPoints(np.asarray(points, np.float64).reshape(-1, 1, 2), k, d).reshape(-1, 2)


def distort(points, width, height):
    k, d = _camera(width, height)
    xy = (np.asarray(points, np.float64).reshape(-1, 2) - [k[0, 2], k[1, 2]]) / [k[0, 0], k[1, 1]]
    out = cv2.fisheye.distortPoints(xy.reshape(-1, 1, 2), k, d)
    return out.reshape(-1, 2)


def fit_quad(contour, lens_ok, *, config=FIT):
    """Return (corners_px int32 (4, 2) | None, reason, stats). Raw pixel contour in."""
    height, width = lens_ok.shape
    pts = contour.reshape(-1, 2)
    area = float(cv2.contourArea(contour))
    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    stats = dict(area_px2=area, hull_area_px2=hull_area, solidity=area/hull_area if hull_area else 0.)
    if stats['solidity'] < config['min_solidity']: return None, 'low_solidity', stats
    m = config['border_px']
    if pts[:, 0].min() <= m or pts[:, 1].min() <= m or pts[:, 0].max() >= width-1-m or pts[:, 1].max() >= height-1-m:
        return None, 'image_clipped', stats
    # The lens circle lies inside the frame: contour points beside an invalid pixel are clipped too.
    near = cv2.erode(lens_ok.astype(np.uint8), np.ones((2*config['lens_margin_px']+1,)*2, np.uint8)) != 0
    if not near[pts[:, 1], pts[:, 0]].all(): return None, 'lens_clipped', stats
    und = undistort(hull.reshape(-1, 2), width, height).astype(np.float32)
    und_area = float(cv2.contourArea(und))
    if und_area <= 0 or not np.isfinite(und_area): return None, 'undistort_failed', stats
    perimeter = float(cv2.arcLength(und, True))
    for fraction in config['eps_fractions']:
        quad = cv2.approxPolyDP(und.reshape(-1, 1, 2), fraction*perimeter, True).reshape(-1, 2)
        if len(quad) != 4: continue
        error = abs(und_area-float(cv2.contourArea(quad.astype(np.float32))))/und_area
        stats.update(eps_fraction=fraction, fit_area_error=error)
        if error > config['max_fit_area_error'] or not cv2.isContourConvex(quad.astype(np.float32).reshape(-1, 1, 2)):
            return None, 'quad_fit_poor', stats
        corners = np.rint(distort(quad, width, height)).astype(np.int32)
        if (corners[:, 0].min() < 0 or corners[:, 1].min() < 0 or corners[:, 0].max() >= width
                or corners[:, 1].max() >= height): return None, 'corner_off_image', stats
        return corners, 'quad', stats
    return None, 'not_four_corners', stats


def floor_shape_ok(polygon, *, min_area_m2=.04, max_area_m2=4., max_aspect=5.):
    """Size/aspect sanity on the floor-projected quad (metres, own frame)."""
    poly = np.asarray(polygon, np.float32).reshape(-1, 2)
    area = float(cv2.contourArea(poly))
    (_, (a, b), _) = cv2.minAreaRect(poly)
    aspect = max(a, b)/max(min(a, b), 1e-9)
    return min_area_m2 <= area <= max_area_m2 and aspect <= max_aspect, dict(area_m2=area, aspect=float(aspect))
