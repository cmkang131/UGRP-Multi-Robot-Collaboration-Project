"""Opt-in candidate evidence screening; no labels, simulator, or peer handles.

The threshold is a fixed engineering heuristic, not a truth classifier or a
learned SayCan affordance. Expired/conflicting text is retained in the channel
and audit, but cannot masquerade as current evidence in the planning prompt.
All feasible act/args remain available for Gemma to select.
"""
import copy
import hashlib
import json
import re

PARAMETERS = dict(stale_after_s=30., unsupported_weight=.25, version='on_v1')
INSTRUCTION = ('Evidence gate is on. Archived reports are unavailable evidence, not current claims. '
               'Choose among the offered candidates using priority_score and estimated_cost; '
               'prefer an offered observation or question when evidence conflicts. '
               'A fresh uncorroborated report can still be wrong. Do not infer its truth from its ID.')


def option(value):
    if value not in ('off', 'on_v1'):
        raise ValueError('UNKNOWN_PLANNER_EVIDENCE_GATE')
    return value


def _claim(body, facts, task=None):
    from harness.task_planner_evidence import reported_fact
    if task:
        from harness.task_planner_cost_rules import SPECS, FACT_KEYS, extract_english, extract_fixed
        domain=next((d for d,s in SPECS.items() if s['task']==task),None)
        if domain:
            values=extract_english(domain,body) if isinstance(body,str) else extract_fixed(domain,body)
            if len(values)==1:
                subject,predicate=FACT_KEYS[domain]
                return dict(subject=subject,predicate=predicate,value=values[0])
    if isinstance(body, str):
        # Keep properties attached to their named subject. A clear door_wide
        # must not corroborate a blocked door_narrow in the same report.
        claims=[]
        for clause in re.split(r'[.;\n]|\b(?:but|while|whereas|and)\b',body.lower()):
            for fact in facts:
                found=reported_fact(clause,[fact])
                if found is not None and found not in claims:claims.append(found)
        return claims[0] if len(claims)==1 else None
    if isinstance(body, dict):
        if isinstance(body.get('fact'), dict): return body['fact']
        if body.get('passage') and body.get('state') in ('clear', 'blocked'):
            return dict(subject=body['passage'], predicate='passage_state', value=body['state'])
    return None


def apply(context, mode='off'):
    option(mode)
    if mode == 'off' or context.get('planner_evidence_gate') == mode:
        return context
    ctx = copy.deepcopy(context)
    ctx['planner_evidence_gate'] = mode
    now = ctx['now_s']; own = ctx['own']
    facts = [f for f in own.get('observed_facts', []) if 0 <= f.get('observed_at', now+1) <= now]
    reports = []; retained = []; archived = []
    messages = ctx['received_messages'] if ctx['condition'] != 'no_comm' else []
    for m in messages:
        claim = _claim(m['body'], facts, ctx.get('task'))
        same = [f for f in facts if claim and all(f.get(k) == claim.get(k) for k in ('subject','predicate'))]
        latest = max(same, key=lambda f:f['observed_at']) if same else None
        fresh_own=bool(latest and now-latest['observed_at']<=PARAMETERS['stale_after_s'])
        conflict = bool(fresh_own and latest['observed_at'] >= m['sent_at'] and latest['value'] != claim.get('value'))
        stale = now-m['sent_at'] > PARAMETERS['stale_after_s']
        # A newer direct observation can corroborate even an expired report.
        corroborated = bool(fresh_own and latest['observed_at'] >= m['sent_at'] and latest['value'] == claim.get('value'))
        status = 'conflict' if conflict else 'stale' if stale else 'unverified_current'
        evidence = dict(message_id=m['id'], age_s=now-m['sent_at'],
                        own_observed_at=latest['observed_at'] if latest else None,
                        status=status, own_corroborated=corroborated)
        reports.append((m, evidence, claim))
        # Keep legacy evidence previews consistent with the gate's subject and
        # time comparison; otherwise the prompt would retain an obsolete flag.
        if facts:
            for prior in ctx.get('evidence_assessment',{}).get('reports',[]):
                if prior['message_id']==m['id']:
                    prior.update(conflicts_with_own_observation=conflict if latest else None,
                        last_directly_observed_at=latest['observed_at'] if latest else None,
                        own_evidence=copy.deepcopy(latest))
        if stale or conflict:
            archived.append(dict(**evidence, body_sha256=hashlib.sha256(json.dumps(m['body'],sort_keys=True).encode()).hexdigest()))
        else: retained.append(m)
    # Preserve original bodies outside the request in Planner audit/channel records.
    ctx['received_messages'] = retained
    ctx['evidence_gate'] = dict(parameters=copy.deepcopy(PARAMETERS), archived_reports=archived,
        policy=INSTRUCTION, selection='Gemma chooses unchanged feasible act/args; priority only',
        limitation='Fresh incorrect claims without newer own evidence cannot be detected.')
    for c in ctx['candidates']:
        p=c['preview']; args=c['args']; algebra=p.get('hypothetical_costs')
        if facts and 'evidence' in p:
            p['evidence']=copy.deepcopy(ctx.get('evidence_assessment',{}).get('reports',[]))
        verification = c['act'] == 'search' or (c['act']=='report' and any(t in args.get('fact','').lower() for t in ('confirm','request','?')))
        dependencies=[]
        for m,e,claim in reports:
            # Offline public algebra defines which actions depend on the unknown
            # public task state. Native acts use explicit public entity names.
            if algebra is not None:
                depends=len(set(algebra.values()))>1
            else:
                body=json.dumps(m['body']).lower()
                names=[args.get(k,'') for k in ('cargo','via','station','area')]
                depends=any(n and re.search(r'(?<!\w)'+re.escape(n.lower())+r'(?!\w)',body) for n in names)
                depends |= args.get('partner')==m['sender'] and c['act'] in ('carry','help')
                depends |= c['act']=='wait' and m['sender'] in ctx.get('can_send_to',[])
            if depends: dependencies.append(copy.deepcopy(e))
        # Do not let a superseded stale message invalidate a current same-sender
        # update. Each public task in the offline algebra is one fact family.
        current={}
        for e in dependencies:
            m=next(m for m,_,_ in reports if m['id']==e['message_id'])
            claim=_claim(m['body'],facts,ctx.get('task'))
            key=(m['sender'],) if algebra is not None else (m['sender'], claim['subject'], claim['predicate']) if claim else (m['sender'],m['id'])
            if key not in current or e['age_s']<current[key]['age_s']:current[key]=e
        used=list(current.values())
        bad=[e for e in used if e['status'] in ('stale','conflict') and not e['own_corroborated']]
        supported=any(e['status']=='unverified_current' or e['own_corroborated'] for e in used)
        status='conflict' if any(e['status']=='conflict' for e in bad) else 'stale' if bad and (algebra is None or not supported) else 'independent' if not used else 'current'
        # Costs already marginalize unsupported reports using the public prior.
        # Physical menus have no algebra; use a conservative affordance weight.
        weight=PARAMETERS['unsupported_weight'] if status in ('stale','conflict') and not verification else 1.
        cost=p.get('estimated_cost', p.get('expected_s'))
        score=(1./(1.+float(cost))) if cost is not None else 1.
        if algebra is None:score*=weight
        if status=='conflict' and not verification:score*=PARAMETERS['unsupported_weight']
        relevant_times=[e['own_observed_at'] for e in dependencies if e['own_observed_at'] is not None]
        if args.get('cargo')=='beam_1' and own.get('last_direct_beam_observation_at') is not None:
            relevant_times.append(own['last_direct_beam_observation_at'])
        p['candidate_evidence']=dict(reports=dependencies, own_observed_at=max(relevant_times,default=None),
            status=status, evidence_weight=weight, verification_action=verification,
            treatment='lower_priority_and_refresh' if status in ('stale','conflict') else 'retain')
        frame_at=(own.get('rgb') or {}).get('t_sim')
        if frame_at is not None and 0 <= frame_at <= now:
            p['candidate_evidence']['own_rgb_observed_at']=frame_at
        p['priority_score']=score
    return ctx
