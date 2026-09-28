"""Explicit pair ablations; the frozen v5h path remains the default."""
from dataclasses import dataclass

# v68 = pre-merge v6 draft (retired, offline replay only); v70 = v6 on main v69
# (retired: recorded by the 2026-09-28 v6 dev cohort, PR #259). v75 = v70 plus
# the opt-in v6b start bootstrap (dock prior + stationary look); next free
# number after main v70 and open PRs v72 (#256), v73 (#257), v74 (#249).
EXECUTION_BUNDLE_ID = 'zone-pair-v75-dock-prior-bootstrap'


@dataclass(frozen=True)
class PairPolicy:
    name: str = 'v5h'
    posterior_relook: bool = False
    beam_relative: bool = False
    # v6b: static dock prior + stop-and-look before the first own motion.
    stationary_bootstrap: bool = False


POLICIES = {
    'v5h': PairPolicy(),
    'b-only': PairPolicy('b-only', posterior_relook=True),
    'a+b': PairPolicy('a+b', posterior_relook=True, beam_relative=True),
    'b-boot': PairPolicy('b-boot', posterior_relook=True, stationary_bootstrap=True),
    'a+b-boot': PairPolicy('a+b-boot', posterior_relook=True, beam_relative=True, stationary_bootstrap=True),
}
# Registered ablation sets. v6 (historical, PR #246/#259) and v6b (this bundle).
REVISION_POLICIES = {'v6': ('v5h', 'b-only', 'a+b'), 'v6b': ('v5h', 'b-boot', 'a+b-boot')}


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
