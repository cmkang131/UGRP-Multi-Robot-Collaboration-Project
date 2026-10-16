"""Count sealed acquisition stages; no simulator, GT, or threshold changes."""
from collections import Counter
from report import EP, EXP, dump, load, rows, metrics_module


def summarize():
    metrics_module().verify(EP)
    decisions = load(EP / 'decisions.json')
    trace = rows(EP / 'own-controller.jsonl')
    grid = load(EP / 'frontend-grid.json')
    acquisition = load(EP / 'result.json')
    rejected = [d for d in decisions if d['status'] == 'rejected']
    inserted = [d for d in decisions if d['inserted']]
    counts = Counter(d['reason'] for d in decisions)
    report = dict(
        rgb=acquisition['frames'], initial_wait=acquisition['frames'] - len(trace),
        detected_geometry=sum(r['wall_segments'] > 0 for r in trace),
        empty_geometry=sum(r['wall_segments'] == 0 for r in trace),
        decision_frames=len(decisions),
        duplicate_frames=len(decisions) - len({d['frame_id'] for d in decisions}),
        unsettled=grid['rejected']['unsettled'], range_segments=grid['rejected']['range_segments'],
        motion_deferred=counts['gmapping_motion_gate'],
        admitted=len(decisions) - counts['gmapping_motion_gate'], inserted=len(inserted),
        accepted=sum(d['status'] == 'accepted' for d in decisions),
        bootstrap=sum(d['status'] == 'bootstrap' for d in decisions),
        rejected_status_inserted=sum(d['inserted'] for d in rejected),
        other_deferred_inserted=sum(d['status'] == 'deferred' for d in inserted),
        reason_counts=dict(counts),
        rejected_reason_counts=dict(Counter(d['reason'] for d in rejected)),
        resampled_rejected=sum(d['resampled'] for d in rejected),
        sensor_weighted_rejected=sum(d.get('sensor_weight_update', False) for d in rejected),
        rbpf_composition=grid['rbpf_composition'], rbpf_insertion=grid['rbpf_insertion'],
        motion_gate=grid['motion_gate'])
    assert report['inserted'] == grid['frames'] == report['admitted']
    assert report['rgb'] == report['initial_wait'] + len(trace)
    dump(EXP / 'results/physical-insertion.json', report)
    return report


if __name__ == '__main__':
    summarize()
