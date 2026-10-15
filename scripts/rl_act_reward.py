"""Training-only truth reward and unchanged ACT15 lift evaluator.

Never import this module into the deployment actor. User 2026-10-16 permits
privileged reward/critic during learning only. Shaping: Ng et al. ICML1999.
"""
from dataclasses import asdict, dataclass
import math

GAMMA = .995  # rl1 plan: per0.1SIMs, discount half-life13.8SIMs
SUCCESS_REWARD = 10.  # ten times the unit potential span; learning coefficient


def potential(distance, angle, distance_p95):
    if not all(math.isfinite(v) for v in (distance, angle, distance_p95)):
        raise ValueError('finite training truth required')
    if distance < 0 or distance_p95 <= 0:
        raise ValueError('nonnegative distance and positive training p95 required')
    return -(min(distance/distance_p95, 1.)+min(abs(angle)/math.pi, 1.))/2


def shaped_reward(before, after, *, first_success, terminal, gamma=GAMMA):
    if not all(math.isfinite(v) for v in (before, after, gamma)) or not 0 < gamma <= 1:
        raise ValueError('invalid shaping transition')
    # A finite task horizon is a terminal, not an artificial collector truncation.
    shaping = gamma*(0. if terminal else after)-before
    success = SUCCESS_REWARD if first_success else 0.
    return {'reward': success+shaping, 'success_reward': success, 'shaping': shaping}


@dataclass(frozen=True)
class Heuristics:
    """Training coefficients, never acceptance criteria; all default OFF.

    h1 integrates to at most one unit over ACT15's 900 ticks. h2 equals its
    ten-unit success bonus. h3 adds a unit-span angle potential. These are
    declared pilot scales, not empirical success thresholds. h5 is ACT work.
    """
    h1_center_v1: bool = False
    h2_false_done_v1: bool = False
    h3_alignment_v1: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in asdict(self).values()):
            raise ValueError('heuristic toggles must be booleans')


@dataclass(frozen=True)
class TrainingTruth:
    """Owner-only reward inputs; never serialize into an actor observation.

    target_xy: selected unoccluded target centre in actual own distorted RGB,
    normalized to [-1,1]. Projection alone cannot establish visibility. None
    means outside/occluded/indiscernible. stable_lift never gates an action.
    """
    distance_m: float
    alignment_rad: float
    target_xy: tuple[float, float] | None
    stable_lift: bool

    def __post_init__(self):
        potential(self.distance_m, self.alignment_rad, 1.)
        if type(self.stable_lift) is not bool:
            raise ValueError('boolean stable lift required')
        if self.target_xy is not None and (len(self.target_xy) != 2 or
                any(not math.isfinite(v) or abs(v) > 1 for v in self.target_xy)):
            raise ValueError('visible centre must be in normalized own-image bounds')


def centre_score(xy):
    # Continuous score avoids an invented central-region acceptance threshold.
    return -1. if xy is None else 1. - math.hypot(*xy) / math.sqrt(2.)


def reward_transition(before, after, *, distance_p95, first_done, terminal,
                      heuristics=Heuristics(), gamma=GAMMA):
    """Training only; log all ON/OFF terms on the same transition.

    h1 is a task preference, not policy-invariant shaping. It may penalize the
    successful final blind segment: inspect a successful teacher before use.
    h2 fires once per issued done. h3 uses signed Ng1999 potential progress,
    not positive-clipped gains that reward oscillation. Counterfactual reward
    terms are NOT an independently trained heuristic ablation.
    """
    if type(first_done) is not bool or type(terminal) is not bool:
        raise ValueError('boolean transition flags required')
    base = shaped_reward(potential(before.distance_m, before.alignment_rad, distance_p95),
                         potential(after.distance_m, after.alignment_rad, distance_p95),
                         first_success=after.stable_lift and not before.stable_lift,
                         terminal=terminal, gamma=gamma)
    angle_before = -min(abs(before.alignment_rad) / math.pi, 1.)
    angle_after = -min(abs(after.alignment_rad) / math.pi, 1.)
    counterfactual = {
        'h1_center_v1': centre_score(after.target_xy) / 900.,
        'h2_false_done_v1': -SUCCESS_REWARD if first_done and not after.stable_lift else 0.,
        'h3_alignment_v1': gamma * (0. if terminal else angle_after) - angle_before,
    }
    terms = {k: v if asdict(heuristics)[k] else 0. for k, v in counterfactual.items()}
    return {**base, 'reward': base['reward'] + sum(terms.values()),
            'heuristic_terms': terms, 'counterfactual_terms': counterfactual,
            'counterfactual_scope': 'same-transition reward only; no causal policy ablation'}


class StableLift:
    # EXACT ACT15 LiftScore, 3f99d58c harness/grasp_act_rollout.py:66.
    # These existing task criteria are not tuned by RL or its reward scale.
    CRITERIA = {'clearance_m': .012, 'tilt_deg': 10., 'finger_each_n': .5, 'hold_s': 3.}

    def __init__(self):
        self.previous_t = None
        self.previous_good = False
        self.stable_s = self.max_stable_s = 0.

    def add(self, now, clearance, tilt, forces, weld):
        if weld:
            raise ValueError('WELD_ACTIVE')
        if not all(math.isfinite(v) for v in (now, clearance, tilt, *forces)) or len(forces) != 2:
            raise ValueError('finite evaluator input required')
        elapsed = 0. if self.previous_t is None else now-self.previous_t
        if not 0 <= elapsed <= .15+1e-8:
            raise ValueError('evaluation clock gap')
        good = clearance >= .012 and tilt <= 10. and min(forces) >= .5
        self.stable_s = self.stable_s+elapsed if good and self.previous_good else 0.
        self.max_stable_s = max(self.max_stable_s, self.stable_s)
        self.previous_t, self.previous_good = now, good
        return self.success

    @property
    def success(self):
        return self.max_stable_s >= 3.-1e-8
