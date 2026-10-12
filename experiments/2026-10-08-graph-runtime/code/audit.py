"""Count exact duplicate matcher inputs in saved own-only online graph receipts.

No matches/optimization rerun and no timing claims; input cell equality is checked.
"""
from collections import OrderedDict
from dataclasses import astuple
import profile_graph as p
from harness.self_pose_graph import make_submaps,GraphOptions,between
from harness.self_graph_cache import GraphCache,array_key
from harness.grid_acceleration import using


def main():
    snapshots=[p.json.loads(s) for s in (p.EP/'online-maps.jsonl').read_text().splitlines()]
    graphs=p.load(p.EP/'graphs.json')
    recorded_count=len(graphs)
    final=p.load(p.RAW/'combined-cold/graph.json')
    graphs.append(dict(t=p.load(p.EP/'frontend-poses.json')[-1]['t'],diagnostics=final['diagnostics']))
    pairs=OrderedDict();fields=OrderedDict();receipts=[]
    for graph in graphs:
        snap=[s for s in snapshots if s['t']<=graph['t']+1e-8][-1]
        rows=[dict(r,robot_id='r3') for r in snap['ledger']]
        d=graph['diagnostics'];o=GraphOptions(**d['options'])
        with using('scalar_rays_v1'):submaps,_=make_submaps('r3',rows,o)
        assert len(submaps)==len(d['submaps'])
        hashes=[];field_hits=0
        for s,recorded in zip(submaps,d['submaps']):
            assert p.encoded(s['grid'].export()['cells'])==p.encoded(recorded['cells'])
            key=GraphCache.submap_key(s);hashes.append(key)
            field_hits+=int(key in fields);fields[key]=True;fields.move_to_end(key)
            if len(fields)>64:fields.popitem(last=False)
        hit=miss=0
        for event in d['loops']:
            if event['reason'] in ('member_scan','temporal_separation','outside_candidate_radius'):continue
            s=submaps[event['submap']];r=rows[event['scan']]
            assert event['frame_id']==r['frame_id']
            key=(hashes[event['submap']],array_key(r['segments']),array_key(between(s['pose'],r['pose'])),astuple(o))
            hit+=int(key in pairs);miss+=int(key not in pairs)
            pairs[key]=True;pairs.move_to_end(key)
            if len(pairs)>8192:pairs.popitem(last=False)
        receipts.append(dict(t=graph['t'],scans=len(rows),submaps=len(submaps),matches=hit+miss,pair_hits=hit,pair_misses=miss,field_hits=field_hits))
        print('audit',graph['t'],hit,miss,flush=True)
    result=dict(graph_calls=len(receipts),recorded_calls=recorded_count,offline_final_calls=1,receipts=receipts,all_submap_cells_identical=True,
                recorded_matched_pairs=sum(x['matches'] for x in receipts[:recorded_count]),recorded_reused_pairs=sum(x['pair_hits'] for x in receipts[:recorded_count]),
                matched_pairs=sum(x['matches'] for x in receipts),reused_pairs=sum(x['pair_hits'] for x in receipts),
                field_requests=sum(x['submaps'] for x in receipts),reused_fields=sum(x['field_hits'] for x in receipts),
                limits=dict(pairs=8192,fields=64),gt_input=False,physics=0)
    p.dump(p.RAW/'reuse-audit.json',result);p.dump(p.EXP/'results/reuse-audit.json',result)

if __name__=='__main__':main()
