"""Permitted report ages and own observations; never consult evaluator labels.

The optional fact records come only from the owning robot's perception history.
Unknown means unknown: absent own evidence cannot certify a fresh report.
"""
import copy
import re

PARAMETERS = dict(stale_after_s=30., fresh_report_weight=.95,
                  tentative_report_weight=.35, stale_report_weight=0.)


def enrich(context):
    ctx = copy.deepcopy(context)
    now = ctx['now_s']
    facts = ctx['own'].get('observed_facts', [])
    evidence = []
    for m in ctx['received_messages']:
        age = now - m['sent_at']
        # A channel payload may explicitly identify its fact, but an NL body is
        # not secretly replaced by a ground-truth proposition.
        body = m['body']
        claim = body.get('fact') if isinstance(body, dict) else reported_fact(body, facts)
        matches = [f for f in facts if claim and f.get('subject') == claim.get('subject')
                   and f.get('predicate') == claim.get('predicate') and f.get('observed_at', now+1) <= now]
        latest = max(matches, key=lambda f:f['observed_at']) if matches else None
        evidence.append(dict(message_id=m['id'], age_s=age, stale=age>30,
            last_directly_observed_at=None if latest is None else latest['observed_at'],
            conflicts_with_own_observation=None if latest is None else latest['value'] != claim.get('value'),
            own_evidence=copy.deepcopy(latest)))
    ctx['evidence_assessment'] = dict(reports=evidence, own_observed_facts=copy.deepcopy(facts),
        policy='Prefer newer own observations over older reports. Verify conflicts before commitment. Freshness is not truth.',
        trust_parameters=PARAMETERS, calibration='heuristic, not empirically calibrated')
    for c in ctx['candidates']:
        c['preview']['evidence'] = copy.deepcopy(evidence)
    return ctx


def cost_previews(ctx, view):
    """Enumerate public algebra, not the evaluator's realized hidden-world cost."""
    from harness.task_planner_cost_rules import rule, costs, domain_of, SPECS
    try: domain = domain_of(view)
    except StopIteration: return ctx  # Other public tasks have no numeric algebra.
    view = copy.deepcopy(view)
    if ctx['condition'] == 'no_comm': view['messages'] = []
    _, estimate = rule(view)
    for c in ctx['candidates']:
        label = c['preview']['public_cost_label']
        c['preview'].update(estimated_cost=estimate['estimated_costs'][label],
            hypothetical_costs={w:costs(domain,view['self_state']['travel_estimates'],w)[label] for w in SPECS[domain]['worlds']},
            estimate_source='public algebra; bounded-age heuristic belief, not hidden state')
    ctx['evidence_assessment']['cost_belief'] = estimate['posterior']
    return ctx


def reported_fact(text, own_facts):
    """Conservative explicit-subject extraction, never a task-vote decoder.

    Do not compare a peer's private view with this robot's absence observation.
    A match must name the same public subject and property as own perception.
    """
    if not isinstance(text,str):return None
    t=text.lower()
    for f in own_facts:
        subject=f.get('subject','');predicate=f.get('predicate')
        if not subject or not re.search(r'(?<![\w])'+re.escape(subject.lower())+r'(?![\w])',t):continue
        value=None
        if predicate=='passage_state':
            if re.search(r'not blocked|is clear|is open|passable',t):value='clear'
            elif re.search(r'is blocked|is obstructed|cannot pass',t):value='blocked'
        elif predicate=='grip':
            if re.search(r'grip is slipping|gripper is slipping',t):value='slipping'
            elif re.search(r'grip is holding|gripper is holding',t):value='holding'
        if value is not None:return dict(subject=subject,predicate=predicate,value=value)
    return None
