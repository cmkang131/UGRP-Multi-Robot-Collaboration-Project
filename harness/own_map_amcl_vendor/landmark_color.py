"""Pinned PR406 definitions; only imports/runtime adapters differ. See provenance.json."""
import cv2
from harness import zone_color_boxes as colors

def cyan(frame):
    return colors._mask(cv2.cvtColor(frame, cv2.COLOR_BGR2HSV), colors.OWN_ZONE_CYAN_HSV) > 0
