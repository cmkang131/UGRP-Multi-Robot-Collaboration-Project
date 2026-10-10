"""Opt-in own-RGB temporal grip appearance monitor; legacy remains default.

This is a stationary-wrist development sensor, not a contact measurement. The
first three images after an externally scheduled grasp/settle form one immutable
visual anchor. No contact, pose, joint measurement or simulator object is accepted.
An unobservable anchor stays unknown; disappearance after an observable anchor
is loss evidence. A new grasp requires a new monitor, never automatic re-anchoring.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np

OPTION = 'grip_temporal_rgb_v1'


@dataclass(frozen=True)
class Config:
    min_area: float = .02
    min_iou: float = .60
    min_retained: float = .60
    max_centroid_shift: float = .10
    consecutive: int = 3
    max_gap_s: float = .15


def silhouette(frame, cargo):
    if frame.shape != (480, 640, 3) or frame.dtype != np.uint8:
        raise ValueError('expected unchanged 640x480 BGR own camera')
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lo, hi = {'long_beam': (25, 54), 'cyan': (80, 105)}[cargo]
    mask = ((hsv[..., 0] >= lo) & (hsv[..., 0] <= hi)
            & (hsv[..., 1] >= 100) & (hsv[..., 2] >= 60))
    # Fixed camera pixel ROI; exclude the lens border, preserve low cyan strip.
    return mask[48:456:4, 64:576:4]


class TemporalGrip:
    def __init__(self, cargo, config=Config()):
        if cargo not in ('long_beam', 'cyan'):
            raise ValueError('fixed task cargo required')
        self.cargo, self.config = cargo, config
        self.reference = None
        self.initial = []
        self.last_t = None
        self.bad = 0
        self.lost = False
        self.unobservable = False

    def observe(self, frame, sim_time):
        if not math.isfinite(sim_time) or (self.last_t is not None and sim_time <= self.last_t):
            self.bad = 0
            return dict(state='unknown', reason='NONMONOTONIC_OR_INVALID_TIME')
        gap = self.last_t is not None and sim_time-self.last_t > self.config.max_gap_s+1e-8
        self.last_t = sim_time
        try:
            mask = silhouette(frame, self.cargo)
        except (ValueError, AttributeError):
            self.bad = 0
            return dict(state='unknown', reason='INVALID_RGB')
        if gap:
            self.bad = 0
            return dict(state='unknown', reason='FRAME_GAP')
        if self.unobservable:
            return dict(state='unknown', reason='ANCHOR_UNOBSERVABLE')
        if self.reference is None:
            self.initial.append(mask)
            if len(self.initial) < 3:
                return dict(state='unknown', reason='ANCHOR_ACQUISITION')
            self.reference = np.sum(self.initial, axis=0) >= 2
            if float(self.reference.mean()) < self.config.min_area:
                self.unobservable = True
                return dict(state='unknown', reason='ANCHOR_UNOBSERVABLE')
        ref = self.reference
        overlap = int((ref & mask).sum())
        iou = overlap/max(1, int((ref | mask).sum()))
        retained = overlap/int(ref.sum())
        if mask.any():
            shift = float(np.linalg.norm((np.argwhere(mask).mean(0)-np.argwhere(ref).mean(0))/np.array(mask.shape)))
        else:
            shift = 1.
        bad = iou < self.config.min_iou or retained < self.config.min_retained or shift > self.config.max_centroid_shift
        self.bad = self.bad+1 if bad else 0
        self.lost |= self.bad >= self.config.consecutive
        return dict(state='grip_lost' if self.lost else 'held', reason='RGB_SILHOUETTE_CHANGE' if self.lost else 'RGB_ANCHOR_RETAINED',
                    iou=iou, retained=retained, centroid_shift=shift, consecutive_bad=self.bad,
                    contact_claim=False, stationary_wrist_only=True)


class GripMonitor:
    """Offline sensor toggle. No existing S4 LLM/controller default is changed."""
    def __init__(self, cargo='long_beam', mode='legacy', config=Config()):
        if mode not in ('legacy', OPTION):
            raise ValueError('unknown grip mode')
        self.mode = mode
        self.temporal = TemporalGrip(cargo, config) if mode == OPTION else None

    def observe(self, image, sim_time, commanded_servo):
        if self.mode == 'legacy':
            from harness.zone_pair_highpose_grip import relation
            return relation(image, commanded_servo)
        from harness.owncam_pair_beam import decode
        return self.temporal.observe(decode(image), sim_time)
