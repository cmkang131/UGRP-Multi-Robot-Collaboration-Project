"""Strict JSON for numeric experiment records, without string fallbacks."""
import json

import numpy as np


class NumpyJSONEncoder(json.JSONEncoder):
    def default(self, value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        return super().default(value)


def dumps(value, **kwargs):
    # Preserve the existing nonfinite-value rejection, including inside arrays.
    kwargs.setdefault('allow_nan', False)
    kwargs.setdefault('cls', NumpyJSONEncoder)
    return json.dumps(value, **kwargs)
