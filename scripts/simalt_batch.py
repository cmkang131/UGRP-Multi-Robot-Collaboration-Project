"""Finite owner of simalt trace subprocesses; never stops unrelated work."""
import argparse
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--concurrency',type=int,choices=(1,4,8),required=True)
    p.add_argument('--python',required=True);p.add_argument('--pilot',required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--sha',required=True)
    a=p.parse_args();children=[];start=time.monotonic()
    folder=a.root/f'A-n{a.concurrency}';folder.mkdir(exist_ok=False)
    try:
        for i in range(a.concurrency):
            out=folder/f'worker-{i}';log=(folder/f'worker-{i}.log').open('w')
            cmd=[a.python,a.pilot,'replay','--source','/tmp/simalt1/source',
                '--plan','/tmp/simalt1/plan.json','--trace','/tmp/simalt1/trace.jsonl',
                '--out',str(out),'--render-backend','egl_l4_v1','--egl-l4-v1','--sha',a.sha]
            child=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            children.append((child,log,out))
        # Wall cap is the user's A+B resource bound, never a planner/search budget.
        for child,log,out in children:
            child.wait(timeout=max(1,7200-(time.monotonic()-start)))
        results=[json.loads((out/'result.json').read_text()) for _,_,out in children]
        ratios=[r['first30']['wall_per_sim'] for r in results if 'first30' in r]
        wall=time.monotonic()-start
        report={'attempted':len(results),'completed':sum(r['completed'] for r in results),
            'failure':sum(r['failure'] for r in results),'HOST_ERROR':sum(r['HOST_ERROR'] for r in results),
            'concurrency':a.concurrency,'batch_wall_s':wall,
            'completed_traces_per_h':sum(r['completed'] for r in results)*3600/wall,
            'first30_median_wall_per_sim':statistics.median(ratios) if ratios else None,
            'first30_ratios':ratios,'raw_paths':[str(out) for _,_,out in children],
            'next_submission_blocked':len(ratios)!=a.concurrency or any(r['HOST_ERROR'] for r in results) or statistics.median(ratios)>6.,
            'gate_source':'docs/gcp_simulation.md: current record-only >3.5 warning / >6.0 block',
            'rejection_table':str(folder/'rejection_table.json')}
        (folder/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (folder/'rejection_table.json').write_text(json.dumps({'funnel':[
            {'gate':'submitted','passed':a.concurrency,'rejected':0},
            {'gate':'first30_complete','passed':len(ratios),'rejected':a.concurrency-len(ratios)},
            {'gate':'trace_complete','passed':report['completed'],'rejected':a.concurrency-report['completed']}],
            'rejections':[] if not report['next_submission_blocked'] else [{'category':'speed_gate',
            'reason':'first30 median >6.0 or HOST_ERROR/incomplete','blocking_object':'g2-standard-4 CPU capacity',
            'minimum_gap_m':None,'minimum_gap_status':'not_geometric'}],
            'raw_path':str(folder),'reproduce':sys.argv},indent=2)+'\n')
        print(json.dumps(report,indent=2))
    finally:
        for child,log,out in children:
            if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
        for child,log,out in children:
            if child.poll() is None:
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            log.close()


if __name__=='__main__':main()
