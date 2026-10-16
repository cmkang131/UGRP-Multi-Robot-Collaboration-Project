"""Recorded-input eligibility and extractive context audit; no physics/provider.

Historical decisions do not predict decisions on changed prompts. Literal
action stability and no-command continuations are reported separately, with
missing/invalid responses in the denominator, never filled from a neighbour.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from harness.s4_event_policy import Events
from harness.s4_event_coalesce import Coalescer
from harness.s4_compact_prompt import project, system, pk


def replay(root, supplemental=()):
    root=Path(root)
    files={name:root/'llm'/name for name in ('requests.json','dispatch.json','result.json','executor_events.json')}
    rows=json.loads(files['requests.json'].read_text())
    ids={r['call_id'] for r in rows}
    rows += [r for r in supplemental if r['run']==root.parent.name and r['call_id'] not in ids]
    rows.sort(key=lambda r:int(r['call_id'].split('-')[1]))
    dispatched={r['call_id']:r for r in json.loads(files['dispatch.json'].read_text())}
    actions={k:r['action'] for k,r in dispatched.items()}
    old=Events();new=Coalescer();seen={};previous={};counts=Counter();types=Counter();details=[]
    old_tokens=new_tokens=0
    for row in rows:
        b=json.loads(row['user']);actor=b['robot_id'];action=actions.get(row['call_id'])
        before=old.observe(actor,b);after=new.observe(actor,b)
        types.update(before)
        counts['wire_snapshots']+=1;counts['event_v1_calls']+=bool(before)
        marker=seen.setdefault(actor,set())
        compact=project(b,compact=True,lang='en')
        trimmed=project(b,compact=True,lang='en',map_as_image_v1=True,
                        context_trim_v1=True,seen_message_ids=marker)
        def tokens(body):
            return pk.count_tokens(system(actor))+pk.count_tokens(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        a,z=tokens(compact),tokens(trimmed)
        if before:old_tokens+=a
        if after:
            counts['coalesced_calls']+=1;new_tokens+=z
            marker.update(m['message_id'] for m in trimmed.get('inbox',[]))
            new.acknowledge(actor)
        else:
            counts['skipped']+=1
            counts['skipped_known_action']+=action is not None
            counts['skipped_literal_matches_previous']+=action is not None and action==previous.get(actor)
            counts['skipped_continue_or_held']+=bool(action and (action.get('kind')=='continue' or
                action.get('kind')=='pair_decision' and action.get('choice')=='held'))
            changed=bool(action and action.get('kind')!='continue' and
                not (action.get('kind')=='pair_decision' and action.get('choice')=='held') and action!=previous.get(actor))
            counts['skipped_changed_noncontinuation']+=changed
            ack=dispatched.get(row['call_id'],{}).get('ack') or {}
            counts['skipped_changed_accepted_noncontinuation']+=changed and ack.get('accepted') is True
        details.append(dict(call_id=row['call_id'],actor=actor,sim_s=b['sim_time_s'],before=before,after=after,
            input_sha256=hashlib.sha256(row['user'].encode()).hexdigest(),
            old_text_tokens_estimate=a,new_text_tokens_estimate=z,recorded_action=action,
            recorded_command_accepted=(dispatched.get(row['call_id'],{}).get('ack') or {}).get('accepted'),
            literal_matches_previous=action is not None and action==previous.get(actor)))
        if action is not None:previous[actor]=action
    counts['pending_inboxes_at_end']=len(new.message_since)
    return dict(run=root.parent.name,status=json.loads(files['result.json'].read_text()).get('status'),
        host_error='-s602-' in root.parent.name,counts=dict(counts),event_types=dict(types),
        selected_reasons=dict(Counter(k for d in details for k in d['after'])),
        text_token_estimate=dict(event_v1_total=old_tokens,coalesced_trim_total=new_tokens,
            method='repository regex token estimator; excludes images, not Google countTokens'),
        scope='snapshot counterfactual; no changed replies, messages, continuous observations or physical outcomes simulated',
        raw=str(root),sha256={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in files.items()},details=details)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--supplemental',type=Path);a=p.parse_args(argv)
    extra=json.loads(a.supplemental.read_text()) if a.supplemental else []
    runs=[replay(a.raw_root/f's4live11-{c}-s{s}-v182/raw',extra)
          for s in (601,602) for c in ('no_comm','peer_ko','leader_ko','structured')]
    a.output.mkdir(parents=True,exist_ok=False)
    detail=json.dumps(runs,ensure_ascii=False).encode()
    packed=subprocess.run(['zstd','-q','-c'],input=detail,capture_output=True,check=True).stdout
    assert subprocess.run(['zstd','-q','-d','-c'],input=packed,capture_output=True,check=True).stdout==detail
    (a.output/'replay.json.zst').write_bytes(packed)
    summary=dict(research_result=False,physical_calls=0,model_calls=0,
                 source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                 runs=[{k:v for k,v in r.items() if k!='details'} for r in runs],
                 detail_sha256=hashlib.sha256(detail).hexdigest(),compressed_sha256=hashlib.sha256(packed).hexdigest(),
                 changed_prompt_decision_agreement=None)
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{ 'run':r['run'], **r['counts']} for r in runs]))


if __name__=='__main__':main()
