"""Summarize sealed recovery events; no simulator or controller changes."""
from collections import Counter
from report import EP, EXP, dump, load, rows, metrics_module


def summarize():
    metrics_module().verify(EP)
    nav, trace = load(EP/'navigation.json'), rows(EP/'own-controller.jsonl')
    acquisition = load(EP/'result.json')
    comparison = load(EXP/'results/comparison.json')
    counts = Counter(x['reason'] for x in nav)
    phases = {'context_clear', 'clear', 'spin', 'backup', 'wait', 'contact_backup'}
    starts = Counter(x['reason'].removeprefix('recovery_') for x in nav
                     if x['reason'] in {'recovery_'+p for p in phases})
    success = Counter(x['action'] for x in nav if x['reason']=='recovery_success')
    failure = Counter(x['action'] for x in nav if x['reason']=='recovery_failure')
    blacklists = [x for x in nav if x['reason'] in
                  {'ABORTED_goal_blacklisted', 'progress_timeout_blacklist', 'ABORTED_unreachable'}]
    followups = [dict(blacklist=e, next_selection=next((x for x in nav
                 if x['t']>=e['t'] and x['reason']=='frontier_selected'), None)) for e in blacklists]
    finished = next((x['t'] for x in nav if x['reason']=='exploration_finished_no_frontier'), None)
    tail = [x for x in trace if finished is not None and x['t']>=finished]
    contacts = rows(EP/'eval_only/contacts.jsonl')
    wall_pairs = [c for r in contacts for c in r['contacts']
                  if any(c[k].startswith('r3__') for k in ('geom1','geom2'))
                  and any('wall' in c[k] for k in ('geom1','geom2'))]
    report = dict(source_sha=acquisition['source_sha'], seed=load(EP/'bundle.json')['task']['seed'],
        physical_runs=1, sim_duration_s=acquisition['total_sim_s']-acquisition['start_sim_s'],
        frozen_options_changed=False, event_counts=dict(counts), recovery_started=dict(starts),
        recovery_success=dict(success), recovery_failure=dict(failure),
        recovery_success_total=sum(success.values()), navigation_resets=counts['navigation_layer_reset'],
        blacklist_total=len(blacklists), blacklist_by_reason=dict(Counter(x['reason'] for x in blacklists)),
        blacklist_followups=followups, frontier_selections=counts['frontier_selected'],
        exhaustion_abort_count=sum(x['reason']=='navigation_action_aborted' and
                                   x.get('cause')=='recovery_exhausted' for x in nav),
        permanent_failed_frames=sum(x['status']=='recovery_exhausted' for x in trace),
        first_exploration_finished_absolute_s=finished,
        first_exploration_finished_elapsed_s=None if finished is None else finished-acquisition['start_sim_s'],
        tail_frames=len(tail), tail_hold_frames=sum(x['command']['kind']=='hold' for x in tail),
        tail_duration_s=None if finished is None else acquisition['total_sim_s']-finished,
        all_status_counts=dict(Counter(x['status'] for x in trace)), hold=comparison['hold'],
        wall_contact_sample_pairs=len(wall_pairs), eval_contact_frames=len(contacts),
        recovery_gate=comparison['recovery_gate'], recovery_gate_pass_count=sum(comparison['recovery_gate'].values()),
        egomap27_gate=comparison['egomap27_gate'], original_quality_criteria=comparison['fresh']['criteria'],
        original_quality_pass_count=sum(comparison['fresh']['criteria'].values()),
        wrong_door_plan_proxy_count=len(comparison['fresh']['wrong_door_attempts']),
        qualification='Recovery starts include contextual clears. Starts without terminal events are not successes. '
        'Unreachable-frontier blacklists and retry-budget exhaustion are reported separately. '
        'Contact count is saved sample pairs plus abort-only runtime safety, not hardware sensing.')
    dump(EXP/'results/physical-recovery.json', report)
    return report


if __name__=='__main__':
    summarize()
