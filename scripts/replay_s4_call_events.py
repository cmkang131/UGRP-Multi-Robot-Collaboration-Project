"""Offline counterfactual eligibility, NOT counterfactual robot success/model replies.

Reads text-only saved own-input snapshots and own executor events. No simulator,
contact, pose truth, image decode, model API or inference is imported.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from harness.s4_event_policy import Events


def replay(root, supplemental=()):
    root=Path(root); requests=json.loads((root/'llm/requests.json').read_text())
    requests += [r for r in supplemental if r['run']==root.parent.name]
    requests.sort(key=lambda r:int(r['call_id'].split('-')[1]))
    policy=Events();eligible=[]
    for row in requests:
        b=json.loads(row['user']);reasons=policy.observe(b['robot_id'],b)
        if reasons:eligible.append(dict(call_id=row['call_id'],actor=b['robot_id'],sim_s=b['sim_time_s'],reasons=reasons))
    events=json.loads((root/'llm/executor_events.json').read_text())
    observed=Counter((e.get('detail') or {}).get('kind',e['event']) for e in events)
    inputs=['llm/requests.json','llm/executor_events.json','llm/result.json','llm/model_calls.json']
    result=json.loads((root/'llm/result.json').read_text())
    return dict(run=root.parent.name,original_calls=len(requests),
        eligible_recorded_snapshots=len(eligible),suppressed_repeated_snapshots=len(requests)-len(eligible),
        eligible=eligible,reasons=dict(Counter(r for e in eligible for r in e['reasons'])),
        observed_executor_events=dict(observed),status=result['status'],
        host_error='-s602-' in root.parent.name,
        supplemental_wire_snapshots=sum(r.get('run')==root.parent.name for r in requests),
        scope='snapshot eligibility estimate; changed replies/messages/timing and continuous RGB anomalies not replayed',
        is_actual_call_count=False,raw=str(root),
        sha256={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs})


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--supplemental',type=Path)
    a=p.parse_args(argv);rows=[];extra=json.loads(a.supplemental.read_text()) if a.supplemental else []
    for seed in (601,602):
        for c in ('no_comm','peer_ko','leader_ko','structured'):
            rows.append(replay(a.raw_root/f's4live11-{c}-s{seed}-v182/raw',extra))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(dict(research_result=False,runs=rows,
        supplemental=None if a.supplemental is None else dict(path=str(a.supplemental),sha256=hashlib.sha256(a.supplemental.read_bytes()).hexdigest())),indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('run','original_calls','eligible_recorded_snapshots','host_error')} for r in rows]))


if __name__=='__main__':main()
