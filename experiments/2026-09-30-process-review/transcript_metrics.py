#!/usr/bin/env python3
"""Optional local metadata-only aggregation; never writes text, tool args or IDs.
The JSONL files remain read-only. Response gaps are NOT model inference latency.
"""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
from analyze import stats, stamp


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--start',default='2026-09-28T04:30:38Z')
    p.add_argument('--end',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();start=stamp(a.start);end=stamp(a.end)
    kinds=collections.Counter();efforts=collections.Counter();gaps=collections.defaultdict(list)
    waits=collections.defaultdict(list);sessions=0;requests=set();tool_seen=set();retry_ms=[]
    allowed={'Bash','Read','Edit','Write','Glob','Grep','Agent','Task','TaskOutput','WebSearch','WebFetch'}
    for path in sorted(a.root.glob('*.jsonl')):
        last_user=None;uses={};active=False
        for line in path.open():
            try:d=json.loads(line);t=stamp(d.get('timestamp'))
            except (ValueError,TypeError):continue
            if not t or not start<=t<end:continue
            active=True;kind=d.get('type');kinds[kind]+=1;m=d.get('message',{})
            if kind=='system' and isinstance(d.get('retryInMs'),(float,int)):
                retry_ms.append(d['retryInMs'])
            if kind=='assistant':
                identity=m.get('id') or d.get('requestId')
                if identity and identity not in requests:
                    requests.add(identity);eff=d.get('effort') or 'unrecorded';efforts[eff]+=1
                    if last_user is not None:
                        delta=(t-last_user).total_seconds()
                        if delta>=0:gaps[eff].append(delta)
                    last_user=None
                for b in m.get('content',[]):
                    if isinstance(b,dict) and b.get('type')=='tool_use':
                        uses[b['id']]=(t,b.get('name') if b.get('name') in allowed else 'other')
            elif kind=='user':
                last_user=t
                content=m.get('content',[])
                if not isinstance(content,list):continue
                for b in content:
                    if isinstance(b,dict) and b.get('type')=='tool_result':
                        ident=b.get('tool_use_id')
                        if ident in uses and ident not in tool_seen:
                            began,name=uses[ident];delta=(t-began).total_seconds()
                            if delta>=0:waits[name].append(delta)
                            tool_seen.add(ident)
        sessions+=active
    value={'window_start':a.start,'window_end':a.end,'sessions_with_records':sessions,
           'record_types':dict(kinds),'unique_assistant_message_ids':len(requests),
           'effort_per_unique_message':dict(efforts),
           'user_or_tool_result_to_first_assistant_event_gap_s':{k:stats(v) for k,v in gaps.items()},
           'tool_request_to_result_elapsed_s':{k:stats(v) for k,v in waits.items()},
           'logged_retry_delay_ms':stats(retry_ms),
           'limitations':['local coordinator sessions only; not all Codex/Claude workers',
                         'metadata gaps include scheduling, retries, streaming and pauses, not isolated inference',
                         'concurrent sessions overlap; summed elapsed time is not project critical path',
                         'no prompt, response, tool arguments, session IDs or per-message IDs exported']}
    a.out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:value[k] for k in ['sessions_with_records','unique_assistant_message_ids','effort_per_unique_message','user_or_tool_result_to_first_assistant_event_gap_s','logged_retry_delay_ms']},indent=2))

if __name__=='__main__':main()
