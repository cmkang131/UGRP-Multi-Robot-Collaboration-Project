"""Static map from an issued command to the effective command of the loaded pair plant (v102 affine dead zone).

The loaded steady speed measured in experiments/2026-10-05-loaded-gain-calibration-v102 is affine in the command above a
small dead zone, ``v = g*sign(u)*max(|u| - u0, 0)`` per axis [forward, left, turn]. ``params.motion_loaded.deadband`` may
carry ``u0`` (three nonnegative values). It acts BEFORE the earlier v6g ramp (``c0``, ``u1``; the PF predictor applies the
ramp itself), so a calibration without ``u0`` -- every calibration before v102 -- keeps its exact prediction, bit for bit.
``harness/owncam_localizer.py`` is sealed by hash pins, so the PF subclass in ``vision_pose_source_pair_v3`` applies
``affine`` around the unchanged base ``predict_to`` instead of editing it.
"""
from __future__ import annotations

import numpy as np


def has_affine(db) -> bool:
    return bool(db) and 'u0' in db and bool(np.any(np.asarray(db['u0'], float) > 0))


def affine(u, db):
    """sign(u)*max(|u| - u0, 0); the identity (same array) without ``u0``."""
    if not has_affine(db):
        return u
    u = np.asarray(u, float)
    return np.sign(u)*np.maximum(np.abs(u) - np.asarray(db['u0'], float), 0.)


def ramp(u, db):
    """The v6g ramp exactly as the PF predictor applies it."""
    u = np.asarray(u, float)
    c0, u1 = np.asarray(db['c0'], float), np.asarray(db['u1'], float)
    return u*np.where(u1 > c0, np.clip((np.abs(u) - c0)/np.maximum(u1 - c0, 1e-9), 0., 1.), 1.)


def effective(u, db):
    """Issued command -> effective command (affine dead zone, then ramp)."""
    return ramp(affine(u, db), db)


def inverse_affine(raw, db):
    """Add the dead zone back to a nonzero effective command (the inverse of ``affine`` for |u| > u0)."""
    if not has_affine(db):
        return raw
    raw = np.asarray(raw, float)
    return np.where(raw != 0, raw + np.sign(raw)*np.asarray(db['u0'], float), raw)
