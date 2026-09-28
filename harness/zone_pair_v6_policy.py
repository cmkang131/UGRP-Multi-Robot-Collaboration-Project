"""Explicit pair ablations; the frozen v5h path remains the default."""
from dataclasses import dataclass

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


POLICIES = {
    'v5h': PairPolicy(),
    'b-only': PairPolicy('b-only', posterior_relook=True),
    'a+b': PairPolicy('a+b', posterior_relook=True, beam_relative=True),
    'b-v6c': PairPolicy('b-v6c', posterior_relook=True, exact_fix_clock=True, grasp_range_entry=True),
}
# Registered ablation sets. v6 (historical, PR #246/#259) and v6c (this bundle).
REVISION_POLICIES = {'v6': ('v5h', 'b-only', 'a+b'), 'v6c': ('v5h', 'b-only', 'b-v6c')}


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
