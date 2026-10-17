"""Call upstream ROVIO FeatureStatistics<1>; no Python imitation of its policy.

Build the explicit opt-in library with scripts/build_egomem_rovio_statistics.py.
Defaults are read from the byte-pinned upstream rovio.info, not tuned locally.
Only UNKNOWN (no correspondence/visibility unverified) and TRACKED are emitted
by our semantic adapter. No simulated camera projection or truth is consulted.
"""
import ctypes
from pathlib import Path
import re

VENDOR = Path(__file__).parent / 'vendor' / 'rovio'
PROFILE = 'rovio_local_v1'
UNKNOWN, TRACKED = 0, 4


def parameters():
    text = (VENDOR / 'rovio.info').read_text()
    names = ('trackingUpperBound', 'trackingLowerBound',
             'minTrackedAndFreeFeatures', 'removalFactor')
    return {name: float(re.search(r'\b'+name+r'\s+([\d.]+);', text)[1]) for name in names}


class RovioLibrary:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.lib = ctypes.CDLL(str(self.path))
        signatures = {
            'create': ([ctypes.c_double], ctypes.c_void_p),
            'destroy': ([ctypes.c_void_p], None),
            'set': ([ctypes.c_void_p, ctypes.c_int], None),
            'advance': ([ctypes.c_void_p, ctypes.c_double], None),
            'values': ([ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)], None),
            'good': ([ctypes.c_void_p, ctypes.c_double, ctypes.c_double], ctypes.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.lib, 'rovio_statistics_'+name)
            function.argtypes, function.restype = args, result
        self.parameters = parameters()

    def create(self, time):
        return RovioStatistics(self, time)


class RovioStatistics:
    def __init__(self, library, time):
        self.library = library
        self.ptr = library.lib.rovio_statistics_create(time)
        self.time = time
        # ImgUpdate.hpp new-feature initialization sets status TRACKED.
        library.lib.rovio_statistics_set(self.ptr, TRACKED)

    def observe(self, time, tracked):
        if time <= self.time:
            raise ValueError('NONCAUSAL_ROVIO_STATISTICS')
        self.library.lib.rovio_statistics_advance(self.ptr, time)
        self.library.lib.rovio_statistics_set(self.ptr, TRACKED if tracked else UNKNOWN)
        self.time = time

    def good(self, factor=1.):
        p = self.library.parameters
        return bool(self.library.lib.rovio_statistics_good(
            self.ptr, p['trackingUpperBound']*factor, p['trackingLowerBound']*factor))

    def values(self):
        values = (ctypes.c_double*5)()
        self.library.lib.rovio_statistics_values(self.ptr, values)
        return dict(zip(('local_quality', 'local_visibility', 'global_quality',
                         'total_observations', 'tracked_observations'), values))

    def close(self):
        if self.ptr:
            self.library.lib.rovio_statistics_destroy(self.ptr)
            self.ptr = None

    def __del__(self):
        self.close()
