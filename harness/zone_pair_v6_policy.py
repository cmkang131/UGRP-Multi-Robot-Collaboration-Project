"""Explicit pair ablations; the frozen v5h path remains the default."""
from dataclasses import dataclass, replace

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
# v81 (stage probes v6e/v6g carry, workflow zone-study-integration-run 2.14.0, coordinator-assigned) = v80 plus the
# opt-in v6e/v6f/v6g pair flags (carry dead-reckoning model, pair-mean yaw, beam-edge relative yaw, general lateral
# breakaway + cross-axis drift model, end inset, own-image validity by optical black, bounded retreat); the b-v6g policy
# is the registered v6e-revision policy. v80 is retired. The other pair policies are unchanged.
# v83 / workflow 2.16.0: b-v6h1 candidate; v82 / 2.15.0 remain unused.
# Pre-seal implementation only. No v6h registration or execution admission yet.
EXECUTION_BUNDLE_ID = 'zone-pair-v83-carry-door-gain'


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
    # v6e yaw (2026-09-29 offline yaw analysis, experiments/2026-09-29-pair-v6e-carry), two more opt-in flags; both
    # need carry_dr_model (they re-parameterise its per-particle yaw-rate bias):
    # carry_pair_yaw: the PF's carry yaw prediction is the MEAN of the own and the partner's loaded-plant yaw
    # targets (a rigid pair turns with the mean); the partner's command of the leg is derived from the static
    # route plan and the role (mirrored command), never received (harness/zone_pair_executor.py, README).
    carry_pair_yaw: bool = False
    # carry_beam_edge: the slope change of the carried beam's lower edge in the own wrist RGB is the robot-minus-beam
    # relative-yaw change and is added to the PF yaw (harness/own_beam_edge.py).
    carry_beam_edge: bool = False
    # v6g (2026-09-29, after the held-out hA 4/10): carry_dr_general adds to the carry_dr_model PF (i) a lateral command
    # deadband (the loaded plant does not respond to the tiny own-estimate steer commands; the linear model did, a
    # 33 mm phantom shift per steer phase) and (ii) a per-particle cross-axis drift ratio proportional to the travelled
    # distance (Thrun et al. 2005 odometry model / AMCL omni alpha5), and takes the yaw-flag biases from a refit on
    # cal placements that span several y offsets and beam headings (harness/owncam_carry_v6e.py, README).
    carry_dr_general: bool = False
    # carry_end_inset_m: opt-in ROUTE change. The last route point is moved back along the last leg by this many
    # metres (the beam stops short of the zone centre); the L7 collision-guard diagnosis (east wall x 5.375 m) motivates
    # 0.10. Changes the end point definition: results with it are reported separately (harness/zone_pair_executor.py).
    carry_end_inset_m: float = 0.
    # v6f (2026-09-29 stage 5 probe, PR #266 baseline 0/13): the destination set-down.
    # (1) The per-step own-image validity gate measures "dark" against the frame's own optical-black
    # reference (the fisheye exterior) instead of the fixed level V < 8, which rejects the
    # shadowed dark floor at the destination on one robot (harness.zone_pair_vision.valid_frame_ob).
    own_image_ob: bool = False
    # (2) After the beam is released (controller state ``released``), the reverse retreat is bounded by
    # the unchanged sweep guard: a vetoed reverse command is not issued and the robot holds (MoveIt
    # Task Constructor MoveRelative min_distance 0), instead of failing the whole job.
    bounded_retreat: bool = False
    # v6h: fixed PR #284 calibration multiplier, only loaded gain[0][0].
    carry_fwd_gain: float = 1.0
    # Only loaded pair base motion; approach and ALL arm sweeps retain 2/2.
    loaded_k_xy: float = 2.0
    loaded_k_yaw: float = 2.0
    loaded_gate_yaw_deg: tuple[float, float] | None = None
    # p2f: no reliable stall detection for the loaded pair when no moved fix arrives.
    progress_arm_on_moved_fix: bool = False
    # Axial timing also inverts the lag plant, with the SAME fixed forward gain.
    carry_axial_lag: bool = False


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
    # b-v6e-base = the b-v6e of the first carry cohorts (PR #266 and the cal raws): dr + lag + both place flags.
    'b-v6e-base': PairPolicy('b-v6e-base', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                             beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True,
                             carry_lateral_lag=True, own_image_ob=True, bounded_retreat=True),
    # b-v6e = b-v6e-base + both yaw flags (pair-mean plant model, own-RGB beam-edge relative yaw); the two
    # ablations switch one yaw flag each.
    'b-v6e': PairPolicy('b-v6e', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True, carry_lateral_lag=True,
                        own_image_ob=True, bounded_retreat=True, carry_pair_yaw=True, carry_beam_edge=True),
    'b-v6e-pm': PairPolicy('b-v6e-pm', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                           beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True,
                           carry_lateral_lag=True, own_image_ob=True, bounded_retreat=True, carry_pair_yaw=True),
    'b-v6e-edge': PairPolicy('b-v6e-edge', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                             beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True,
                             carry_lateral_lag=True, own_image_ob=True, bounded_retreat=True, carry_beam_edge=True),
    # v6g = b-v6e + carry_dr_general; b-v6g-l7 = b-v6g + the 0.10 m end inset (the L7 route change, reported separately).
    'b-v6g': PairPolicy('b-v6g', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True, carry_lateral_lag=True,
                        own_image_ob=True, bounded_retreat=True, carry_pair_yaw=True, carry_beam_edge=True,
                        carry_dr_general=True),
    'b-v6g-l7': PairPolicy('b-v6g-l7', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                           beam_wide_hue=True, align_fine_motion=True, carry_dr_model=True, carry_lateral_lag=True,
                           own_image_ob=True, bounded_retreat=True, carry_pair_yaw=True, carry_beam_edge=True,
                           carry_dr_general=True, carry_end_inset_m=.10),
    # v6f = b-v6c + own_image_ob + bounded_retreat; the two ablations switch one flag each.
    'b-v6f-a': PairPolicy('b-v6f-a', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                          own_image_ob=True),
    'b-v6f-b': PairPolicy('b-v6f-b', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                          bounded_retreat=True),
    'b-v6f': PairPolicy('b-v6f', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        own_image_ob=True, bounded_retreat=True),
}
POLICIES['b-v6h1'] = replace(POLICIES['b-v6g'], name='b-v6h1',
                             carry_fwd_gain=0.9483378899463337,
                             loaded_k_xy=1.0, loaded_k_yaw=1.0,
                             loaded_gate_yaw_deg=(5.0, 4.0),
                             progress_arm_on_moved_fix=True, carry_axial_lag=True)
# Registered ablation sets. v6 (historical, PR #246/#259), v6b (historical DRAFT,
# PR #261, bundle v75), v6c (PR #263, bundle v76; sealed, now historical) and
# v6d (PR #265, bundle v80; now historical) and v6e (current carry stage-probe DRAFT, bundle v81; b-v6g).
REVISION_POLICIES = {'v6': ('v5h', 'b-only', 'a+b'), 'v6b': ('v5h', 'b-boot', 'a+b-boot'),
                     'v6c': ('v5h', 'b-only', 'b-v6c'), 'v6d': ('v5h', 'b-only', 'b-v6d'),
                     'v6e': ('v5h', 'b-only', 'b-v6g'),
                     'v6h': ('v5h', 'b-only', 'b-v6h1')}
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
