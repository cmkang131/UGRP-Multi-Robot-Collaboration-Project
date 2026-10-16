"""Raw recount and separate episode/frame/event/candidate funnels, GCP only."""
import argparse,collections,hashlib,json,math,sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    assert sys.platform=='linux';sys.path.insert(0,str(a.source))
    from scripts.audit_beampair1 import read,read_bytes,recount,ordered_funnel,verify_manifest,dump
    from scripts.analyze_beampair1 import rejection_rows,candidate_funnels,montage
    a.out.mkdir(exist_ok=False);(a.out/'montages').mkdir()
    done=read(a.batch/'DONE.json');batch=read(a.batch/'batch-plan.json');cfg=batch['config']
    rows=[];dist=collections.defaultdict(list);frame=collections.Counter();event=collections.Counter()
    for item in done['completed']:
        raw=Path(item['raw']);entry=recount(raw);result=read(raw/'result.json');adapter=read(raw.parent/'adapter/beampair1-result.json')
        assert adapter['source_sha']==cfg['source_sha'] and adapter['dependency_sha']=='26f84d0f0ada1c33473c83cca2d3415ce51bd247'
        assert adapter['box_geometry']=='beampair_box_geometry_v1' and adapter['planning_boundary']==cfg.get('planning_boundary','beampair_checks_only_v1')
        assert not adapter['training_rgb'] and adapter['held_object_hidden_v1']
        supervised=(raw.parent/'SUPERVISOR_STOP.json').is_file()
        assert adapter['held_world_reads']==0
        if 'weld' in result:assert result['weld']=='off'
        else:assert supervised and not result.get('physical_success')
        entry.update(seed=item['seed'],category='supervisor_stop' if supervised else item['category'],
            saved_supervisor_category=item['category'],weld_reported=result.get('weld'),original_category=item['original_category'],
            adapter_sha=adapter['source_sha'],box_geometry=adapter['box_geometry'],planning_boundary=adapter['planning_boundary'],
            peer_yield=adapter['peer_yield'],adapter_manifest_files=verify_manifest(raw.parent/'adapter'))
        states=[{e.get('to') for e in t['events']} for t in result['teachers'].values()]
        entry['stages']={key:len(states)==2 and all(bool(s&set(phases)) for s in states) for key,phases in [
            ('both_align',['align','ready','pick','complete']),('both_ready',['ready','pick','complete']),
            ('both_pick',['pick','complete']),('both_command_complete',['complete'])]}
        for key,phases in [('own_ready',['ready','pick','complete']),('own_pick',['pick','complete']),('own_complete',['complete'])]:
            event[key]+=sum(bool(s&set(phases)) for s in states)
        entry['planning_compute']={r:t.get('search20_compute') for r,t in result['teachers'].items()}
        for v in entry['planning_compute'].values():
            if v:
                assert v['budget_kind']=='checks' and v['max_checks']==98304
                assert v['max_wall_s'] is None and v['max_wall_safety_s'] is None
        for row in [json.loads(x) for x in read_bytes(raw/'eval-only.jsonl')[0].splitlines() if x.strip()]:
            for r in ('r1','r2'):
                frame['N']+=1;frame['any_visible']+=row['visibility'][r]['visible_probes']>0
                frame['meaningful_visible']+=row['visibility'][r]['visible_probes']>=5
                frame['admitted_not_held']+=any(m['id']=='band_'+entry['assigned_ends'][r] for m in row.get('visible_measurements',{}).get(r,[]))
        rs=rejection_rows(result);local=collections.Counter()
        for r in rs:
            if not r.get('reason_category') or r.get('blocked_object')=='not_recorded' or r.get('gap_scope')=='source_missing_clearance_audit':
                raise ValueError('missing named rejection evidence')
            key=(r['reason_category'],r['blocked_object']);local[key]+=1
            dist[key].append(dict(seed=entry['seed'],min_gap_m=r['min_gap_m']))
        entry['top_recorded_blockers']=[dict(reason_category=k[0],blocked_object=k[1],N=n,
            min_gap_m=min((v['min_gap_m'] for v in dist[k] if v['seed']==entry['seed'] and v['min_gap_m'] is not None),default=None)) for k,n in local.most_common(6)]
        entry['candidate_populations']=candidate_funnels(result)
        if not entry['strict_success'] or item['original_category']=='known_success':
            entry['montage']=montage(raw,a.out/'montages'/f"{entry['seed']}.jpg")
        rows.append(entry)
    N=len(cfg['runs']);left={i for i,r in enumerate(rows) if r['status']=='complete' and r['category']!='supervisor_stop'}
    counts=[('started',len(rows)),('finalized_complete',len(left))]
    for key in ('both_align','both_ready','both_pick','both_command_complete'):
        left={i for i in left if rows[i]['stages'][key]};counts.append((key,len(left)))
    left={i for i in left if rows[i]['strict_success'] and rows[i]['legacy_success']};counts.append(('strict_joint_hold_3s',len(left)))
    left={i for i in left if rows[i]['visible_eligible']};counts.append(('visible_input_eligible_success',len(left)))
    distribution=[dict(reason_category=k[0],blocked_object=k[1],N=len(v),affected_seeds=sorted({r['seed'] for r in v}),
        min_gap_m=min((r['min_gap_m'] for r in v if r['min_gap_m'] is not None),default=None)) for k,v in dist.items()]
    distribution.sort(key=lambda x:-x['N'])
    table=dict(source_sha=cfg['source_sha'],candidate=cfg['candidate'],raw_root=str(a.batch),
        episode_funnel=ordered_funnel(N,counts),candidate_populations={str(r['seed']):r['candidate_populations'] for r in rows},
        frame_funnel=ordered_funnel(frame['N'],[(k,frame[k]) for k in ('any_visible','meaningful_visible','admitted_not_held')]),
        event_funnel=ordered_funnel(2*len(rows),[(k,event[k]) for k in ('own_ready','own_pick','own_complete')]),
        reason_object_distribution=distribution,missing_rejection_audit_N=0,
        reproduce=' '.join(sys.argv),analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    summary=dict(source_sha=cfg['source_sha'],candidate=cfg['candidate'],N=len(rows),planned_N=N,n=len(left),
        HOST_ERROR_N=sum(r['category']=='HOST_ERROR' for r in rows),teacher_failure_N=sum(r['category']=='teacher_failure' for r in rows),
        supervisor_stop_N=sum(r['category']=='supervisor_stop' for r in rows),
        cap_end_N=sum(r['cap_end'] for r in rows),unstarted_N=len(done['not_started']),
        invisible_measurements=sum(r['audit']['invisible_measurements'] for r in rows),held_world_reads=sum(r['audit']['held_world_reads'] for r in rows),
        known_success_N=sum(r['strict_success'] and r['legacy_success'] and r['original_category']=='known_success' for r in rows),
        known_failure_recovered_N=sum(r['strict_success'] and r['legacy_success'] and r['original_category']=='known_failure_or_cap' for r in rows),
        run_first_pass=len(left)==N and len(rows)==N,gate40_submitted=False,pooling=False,runs=rows,
        analysis_sha256=table['analysis_sha256'],reproduce=table['reproduce'])
    dump(a.out/'summary.json',summary);dump(a.out/'rejection_table.json',table)
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))

if __name__=='__main__':main()
