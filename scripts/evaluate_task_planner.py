"""New planner requests on coordinator's frozen 384 worlds + synthetic solo cases.

Four arms; leader arm reuses English reports received by r1 (leader). This is
NOT a multi-turn topology experiment. Labels are joined only after decisions.
The old source's `results_scored` supplies labels; no evaluator data is passed
to candidates, requests, fallback or model. Every error stays in N.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.task_planner import Planner, candidate, signature
from harness.task_planner_model import add_model_options, selected
from harness.task_planner_gemma import Gemma, Budget

ARMS = {'no_comm': 'none', 'structured': 'fixed', 'peer_en': 'english', 'leader_en': 'english'}


def carry(cargo, to='A1', via='door_1', approach='west', mode='solo', partner=None):
    a = dict(cargo=cargo, to=to, via=via, approach=approach, mode=mode)
    if mode == 'joint': a.update(partner=partner or 'r2', side='end_neg')
    return 'carry', a


def action(label, view):
    """Public label->act semantics. No case ID/hidden world/label consulted."""
    choices = set(view['candidates'])
    if choices == {'cyan', 'red', 'beam'}:
        return ('help', dict(partner='r2', cargo='beam_1', side='end_neg')) if label == 'beam' else carry(label, 'A1' if label == 'cyan' else 'B1')
    if choices == {'pair_now', 'solo_first', 'recruit_r3'}:
        return carry('cyan', 'A1') if label == 'solo_first' else ('help', dict(partner='r2' if label == 'pair_now' else 'r3', cargo='beam_1', side='end_neg'))
    if choices == {'accept', 'decline', 'verify'}:
        return {'accept': ('help', dict(partner='r2', cargo='beam_1', side='end_neg')),
                'decline': carry('cyan'), 'verify': ('report', dict(fact='Please confirm whether you still need help with beam_1.'))}[label]
    if choices == {'wait', 'reassign', 'solo'}:
        return {'wait': ('wait', dict(until='partner_arrives', max_s=20.)),
                'reassign': ('help', dict(partner='r3', cargo='beam_1', side='end_neg')), 'solo': carry('cyan')}[label]
    if choices == {'yield', 'proceed', 'negotiate'}:
        return {'yield': ('yield', dict(where='bay_1')), 'proceed': ('go_to', dict(station='corridor_1_exit')),
                'negotiate': ('report', dict(fact='Please confirm whose turn it is in corridor_1.'))}[label]
    if choices == {'narrow', 'wide', 'inspect'}:
        return ('search', dict(area='door_narrow')) if label == 'inspect' else ('reroute', dict(via='door_'+label))
    if choices == {'initial', 'new', 'recover'}:
        return 'search', dict(area={'initial': 'initial_order_slot', 'new': 'P1-3', 'recover': 'pickup_floor'}[label])
    if choices == {'rotate', 'retreat', 'retrieve'}:
        return {'rotate': carry('beam_1', to='beam_staging', via='rotate_clear_of_can', approach='end_neg', mode='joint'),
                'retreat': ('report', dict(fact='Please back away from can_1 west approach.')),
                'retrieve': carry('can_1', to='C1')}[label]
    raise ValueError('UNKNOWN_PUBLIC_TASK')


def adapt(row, arm, planner_evidence_gate='off'):
    view = row['input']; p = Planner(view['self_state']['robot_id'], arm, leader='r1', planner_evidence_gate=planner_evidence_gate)
    for i, m in enumerate(view.get('messages', [])):
        if arm == 'no_comm': break
        body = copy.deepcopy(m['body'])
        if isinstance(body, str): body = f"Observation confidence: {m['confidence']}. " + body
        p.receive(dict(id=f'source-{i}', sender=m['sender'], recipient=p.robot_id,
                       sent_at=m['observation_time_s'], delivered_at=view['now_s']-1, body=body), view['now_s'])
    menu, labels = [], {}
    for label, description in view['candidates'].items():
        act, args = action(label, view)
        c = candidate(act, args, required_robots=2 if act == 'help' or args.get('mode') == 'joint' else 1,
                      source='coordinator_synthetic_cost_model; metric distance/time unknown', description=description)
        # Preserve the public algebra's variable labels in the preview. No hidden scores.
        c['preview']['public_cost_label'] = label
        menu.append(c); labels[signature(c)] = label
    public_rules = {k: copy.deepcopy(view[k]) for k in ('possibilities', 'cost_rule', 'cost_units',
                                                     'evidence_policy', 'fixed_signal_dictionary')}
    own = copy.deepcopy(view['self_state'])
    ctx = p.context(now=view['now_s'], orders=view['public_context']['orders'],
                    static_map=view['public_context']['static_map'], own=own, candidates=menu,
                    task=view['task'], public_rules=public_rules)
    from harness.task_planner_evidence import cost_previews
    cost_previews(ctx, view)
    from harness.task_planner_evidence_gate import apply
    ctx = apply(ctx, planner_evidence_gate)
    return p, ctx, labels


def supplements(planner_evidence_gate='off'):
    """Authored 24 solo choices. Held-out from original dataset; not physical evidence.

    Independent destination/route/approach differences, no incoming reports.
    Ground truth is lowest finite preview time among safe empty slots.
    """
    for i in range(24):
        p = Planner('r1', 'no_comm', planner_evidence_gate=planner_evidence_gate)
        menu = []
        for slot in ('A1', 'A2'):
            for route in ('west_corridor', 'east_corridor'):
                for approach in ('north', 'south'):
                    # Rotate the optimum across all 8 combinations, independently of list order.
                    j = (slot == 'A2')*4 + (route == 'east_corridor')*2 + (approach == 'south')
                    t = 10 + ((j-i) % 8)*3
                    act, args = carry('solo_box', slot, route, approach)
                    menu.append(candidate(act, args, distance_m=t*.1, expected_s=t, blockage_risk='low', unloading_empty='yes'))
        ctx = p.context(now=0., orders=[dict(order_id='solo_box', required_robots=1, destination_zone='A')],
            static_map=dict(routes=['west_corridor', 'east_corridor'], slots=['A1', 'A2'], approaches=['north', 'south']),
            own=dict(robot_id='r1', pose=dict(xy=[0, 0], source='synthetic_own_estimate')),
            candidates=menu[i % 8:] + menu[:i % 8],
            task='Carry solo_box to any free slot in zone A. Choose destination, route and approach minimizing expected time.')
        best = min(menu, key=lambda c: c['preview']['expected_s'])
        yield p, ctx, signature(best)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True); ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--execute', action='store_true'); ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int); ap.add_argument('--relay-url', default='http://127.0.0.1:18424')
    ap.add_argument('--planner-evidence-gate', choices=('off','on_v1'), default='off')
    ap.add_argument('--max-usd', type=float, default=2.)
    add_model_options(ap)
    a = ap.parse_args()
    if a.out.exists(): raise SystemExit('new output directory required')
    a.out.mkdir(parents=True)
    source = json.loads((a.source/'cases_public.json').read_text())
    scored = json.loads((a.source/'results_scored.json').read_text())
    # Labels are evaluator-only and never sent into adapt/model.
    gold = {r['case_id']: r for r in scored if r['model'] == 'rules' and r['condition'] == 'none'}
    assert len(gold) == 384
    main_count = sum(not r['ambiguous'] for r in gold.values())
    jobs = [(row, arm) for arm, source_arm in ARMS.items() for row in source if row['condition'] == source_arm]
    if a.limit is not None: jobs = jobs[:a.limit]
    dump(a.out/'RUN_META.json', dict(**{'class':'dev'}, pr=473, planner_evidence_gate=a.planner_evidence_gate, branch=subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
         sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), batch='planner-offline-v357'))
    manifest = {str(a.source/n): hashlib.sha256((a.source/n).read_bytes()).hexdigest()
                for n in ('README.md', 'cases_public.json', 'results_scored.json', 'benchmark.py')}
    dump(a.out/'source_manifest.json', manifest)
    budget = Budget(max_calls=2*(len(jobs)+24), max_usd=a.max_usd)
    model = Gemma(url=a.relay_url, budget=budget, selection=selected(a),planner_prompt_order=a.planner_prompt_order) if a.execute else None
    lock = threading.Lock()
    def run(job):
        row, arm = job
        p, ctx, labels = adapt(row, arm, a.planner_evidence_gate)
        if model is None:
            return dict(case_id=row['case_id'], condition=arm, status='not_called', correct=False,
                        ambiguous=gold[row['case_id']]['ambiguous'])
        result = p.decide(ctx, model)
        decision = result['decision']; label = labels.get(signature(decision)) if decision else None
        # Model-only score: failure fallback cannot masquerade as Gemma accuracy.
        g = gold[row['case_id']]
        record = dict(case_id=row['case_id'], condition=arm, domain=g['domain'], quality=g['quality'],
                      ambiguous=g['ambiguous'], choice=label, correct=bool(not result['fallback'] and label in g['best_choices']),
                      effective_correct=label in g['best_choices'], fallback=result['fallback'],
                      status='fallback' if result['fallback'] else 'ok', attempts=len(p.audit), audit=p.audit)
        with lock:
            with (a.out/'calls.jsonl').open('a') as f: f.write(json.dumps(record, ensure_ascii=False)+'\n')
        return {k:v for k,v in record.items() if k != 'audit'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(run, jobs))
    extra = []
    for i, (p, ctx, best) in enumerate(supplements(a.planner_evidence_gate)):
        result = p.decide(ctx, model) if model else None
        extra.append(dict(id=f'authored-solo-{i}', source='new synthetic planner destination/route/approach cases',
                          correct=bool(result and not result['fallback'] and signature(result['decision']) == best),
                          status='not_called' if result is None else 'fallback' if result['fallback'] else 'ok',
                          audit=p.audit))
    dump(a.out/'solo.json', extra)
    summary = dict(schema='ugrp.task_planner.offline.v1', research_result=False,
                   source_count=384, main_count=main_count, ambiguous_count=384-main_count,
                   leader_scope='r1 leader receives r2 original English report; same observation as peer_en; not multi-turn relay',
                   conditions={}, synthetic_solo=dict(n=sum(x['correct'] for x in extra), N=len(extra)),
                   budget=dict(calls=budget.calls, accounted_usd=budget.charged, unknown_cost_calls=budget.unknown))
    for arm in ARMS:
        rs = [r for r in rows if r['condition']==arm]; main = [r for r in rs if not r['ambiguous']]; amb = [r for r in rs if r['ambiguous']]
        summary['conditions'][arm] = dict(n=sum(r['correct'] for r in main), N=len(main),
            ambiguous=dict(n=sum(r['correct'] for r in amb), N=len(amb)),
            errors=sum(r['status'] != 'ok' for r in rs),
            effective_n=sum(r.get('effective_correct',False) for r in main),
            by_quality={q:dict(n=sum(r['correct'] for r in main if r.get('quality')==q),
                              N=sum(r.get('quality')==q for r in main)) for q in sorted({r.get('quality','') for r in main})},
            by_domain={d:dict(n=sum(r['correct'] for r in main if r.get('domain')==d),
                              N=sum(r.get('domain')==d for r in main)) for d in sorted({r.get('domain','') for r in main})})
    dump(a.out/'scored.json', rows); dump(a.out/'summary.json', summary)
    dump(a.out/'artifact_manifest.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.out.iterdir() if p.is_file()})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
