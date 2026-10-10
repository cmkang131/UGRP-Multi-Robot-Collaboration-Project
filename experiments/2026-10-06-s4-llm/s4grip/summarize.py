"""Summarize the completed immutable offline replay; no simulation imports."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('replay', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    summary = json.loads((a.replay/'summary.json').read_text())
    dataset = a.replay/'eval-only-frames.jsonl'
    assert sha(dataset) == summary['dataset_sha256']
    unique, groups, cv, reasons = defaultdict(set), defaultdict(Counter), Counter(), Counter()
    for line in dataset.open():
        row = json.loads(line)
        label = row['ground_truth']['label']
        unique[label].add(row['image_sha256'])
        groups[row['raw'].split('/')[0].split('-')[0]][label] += 1
        cv[(label, row['legacy_relation']['ok'])] += 1
        reasons[row['legacy_relation']['reason']] += 1
        assert row['s4_llm_prediction'] is None
    c = summary['counts']
    def fraction(n, d):
        return dict(n=n, N=d, rate=n/d if d else None)
    report = dict(
        scope='offline stored RGB; research_result=false; evaluation-only contact proxy',
        physics_runs=0, render_calls=0, actual_model_calls=0,
        source_summary=dict(path=str(a.replay/'summary.json'), sha256=sha(a.replay/'summary.json')),
        dataset=dict(path=str(dataset), sha256=sha(dataset), frames=c['frames']),
        counts=c, unique_image_sha256_counts={k: len(v) for k, v in unique.items()},
        by_group=dict(groups),
        s4_llm=dict(recorded_predictions=0, held_prediction_coverage=fraction(0,c['frame_held_contact']),
                    loss_prediction_coverage=fraction(0,c.get('frame_lost_contact',0)),
                    true_positive=None, false_positive=None, detection_delay_frames=None,
                    reason='No S4 LLM predictions for these S3 images; new model calls forbidden'),
        legacy_cv_diagnostic=dict(
            held_accept=fraction(cv[('held_contact',True)],c['frame_held_contact']),
            held_reject=fraction(cv[('held_contact',False)],c['frame_held_contact']),
            false_held_on_pregrasp=fraction(cv[('not_held',True)],c['frame_not_held']),
            pregrasp_reject=fraction(cv[('not_held',False)],c['frame_not_held']),
            hypothetical_loss_true_positive=fraction(cv[('lost_contact',False)],c.get('frame_lost_contact',0)),
            hypothetical_loss_false_positive=fraction(cv[('held_contact',False)],c['frame_held_contact']),
            detection_delay_frames=None, reasons=dict(reasons),
            warning='False is LOST_OR_UNOBSERVABLE, not a deployed binary loss alarm; held runs duplicate'),
        loss_episodes=dict(contact_only=len(summary['contact_loss_episodes']),
                           own_rgb_at_onset=sum(e['own_rgb_at_onset'] for e in summary['contact_loss_episodes']),
                           paired_loss_frames=c.get('frame_lost_contact',0)),
        source_shas=sorted({r['source_sha'] for r in summary['runs']}),
        raw_runs_with_rgb=sum(r['counts'].get('frames',0)>0 for r in summary['runs']),
        ambiguous_raw_runs=[r['raw'] for r in summary['runs'] if r['errors']],
        replay_module_sha256=summary['module_sha256'])
    if a.output.exists():
        raise FileExistsError(a.output)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['counts','legacy_cv_diagnostic','loss_episodes']},indent=2))


if __name__ == '__main__':
    main()
