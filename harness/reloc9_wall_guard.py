"""Default-off measured wall-top guard; static 0.40 m height + own image/FK only.

Keep the hash-pinned legacy observer and endpoint adapter byte-identical. This
post-filter never invents an edge when the top is outside the frame or absent.
"""
import copy
import math
import numpy as np

OPTION = 'reloc9_wall_height_guard_v1'
HEIGHT_M = .40


def validate(enabled):
    if type(enabled) is not bool:
        raise ValueError(OPTION+' must be bool')


def supported_columns(und, cm, bottom, top):
    from harness.opencv_wall_observation import edge_step
    bottom, top = np.asarray(bottom), np.asarray(top)
    predicted = cm.rows(cm.t_of_row(bottom), HEIGHT_M)
    img = und.astype(np.float32)
    lum = .114*img[..., 0]+.587*img[..., 1]+.299*img[..., 2]
    chroma = img[..., 0]-img[..., 2]
    tolerance = np.minimum(12., 4.+.10*np.maximum(0., bottom-predicted))
    valid = (np.isfinite(bottom) & np.isfinite(top) & np.isfinite(predicted)
             & (top >= 4) & (top < und.shape[0]-4) & (bottom-top >= 4)
             & (predicted >= 4) & (predicted < und.shape[0]-4)
             & (abs(top-predicted) <= tolerance))
    for j in np.flatnonzero(valid):
        valid[j] = edge_step(lum, chroma, int(round(top[j])), cm.columns[j]) >= 4.
    return valid, dict(option=OPTION, height_m=HEIGHT_M, candidate_columns=int(np.isfinite(bottom).sum()),
        top_supported_columns=int(valid.sum()), removed_columns=int((np.isfinite(bottom) & ~valid).sum()),
        predicted_top_rows=[float(v) if math.isfinite(v) else None for v in predicted],
        scope='measured in-frame top + commanded FK; no map pose, GT or top camera')


def filter_observation(obs, und, cm, enabled=False):
    validate(enabled)
    if not enabled:
        return obs, None
    keep, audit = supported_columns(und, cm, obs.b_lo, obs.t_lo)
    out = copy.deepcopy(obs)
    for key in ('b_kind', 't_kind'):
        getattr(out, key)[~keep] = 0
    for key in ('b_lo', 'b_hi', 't_lo', 't_hi'):
        getattr(out, key)[~keep] = np.nan
    return out, audit
