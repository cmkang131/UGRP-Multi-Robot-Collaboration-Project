"""Post-run only: real released decisions/commands and independent physics labels."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines()] if Path(path).exists() else []
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def first_carry_window(states):
    starts={};ends={}
    for row in states:
        for rid in ('r1','r2'):
            value=row['robots'].get(rid)
            carry=value and value['state']=='carry' and value['seg']==0
            if rid not in starts and carry:starts[rid]=row['t']
            elif rid in starts and rid not in ends and not carry:ends[rid]=row['t']
    return (max(starts.values()),min(ends.values(),default=math.inf)) if len(starts)==2 else None


def contact_carry(contacts,truth,window):
    truth={round(r['t'],8):r['items']['beam_1'] for r in truth};points=[]
    if window is not None:
        for row in contacts:
            t=row['t'];cargo=truth.get(round(t,8))
            if not cargo or not window[0]<=t<window[1] or cargo['z']<=.06:continue
            touched={c[k] for c in row['contacts'] if 'cargo_beam_1' in c['geom1'] or 'cargo_beam_1' in c['geom2'] for k in ('geom1','geom2')}
            if all(r+'__'+side+'_finger' in touched for r in ('r1','r2') for side in ('left','right')):
                points.append((t,cargo['x'],cargo['y']))
    excursion=max((math.dist(p[1:],points[0][1:]) for p in points),default=0.)
    return dict(n=int(excursion>=.020),N=1,excursion_m=excursion,contact_supported_samples=len(points),
        first_carry_window=None if window is None else [window[0],None if math.isinf(window[1]) else window[1]])


def evaluate(raw):
    result=read(raw/'result.json');h=read(raw/'pair-handshake.json') if (raw/'pair-handshake.json').exists() else {}
    manifest=read(raw/'artifacts.sha256.json')
    for p,digest in manifest.items():
        if sha(raw/p)!=digest:raise ValueError('raw artifact mismatch: '+p)
    permit=(h.get('permits') or [None])[0]
    claims=h.get('claims',{});decisions=h.get('decisions',[])
    commands=read(raw/'decision-command-links.json');states=read(raw/'stage-states.json')
    start=states[0]['t']-states[0]['relative_sim_s'] if states else 0.
    dispatch=read(raw/'llm/dispatch.json') if (raw/'llm/dispatch.json').exists() else []
    actual_claims={d['actor']:d['call_id'] for d in dispatch if d['action']['kind']=='claim' and d.get('ack',{}).get('accepted')}
    claim_ok=all(claims.get(r) and claims[r]==actual_claims.get(r) for r in ('r1','r2'))
    votes_ok=bool(permit and all(any(d['robot_id']==r and d['call_id']==permit[key][r] and d['accepted']
        and d['action']['choice']==choice for d in decisions) for r in ('r1','r2') for key,choice in (('go_calls','go'),('ack_calls','ack_go'))))
    moves=[c for c in commands if c['robot_id'] in ('r1','r2') and permit and c.get('pair_permit')==permit
        and c['action']['kind'] in ('drive','mecanum') and (c['action'].get('forward',0) or c['action'].get('left',0))]
    times={r:next((c['t'] for c in moves if c['robot_id']==r),None) for r in ('r1','r2')}
    simultaneous=bool(votes_ok and all(t is not None for t in times.values()) and abs(times['r1']-times['r2'])<=.05+1e-8
        and min(times.values())-start>=permit['at']-1e-8)
    window=first_carry_window(rows(raw/'pair-controller-states.jsonl'))
    carry=contact_carry(rows(raw/'eval_only/contacts.jsonl'),rows(raw/'eval_only/referee_truth.jsonl'),window)
    channel=read(raw/'llm/channel.json') if (raw/'llm/channel.json').exists() else None
    return dict(condition=result['condition'],status=result['status'],claim=dict(n=int(claim_ok),N=1),
        go_ack=dict(n=int(votes_ok),N=1),simultaneous_departure=dict(n=int(simultaneous),N=1,first_command_t=times),
        carry_20mm=carry,plumbing_carry=dict(n=int(claim_ok and votes_ok and simultaneous and carry['n']),N=1),
        pair_failure=result.get('pair_failure'),failure=result.get('failure_type'),lowering='observed only; outside verdict',
        model_calls=result['model_calls'],model_usage=result['model_usage'],model_response_wall_s=result['model_response_wall_s'],
        channel=channel,model_failures=read(raw/'llm/transport_errors.json') if (raw/'llm/transport_errors.json').exists() else [],
        fixed_signals=len(h.get('signals',[])),verified_artifacts=len(manifest),raw_path=str(raw),
        result_sha256=sha(raw/'result.json'),manifest_sha256=sha(raw/'artifacts.sha256.json'),research_result=False)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    from scripts.run_s4_pair_live5 import ROOT,RECORD
    if a.output.exists():raise FileExistsError(a.output)
    seq=[]
    for job in read(ROOT/RECORD/'plan.json')['runs']:
        raw=a.raw_root/job['name']/'raw'
        seq.append(evaluate(raw) if (raw/'result.json').exists() else dict(condition=job['condition'],status='MISSING_RAW',research_result=False))
    a.output.write_text(json.dumps(seq,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:r.get(k) for k in ('condition','status','claim','go_ack','simultaneous_departure','carry_20mm','model_calls')} for r in seq]))


if __name__=='__main__':raise SystemExit(main())
