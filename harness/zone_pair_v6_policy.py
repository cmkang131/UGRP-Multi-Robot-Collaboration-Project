"""Explicit pair ablations; the frozen v5h path remains the default."""
from dataclasses import dataclass

# v68 = pre-merge v6 draft (retired, offline replay only); v70 = v6 on main v69
# (retired: recorded by the 2026-09-28 v6 dev cohort, PR #259). v75 = v70 plus
# the opt-in v6b start bootstrap (dock prior + stationary look), PR #261;
# retired with the v6b DRAFT (historical, recorded by the v6b offline replay).
# v77 = v75 plus the B7 real model driver and registered speech caps
# (PR #256; the pre-merge candidate v72 never ran and was never on main).
# The pair policies are unchanged. v76 is claimed by open PR #263 (v6c).
# v78 = v77 plus the B6 eval-only referee and scenario hidden events (PR #257;
# pre-merge candidate v73 never ran). Pair policies unchanged; v77 retired.
# v79 = v78 plus explicitly versioned MasterPi v3 scenes and command geometry
# (PR #249; pre-merge candidate v74 never ran). Pair policies unchanged; v78 retired.
# v76 (PR #263, number reserved by the coordinator) = main v79 plus the opt-in
# v6c flags (exact PF fix clock, grasp-range beam colour at the pre-grasp
# entry). The v6c stage probes (2026-09-29) ran the pre-merge v76 on main v70;
# v79 is retired.
# v80 (PR stage probe b-v6d, workflow zone-study-integration-run 2.13.0, coordinator-assigned) = v76 plus
# the opt-in b-v6d flags (wide-hue beam heading in the close p45/inspect views, M1 ``fine`` motion profile
# for align pulses); v76 is retired. The other pair policies are unchanged.
EXECUTION_BUNDLE_ID = 'zone-pair-v80-align-widehue-finemotion'


@dataclass(frozen=True)
class PairPolicy:
    name: str = 'v5h'
    posterior_relook: bool = False
    beam_relative: bool = False
    # v6b: static dock prior + stop-and-look before the first own motion.
    stationary_bootstrap: bool = False
    # v6c (2026-09-29 stage probes, PR #260): the PF clock ends exactly at the
    # capture time it was predicted to, so a fresh fix has age 0, never < 0.
    exact_fix_clock: bool = False
    # v6c: standoff fit and pre-close partial evidence use the grasp-range beam
    # colour (hue 25-54, as grip_view/co-motion) and a settled final descent frame.
    grasp_range_entry: bool = False
    # v6d (2026-09-29 stage-2 replay of the b-v6c probe, see harness/owncam_align_motion_v6d.py and
    # experiments/2026-09-29-pair-v6d-align): (1) beam heading in the close p45/inspect views uses the
    # hue range 25-54, because the beam top renders yellow there (hue 25-36) and the lime-only mask kept
    # just the end faces (posture-only condition, so it also applies to r2, where it is unverified);
    # (2) the PF predicts align pulses with the M1 ``fine`` motion profile (whole parameter set: gain/tau,
    # its own noise_abs, slip scale off).
    beam_wide_hue: bool = False
    align_fine_motion: bool = False
    # v6e (2026-09-29 carry stage probes, PR #266), two independent flags:
    # carry_dr_model: the PF carries the loaded plant's calibrated dead-reckoning error (motion-gated white
    # noise, a constant per-leg yaw-rate bias, loaded slip-scale spread) instead of the registered
    # rest-diffusing rate noise (harness/owncam_carry_v6e.py). The gate and its thresholds are unchanged.
    carry_dr_model: bool = False
    # carry_lateral_lag: the open-loop lateral carry leg length inverts the calibrated first-order-lag loaded
    # plant instead of the constant CARRY_ODOM_SCALE['lateral'] (harness/owncam_carry_v6e.py).
    carry_lateral_lag: bool = False


POLICIES = {
    'v5h': PairPolicy(),
    'b-only': PairPolicy('b-only', posterior_relook=True),
    'a+b': PairPolicy('a+b', posterior_relook=True, beam_relative=True),
    'b-boot': PairPolicy('b-boot', posterior_relook=True, stationary_bootstrap=True),
    'a+b-boot': PairPolicy('a+b-boot', posterior_relook=True, beam_relative=True, stationary_bootstrap=True),
    'b-v6c': PairPolicy('b-v6c', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True),
    'b-v6d': PairPolicy('b-v6d', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        beam_wide_hue=True, align_fine_motion=True),
    # v6e carry ablation: the latest policy b-v6d plus one or both carry flags.
    'b-v6e-dr': PairPolicy('b-v6e-dr', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                           beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True),
    'b-v6e-lag': PairPolicy('b-v6e-lag', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                            beam_wide_hue=True, align_fine_motion=True, carry_lateral_lag=True),
    'b-v6e': PairPolicy('b-v6e', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True, carry_lateral_lag=True),
}
# Registered ablation sets. v6 (historical, PR #246/#259), v6b (historical DRAFT,
# PR #261, bundle v75), v6c (PR #263, bundle v76; sealed, now historical) and
# v6d (current stage-probe DRAFT, bundle v80).
REVISION_POLICIES = {'v6': ('v5h', 'b-only', 'a+b'), 'v6b': ('v5h', 'b-boot', 'a+b-boot'),
                     'v6c': ('v5h', 'b-only', 'b-v6c'), 'v6d': ('v5h', 'b-only', 'b-v6d')}
# Beam postures in which the b-v6d wide hue range applies (search keeps the v1 lime range: the far
# view of the beam is lime, and the partner robot's yellow parts enter it; replay, README).
WIDE_HUE_LO = 25
WIDE_HUE_POSTURES = ('p45', 'inspect')


def pair_policy(name='v5h'):
    if name not in POLICIES:
        raise ValueError('unknown pair policy')
    return POLICIES[name]


def informative_fix(report):
    """Provider-neutral receipt, separate from detector acceptance and sigma."""
    q = {} if report is None else report.observation_quality or {}
    if q.get('lost') is True:
        return False
    if q.get('last_fix_quality') is not None:
        q = q['last_fix_quality']
        if q.get('t') != report.last_fix_t:
            return False
    return (q.get('informative') is True and q.get('accepted') is True
            and q.get('settled') is True and q.get('ambiguous') is False)
