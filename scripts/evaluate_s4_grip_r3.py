"""Post-run scoring of live RGB decisions against evaluation-only contacts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from scripts.run_s4_grip_r3 import PLAN
from scripts.evaluate_s4_grip_dataset import score


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def lines(path):return [json.loads(x) for x in path.read_text().splitlines()]


def evaluate(root,split):
    plan=json.loads(PLAN.read_text());episodes=[];sources={};hash_verified=0
    for job in plan['runs']:
        if job['split']!=split:continue
        jobroot=root/job['name'];result_path=jobroot/'raw/result.json'
        if not result_path.exists():
            episodes.append(dict(job=job['name'],mode=job['mode'],status='MISSING_JOB',planned_cases=4));continue
        result=json.loads(result_path.read_text())
        for record in result['runs']:
            raw=jobroot/'raw'/record['case']['id'];entry=dict(job=job['name'],mode=job['mode'],case=record['case'],status=record['status'],raw=str(raw))
            for path in [raw/'result.json',raw/'bundle.json']:
                sources[str(path)]=sha(path)
            if record['status']!='COLLECTED':episodes.append(entry);continue
            manifest=json.loads((raw/'artifacts.sha256.json').read_text())
            for relative,digest in manifest.items():
                if sha(raw/relative)!=digest:raise ValueError('raw hash mismatch')
                hash_verified+=1
            frames=[f for f in lines(raw/'robots/r3/frames.jsonl') if f['phase']=='monitor']
            labels=lines(raw/'eval_only/labels.jsonl');predictions=lines(raw/'robots/r3/predictions.jsonl')
            assert len(frames)==len(labels)==len(predictions)==61
            for f,p,l in zip(frames,predictions,labels):
                assert abs(f['sim_time']-p['sim_time'])<1e-8 and abs(p['sim_time']-l['sim_time'])<1e-8
            entry.update(score=score(labels,predictions),reobserve_attempts=record['reobserve_attempts'],commands=record['commands'])
            for path in [raw/'eval_only/labels.jsonl',raw/'robots/r3/frames.jsonl',raw/'robots/r3/predictions.jsonl']:
                sources[str(path)]=sha(path)
            episodes.append(entry)
    modes={}
    for mode in plan['modes']:
        seq=[e for e in episodes if e['mode']==mode and e.get('score',{}).get('start_held')]
        requested_loss=[e for e in seq if e['case']['variant']=='loss']
        positives=[e for e in requested_loss if e['score']['actual_loss']]
        requested_hold=[e for e in seq if e['case']['variant']=='hold']
        negatives=[e for e in requested_hold if not e['score']['actual_loss']]
        counts=Counter()
        for e in seq:counts.update(e['score']['frame_counts'])
        modes[mode]=dict(start_held=dict(n=len(seq),N=4),loss_generated=dict(n=len(positives),N=2),
            true_positive=dict(n=sum(e['score']['detected'] for e in positives),N=len(positives)),
            hold_false_alarm=dict(n=sum(e['score']['false_alarm'] for e in negatives),N=len(negatives)),
            hold_induced_loss=dict(n=sum(e['score']['actual_loss'] for e in requested_hold),N=len(requested_hold)),
            early_alarms=dict(n=sum(e['score']['false_alarm'] for e in positives),N=len(positives)),
            held_unknown=dict(n=counts['held_unknown'],N=counts['label_held']),
            lost_unknown=dict(n=counts['lost_unknown'],N=counts['label_lost']),
            delays_frames=[e['score']['delay_frames'] for e in positives if e['score']['detected']],
            delays_sim_s=[e['score']['delay_sim_s'] for e in positives if e['score']['detected']],
            reobserve_attempts=sum(e['reobserve_attempts'] for e in seq))
    return dict(split=split,modes=modes,episodes=episodes,sources_sha256=sources,verified_artifacts=hash_verified,research_result=False)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--split',choices=['explore','confirm'],required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    report=evaluate(a.raw_root,a.split);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['modes']))


if __name__=='__main__':raise SystemExit(main())
