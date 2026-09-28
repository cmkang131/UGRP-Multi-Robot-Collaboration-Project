"""Version 2 motion/distribution initialization over the hash-frozen M1 methods.

No measurement catalogue is constructed. The original module and VIS3 factory
are untouched; a private class adapter is passed to the factory, never patched
into shared globals. Field/RNG parity with the scored PF is regression-tested.
"""
import copy
from types import SimpleNamespace
import numpy as np


def motion_module(frozen):
    class MotionLocalizer(frozen.OwnCamLocalizer):
        def __init__(self, static_map, params=None, seed=0):
            self.params = copy.deepcopy(dict(frozen.DEFAULT_PARAMS if params is None else params))
            self.map = static_map
            self.rng = np.random.default_rng(seed)
            self.n = int(self.params['particles'])
            self.px = np.zeros((self.n, 3))
            self.scale = np.ones((self.n, 3))
            self.logw = np.zeros(self.n)
            self.initialized = False
            self.t = 0.
            self.cmd = np.zeros(3)
            self.cmd_expires = -1.
            self.vel = np.zeros(3)
            self.servo = {}
            self.load = frozen.LoadState()
            m = self.params['map']
            x0, x1, y0, y1 = static_map['bounds_m']
            c = m['robot_clearance_m']
            self.bounds = (x0+c, x1-c, y0+c, y1-c)
            self.rects = np.array([[o['center_m'][0], o['center_m'][1], o['half_extents_m'][0]+c,
                                   o['half_extents_m'][1]+c] for o in static_map['obstacles']
                                  if o.get('kind') == 'wall'], float).reshape(-1, 4)
            # Historical report storage only; scan measurement owns fix receipts.
            self.last_tag_t = None
            self.stats = {'updates': 0, 'resets': 0, 'resamples': 0}
            self.motion_profile = None
            self.last_best_loglik = None
            self.last_servo_cmd_t = -1e9
            self.kidnap_run = 0

    return SimpleNamespace(**{**vars(frozen), 'OwnCamLocalizer': MotionLocalizer})
