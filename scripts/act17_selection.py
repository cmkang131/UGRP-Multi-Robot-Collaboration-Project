"""Freeze a real completed same-seed M/F/S VAL8 before any FINAL setup."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act17_open_loop import read
from act17_compact_records import original_sha256
from act16w_runtime import sha256

# Pre-outcome operator tie preference: current full RGB + ordinary ACT episode
# sampling, then history baseline, then the stage-sampling hypothesis.
PRIORITY=('F','M','S')


def completed_validation(report,protocol):
    if (not report.get('complete') or report.get('cohort')!='act17-v7-native' or report.get('split')!='validation'
            or report.get('teacher_actions_executed')!=0 or report.get('policy_privileged_inputs')!=0):
        raise ValueError('real completed own-only v7 VAL comparison required')
    wanted=set(protocol['validation8_seeds']);counts={}
    if len(report['rows'])!=24 or set(report['candidates'])!=set(PRIORITY):raise ValueError('exact M/F/S comparison required')
    for candidate in PRIORITY:
        rows=[r for r in report['rows'] if r['candidate']==candidate]
        if len(rows)!=8 or {r['seed'] for r in rows}!=wanted:raise ValueError('all three exact unique VAL8 comparisons required')
        n=sum(r['task_success'] for r in rows)
        if report['candidates'][candidate]!={'n':n,'N':8}:raise ValueError('VAL counts differ from actual rows')
        counts[candidate]=n
    return counts


def validate_final_selection(selection,protocol,model_hash):
    path=Path(selection['validation_report'])
    if original_sha256(path)!=selection['validation_report_sha256']:raise ValueError('frozen validation evidence changed')
    report=read(path);counts=completed_validation(report,protocol)
    winner=next((c for c in PRIORITY if counts[c]==8),None)
    if (winner is None or selection.get('candidate')!=winner or selection.get('frozen_before_final') is not True
            or selection.get('checkpoint_sha256')!=model_hash or report['models'][winner]['sha256']!=model_hash
            or selection.get('validation_n')!=8 or selection.get('validation_N')!=8
            or sorted(selection.get('completed_candidates',[]))!=['F','M','S']):
        raise ValueError('all8 task pass and pre-outcome fixed selection required')
    return winner


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['validation','protocol','out']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();protocol=read(a.protocol);report=read(a.validation);counts=completed_validation(report,protocol)
    winner=next((c for c in PRIORITY if counts[c]==8),None)
    value=dict(approved=winner is not None,frozen_before_final=winner is not None,candidate=winner,
        validation_report=str(a.validation),validation_report_sha256=original_sha256(a.validation),counts=counts,
        completed_candidates=sorted(PRIORITY),tie_priority=list(PRIORITY),rule='all8 task cases pass; then fixed F,M,S; no final results used',
        protocol_sha256=sha256(a.protocol),status='FROZEN' if winner else 'NO_VAL8_PASS')
    if winner:
        value.update(checkpoint_path=report['models'][winner]['path'],checkpoint_sha256=report['models'][winner]['sha256'],validation_n=8,validation_N=8)
    with a.out.open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps(dict(status=value['status'],candidate=winner,counts=counts)))


if __name__=='__main__':main()
