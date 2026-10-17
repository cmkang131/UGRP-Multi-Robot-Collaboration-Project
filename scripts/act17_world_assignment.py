"""Pure experimental-world routing; candidate IDs never enter policy tensors."""
from copy import deepcopy


def expand_cases(plans,candidates):
    if not candidates or len(set(candidates))!=len(candidates) or not set(candidates)<={'M','F','S'}:
        raise ValueError('unique registered candidate set required')
    if not plans or len(plans)*len(candidates)>24:raise ValueError('at most24 independent physical worlds')
    expanded=[];assignment=[]
    for candidate in candidates:
        for plan in plans:
            # Each world owns its mutable authored setup; no shared spawn dict.
            value=deepcopy(plan);value['act17_candidate']=candidate
            expanded.append(value);assignment.append(candidate)
    return expanded,assignment


def validate_assignment(plans,assignment):
    if not plans or len(plans)!=len(assignment) or len(plans)>24:raise ValueError('world assignment size differs')
    if not set(assignment)<={'M','F','S'}:raise ValueError('unknown experimental candidate')
    sets=[]
    for candidate in sorted(set(assignment)):
        values=[p for p,c in zip(plans,assignment) if c==candidate]
        if any(p.get('act17_candidate')!=candidate for p in values):raise ValueError('plan assignment differs')
        seeds=[p['seed'] for p in values]
        if len(set(seeds))!=len(seeds):raise ValueError('duplicate seed within one candidate')
        sets.append(set(seeds))
    if any(value!=sets[0] for value in sets):raise ValueError('matched candidate seed sets required')


def executor_factory(original,actors,assignment):
    index=0
    def create(_unused_predictor):
        nonlocal index
        if index>=len(assignment):raise ValueError('too many per-world executors')
        actor=actors[assignment[index]];index+=1
        return original(actor.predict)
    return create
