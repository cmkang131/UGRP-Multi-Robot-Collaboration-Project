"""Default-off static-map localization from own RGB endpoints and issued motion.

Reuse the pinned AMCL likelihood-field, augmented recovery/resampling and own
landmark likelihood. Global initialization uses only static free geometry; no
starting pose, live scene, evaluator, peer state or measured joints are accepted.
Fixed 2000 particles is Nav2's documented default maximum (no KLD claim).
"""
import math
import numpy as np
from harness.self_map_relocalize import Relocalizer
from harness.own_map_amcl_vendor import field, augmented
from harness.own_map_amcl_vendor.landmarks import MapFeatures
from harness.ego_pose_continuity import dominant_cluster

OPTIONS = ('off', 'static_walls_v1', 'static_landmarks_v1')


def create(static_map, *, option='off', seed=0):
    if option not in OPTIONS:
        raise ValueError('UNKNOWN_STATIC_RGB_LOCALIZER')
    if option == 'off':
        return None
    return StaticRGBLocalizer(static_map, option=option, seed=seed)


class StaticRGBLocalizer(Relocalizer):
    def __init__(self, static_map, *, option, seed):
        if option not in OPTIONS[1:]:
            raise ValueError('EXPLICIT_STATIC_RGB_LOCALIZER_REQUIRED')
        self.option = option
        self.field = field.Field(static_map)
        lo_x,hi_x,lo_y,hi_y = map(float, static_map['bounds_m'])
        if not (hi_x>lo_x and hi_y>lo_y):
            raise ValueError('FINITE_STATIC_BOUNDS_REQUIRED')
        # Rejection sampling in known free space. This is a distribution, not an
        # initial location hint. Radius 0.15m is the existing robot footprint.
        self.bounds = np.array([lo_x,hi_x,lo_y,hi_y])
        self.rng = np.random.default_rng(seed)
        self.n = 2000
        self.px = self._uniform_free(self.n)
        self.logw = np.zeros(self.n)
        self._inject = 0.
        self.stats = dict(resamples=0)
        self.policy = augmented.Policy()
        self.odom = np.zeros(3)
        self.anchor = None
        self.updates = 0
        self.likelihood_tempering = 'off'
        self.tempering_audit = []
        self.sensor_landmarks = 'floor_zones_doors_v1' if option=='static_landmarks_v1' else 'off'
        self.landmark_map = MapFeatures(static_map) if self.sensor_landmarks!='off' else None

    def _uniform_free(self, n):
        got=[];remaining=n
        for _ in range(100):
            xy=self.rng.uniform(self.bounds[[0,2]],self.bounds[[1,3]],size=(max(remaining*2,32),2))
            xy=xy[self.field.distances(xy)>.15][:remaining]
            if len(xy):got.append(xy);remaining-=len(xy)
            if not remaining:break
        if remaining:raise ValueError('STATIC_MAP_NO_FREE_PRIOR')
        return np.c_[np.concatenate(got),self.rng.uniform(-math.pi,math.pi,n)]

    def step(self, **kwargs):
        row=super().step(**kwargs)
        pose,cluster=dominant_cluster(self.px,self._weights())
        row.update(full_posterior_pose=row['pose'],pose=pose.tolist(),cluster=cluster,
                   option=self.option,initial_pose_source='uniform_static_free_space')
        return row
