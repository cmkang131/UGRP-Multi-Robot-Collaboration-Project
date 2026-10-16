"""Offline sampled r76 text replay. No provider, physics, render or remote access."""
import argparse
import hashlib
import json
from pathlib import Path
from harness.e2e_dialogue_decider import unpack
from harness.e2e_dialogue_call_policy import Policy, compact
from harness.zone_study_prompts_ko import count_tokens


def replay(root):
    results=[]
    for run in sorted(Path(root).iterdir()):
        ledger_path=run/'llm/model_calls.json'
        if not ledger_path.is_file(): continue
        ledger=json.loads(ledger_path.read_text());by_id={r['call_id']:r for r in ledger}
        policy=Policy(); rows=[]
        for path in sorted((run/'wire').glob('*-request.json')):
            request=json.loads(path.read_text());body,_=unpack(request)
            d=body['dialogue'];obs=body.get('own_protocol_observation') or {}
            # These snapshots have no body-controller stage. Do not invent one.
            own=dict(stage=None,approach=None,grip=obs.get('own_grip'),alignment=obs.get('own_alignment'))
            protocol={k:d.get(k) for k in ('route_hash','proposal_message_id','approved','own_claim','key','own_go_sent','peer_go_ref','own_ack_sent')}
            proposal=body.get('own_route_proposal')
            protocol['proposable_route']=(proposal['route']['route_hash'] if proposal and body['robot_id']=='r1'
                and not d['approved'] and d['proposal_message_id'] is None else None)
            protocol['grip_alert']=obs.get('own_grip') if d['key'] or obs.get('own_grip')=='slipping' else None
            event=policy.decide(body['robot_id'],body['sim_time_s'],own,protocol,body.get('peer_reports') or [])
            system=request['messages'][0]['content'];new,new_system=compact(body,system)
            old_text=system+json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            new_text=new_system+json.dumps(new,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            cid=path.name.split('-',1)[1].removesuffix('-request.json')
            original_tokens=(by_id[cid].get('provider_usage') or {}).get('total_tokens')
            rows.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                call_id=cid,sim_s=body['sim_time_s'],admitted=event['admitted'],reason=event['reason'],
                original_provider_tokens=original_tokens,
                old_text_proxy_tokens=count_tokens(old_text),new_text_proxy_tokens=count_tokens(new_text),
                old_prompt_utf8_bytes=len(old_text.encode()),new_prompt_utf8_bytes=len(new_text.encode())))
        results.append(dict(run=run.name,raw=str(run),ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
            full_recorded_calls=len(ledger),full_known_provider_tokens=sum((r.get('provider_usage') or {}).get('total_tokens',0) for r in ledger),
            sampled_requests=len(rows),sample_admitted=sum(r['admitted'] for r in rows),
            sample_old_text_proxy_tokens=sum(r['old_text_proxy_tokens'] for r in rows),
            sample_compact_all_text_proxy_tokens=sum(r['new_text_proxy_tokens'] for r in rows),
            sample_event_compact_text_proxy_tokens=sum(r['new_text_proxy_tokens'] for r in rows if r['admitted']),
            sampled_peak_prompt_utf8_bytes=max(r['new_prompt_utf8_bytes'] for r in rows),rows=rows))
    return dict(schema='ugrp.e2e18_callrate_replay.v1',scope='sampled request admission and text replay; no changed trajectories or responses generated',
        missing='Full input event stream and own-controller stage absent. Never extrapolate sampled calls to full r76 or 600 SIM seconds.',
        token_basis='ugrp.zone_study_tokens.v1 text-only proxy; excludes images/output and is NOT new provider usage',runs=results)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(replay(a.raw),indent=2,ensure_ascii=False)+'\n')
