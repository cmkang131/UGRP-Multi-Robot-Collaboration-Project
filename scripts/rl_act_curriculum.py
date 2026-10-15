"""Default-OFF training reset curriculum; no policy observations or actions.

Starts are ranked by empirical distance/yaw percentiles. First training third
uses the easiest quartile, second third the easiest half, final third all.
Fractions partition the finite pilot, not success/acceptance gates. Evaluation
uses its separately sealed, unmodified manifest. Florensa et al. 2017 inspires
this simple curriculum; it is not a reverse-curriculum reproduction.
"""
from dataclasses import dataclass
import math
import random


@dataclass(frozen=True)
class Start:
    seed: int
    distance_m: float
    yaw_rad: float
    plan: dict


class Curriculum:
    def __init__(self, starts, *, evaluation_seeds, transition_limit, rng_seed,
                 h4_curriculum_v1=False):
        if (type(h4_curriculum_v1) is not bool or type(transition_limit) is not int
                or transition_limit <= 0 or not starts):
            raise ValueError('explicit finite curriculum configuration required')
        if len({s.seed for s in starts}) != len(starts):
            raise ValueError('duplicate training seeds')
        if set(s.seed for s in starts) & set(evaluation_seeds):
            raise ValueError('training/evaluation seeds overlap')
        for s in starts:
            if (type(s.seed) is not int or not math.isfinite(s.distance_m) or s.distance_m < 0
                    or not math.isfinite(s.yaw_rad) or s.plan.get('seed') != s.seed):
                raise ValueError('invalid start manifest')
        def rank(v, values):
            return sum(x < v for x in values) / len(values)
        distances = [s.distance_m for s in starts]
        angles = [abs(s.yaw_rad) for s in starts]
        self.starts = tuple(sorted(starts, key=lambda s: (
            rank(s.distance_m, distances) + rank(abs(s.yaw_rad), angles), s.seed)))
        self.limit, self.enabled = transition_limit, h4_curriculum_v1
        self.rng = random.Random(rng_seed)

    def pool(self, transitions):
        if type(transitions) is not int or not 0 <= transitions <= self.limit:
            raise ValueError('transition count outside finite pilot')
        fraction = (1. if not self.enabled or transitions * 3 >= self.limit * 2 else
                    .5 if transitions * 3 >= self.limit else .25)
        return self.starts[:max(1, math.ceil(len(self.starts) * fraction))]

    def sample(self, transitions, nworld):
        if type(nworld) is not int or nworld <= 0:
            raise ValueError('positive world count required')
        from copy import deepcopy
        return [deepcopy(self.rng.choice(self.pool(transitions)).plan) for _ in range(nworld)]
