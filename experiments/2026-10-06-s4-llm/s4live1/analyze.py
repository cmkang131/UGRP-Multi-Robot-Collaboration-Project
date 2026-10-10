"""Post-batch S4 audit. Reads completed raw only; no controller or physics imports."""
import argparse,base64,hashlib,json,math,sqlite3
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]

def wire_audit(directory, receipts):
    """Match durable ledger to exact HTTP bytes and proxy receipts, including retries."""
    p=directory/'raw'
    db=sqlite3.connect(f'file:{p / "budget.sqlite"}?mode=ro',uri=True)
    try: rows=[json.loads(r[0]) for r in db.execute('SELECT record FROM requests')]
    finally: db.close()
    checks=[]
    for r in rows:
        request=p/'wire'/Path(r['request_path']).name
        response=p/'wire'/Path(r['response_path']).name if r.get('response_path') else None
        raw=json.loads(request.read_text()); images=[]
        for msg in raw['messages']:
            for part in msg.get('content',[]) if isinstance(msg.get('content'),list) else []:
                if part.get('type')=='image_url':
                    encoded=part['image_url']['url'].split(',',1)[1]
                    data=base64.b64decode(encoded,validate=True)
                    images.append(dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
        call_id=f'{r["run_key"]}:{r["call_id"]}:{r["ledger_seq"]}'
        matching=[v for v in receipts if v['call_id']==call_id
            and v['request_sha256']==r['body_sha256']
            and v['response_sha256']==r.get('response_sha256')
            and abs(v['started_unix']-r['sent_at_ns']/1e9)<10]
        check=dict(call_id=r['call_id'],request_sha256=sha(request),
            response_sha256=sha(response) if response and response.exists() else None,
            image_hashes=images,proxy_matches=len(matching),
            request_hash_match=sha(request)==r['body_sha256'],
            response_hash_match=response is not None and sha(response)==r.get('response_sha256'),
            image_hash_match=images==r.get('images'),provider_usage=r.get('provider_usage'),
            status=r['status'],latency_ms=r.get('latency_ms'),usage_known=r.get('usage_known'))
        checks.append(check)
    return dict(calls=checks,verified=all(c['request_hash_match'] and c['response_hash_match']
        and c['image_hash_match'] and c['proxy_matches']==1 for c in checks),
        upstream_attempts_and_billing_verified=False)

def analyze(directory):
    exit_code=int((directory/'EXIT').read_text().strip())
    p=directory/'raw'; manifest=read(p/'artifacts.sha256.json')
    mismatches=[name for name,value in manifest.items() if sha(p/name)!=value]
    if mismatches:raise ValueError(mismatches)
    result=read(p/'result.json'); states=read(p/'stage-states.json')
    commands=read(p/'decision-command-links.json'); calls=read(p/'model_calls.json')['rows']
    dispatch=read(p/'llm/dispatch.json'); req=read(p/'llm/requests.json')
    supervisors=lines(p/'eval_only/r3/physical-supervisor.jsonl')
    truth={round(r['t'],6):r['items']['cyan_1'] for r in lines(p/'eval_only/referee_truth.jsonl')}
    lifted=[r for r in supervisors if all(r['finger_contacts']) and r['cyan_z_m']>.06]
    xy=[(truth[round(r['t'],6)]['x'],truth[round(r['t'],6)]['y']) for r in lifted]
    travel=max((math.dist(xy[0],q) for q in xy),default=0.)
    onset=states[0]['t'] if states else None; first={}
    for row in states:first.setdefault(row['state'],row['relative_sim_s'])
    departures=result.get('departure_decisions',[d['departure_gate'] for d in dispatch if 'departure_gate' in d])
    permits={d['call_id']:d for d in departures if d['accepted']}
    claims={d['call_id']:d for d in dispatch if d['action']['kind']=='claim' and d.get('ack',{}).get('accepted')}
    wire={r['call_id']:r for r in calls if r['status']=='sent' and r.get('response_sha256')}
    violations=[]
    for row in commands:
        claim=claims.get(row['claim_call_id'])
        if claim is None or row['claim_call_id'] not in wire or row['t']+1e-6<onset+claim['sim_s']:
            violations.append('command_without_released_model_claim')
        if row.get('departure_call_id') and row['departure_call_id'] not in permits:
            violations.append('command_without_departure_permit')
    moving=lambda a:a['kind'] in ('drive','mecanum') and any(a.get(k,0) for k in ('forward','left','turn'))
    carry_commands=[c for c in commands if c.get('departure_call_id') and moving(c['action'])]
    channel=read(p/'llm/channel.json'); bundle=read(p/'bundle.json')
    policy={k:bundle.get(k) for k in ('seed','provider_seeds','controller_config','weld','case_cap_s',
        'departure_window_s','stage_scope','scenario_sha256','map_bundle_sha256','order_sheet_sha256',
        'source_sha256','dev_light','heading_scope','controller_inputs','drive_profile','contact_profile')}
    row=dict(name=directory.name,raw=str(p),source_sha=result['source_sha'],condition=result['condition'],
        status=result['status'],exit_code=exit_code,research_result=False,sim_s=result['check_sim_s'],wall_s=result['wall_s'],
        model_calls=result['model_calls'],model_usage=result['model_usage'],model_response_wall_s=result['model_response_wall_s'],
        commands=result['commands_issued'],accepted_claims={d['actor']:d['call_id'] for d in claims.values()},
        departure_accepted=bool(permits),departure_decisions=departures,
        carry_motion_commands=len(carry_commands),causal_violations=violations,first_states=first,
        lifted_contact_samples=len(lifted),max_cyan_com_z_m=max((r['cyan_z_m'] for r in supervisors),default=None),
        contact_lift_xy_m=travel,channel=channel,invalid_replies=sum(r['status']!='ok' for r in req),
        verified_artifacts=len(manifest),hash_mismatches=mismatches,
        physical_success=None,stage_plumbing_pass=bool(claims and commands and not violations),
        carry_plumbing_pass=bool(carry_commands and permits and not violations),
        configuration_fingerprint=hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest(),
        result_sha256=sha(p/'result.json'),manifest_sha256=sha(p/'artifacts.sha256.json'),
        managed_manifest_sha256=sha(directory/'managed/manifest.json'))
    return row

def interrupted(directory):
    """Host interruption is not a simulator failure; only persistently observed lower bounds."""
    p=directory/'raw'; bundle=read(p/'bundle.json')
    assert (directory/'EXIT').read_text().strip()=='143'
    assert not (p/'result.json').exists()
    truth=lines(p/'eval_only/referee_truth.jsonl')
    return dict(name=directory.name,raw=str(p),source_sha=(directory/'SOURCE_SHA').read_text().strip(),
        condition=bundle['condition'],research_result=False,status='HOST_INTERRUPTED',exit_code=143,
        cause='Supervisor poweroff bug at 2026-10-10T09:32:44Z; user confirmed',
        result_complete=False,physical_success=None,stage_plumbing_pass=None,
        last_persisted_absolute_sim_s=max((r['t'] for r in truth),default=None),
        command_and_scheduler_logs_complete=False,ledger_finalized=False)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--receipts',type=Path,required=True);v=a.parse_args()
    names=['s4live1-smoke-no_comm-s601-v157']+[f's4live1-{c}-s601-v157' for c in ('no_comm','peer_ko','leader_ko','structured')]
    # All exits must exist before looking at any of the four batch outcomes.
    for name in names:assert (v.root/name/'EXIT').exists(), name
    rows=[analyze(v.root/n) for n in names]
    receipts=lines(v.receipts)
    stopped=[interrupted(v.root/(n+'-host-stop-093244Z')) for n in names[1:]]
    for row in rows+stopped:
        row['wire_audit']=wire_audit(v.root/row['name'],receipts)
        assert row['wire_audit']['verified'], row['name']
    out=dict(schema='ugrp.s4live1_audit.v1',research_result=False,runs=rows,
        host_interrupted_attempts=stopped,relay_receipts_path=str(v.receipts),relay_receipts_sha256=sha(v.receipts),
        same_configuration=len({r['configuration_fingerprint'] for r in rows[1:]})==1,
        caveats=['synthetic alignment entrance; no navigation or E2E success',
        'pair claim-only, no alignment/GO/transport',
        'provider-reported tokens; upstream attempts/billing not independently reconciled',
        'delayed/invalid response behavior tested offline; do not infer live fault injection'])
    with v.output.open('x') as f:json.dump(out,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps([{k:r[k] for k in ('name','model_calls','commands','departure_accepted','carry_motion_commands','contact_lift_xy_m','invalid_replies')} for r in rows]))
