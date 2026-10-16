"""Counterfactual label-coverage ceiling from already issued student history.

Runs only the frozen hold-boundary predicate, not the teacher or any physics.
The ceiling is not actual DAgger data: additional oracle admission can reject
more samples. No validation images/labels enter training or fit thresholds.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys

from act16w_runtime import require_gcp2,frozen_source,sha256
from act16w_dagger import OracleHoldBoundary

ROOT=Path(__file__).resolve().parents[1]


def lines(path):
    actual=path if path.exists() else Path(str(path)+'.zst')
    raw=actual.read_bytes() if actual.suffix!='.zst' else subprocess.check_output(['zstd','-dc',str(actual)])
    return [json.loads(x) for x in raw.splitlines() if x.strip()],actual


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host,source=require_gcp2(training=True),frozen_source(ROOT)
    rows=[];raw=[]
    for arm in ('A','B'):
        base=a.experiment/('validation-'+arm)/'validation'
        summary=json.loads((base/'summary.json').read_text())
        if not summary['complete'] or summary['N']!=8:raise ValueError('completed native VAL8 required')
        for group in sorted(base.glob('group-*')):
            plans=json.loads((group/'plans.json').read_text())['episodes']
            values,path=lines(group/'evaluation/actor-inputs.jsonl');raw.append(dict(path=str(path),sha256=sha256(path)))
            for i,plan in enumerate(plans):
                observations=[x['observation'] for x in values if x['world']==i]
                if not observations:raise ValueError('empty actor trace')
                boundary=OracleHoldBoundary(observations[0]['issued'][-1]);allowed=[];blocked=[]
                for j,obs in enumerate(observations):
                    result=boundary.query(obs['issued'],lambda:True)
                    (allowed if result is True else blocked).append(j)
                rows.append(dict(arm=arm,seed=plan['seed'],states=len(observations),
                    possible_queries_upper_bound=len(allowed),noninitial_possible_queries_upper_bound=sum(j>0 for j in allowed),
                    rejected_by_hold_boundary=len(blocked),first_blocked_observation=blocked[0] if blocked else None,
                    initial_open_pwm=boundary.initial_open_pwm,
                    first_blocked_issued_gripper=[c['pwm']['1'] for c in observations[blocked[0]]['issued']] if blocked else None))
    if len(rows)!=16:raise ValueError('exact A/B16 trace coverage required')
    total=sum(x['states'] for x in rows);kept=sum(x['possible_queries_upper_bound'] for x in rows)
    report=dict(status='complete',complete=True,host=host,source_sha=source,utc=datetime.now(timezone.utc).isoformat(),
        counterfactual_only=True,actual_DAgger_collection=False,teacher_queries=0,physics_steps=0,
        validation_data_admitted_to_training=False,thresholds_fitted=False,
        funnel=[dict(gate='recorded_student_states',passed=total,rejected=0),
                dict(gate='possible_query_before_potential_close_upper_bound',passed=kept,rejected=total-kept)],
        noninitial_possible_queries_upper_bound=sum(x['noninitial_possible_queries_upper_bound'] for x in rows),
        rejections=[dict(category='potential_hold_after_student_issued_close',reason='frozen guard permanently rejects any issued gripper PWM below startup OPEN',count=total-kept,
            blocking_object='not_applicable_training_label_admission',minimum_gap_m=None,minimum_gap_status='not_applicable_non_geometric')],
        rows=rows,raw=raw,scope=__doc__,reproduce=sys.argv)
    with a.out.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:report[k] for k in ('status','funnel','noninitial_possible_queries_upper_bound')}))


if __name__=='__main__':main()
