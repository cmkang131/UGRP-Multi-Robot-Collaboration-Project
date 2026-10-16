"""Time identity independent of the memory algorithm/schema version.

raw_sim_v1: issued commands/holds and capture/last_fix/last_look_fix keep raw
SIM time. Existing quantized PF reports retain their own 1e-4 s comparison
contract; memory predicates/tolerances are unchanged. Historical records with
no time_contract stay unlabelled: do not infer this identity from v2/v3 alone.
"""

TIME_CONTRACT = 'raw_sim_v1'


def condition_label(condition, time_contract=None):
    """Display an explicitly recorded contract; preserve historical labels."""
    return condition if time_contract is None else f'{condition}; time_contract={time_contract}'
