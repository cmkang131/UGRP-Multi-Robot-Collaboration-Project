"""Explicit diagnostic-only NumPy scalar conversion; no controller mutation."""
import numpy as np

OPTION='python_v1'


def normalize(value):
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
    return value
