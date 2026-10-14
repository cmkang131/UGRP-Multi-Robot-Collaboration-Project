"""Own-RGB band presence, separate from metric grasp-pose admission.

OpenCV HSV/connected components with lime adjacency. No scene state, labels,
robot identity or coordinates. Partial/distant bands remain visual evidence,
not permission to grasp. Enabled only by explicit end-color v3 options.
"""
import cv2
import numpy as np
from harness import owncam_pair_beam as beam

HSV = {'teal': ((70, 100, 35), (90, 255, 255)),
       'blue': ((112, 100, 35), (128, 255, 255))}
MIN_COMPONENT_PIXELS = 32
LIME_ADJACENCY_KERNEL = 7


def parameters():
    return dict(hsv=HSV, min_component_pixels=MIN_COMPONENT_PIXELS,
                lime_adjacency_kernel=LIME_ADJACENCY_KERNEL, connectivity=8)


def detect(frame, color):
    low, high = HSV[color]
    colored = cv2.inRange(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV),
                          np.array(low), np.array(high))
    count, labels, stats, centers = cv2.connectedComponentsWithStats(colored, connectivity=8)
    adjacent = cv2.dilate(beam.lime_mask(frame).astype(np.uint8), np.ones((LIME_ADJACENCY_KERNEL,) * 2, np.uint8)) > 0
    kept = np.zeros(frame.shape[:2], bool)
    patches = []
    for idx in range(1, count):
        x, y, w, h, area = map(int, stats[idx])
        if area < MIN_COMPONENT_PIXELS:
            continue
        component = labels[y:y+h, x:x+w] == idx
        if not np.any(component & adjacent[y:y+h, x:x+w]):
            continue
        kept[y:y+h, x:x+w] |= component
        patches.append(dict(bbox_xyxy=[x, y, x+w, y+h], pixels=area,
                            center_px=centers[idx].tolist()))
    return kept, dict(band_visible=bool(patches), color_components=patches,
                      color_detector='hsv_components_v3')
