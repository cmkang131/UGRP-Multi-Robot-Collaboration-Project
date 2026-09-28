"""Explicit pair ablations; the frozen v5h path remains the default."""
from dataclasses import dataclass

# v80 (workflow zone-study-integration-run 2.13.0) is RESERVED for the b-v6d flags below; this branch
# is a stage probe and registers neither (the catalog and EXECUTION_BUNDLE_ID stay untouched).
# v68 = pre-merge v6 draft (retired, offline replay only); v70 = v6 on main v69
# (retired: recorded by the 2026-09-28 v6 dev cohort, PR #259). v76 = v70 plus
# the opt-in v6c flags (exact PF fix clock, grasp-range beam colour at the
# pre-grasp entry). Next free number after main v70 and open PRs v72 (#256),
# v73 (#257), v74 (#249), v75 (#261).
EXECUTION_BUNDLE_ID = 'zone-pair-v76-fixclock-grasp-entry'


@dataclass(frozen=True)
class PairPolicy:
    name: str = 'v5h'
    posterior_relook: bool = False
    beam_relative: bool = False
    # v6c (2026-09-29 stage probes, PR #260): the PF clock ends exactly at the
    # capture time it was predicted to, so a fresh fix has age 0, never < 0.
    exact_fix_clock: bool = False
    # v6c: standoff fit and pre-close partial evidence use the grasp-range beam
    # colour (hue 25-54, as grip_view/co-motion) and a settled final descent frame.
    grasp_range_entry: bool = False
    # v6d (2026-09-29 stage-2 replay of the b-v6c probe, see harness/owncam_align_motion_v6d.py and
    # experiments/2026-09-29-pair-v6d-align): (1) beam heading in the close p45/inspect views uses the
    # hue range 25-54, because the beam top renders yellow there (hue 25-36) and the lime-only mask kept
    # just the end faces; (2) the PF predicts align pulses with the M1 ``fine`` motion profile.
    beam_wide_hue: bool = False
    align_fine_motion: bool = False


POLICIES = {
    'v5h': PairPolicy(),
    'b-only': PairPolicy('b-only', posterior_relook=True),
    'a+b': PairPolicy('a+b', posterior_relook=True, beam_relative=True),
    'b-v6c': PairPolicy('b-v6c', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True),
    'b-v6d': PairPolicy('b-v6d', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True,
                        beam_wide_hue=True, align_fine_motion=True),
}
# Registered ablation sets. v6 (historical, PR #246/#259), v6c (bundle v76) and v6d (stage probe).
REVISION_POLICIES = {'v6': ('v5h', 'b-only', 'a+b'), 'v6c': ('v5h', 'b-only', 'b-v6c'),
                     'v6d': ('v5h', 'b-only', 'b-v6c', 'b-v6d')}
# Beam postures in which the b-v6d wide hue range applies (search keeps the v1 lime range: the far
# view of the beam is lime, and the partner robot's yellow parts enter it; replay, README).
WIDE_HUE_LO = 25
WIDE_HUE_POSTURES = ('p45', 'inspect')
# Opt-in b-v6d probe flags; the registered contract lists them only when set (scripts/zone_pair_v6_contract.py).
V6D_PROBE_FLAGS = ('beam_wide_hue', 'align_fine_motion')


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
