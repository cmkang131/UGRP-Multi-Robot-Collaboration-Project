"""Read-only gcp2 raw audit, before any reloc21 controller changes."""
import collections
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess

R = Path('/home/ugrp/ugrp-sim/runs')


def read(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-dc', str(p)+'.zst'])


def obj(p):
    return json.loads(read(p))


def rows(p):
    return [json.loads(x) for x in read(p).splitlines()]


def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    runs = []
    for n in (1, 2, 3):
        for t in obj(R/f'reloc20-round{n}/queue.json')['runs']:
            raw = Path(t['raw']); d = obj(raw/'result.json')
            r = {k: t[k] for k in ('name','kind','condition','seed','source_sha','raw')}
            r.update(raw_status=d['status'], original_reason=d.get('termination_reason',d.get('stop_reason')),
                     error=d.get('error'), sim_s=d.get('sim_s',d.get('elapsed_sim_s')),
                     result_decoded_sha256=hashlib.sha256(read(raw/'result.json')).hexdigest(),
                     input_audit=d.get('input_audit'), place=d.get('zone_placement_success') is True)
            if t['kind'] == 'carry' and d.get('sim_s') is not None:
                c = rows(raw/'teacher-commands.jsonl'); ev=rows(raw/'eval-only.jsonl')
                carry=d['teacher']['carry']; path=carry.get('path') or []
                last=next(x for x in reversed(c) if x.get('phase_before',x['phase']) not in ('failed','complete'))
                pose=last['map_pose']['pose_estimate']; goal=carry.get('stand_off_xy')
                phase=last.get('phase_before',last['phase'])
                travel=[x for x in c if x.get('phase_before',x['phase'])=='carry_to_zone']
                categories=collections.Counter(); reasons=collections.Counter(); gaps=[]
                for x in travel:
                    delta=x['map_pose'].get('last_nominal_delta')
                    if delta is None:
                        # Historical off runner has no nominal ODE increment;
                        # classify issued pulses, not actual physical motion.
                        from harness.grasp_act_visible_world import command_delta
                        delta=command_delta(x['command'],.1)
                    stall=x.get('reloc20_motion',{}).get('stall') or {}
                    geom=x.get('reloc20_motion',{}).get('footprint') or {}
                    # Preceding issued delta, exclusive bins at the recorded tick.
                    category=('rgb_backup' if stall.get('suppressed') else
                              'geometry_hold' if geom.get('reason')=='issued_motion_enclosure_overlap' else
                              'turn' if abs(delta[2])>1e-10 and math.hypot(*delta[:2])<1e-10 else
                              'translation' if math.hypot(*delta[:2])>1e-10 else 'idle')
                    categories[category]+=.1; reasons[stall.get('reason','off')]+=1
                    if geom.get('minimum_gap_m') is not None:gaps.append(geom['minimum_gap_m'])
                first=travel[0]['map_pose']['pose_estimate'] if travel else None
                r.update(termination='cap_end' if r['original_reason'] in ('sim_cap','phase_timeout') else r['original_reason'],
                    last_phase=phase, phase_entered_t=next((e['t'] for e in reversed(d['teacher']['events']) if e.get('to')==phase),None),
                    control_started=True,lift=d.get('lift_success'),travel_started=bool(travel),
                    destination_visual_enabled=obj(raw/'plan.json').get('destination_visual_acquire_v1'),
                    destination_entered=any(x.get('phase_before',x['phase'])=='destination_acquire' for x in c),
                    remaining_euclidean_estimate_m=math.dist(pose[:2],goal) if goal else None,
                    remaining_path_estimate_m=sum(math.dist(a,b) for a,b in zip(path,path[1:])) if path else None,
                    goal=goal,final_estimate=pose,first_travel_estimate=first,
                    travel_time_bins_sim_s=dict(categories),stall_reasons=dict(reasons),
                    travel_max_displacement_estimate_m=max((math.dist(first[:2],x['map_pose']['pose_estimate'][:2]) for x in travel),default=None),
                    final_plan_funnel=(carry.get('reloc20_motion') or {}).get('footprint',{}),
                    context=dict(category='sim_time_limit',blocked_object='carry_route_or_destination_visual_evidence',
                                 minimum_gap_m=min(gaps) if gaps else None,gap_scope='minimum last planner context across travel; not physical bottleneck'),
                    phases=dict(collections.Counter(x.get('phase_before',x['phase']) for x in c)),
                    final_carry_keys=list(carry), command_sha256=hashlib.sha256(read(raw/'teacher-commands.jsonl')).hexdigest())
            elif t['kind']=='selfmap':
                trace=rows(raw/'trace.jsonl')
                r.update(termination='controller_failure', failure_class='localization_exhausted',
                    original_termination=d['termination_category'],control_started=bool(trace),
                    last_phase=trace[-1].get('stage'),
                    context=dict(category='relocalization_exhausted',blocked_object='own_rgb_static_registration',minimum_gap_m=None,gap_scope='not_applicable_localization'),
                    trace_final={k:v for k,v in trace[-1].items() if k not in ('map','rgb')})
            else:
                r.update(termination='HOST_ERROR',failure_class='precontrol_configuration',control_started=False,
                    last_phase='precontrol',context=dict(category='map_declaration',blocked_object='authored_floor_map_catalogue',minimum_gap_m=None,gap_scope='not_applicable_configuration'),
                    already_resolved_by='reloc20 1b3108601 hash-bound scenario catalogue; preserve historical failure')
            runs.append(r)
    result=dict(schema='ugrp.reloc21.prior.v1',analysis_host=platform.node(),
        reproduce=f'python3 {__file__}',analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        raw_terminations=dict(collections.Counter(r['raw_status'] for r in runs)),
        normalized_terminations=dict(collections.Counter(r['termination'] for r in runs)),
        funnel=dict(attempts=16,controller_started=sum(r['control_started'] for r in runs),carry_attempts=10,
                    carry_control_started=sum(r['control_started'] for r in runs if r['kind']=='carry'),
                    carry_travel_started=sum(r.get('travel_started',False) for r in runs),
                    destination_entered=sum(r.get('destination_entered',False) for r in runs),
                    place=sum(r['place'] for r in runs)),
        zero_of_nine_clarification='0/9 is place success in reloc20 delivery. Carry control actually started 9/10 attempts; full-plan audit was offline geometry, not nine rejected controller launches.',
        runs=runs)
    p=R/'reloc21-prior/rejection-table.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n')
    lines=['# reloc20 16시도 종료 관문표','', '|실행|종료|마지막 단계|잔여 직선/경로 m|', '|---|---|---|---|']
    for r in runs:
        a=r.get('remaining_euclidean_estimate_m');b=r.get('remaining_path_estimate_m')
        remaining=f'{a:.3f}/'+(f'{b:.3f}' if b is not None else '경로 없음') if a is not None else '해당 없음'
        lines.append(f"|{r['name']}|{r['termination']}: {r['original_reason'] or r.get('error')}|{r['last_phase']}|{remaining}|")
    lines += ['',json.dumps(result['funnel'],ensure_ascii=False),'','잔여 거리는 자기 추정 좌표계이며 실제 정답 도착 거리와 다르다. HOST_ERROR 원상태는 보존하고 위치추정 소진을 별도 분류했다.']
    (p.parent/'gate-table.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(funnel=result['funnel'],terminations=result['normalized_terminations'],
        carry=[{k:r[k] for k in ('name','last_phase','remaining_euclidean_estimate_m','remaining_path_estimate_m','travel_time_bins_sim_s')} for r in runs if r.get('travel_started')]),indent=2))


if __name__=='__main__':main()
