"""Recount every recorded run; keep candidate, frame and event populations distinct."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from harness.grasp_act_data import read_json,write_json,read_rows,sha256
from harness.beampair_recording import existing,compress_jsons
from scripts.audit_beampair1 import recount,ordered_funnel,verify_manifest
from scripts.analyze_beampair1 import rejection_rows,candidate_funnels


def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    done=read_json(a.batch/'DONE.json');a.out.mkdir(exist_ok=False)
    rows=[];rejections=[];reasons=Counter();outcomes=Counter();blocks=Counter();frames=Counter();events=Counter()
    for item in done['completed']:
        run=Path(item['path']);raw=run/'raw';result=read_json(existing(raw,'result.json'))
        adapter=read_json(existing(run/'adapter','beampair1-result.json'))
        entry=recount(raw);entry.update(seed=item['seed'],run=str(run),category=item['category'],
            data_admitted=item['admitted'],adapter_manifest_files=verify_manifest(run/'adapter'))
        assert adapter['source_sha']=='72c0e83dab384b4f7d4bb73e37e440e0d1b248f6'
        assert adapter['training_rgb'] and adapter['held_object_hidden_v1'] and adapter['held_world_reads']==0
        assert adapter['hidden_measurement_ticks']>=0
        assert adapter['peer_yield']=='beampair_peer_yield_v1'
        # The pinned runner writes weld only after normal finalization. Its
        # PlanningSafetyCap exception is a failed cap_end, not a data source.
        # Preserve the missing field as unknown; never manufacture OFF.
        if 'weld' in result:assert result['weld']=='off'
        else:assert item['category']=='cap_end' and not result['physical_success']
        entry['weld_reported']=result.get('weld')
        entry['terminal_metadata_missing']=['weld'] if 'weld' not in result else []
        truth=read_rows(existing(raw,'eval-only.jsonl'));fs=Counter()
        for f in truth:
            for rid in ('r1','r2'):
                fs['N']+=1;fs['any_visible']+=f['visibility'][rid]['visible_probes']>0
                fs['meaningful_visible']+=f['visibility'][rid]['visible_probes']>=5
                fs['admitted_not_held']+=any(m['id']=='band_'+entry['assigned_ends'][rid] for m in f.get('visible_measurements',{}).get(rid,[]))
        entry['frame_funnel']=ordered_funnel(fs['N'],[(k,fs[k]) for k in ('any_visible','meaningful_visible','admitted_not_held')]);frames.update(fs)
        teachers=result.get('teachers',{});states=[{e.get('to') for e in t.get('events',[])} for t in teachers.values()]
        entry['stages']={key:len(states)==2 and all(bool(s&set(phases)) for s in states) for key,phases in [
            ('both_align',['align','ready','pick','complete']),('both_ready',['ready','pick','complete']),
            ('both_pick',['pick','complete']),('both_command_complete',['complete'])]}
        for key in ('own_ready','own_pick','own_complete'):events[key]+=sum(bool(s&set({'own_ready':['ready','pick','complete'],'own_pick':['pick','complete'],'own_complete':['complete']}[key])) for s in states)
        rs=rejection_rows(result);entry['candidate_populations']=candidate_funnels(result)
        if not item['admitted']:
            for value in entry['outcomes'].values():
                if value and value!='success':outcomes[value]+=1
            # A recorded geometric rejection is evidence, not a causal claim.
            last=next((r for r in reversed(rs) if r.get('blocked_object') not in ('not_recorded','not_applicable') and r.get('min_gap_m') is not None),None)
            entry.update(blocked_object=last['blocked_object'] if last else 'none:'+entry['reason_category'],
                min_gap_m=last['min_gap_m'] if last else None,
                gap_scope='last recorded rejection, not terminal cause' if last else 'non_geometric_terminal_outcome')
        for r in rs:
            compact={k:v for k,v in r.items() if k not in ('candidate','blocker')}
            compact.update(seed=item['seed'],raw=str(raw));rejections.append(compact)
            reasons[r['reason_category']]+=1;blocks[r['blocked_object']]+=1
        rows.append(entry)
    counts=[('started',len(rows)),('finalized_complete',sum(r['status']=='complete' for r in rows))]
    remaining=set(range(len(rows)))
    for key in ('both_align','both_ready','both_pick','both_command_complete'):
        remaining={i for i in remaining if rows[i]['status']=='complete' and rows[i]['stages'][key]};counts.append((key,len(remaining)))
    remaining={i for i in remaining if rows[i]['strict_success']};counts.append(('joint_hold_3s',len(remaining)))
    remaining={i for i in remaining if rows[i]['legacy_success'] and rows[i]['visible_eligible']};counts.append(('input_eligible_success',len(remaining)))
    manifest_files=sum((r.get('manifest_verified_files') or 0)+(r.get('adapter_manifest_files') or 0) for r in rows)
    missing=sum(r.get('blocked_object')=='not_recorded' or r.get('gap_scope')=='source_missing_clearance_audit'
        or not r.get('reason_category') for r in rejections)
    table=dict(episode_funnel=ordered_funnel(200,counts),candidate_populations={str(r['seed']):r['candidate_populations'] for r in rows},
        frame_populations={str(r['seed']):r['frame_funnel'] for r in rows},
        frame_funnel=ordered_funnel(frames['N'],[(k,frames[k]) for k in ('any_visible','meaningful_visible','admitted_not_held')]),
        event_funnel=ordered_funnel(2*len(rows),[(k,events[k]) for k in ('own_ready','own_pick','own_complete')]),
        rejection_reason_distribution=dict(reasons),blocked_object_distribution=dict(blocks),terminal_outcome_distribution=dict(outcomes),
        source_batch=str(a.batch),source_sha='72c0e83dab384b4f7d4bb73e37e440e0d1b248f6',
        reproduce=' '.join(sys.argv),analysis_sha256=sha256(__file__),
        scope='fresh record200 only; original gate40 and two identity cohorts are excluded',missing_rejection_audit_N=missing)
    write_json(a.out/'rejection_table.json',table);write_json(a.out/'candidate-rejections.json',rejections)
    summary=dict(n=len(remaining),N=len(rows),cap_end_N=sum(r.get('cap_end',False) for r in rows),
        terminal_metadata_missing_N=sum(bool(r['terminal_metadata_missing']) for r in rows),
        HOST_ERROR_N=sum(r['category']=='HOST_ERROR' for r in rows),unstarted_N=len(done['not_started']),
        physical_success_N=sum(r['legacy_success'] for r in rows),raw_adapter_verified_files=manifest_files,missing_rejection_audit_N=missing,
        terminal_outcome_distribution=dict(outcomes),invisible_measurements=sum(r['audit']['invisible_measurements'] for r in rows),
        held_world_reads=sum(r['audit']['held_world_reads'] for r in rows),runs=rows,source_batch=str(a.batch))
    write_json(a.out/'summary.json',summary);compress_jsons(a.out)
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))


if __name__=='__main__':main()
